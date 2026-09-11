"""
`nb ask` -- probe the model until the question is answered, then propose and exit.

The exit is the gate. Every run stops here, always, at the same place, and the
process ends: that is what makes an orchestration framework unnecessary, because
there is no pause the process did not choose.
"""

import sys

from ..config import MAX_TURNS
from ..loop import Terminal, run
from ..session import Session
from ..tools.interact import render_proposal
from ..preflight import check as preflight
from .common import setup, report

BRIEF = """\
You are in the ASK phase.

The question:

    {question}

**Everything about this notebook is already in front of you.** Every chapter's
`index.qmd` is quoted above, in full, along with every `_analysis.py` signature
and every entry that already exists with the answer it reached. Do not go
looking for what you have already been given -- re-reading an index.qmd, listing
directories to see which chapters exist, or grepping for a term costs turns and
tells you nothing new.

Pick the chapter from what is above. If two look plausible, `probe` is how you
tell them apart -- load one and look at the names it defines. That is one turn;
reading files to infer it is many.

Then probe for the answer. `probe` takes Python with the chapter already loaded
and the solve budget already armed: do not import the chapter, and do not use it
to explore the filesystem. `chapter` is required -- the wrong one silently
answers about a different aircraft. End your probes with `aero_report()`.

`bash` is an escape hatch for when something breaks, not a way to look around.
Git archaeology is almost never the answer to a design question.

Ask `ask_specified` the moment you hit an input where a different answer would
change what is being built. Do not save it for the proposal.

When the question is answered -- and not before -- call `propose`. Put everything
the write phase needs into it: it does not get this conversation. If the ask
really contained several distinct questions, the first becomes this proposal and
the rest go in `queue`.

Write nothing into the notebook in this phase. You are deciding what to write.

# How to spend your turns

You have {max_turns}. A well-run ask uses five or six: pick the chapter, probe
for the answer, probe once more to check it, propose. Spending twenty on
orientation is the failure mode this brief exists to prevent.

Before your first call, decide two things and say them in one sentence: which
chapter, and what you are going to compute. Then do that.

Reading existing entries tells you what was already answered, not how to answer
this. You have every entry's title and result above; that is enough to know
whether you are repeating one. Open an entry only to link it (rule 10) or to
check a number you think you are contradicting.

If a probe errors, read the traceback and fix the probe. Do not go looking
through the notebook for why -- the traceback already says.
"""

def main(notebook_path, question, verbose=True):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            print(f"  {b}")
        return 1

    from ..config import Notebook
    notebook = Notebook(notebook_path)
    session = Session(notebook, question)

    print(f"  notebook  {notebook.root.name}")
    fs, handlers, make_config = setup(session)
    notebook.run.mkdir(parents=True, exist_ok=True)
    notebook.transcript_path.write_text("")

    contents = [{"role": "user", "parts": [{"text": BRIEF.format(question=question, max_turns=MAX_TURNS)}]}]

    def on_turn(n, resp, turn):
        if verbose:
            calls = [p.function_call.name for p in (turn.parts or []) if p.function_call]
            print(report(resp, f"turn {n + 1}") +
                  (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))

    try:
        try:
            run(contents, make_config(), handlers,
                transcript=notebook.transcript_path, max_turns=MAX_TURNS,
                on_turn=on_turn)
        except Terminal as t:
            print(render_proposal(t.payload, notebook))
            return 0
    finally:
        fs.stop()

    print("\n  The loop ended without a proposal. Nothing was written.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], " ".join(sys.argv[2:])))
