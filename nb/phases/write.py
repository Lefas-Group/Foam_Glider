"""
`nb write` -- turn an approved proposal into a committed entry.

Lint is both a tool and a mandatory step. The tool lets the loop fix violations
in place; the step after the loop is the guarantee, because without it the model
can simply decline to call the tool and declare itself done.
"""

import datetime
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time

from ..config import (MAX_LINT_ATTEMPTS, MAX_TURNS, MAX_VERIFY_ATTEMPTS,
                      PROBE_POOL, Notebook)
from ..loop import Refactor, run
from ..schema import Proposal
from ..session import Session
from ..preflight import check as preflight
from ..tools import guards, verifiers
from ..tools.scaffold import create_chapter
from .. import metrics
from . import verify as verify_phase
from .view import site
from .common import setup, report
from ..log import open_log, say, tell

BRIEF = """\
You are in the WRITE phase. The proposal below was approved. Write the entry.

{proposal}

The probe that produced this is gone -- everything you need is above.

`handoff` is a note to the human about things nobody asked about. Do NOT put it
in the entry: an entry answers the question asked and stops.

1. Create the entry at `{chapter}/{stem}.qmd`. Use `write_file` for the initial
   version, then `edit_file` for every change after that.
   Its FIRST code cell must open with exactly these two lines (rule 28):

       ENTRY_CEILING = {ceiling}   # s for this render, granted by the user
       SOLVE_BUDGET = {solve}     # s for any one solve

   ENTRY_CEILING is not yours to choose -- it is what the user granted at the
   prompt, the commit is refused if you change it, and a render that overruns
   it is killed. SOLVE_BUDGET is yours: pick what one solve needs, knowing it
   cannot outlive the render that contains it. Record both in the entry's
   `## Specified` callout as inline expressions (rule 18), e.g.
   "Render budget `{{python}} f\"{{ENTRY_CEILING:.0f}}\"` s."
   If the work genuinely cannot fit, ask for more with `ask_specified` rather
   than writing a different number.
2. Its code must recompute the answer, not restate it. Every number in prose is
   an inline `{{python}}` expression, never typed out (rule 1).
3. Call `lint` with chapter `{chapter}` and fix what it reports. Each message
   names its own fix. Lint runs again after you stop regardless, so there is
   nothing to gain by stopping early.
4. If your entry repeats three or more consecutive code lines from a sibling
   (rule 2), promote them to `{chapter}/_analysis.py` and call from there --
   change only YOUR entry, never the earlier one -- then pass the promoted
   function to `footer(...)` (rule 13).
5. The vehicle lives in `{chapter}/_model.py`, never in the entry cell (rule
   19). If that file is still the bare scaffold, fill it: the aircraft, its
   operating conditions, its derived quantities. A parametric vehicle is a
   FUNCTION there taking the design variables and returning the `Airplane`;
   the entry calls it. `_model.qmd` already execs it, so those names are in
   scope in your cell -- do not import or redefine them.

6. A helper that solves takes `verbose=False` and passes it to `opti.solve()`
   (rule 23). IPOPT prints a sixty-line convergence table otherwise, and an
   entry that publishes one has buried its answer under the working. Keep it a
   PARAMETER rather than hard-coding False, so a probe can still turn it on.

7. Anything true of EVERY entry in `{chapter}` belongs in its index.qmd, not in
   your entry -- the section, the objective, the fixed dimensions, what is left
   out. Your entry keeps what THIS question produced. If the index still holds
   template placeholders, fill them (rule 24).

8. The title in the proposal is the entry's title (rule 26): one question, at
   most 18 words, ending in `?`. It is also the filename, so a brief pasted in
   whole gives a 70-character stem nobody can read.

Today is {today}, so the entry stem is already dated for you. Stop when lint is
clean; rendering and committing are handled after you finish.
"""


def _stem(notebook, chapter, title, today):
    """`YYYY-MM-DD-NN-slug`; NN counts within the day so same-day entries sort."""
    slug = "".join(c if c.isalnum() else "-" for c in title.lower())
    slug = "-".join(p for p in slug.split("-") if p)[:70].rstrip("-")
    existing = [p.name for p in notebook.entries(chapter)]
    n = sum(1 for e in existing if e.startswith(today)) + 1
    return f"{today}-{n:02d}-{slug}"


def _touched(notebook, chapter, *names):
    """Which of `names` in this chapter git sees as changed."""
    repo = notebook.root.parent
    out = []
    for name in names:
        f = notebook.chapters_dir / chapter / name
        if not f.exists():
            continue
        rel = str(f.relative_to(repo))
        if subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=repo,
                          capture_output=True, text=True).stdout.strip():
            out.append(rel)
    return out


def _refresh_index_freeze(notebook, chapter):
    """
    Drop the chapter index's freeze when what it renders has moved.

    Quarto's freeze tracks the PAGE, not its includes -- so a chapter index,
    which execs `_model.py` and prints its source, goes on showing the version
    it was frozen against forever. Rule 19 makes that live: `_model.py` now
    changes on every new-chapter run.

    Scoped to the one index, and only when git says an input actually changed.
    `check.py` solves the same problem by deleting a whole chapter's freeze and
    re-solving it, which is right when proving a refactor moved nothing and far
    too expensive here.
    """
    if not _touched(notebook, chapter, "_model.py", "_analysis.py"):
        return
    shutil.rmtree(notebook.freeze / chapter / "index", ignore_errors=True)


# EVERY fenced block, not just the python ones. The rendered markdown carries
# two kinds -- the echoed source, which Quarto tags "``` {.python .cell-code}",
# and captured STDOUT, which is a bare "```" fence. The first version matched on
# "python" and let sixty lines of IPOPT convergence table through ahead of the
# answer. Nothing a reader wants is inside a fence: the hero, the prose, the
# callouts and the tables are all outside them.
CODE_CELL = re.compile(r"^```+[^\n]*\n.*?^```+[ \t]*$", re.S | re.M)


def rendered_prose(notebook, chapter, stem):
    """
    The entry as it actually rendered, with every inline expression resolved.

    Rule 1 forces the numbers in prose to be `{python} …` expressions, so the
    SOURCE contains none of the entry's actual claims -- they exist only in the
    freeze. This is therefore the one place the finished entry can be read, and
    until now nothing ever showed it to a human: verify read it, but verify is a
    model.

    Code cells stripped, which is most of the bytes and none of the argument:
    measured 5,624 tokens full against 851 without.
    """
    f = notebook.freeze / chapter / stem / "execute-results" / "html.json"
    try:
        md = json.loads(f.read_text())["result"]["markdown"]
    except (OSError, ValueError, KeyError):
        return None
    md = CODE_CELL.sub("", md)
    # Quarto writes a figure's path relative to the chapter directory, so it
    # resolves nowhere from a terminal and nowhere at all for a coordinator
    # reading this prose off a pipe. The same PNG sits under the freeze, which
    # exists the moment the entry renders -- before this runs, and whether or
    # not a site was ever built. Rewriting it here keeps the figure inline,
    # where the argument put it, and keeps its caption, which is usually the
    # densest sentence written about it.
    md = md.replace(f"]({stem}_files/", f"]({notebook.freeze / chapter / stem}/")
    # Quarto's cell wrappers and anchors carry nothing a reader wants. The
    # attributes have to go with the anchor: an image carries its measured
    # `{#fig-x width=901 height=458}`, and stripping the id alone left the
    # dimensions sitting in the prose.
    md = re.sub(r"^:::+.*$", "", md, flags=re.M)
    md = re.sub(r"\{#[\w-]+[^}]*\}", "", md)
    return _readable(md) or None


# Quarto markup that means nothing outside a rendered page.
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
SPAN = re.compile(r"\[([^\]]*)\]\{\.[\w-]+\}")     # [12.7°]{.hero-value}
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HERO = re.compile(r"\[([^\]]*)\]\{\.hero-value\}\s*\n\[([^\]]*)\]\{\.hero-label\}")
ESCAPED = re.compile(r"\\([.\-*_#])")                # 0\.10 -> 0.10


def _readable(md, width=76):
    r"""
    The rendered entry as something a person can read in a terminal.

    The freeze holds Quarto markdown, and printing it raw put `---` frontmatter,
    `[12\.7°]{.hero-value}` spans, escaped decimals and `{.runtime}` in front of
    the reader -- the answer was in there, but it had to be dug out.

    A presentation layer rather than a change to what is stored: the freeze is
    untouched, and the same cleanup serves a coordinator reading this off a
    pipe, which is no better served by span syntax than a person is.

    Figures keep their caption and their absolute path, on separate lines --
    the path is long enough that inlining it buried the sentence that explains
    what the figure shows.
    """
    import textwrap
    title = ""
    m = re.search(r'^title:\s*"(.+)"$', md[:400], re.M)
    if m:
        title = m.group(1)
    md = FRONTMATTER.sub("", md)
    # The hero pair is one fact -- a number and what it measures -- written as
    # two spans on two lines so the page can style them. Joined before the
    # spans are stripped, which is the only point where they are still
    # distinguishable from ordinary prose.
    md = HERO.sub(lambda m: f"{m.group(1)}  {m.group(2)}", md)
    md = SPAN.sub(r"\1", md)
    md = ESCAPED.sub(r"\1", md)
    md = md.replace("**", "")

    out = [title, ""] if title else []
    for line in md.splitlines():
        line = line.rstrip()
        if not line:
            continue
        img = IMAGE.match(line.strip())
        if img:
            cap, path = img.group(1), img.group(2)
            out.append("")
            out += textwrap.wrap(f"figure  {cap}", width=width,
                                 subsequent_indent="        ")
            out.append(f"        {path}")
            continue
        if line.startswith("#"):
            out += ["", line.lstrip("# ")]
            continue
        if line.startswith("Answer.") and out and out[-1]:
            out.append("")
        out += textwrap.wrap(line, width=width) or [""]
    return "\n".join(out).strip()


def _commit_with_lock_retry(repo, title, paths, attempts=3):
    """
    `git commit -m <title> -- <paths>`, retried past a held index.lock.

    Git does not queue on `.git/index.lock`; it fails immediately. The window is
    small -- a commit is milliseconds at the end of a run measured in minutes --
    but it is a loud, harmless, retryable failure, which is the easy kind.
    """
    for attempt in range(attempts):
        out = subprocess.run(["git", "commit", "-m", title, "--"] + paths,
                             cwd=repo, capture_output=True, text=True)
        if out.returncode == 0 or "index.lock" not in (out.stdout + out.stderr):
            return out
        time.sleep(0.5 * (attempt + 1))
    return out


def _commit(notebook, chapter, stem, entry_path, title, extra_paths=()):
    """
    Commit exactly what this run produced, by path.

    Never `git add -A`. The working tree carries untracked Quarto output --
    `chapters/**/*.html`, `site_libs/` -- from any `quarto preview` or render
    that happened to be running, and a blanket add sweeps it into history.

    `extra_paths` exists for an accepted refactor. `check` deletes and
    re-renders EVERY page that reaches the changed function, so the siblings'
    frozen output on disk no longer matches what is committed -- and committing
    only this entry's freeze would leave the repository in the exact state the
    freeze exists to prevent, a committed freeze that does not correspond to the
    committed code.
    """
    repo = notebook.root.parent
    rel = lambda p: str(pathlib.Path(p).relative_to(repo))

    paths = [rel(entry_path)]
    paths += [rel(p) for p in extra_paths if pathlib.Path(p).exists()]
    freeze = notebook.freeze / chapter / stem
    if freeze.exists():
        paths.append(rel(freeze))
    # Shared machinery the run may have touched -- rule 2 promotion lands here.
    for name in ("_analysis.py", "_model.py"):
        f = notebook.chapters_dir / chapter / name
        if f.exists():
            changed = subprocess.run(
                ["git", "status", "--porcelain", "--", rel(f)],
                cwd=repo, capture_output=True, text=True).stdout.strip()
            if changed:
                paths.append(rel(f))

    add = subprocess.run(["git", "add", "--"] + paths, cwd=repo,
                         capture_output=True, text=True)
    if add.returncode != 0:
        return None, f"git add failed: {add.stderr.strip()[:200]}"

    # PATHSPEC, not a bare commit. `git commit -m <title>` commits the whole
    # INDEX, so a second run that has staged its own entry in the meantime gets
    # swept into this one -- verified: A's commit contained both A's and B's
    # files, under A's message, and B was then left with nothing to commit. A
    # pathspec-limited commit takes working-tree content for exactly these paths
    # and ignores the rest of the index, so two runs cannot contaminate each
    # other. The `git add` above still matters: it is what makes a NEW file
    # known to git, which `commit -- <path>` alone does not do.
    out = _commit_with_lock_retry(repo, title, paths)
    if out.returncode != 0:
        return None, f"git commit failed: {(out.stdout + out.stderr).strip()[:200]}"
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    return sha, ", ".join(paths)


def main(notebook_path, verbose=True, allow_refactor=False,
         accept_refactor=False, header=True):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            tell(f"  {b}")
        return 1

    notebook = Notebook(notebook_path)
    # Before open_log, deliberately: there is no run to log against, and the
    # log's separator wants a title that only the proposal can supply.
    if not notebook.proposal_path.exists():
        tell(f"  no proposal at {notebook.proposal_path}. Run `nb ask` first.")
        return 1
    raw = json.loads(notebook.proposal_path.read_text())
    # What `ask` had left of the pool when it stopped. Popped BEFORE validation
    # so it never becomes a Proposal field, and so never appears in the
    # `propose` tool schema as something the model is invited to fill in.
    pool = raw.pop("_pool_left", PROBE_POOL)
    ceiling = raw.pop("_render_ceiling", None)
    pool_total = raw.pop("_pool_total", None)
    proposal = Proposal.model_validate(raw)
    open_log(notebook, "write", proposal.title)

    if header:
        tell(f"  notebook  {notebook.root.name}")
        # With `say()` off the terminal, nothing else says the detail exists.
        tell(f"  telemetry  python -m nb watch {notebook.root.name}")
    tell(f"  entry     {proposal.title}")

    chapter_msg = None
    # Either route can be the first entry in a scaffold chapter: `propose`
    # refuses to hand one over without a chapter_title, so by here we have a
    # name for it and the claim is the same operation as creating one.
    if proposal.route == "new_chapter" or (
            proposal.chapter == notebook.claimable_stub()):
        # chapter_title, not proposal.title: the chapter is named for what it
        # holds ("Flight path"), not for whichever question happened to create it.
        # The returned name is authoritative: create_chapter owns the number, and
        # may have claimed an empty scaffold chapter instead of adding a sibling.
        proposal.chapter, chapter_msg = create_chapter(
            notebook, proposal.chapter,
            proposal.chapter_title or proposal.title, proposal.chapter_defines)
        tell(f"  chapter   {chapter_msg.splitlines()[0]}")
        if chapter_msg.startswith("rejected"):
            return 1

    today = datetime.date.today().isoformat()
    stem = _stem(notebook, proposal.chapter, proposal.title, today)
    # title, not question: on a split ask the model keeps the whole original
    # in `question` and puts this entry's own question in `title`, so a row
    # keyed on `question` would label every entry of a multi-part ask the same.
    run_metrics = metrics.Run(notebook, "write", proposal.title)
    run_metrics.set(chapter=proposal.chapter, entry_stem=stem)
    session = Session(notebook, proposal.question, proposal.chapter,
                      metrics=run_metrics, probe_pool=pool)
    session.render_ceiling = ceiling
    # Accepting implies allowing: you cannot accept a diff you were never
    # permitted to produce.
    allow_refactor = allow_refactor or accept_refactor
    session.allow_refactor = allow_refactor
    accepted = []
    # Snapshot the shared modules BEFORE the loop. Adding an `_analysis.py`
    # helper is safe -- rule 2 promotion leaves siblings untouched -- but
    # changing the body of one a sibling already calls is a refactor, and the
    # difference is only visible by comparing.
    _chapter_dir = notebook.chapters_dir / proposal.chapter
    _before = {n: guards.bodies(_chapter_dir / n)
               for n in ("_model.py", "_analysis.py")}
    _siblings = len(notebook.entries(proposal.chapter))

    fs, handlers, make_config = setup(session, phase="write")
    try:
        if allow_refactor:
            tell("  refactor  allowed — _model.py is writable, and the chapter "
                  "will be re-proved before commit")
        import lint as _lint
        _default_solve, _default_ceiling = _lint._defaults(notebook.root)
        brief = BRIEF.format(
            proposal=json.dumps(proposal.model_dump(), indent=2),
            chapter=proposal.chapter, stem=stem, today=today,
            ceiling=f"{(ceiling if ceiling is not None else _default_ceiling or 200.0):.1f}",
            solve=f"{(_default_solve or 60.0):.1f}")
        contents = [{"role": "user", "parts": [{"text": brief}]}]
        # The scaffolder's own message -- which is the only place that says where
        # the vehicle goes. It used to be printed to the terminal and nowhere
        # else, so the model never saw it and wrote the vehicle into the entry.
        if chapter_msg:
            contents.append({"role": "user", "parts": [{"text": chapter_msg}]})

        def on_turn(n, resp, turn):
            run_metrics.turn(resp)
            if verbose:
                calls = [p.function_call.name for p in (turn.parts or [])
                         if p.function_call]
                say(report(resp, f"turn {n + 1}") +
                      (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))

        first_pass = None

        def loop_once():
            run(contents, make_config(), handlers,
                transcript=notebook.transcript_path, max_turns=MAX_TURNS,
                on_turn=on_turn)

        # --- lint, which is mandatory whatever the loop believes ------------
        for attempt in range(MAX_LINT_ATTEMPTS):
            loop_once()
            clean, problems = verifiers.is_clean(notebook, proposal.chapter)
            if first_pass is None:
                # The eval metric: violations before any correction round.
                first_pass = len(problems)
                run_metrics.set(first_pass_violations=first_pass)
            tell(f"  lint      {'clean' if clean else f'{len(problems)} blocking'}"
                  f" (attempt {attempt + 1})")
            if clean:
                break
            contents.append({"role": "user", "parts": [{"text":
                "Lint is not clean. Fix every one of these, then stop:\n\n"
                + "\n".join(f"  {p}" for p in problems)}]})
        else:
            tell(f"  lint      still failing after {MAX_LINT_ATTEMPTS} attempts. "
                  f"Nothing committed; the entry is on disk to fix by hand.")
            run_metrics.close("lint_failed")
            return 1

        # --- verify: does the prose match what actually rendered? -----------
        entry_path = notebook.chapters_dir / proposal.chapter / f"{stem}.qmd"
        _refresh_index_freeze(notebook, proposal.chapter)
        findings = []
        for attempt in range(MAX_VERIFY_ATTEMPTS):
            result, note = verify_phase.check(
                notebook, proposal.chapter, stem, entry_path=entry_path)
            if note:
                # NOT a skip-and-commit. Both cases this covers -- the render
                # failed, or there is no freeze to read -- mean the entry could
                # not be checked against its own output, and one of them means
                # the page does not build at all. Committing either would put
                # exactly the thing verify exists to catch into history.
                tell(f"  verify    could not run — {note}")
                run_metrics.close("verify_failed")
                return 1
            findings = result.findings
            tell(f"  verify    {'ok' if result.ok else f'{len(findings)} finding(s)'}"
                  f" (attempt {attempt + 1})")
            for f in findings:
                tell(f"              {f}")
            if result.ok:
                break
            if attempt == MAX_VERIFY_ATTEMPTS - 1:
                break
            contents.append({"role": "user", "parts": [{"text":
                "The rendered page contradicts its own prose. A fresh reader "
                "compared the two and found:\n\n"
                + "\n".join(f"  {f}" for f in findings)
                + "\n\nFix the prose to match what the output actually shows — "
                  "not the other way round — then stop."}]})
            loop_once()
            clean, problems = verifiers.is_clean(notebook, proposal.chapter)
            if not clean:
                tell(f"  lint      {len(problems)} blocking after the verify fix; "
                      f"stopping. The entry is on disk.")
                run_metrics.close("lint_failed")
                return 1

        run_metrics.set(verify_findings=len(findings))
        if findings:
            tell(f"\n  Not committed: {len(findings)} verify finding(s) unresolved "
                  f"after {MAX_VERIFY_ATTEMPTS} attempts. The entry is on disk.")
            run_metrics.close("verify_failed")
            return 1

        # --- the chapter's shared machinery moved: prove it moved nothing ---
        # Adding an `_analysis.py` helper is additive and safe; changing the
        # body of one a sibling already calls is a refactor, and Quarto's freeze
        # tracks the page rather than its includes, so nothing else would ever
        # notice. `check` deletes the freeze, re-renders and diffs -- expensive,
        # which is why it runs only when a body actually moved and the chapter
        # actually has siblings to break.
        moved = []
        if _siblings:
            for name in ("_model.py", "_analysis.py"):
                moved += [f"{name}:{fn}" for fn in guards.changed_bodies(
                    _before[name], guards.bodies(_chapter_dir / name))]
        if moved:
            tell(f"  check     {', '.join(moved)} changed — re-proving "
                  f"{_siblings} sibling entr"
                  f"{'y' if _siblings == 1 else 'ies'}")
            out = verifiers.check(notebook, proposal.chapter)
            # `check` reports its own exit code in the first line; non-zero
            # means the diff was not empty, which IS the finding.
            if not str(out).startswith("check exit=0"):
                # The diff prints EITHER WAY. Accepting is meant to be loud:
                # `refactoring.md` holds that a refactor which moves anything
                # wants superseding rather than silent updating, and accepting
                # overrides that judgement, so the evidence goes on the record
                # rather than being swallowed by a flag.
                tell(f"\n  {'─' * 70}\n  REFACTOR CHANGED THE ANSWERS"
                     f"{' — ACCEPTED' if accept_refactor else ' — not committed'}"
                     f"\n  {'─' * 70}\n{out}\n")
                if not accept_refactor:
                    tell(f"  The entry and the changed machinery are on disk. "
                         f"Either the change is wrong, or the entries it moved\n"
                         f"  need superseding rather than silently updating. If "
                         f"the diff is presentation only and you have read it:\n"
                         f"    python -m nb write {notebook.root.name} "
                         f"--accept-refactor\n")
                    run_metrics.close("refactor_moved_answers")
                    return 1
                accepted = moved
            else:
                tell("  check     clean — the refactor moved nothing")
    except Refactor as r:
        # The agent tried to change the vehicle, was refused, and said why.
        # Ending here is the point: re-proving a chapter is minutes of solves,
        # and whether to spend them is not the agent's call.
        run_metrics.close("needs_refactor")
        tell(f"\n  {'─' * 70}\n  REFACTOR NEEDED — nothing committed\n"
             f"  {'─' * 70}\n"
             f"  chapter   {r.chapter}  ({r.entries} entr"
             f"{'y' if r.entries == 1 else 'ies'} would be re-proved)\n"
             f"  why       {r.why}\n\n  If that is right:\n"
             f"    python -m nb write {notebook.root.name} --allow-refactor\n")
        return 2
    finally:
        fs.stop()

    # --- commit ------------------------------------------------------------
    # An accepted refactor re-rendered every page reaching the changed function,
    # so the whole chapter's freeze goes in -- siblings and the chapter index --
    # or the committed freeze stops matching the committed code.
    title = proposal.title
    # Rule 26 lets the title be a rephrasing, so the words actually used to ask
    # have to survive somewhere that cannot be edited later. `proposal.json` is
    # overwritten by the next run; the commit is not.
    if proposal.question and proposal.question.strip() != title.strip():
        title += f"\n\nAsked: {proposal.question.strip()}"
    # The render ceiling was GRANTED, not negotiated. Refuse to commit an entry
    # that awarded itself a different one -- otherwise the number typed at the
    # prompt is decoration, and the run's real spend is whatever the agent felt
    # like. More is available, but only through `ask_specified`, which stops and
    # asks a person.
    if ceiling is not None:
        import lint
        _, declared = lint.limits_of(notebook.root, entry_path)
        if declared != ceiling:
            tell(f"  Not committed: the entry declares ENTRY_CEILING = "
                 f"{declared}, but {ceiling:.0f} s was granted at the prompt.\n"
                 f"  The budget is the user's to set. Ask for more with a "
                 f"Specified input rather than\n  writing a different number.")
            run_metrics.close("ceiling_changed")
            return 1

    extra = ()
    if accepted:
        extra = (notebook.freeze / proposal.chapter,)
        title += ("\n\nAccepted refactor: " + ", ".join(accepted) +
                  f". {_siblings} sibling entr"
                  f"{'y' if _siblings == 1 else 'ies'} re-proved and re-frozen.")
    sha, detail = _commit(notebook, proposal.chapter, stem, entry_path,
                          title, extra_paths=extra)
    if sha is None:
        tell(f"  commit    FAILED — {detail}")
        run_metrics.close("commit_failed")
        return 1
    tell(f"  commit    {sha}  ({detail})")
    tell(f"  first-pass violations: {first_pass}")
    if session.probe_pool:
        # The QUESTION's total against the grant, not this phase's slice against
        # what was left of it: "4 s of 272 s" made the run look like it had been
        # given a budget nobody chose.
        total = pool_total or session.probe_pool
        spent = total - (session.probe_left or 0.0)
        tell(f"  budget    {spent:.0f} s of {total:.0f} s probe pool used")
    run_metrics.close("committed_refactor" if accepted else "committed")

    # The entry itself, with real numbers. Conversation, not telemetry: it is
    # the thing to read, and with no gate before it this is where a reader --
    # human or coordinating agent -- first sees what was actually claimed.
    prose = rendered_prose(notebook, proposal.chapter, stem)
    if prose:
        tell(f"\n{'─' * 72}\n{prose}\n{'─' * 72}")

    # After the commit, never before: a project render touches every page in the
    # notebook, and an unrelated broken one must not be able to block an entry
    # that has already passed lint, render and verify on its own terms.
    site(notebook, page=notebook.root / "_site" / "chapters"
                        / proposal.chapter / f"{stem}.html")

    # --- advance the queue -------------------------------------------------
    if proposal.queue:
        nxt, rest = proposal.queue[0], proposal.queue[1:]
        tell(f"\n  {len(proposal.queue)} question(s) queued. Next:\n    {nxt}\n")
        from .ask import main as ask
        # The pool is per QUESTION CHAIN, not per phase: a queue that claimed a
        # fresh pool per question would make the number agreed at the prompt
        # mean nothing.
        return ask(notebook_path, nxt, carry_queue=rest, verbose=verbose,
                   pool=session.probe_left, ceiling=ceiling)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
