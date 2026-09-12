"""
`nb write` -- turn an approved proposal into a committed entry.

Lint is both a tool and a mandatory step. The tool lets the loop fix violations
in place; the step after the loop is the guarantee, because without it the model
can simply decline to call the tool and declare itself done.
"""

import datetime
import json
import pathlib
import shutil
import subprocess
import sys

from ..config import (MAX_LINT_ATTEMPTS, MAX_TURNS, MAX_VERIFY_ATTEMPTS,
                      Notebook)
from ..loop import run
from ..schema import Proposal
from ..session import Session
from ..preflight import check as preflight
from ..tools import verifiers
from ..tools.scaffold import create_chapter
from .. import cache, metrics
from . import verify as verify_phase
from .view import site
from .common import setup, report

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
    out = subprocess.run(["git", "commit", "-m", title], cwd=repo,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None, f"git commit failed: {(out.stdout + out.stderr).strip()[:200]}"
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                         capture_output=True, text=True).stdout.strip()
    return sha, ", ".join(paths)


def main(notebook_path, verbose=True):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            print(f"  {b}")
        return 1

    notebook = Notebook(notebook_path)
    if not notebook.proposal_path.exists():
        print(f"  no proposal at {notebook.proposal_path}. Run `nb ask` first.")
        return 1
    proposal = Proposal.model_validate(json.loads(notebook.proposal_path.read_text()))

    print(f"  notebook  {notebook.root.name}")
    print(f"  entry     {proposal.title}")

    chapter_msg = None
    if proposal.route == "new_chapter":
        # chapter_title, not proposal.title: the chapter is named for what it
        # holds ("Flight path"), not for whichever question happened to create it.
        # The returned name is authoritative: create_chapter owns the number, and
        # may have claimed an empty scaffold chapter instead of adding a sibling.
        proposal.chapter, chapter_msg = create_chapter(
            notebook, proposal.chapter,
            proposal.chapter_title or proposal.title, proposal.chapter_defines)
        print(f"  chapter   {chapter_msg.splitlines()[0]}")
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

    fs, handlers, make_config = setup(session)
    try:
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
                print(report(resp, f"turn {n + 1}") +
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
            print(f"  lint      {'clean' if clean else f'{len(problems)} blocking'}"
                  f" (attempt {attempt + 1})")
            if clean:
                break
            contents.append({"role": "user", "parts": [{"text":
                "Lint is not clean. Fix every one of these, then stop:\n\n"
                + "\n".join(f"  {p}" for p in problems)}]})
        else:
            print(f"  lint      still failing after {MAX_LINT_ATTEMPTS} attempts. "
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
                print(f"  verify    could not run — {note}")
                run_metrics.close("verify_failed")
                return 1
            findings = result.findings
            print(f"  verify    {'ok' if result.ok else f'{len(findings)} finding(s)'}"
                  f" (attempt {attempt + 1})")
            for f in findings:
                print(f"              {f}")
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
                print(f"  lint      {len(problems)} blocking after the verify fix; "
                      f"stopping. The entry is on disk.")
                run_metrics.close("lint_failed")
                return 1

        run_metrics.set(verify_findings=len(findings))
        if findings:
            print(f"\n  Not committed: {len(findings)} verify finding(s) unresolved "
                  f"after {MAX_VERIFY_ATTEMPTS} attempts. The entry is on disk.")
            run_metrics.close("verify_failed")
            return 1
    finally:
        fs.stop()

    # --- commit ------------------------------------------------------------
    sha, detail = _commit(notebook, proposal.chapter, stem, entry_path,
                          proposal.title)
    if sha is None:
        print(f"  commit    FAILED — {detail}")
        run_metrics.close("commit_failed")
        return 1
    print(f"  commit    {sha}  ({detail})")
    print(f"  first-pass violations: {first_pass}")
    run_metrics.close("committed")

    # After the commit, never before: a project render touches every page in the
    # notebook, and an unrelated broken one must not be able to block an entry
    # that has already passed lint, render and verify on its own terms.
    site(notebook)

    # --- advance the queue -------------------------------------------------
    # The commit moved the manifest, so the cache just used can never be reused:
    # its key is stale by construction. Releasing it here stops it billing out
    # the rest of its hour. When a queued question follows, `build()` releases it
    # as part of creating the next one instead.
    if not proposal.queue:
        cache.release(notebook)

    if proposal.queue:
        nxt, rest = proposal.queue[0], proposal.queue[1:]
        print(f"\n  {len(proposal.queue)} question(s) queued. Next:\n    {nxt}\n")
        from .ask import main as ask
        return ask(notebook_path, nxt, carry_queue=rest, verbose=verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
