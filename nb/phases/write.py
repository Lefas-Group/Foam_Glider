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
                      Notebook)
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
    # Quarto's cell wrappers and anchors carry nothing a reader wants.
    md = re.sub(r"^:::+.*$", "", md, flags=re.M)
    md = re.sub(r"\{#[\w-]+\}", "", md)
    return "\n".join(line.rstrip() for line in md.splitlines()
                      if line.strip()) or None


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


def _commit(notebook, chapter, stem, entry_path, title):
    """
    Commit exactly what this run produced, by path.

    Never `git add -A`. The working tree carries untracked Quarto output --
    `chapters/**/*.html`, `site_libs/` -- from any `quarto preview` or render
    that happened to be running, and a blanket add sweeps it into history.
    """
    repo = notebook.root.parent
    rel = lambda p: str(pathlib.Path(p).relative_to(repo))

    paths = [rel(entry_path)]
    freeze = notebook.freeze / chapter / stem
    if freeze.exists():
        paths.append(rel(freeze))
    # Shared machinery the run may have touched -- rule 2 promotion lands here.
    for name in ("_analysis.py", "_model.py", "_budget.py"):
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


def main(notebook_path, verbose=True, allow_refactor=False):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            say(f"  {b}")
        return 1

    notebook = Notebook(notebook_path)
    open_log(notebook)
    if not notebook.proposal_path.exists():
        say(f"  no proposal at {notebook.proposal_path}. Run `nb ask` first.")
        return 1
    proposal = Proposal.model_validate(json.loads(notebook.proposal_path.read_text()))

    say(f"  notebook  {notebook.root.name}")
    say(f"  entry     {proposal.title}")

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
        say(f"  chapter   {chapter_msg.splitlines()[0]}")
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
                      metrics=run_metrics)
    session.allow_refactor = allow_refactor
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
            say("  refactor  allowed — _model.py is writable, and the chapter "
                  "will be re-proved before commit")
        brief = BRIEF.format(
            proposal=json.dumps(proposal.model_dump(), indent=2),
            chapter=proposal.chapter, stem=stem, today=today)
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
            say(f"  lint      {'clean' if clean else f'{len(problems)} blocking'}"
                  f" (attempt {attempt + 1})")
            if clean:
                break
            contents.append({"role": "user", "parts": [{"text":
                "Lint is not clean. Fix every one of these, then stop:\n\n"
                + "\n".join(f"  {p}" for p in problems)}]})
        else:
            say(f"  lint      still failing after {MAX_LINT_ATTEMPTS} attempts. "
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
                say(f"  verify    could not run — {note}")
                run_metrics.close("verify_failed")
                return 1
            findings = result.findings
            say(f"  verify    {'ok' if result.ok else f'{len(findings)} finding(s)'}"
                  f" (attempt {attempt + 1})")
            for f in findings:
                say(f"              {f}")
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
                say(f"  lint      {len(problems)} blocking after the verify fix; "
                      f"stopping. The entry is on disk.")
                run_metrics.close("lint_failed")
                return 1

        run_metrics.set(verify_findings=len(findings))
        if findings:
            say(f"\n  Not committed: {len(findings)} verify finding(s) unresolved "
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
            say(f"  check     {', '.join(moved)} changed — re-proving "
                  f"{_siblings} sibling entr"
                  f"{'y' if _siblings == 1 else 'ies'}")
            out = verifiers.check(notebook, proposal.chapter)
            # `check` reports its own exit code in the first line; non-zero
            # means the diff was not empty, which IS the finding.
            if not str(out).startswith("check exit=0"):
                tell(f"\n  {'─' * 70}\n  REFACTOR CHANGED THE ANSWERS — not "
                     f"committed\n  {'─' * 70}\n{out}\n"
                     f"  The entry and the changed machinery are on disk. Either "
                     f"the change is wrong, or the entries it moved need\n"
                     f"  superseding rather than silently updating.\n")
                run_metrics.close("refactor_moved_answers")
                return 1
            say("  check     clean — the refactor moved nothing")
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
    sha, detail = _commit(notebook, proposal.chapter, stem, entry_path,
                          proposal.title)
    if sha is None:
        say(f"  commit    FAILED — {detail}")
        run_metrics.close("commit_failed")
        return 1
    tell(f"  commit    {sha}  ({detail})")
    say(f"  first-pass violations: {first_pass}")
    run_metrics.close("committed")

    # The entry itself, with real numbers. Conversation, not telemetry: it is
    # the thing to read, and with no gate before it this is where a reader --
    # human or coordinating agent -- first sees what was actually claimed.
    prose = rendered_prose(notebook, proposal.chapter, stem)
    if prose:
        tell(f"\n{'─' * 72}\n{prose}\n{'─' * 72}")

    # After the commit, never before: a project render touches every page in the
    # notebook, and an unrelated broken one must not be able to block an entry
    # that has already passed lint, render and verify on its own terms.
    site(notebook)

    # --- advance the queue -------------------------------------------------
    if proposal.queue:
        nxt, rest = proposal.queue[0], proposal.queue[1:]
        say(f"\n  {len(proposal.queue)} question(s) queued. Next:\n    {nxt}\n")
        from .ask import main as ask
        return ask(notebook_path, nxt, carry_queue=rest, verbose=verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
