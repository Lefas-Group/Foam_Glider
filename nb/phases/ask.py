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
from .. import metrics
from .common import setup, report
from ..log import open_log, say, tell

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

def main(notebook_path, question, carry_queue=None, verbose=True):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            say(f"  {b}")
        return 1

    from ..config import Notebook
    notebook = Notebook(notebook_path)
    open_log(notebook)
    run_metrics = metrics.Run(notebook, "ask", question)
    session = Session(notebook, question, carry_queue=carry_queue,
                      metrics=run_metrics)

    say(f"  notebook  {notebook.root.name}")
    fs, handlers, make_config = setup(session, phase="ask")
    gate = None
    notebook.run.mkdir(parents=True, exist_ok=True)
    notebook.transcript_path.write_text("")

    contents = [{"role": "user", "parts": [{"text": BRIEF.format(question=question, max_turns=MAX_TURNS)}]}]

    def on_turn(n, resp, turn):
        run_metrics.turn(resp)
        if verbose:
            calls = [p.function_call.name for p in (turn.parts or []) if p.function_call]
            say(report(resp, f"turn {n + 1}") +
                  (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))

    try:
        try:
            run(contents, make_config(), handlers,
                transcript=notebook.transcript_path, max_turns=MAX_TURNS,
                on_turn=on_turn)
        except Terminal as t:
            proposal = t.payload
            run_metrics.set(chapter=proposal.chapter,
                            solves=session.solves,
                            solve_seconds=round(session.solve_seconds, 1))
            run_metrics.close("proposed")
            if session.probe_pool:
                say(f"  budget    {session.probe_spent:.0f} s of "
                    f"{session.probe_pool:.0f} s probe pool used")
            # A new chapter is the one stop that survives on this side of the
            # run: it is a structural commitment later entries build on, far
            # harder to undo than an entry, and it is decided BEFORE any of the
            # work it authorises is paid for. Everything else goes straight on
            # to writing -- there is nothing left to approve once lint, render
            # and verify have passed, and an entry that turns out wrong is
            # corrected by the next entry, never by deletion.
            if proposal.route == "new_chapter":
                tell(render_proposal(proposal, notebook))
                return 0
            gate = proposal
        except RuntimeError as e:
            run_metrics.close("max_turns")
            say(f"\n  {e}. Nothing was written.")
            return 1
        except SystemExit:
            # Raised when a prompt hits EOF or is interrupted. Record it before
            # it propagates: "where runs die" is half the point of the table, and
            # a run that stopped at an unanswered question is the most
            # interesting death there is.
            run_metrics.close("no_answer")
            raise
    finally:
        fs.stop()

    if gate is None:
        run_metrics.close("no_proposal")
        say("\n  The loop ended without a proposal. Nothing was written.")
        return 1

    # One command, two conversations. The write phase starts fresh from the
    # proposal inside this same process: it costs ~6% less than carrying the
    # whole probe history forward (measured $0.404 split against $0.429 merged),
    # and it is what the two surviving stops resume from, since nothing persists
    # a conversation across a process boundary.
    say("")
    from .write import main as write
    return write(notebook_path, verbose=verbose)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], " ".join(sys.argv[2:])))
