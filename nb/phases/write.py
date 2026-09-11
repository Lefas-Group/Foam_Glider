"""
`nb write` -- turn an approved proposal into a committed entry.

Lint is both a tool and a mandatory step. The tool lets the loop fix violations
in place; the step after the loop is the guarantee, because without it the model
can simply decline to call the tool and declare itself done.
"""

import datetime
import json
import subprocess
import sys

from ..config import MAX_LINT_ATTEMPTS, MAX_TURNS, Notebook
from ..loop import run
from ..schema import Proposal
from ..session import Session
from ..preflight import check as preflight
from ..tools import verifiers
from ..tools.scaffold import create_chapter
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

    if proposal.route == "new_chapter":
        msg = create_chapter(notebook, proposal.chapter, proposal.title)
        print(f"  chapter   {msg.splitlines()[0]}")
        if msg.startswith("rejected"):
            return 1

    today = datetime.date.today().isoformat()
    stem = _stem(notebook, proposal.chapter, proposal.title, today)
    session = Session(notebook, proposal.question, proposal.chapter)

    fs, handlers, make_config = setup(session)
    try:
        brief = BRIEF.format(
            proposal=json.dumps(proposal.model_dump(), indent=2),
            chapter=proposal.chapter, stem=stem, today=today)
        contents = [{"role": "user", "parts": [{"text": brief}]}]

        def on_turn(n, resp, turn):
            if verbose:
                calls = [p.function_call.name for p in (turn.parts or [])
                         if p.function_call]
                print(report(resp, f"turn {n + 1}") +
                      (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))

        first_pass = None
        for attempt in range(MAX_LINT_ATTEMPTS):
            run(contents, make_config(), handlers,
                transcript=notebook.transcript_path, max_turns=MAX_TURNS,
                on_turn=on_turn)

            clean, problems = verifiers.is_clean(notebook, proposal.chapter)
            if first_pass is None:
                # The eval metric: violations before any correction round.
                first_pass = len(problems)
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
            return 1
    finally:
        fs.stop()

    print(f"  first-pass violations: {first_pass}")
    print("\n  Not committed. Review, then render and commit:")
    print(f"    uv run python nb/vendor/check.py {notebook.root.name} {proposal.chapter}")
    if proposal.queue:
        print(f"\n  {len(proposal.queue)} question(s) still queued:")
        for q in proposal.queue:
            print(f"    nb ask {notebook.root.name} \"{q}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
