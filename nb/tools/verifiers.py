"""
lint / render / check -- the deterministic half, wrapped as tools.

These are the vendored scripts, called rather than reimplemented. `lint.check()`
returns structured tuples so it is called directly; `check.main()` only prints,
so its stdout is captured the same way check.py captures lint's.
"""

import contextlib
import io
import subprocess

from ..config import Notebook
from ..text import tail
from ..log import say


# Rule 12's message, identified the only way lint's output allows. check.py
# matches the same substring for the same reason, and says it plainly:
#
#   "it is a complaint that the render about to happen is exactly the fix, so
#    gating the render on it deadlocks."
#
# That is precisely what happened here. Rule 12 is blocking, the write phase's
# lint gate demands zero blocking problems, and the render that would clear it
# does not run until lint passes. For a while the deadlock was hidden: the
# message used to name `check.py`, and running it re-rendered and rewrote the
# freeze -- so the model was not wasting thirteen minutes on a checker out of
# confusion, it was using the only lever that cleared a blocking gate. Take the
# command away without taking the gate away and the model reasons, correctly,
# "the prompt demands that I fix something that I can't", stops, and the run
# dies on `lint_failed`. Observed, three attempts in a row.
#
# So it is filtered out BEFORE the render rather than rewritten. It is still
# enforced afterwards, by check.py's own post-render pass and by `nb lint`; and
# the phase's render refreshes the chapter's freeze, which is what actually
# resolves it.
FREEZE_STALE = "but the freeze is not"


def _problems(root, chapters, pre_render=True):
    """
    (blocking, warnings) as message strings.

    There is no rule number anywhere in lint's output -- the message string IS
    the unit, and `"(warning)"` is an in-string marker rather than a field, so
    severity is split exactly the way check.py splits it.

    `pre_render` drops rule 12, which no edit can satisfy. See `FREEZE_STALE`.
    """
    import lint
    blocking, warnings = [], []
    for where, msg in lint.check(root, chapters):
        if pre_render and FREEZE_STALE in msg:
            continue
        label = "" if where is None else f"{where.name}: "
        (warnings if "(warning)" in msg else blocking).append(f"{label}{msg}")
    return blocking, warnings


def _word_budgets(notebook, chapter):
    """Prose words against rule 6's budget, per entry, so nobody counts by hand."""
    import lint
    lines = []
    for e in sorted((notebook.chapters_dir / chapter).glob("*.qmd")):
        if not lint.ENTRY_FILE.match(e.name):
            continue
        try:
            n = lint.words(lint.body_prose(e.read_text()))
        except OSError:
            continue
        lines.append(f"  {e.stem[:44]}: {n}/{lint.MAX_PROSE} words of prose")
    return ("\n\nprose budgets (rule 6):\n" + "\n".join(lines)) if lines else ""


def lint_chapter(notebook, chapter, session=None):
    """
    Lint one chapter. Scoped to the chapter, not the entry, because rule 2
    (repeated code) and rule 10 (sibling links) are cross-entry by nature.

    Answers "nothing has changed" when no file has been written since the last
    call. Re-running a pure function over unchanged inputs cannot produce a
    different answer, and a model that asks anyway is spending a turn to be told
    what it already knows -- which the transcripts show happening two or three
    times a run.

    The word counts are here for the same reason: rule 6 is a budget, and the
    model twice shelled out to `bash` to count against it by hand. A budget you
    have to measure yourself is a budget you measure wrong.
    """
    if session is not None:
        writes = getattr(session, "writes", 0)
        if getattr(session, "_lint_at", None) == writes:
            return ("lint: nothing has been written since your last call, so "
                    "the answer is unchanged. Edit something, or move on.")
        session._lint_at = writes

    blocking, warnings = _problems(notebook.root, [chapter])
    budgets = _word_budgets(notebook, chapter)
    if not blocking and not warnings:
        return "lint clean." + budgets
    out = []
    if blocking:
        out.append(f"{len(blocking)} blocking problem(s) -- fix all of these:")
        out += [f"  {p}" for p in blocking]
    if warnings:
        out.append(f"{len(warnings)} warning(s), not blocking:")
        out += [f"  {w}" for w in warnings]
    return tail("\n".join(out)) + budgets


def is_clean(notebook, chapter):
    """True when nothing blocking remains. The mandatory step after the loop."""
    blocking, _ = _problems(notebook.root, [chapter])
    return not blocking, blocking


def pages(n):
    """`1 page` / `5 pages`. A count the reader trips over is a count reread."""
    return f"{n} page" if n == 1 else f"{n} pages"


def pages_of(root):
    """
    Every page a render can execute: `chapters/*/*.qmd` minus the
    leading-underscore includes, plus the notebook's front page.

    Here rather than in `lint` so the vendored checker keeps its own copy of
    this rule and nothing has to stay in step with an import.

    The front page is in the list because it is a page a render executes, and
    leaving it out understated "N served from cache" by one on every project
    render -- the one page that is now rebuilt on every commit.
    """
    chapters = sorted(d for d in (root / "chapters").iterdir() if d.is_dir())
    out = [q for c in chapters for q in sorted(c.glob("*.qmd"))
           if not q.name.startswith("_")]
    index = root / "index.qmd"
    return (out + [index]) if index.exists() else out


def render_plan(root, path):
    """
    (scope, pages, deadline, why) -- what this render will do, and why.

    Everything about the TARGET comes from `will_execute(root, path)` and
    `render_deadline(root, path)`, both pure functions of the same two
    arguments, and `render_quarto` calls the second again with those same
    arguments under the same lock -- so the deadline announced is the deadline
    enforced, by construction rather than by agreement. This line has been wrong
    twice, both times by answering one question with another question's number,
    and that is the failure the constraint exists to prevent.

    The project comparison IS a second call, deliberately. It answers a
    different question -- "what would a project render have executed?" -- and is
    reported as its own clause rather than folded into the target's count.
    """
    import lint
    todo = lint.will_execute(root, path)
    deadline = lint.render_deadline(root, path)
    if path == root:
        # The one case where the freeze counts, which is why the reason here is
        # about what was SPARED rather than about what is being re-run.
        cached = len(pages_of(root)) - len(todo)
        why = f"{cached} served from cache" if cached else "nothing frozen yet"
        return "project", todo, deadline, why

    # Quarto honours `freeze` on a PROJECT render only. Name a target and every
    # page under it executes, whatever `_freeze/` holds -- so a chapter target
    # is routinely more expensive than rendering the whole notebook, which is
    # the opposite of the intuition and invisible from the count alone.
    scope = ("front page" if path == root / "index.qmd"
             else "entry" if path.is_file() else "chapter")
    why = "targeted, so the freeze is ignored"
    project = len(lint.will_execute(root, root))
    if len(todo) > project:
        why += (" — a whole-notebook render would execute "
                + (f"{project}" if project else "nothing"))
    return scope, todo, deadline, why


def render(notebook, target="", why="", session=None):
    """
    `quarto render`. Target may be a chapter or a single entry path; empty
    renders the whole notebook.

    Quarto's freeze tracks the page, not its includes, so this alone will happily
    serve a cached result for an entry whose `_model.py` changed underneath it.
    That is what `check` is for.

    `why` is the CALLER's reason, printed beside the scope. `check.py` has
    reported both since it was written ("set aside 2 chapter(s) … —
    _analysis.py changed") and every other render path reported neither, so a
    reader watching a run go quiet for 110 s could not tell an honest page from
    a needless chapter.

    `session` is optional and only counts: renders, and the pages they actually
    executed. The pages are the cost, not the call -- a chapter target and an
    entry target are one render each, and sixteen pages against one.
    """
    path = notebook.root if not target else notebook.root / target
    # Deadlined: a wedged Jupyter kernel used to hang here forever, the same
    # shape as the socket that hung a run for four hours. lint.render_quarto
    # sizes the deadline from what will actually execute and names the page it
    # died on.
    import lint
    # Announced before it starts, so `nb watch` knows how long silence here is
    # allowed to last. Without it the watcher falls back to a flat 120 s and
    # would cry wolf over an honest 200 s render.
    # From the SAME path render_quarto will deadline on. Computed from the root
    # here once, it announced a project-sized number for a one-page render --
    # 90 s against the 60 s actually enforced, which is worse than saying
    # nothing, since `nb watch` sizes its staleness warning on this line.
    def _announce():
        # SIZED INSIDE THE LOCK, immediately before the render it describes.
        # This line used to count `unfrozen` and say "0 page(s) to execute"
        # against a render that then died naming three. Two faults, both found
        # on 2026-09-18: a targeted render ignores the freeze, so nothing under
        # it is ever spared; and the kill message counted the whole project
        # while this counted only the target. Two questions, one answer
        # printed. See `render_plan` for what keeps them one question now.
        scope, todo, deadline, plan_why = render_plan(notebook.root, path)
        reason = f"{plan_why} · {why}" if why else plan_why
        say(f"  render    {scope} · {pages(len(todo))} · "
            f"deadline {deadline:.0f} s · {reason}")
        return len(todo)

    # UNDER A LOCK, and retried once. Two renders on one project fail four
    # trials out of four, on `_freeze/site_libs/`, which the Quarto project
    # shares. The lock covers other agents; the retry covers what no lock
    # inside `nb` can see -- a person running `quarto preview` in another
    # terminal, which holds nothing and re-renders on every file change.
    #
    # Retrying is nearly free: the failure happens AFTER the page executes, so
    # the freeze is already written and the second attempt is a cache hit,
    # measured at 14 s. And it matters more than it looks, because a failed
    # render is handed to the model as something to FIX -- so a race would
    # otherwise present as a bug in an entry that is correct.
    from ..locks import render_lock
    for attempt in (1, 2):
        with render_lock(notebook) as got:
            if not got:
                say("  render    proceeding without the lock — timed out "
                    "waiting for another render")
            executed = _announce()
            r = lint.render_quarto(path, notebook.root, cwd=notebook.root)
        if session is not None:
            session.record_render(executed)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return tail(f"render ok.\n{out}", 2000)
        if attempt == 1 and "site_libs" in out:
            say("  render    site_libs race — retrying once (the freeze "
                "survives, so this is a cache hit)")
            continue
        return tail(f"render FAILED (exit {r.returncode}):\n{out}")


# Prefix on the note `build_entry` returns when the page did not BUILD, so the
# caller can tell it apart from "there is no freeze to read" without parsing a
# traceback. The two are different failures: a build error names a line and the
# model fixes it in a turn, a missing freeze is nothing it can act on.
BUILD_FAILED = "render failed,"


def build_entry(notebook, chapter, stem, entry_path, session=None):
    """
    Render one entry and confirm it left a freeze. Returns a note, or None.

    Extracted from `verify.check`, which rendered before it read because
    "verifying against a stale freeze is worse than not verifying at all" --
    so the render and the repair loop around it were entangled with a model
    call that has now been deleted. They are not the same job: this one is
    deterministic, it is the last thing standing between a page that does not
    build and a commit, and lint has already passed by the time it runs.

    It cost a whole run once, on a `from _analysis import …` that no rule then
    caught.

    `session` so this render is COUNTED. The first live run recorded
    `renders=1` for a write phase that rendered twice -- the agent's own call
    and this one -- because only the tool handler passed a session. A cost
    metric that misses the render the phase always does is the wrong number in
    the direction that flatters.
    """
    if entry_path is not None:
        out = render(notebook, str(entry_path.relative_to(notebook.root)),
                     why="the entry must build before it is committed",
                     session=session)
        if "FAILED" in out:
            return f"{BUILD_FAILED} the page did not build:\n{out}"
    frozen = (notebook.freeze / chapter / stem
              / "execute-results" / "html.json")
    if not frozen.exists():
        return f"no freeze for {chapter}/{stem} after rendering it"
    return None


def check(notebook, chapter="", force_all=False, no_render=False):
    """
    The full gate: lint, discard the invalidated freezes, render, lint again,
    then diff the rendered values and figures against git.

    Deleting the freeze is not optional -- freeze tracks the page and not its
    includes, so without it a fresh render is compared against a cache hit and
    the match is an artefact. There is no flag to skip it.
    """
    import check as check_mod
    argv = [str(notebook.root)]
    if chapter:
        argv.append(chapter)
    if no_render:
        argv.append("--no-render")
    if force_all:
        argv.append("--all")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = check_mod.main(argv)
    return tail(f"check exit={code}\n{buf.getvalue()}")
