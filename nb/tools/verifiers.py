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


def _problems(root, chapters):
    """
    (blocking, warnings) as message strings.

    There is no rule number anywhere in lint's output -- the message string IS
    the unit, and `"(warning)"` is an in-string marker rather than a field, so
    severity is split exactly the way check.py splits it.
    """
    import lint
    blocking, warnings = [], []
    for where, msg in lint.check(root, chapters):
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


def render(notebook, target=""):
    """
    `quarto render`. Target may be a chapter or a single entry path; empty
    renders the whole notebook.

    Quarto's freeze tracks the page, not its includes, so this alone will happily
    serve a cached result for an entry whose `_model.py` changed underneath it.
    That is what `check` is for.
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
        # SIZED INSIDE THE LOCK, immediately before the render it describes,
        # and from `will_execute` -- the SAME call `render_quarto` deadlines on.
        # This line used to count `unfrozen` and say "0 page(s) to execute"
        # against a render that then died naming three. Two faults, both found
        # on 2026-09-18: a targeted render ignores the freeze, so nothing under
        # it is ever spared; and the kill message counted the whole project
        # while this counted only the target. Two questions, one answer
        # printed. Both sides now ask `will_execute`, which is also what
        # `render_quarto` deadlines on.
        deadline = lint.render_deadline(notebook.root, path)
        todo = lint.will_execute(notebook.root, path)
        say(f"  render    deadline {deadline:.0f} s "
            f"({len(todo)} page(s) to execute)")

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
            _announce()
            r = lint.render_quarto(path, notebook.root, cwd=notebook.root)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return tail(f"render ok.\n{out}", 2000)
        if attempt == 1 and "site_libs" in out:
            say("  render    site_libs race — retrying once (the freeze "
                "survives, so this is a cache hit)")
            continue
        return tail(f"render FAILED (exit {r.returncode}):\n{out}")


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
