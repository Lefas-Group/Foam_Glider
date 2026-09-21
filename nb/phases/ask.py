"""
`nb ask` -- probe the model until the question is answered, then propose and exit.

The exit is the gate. Every run stops here, always, at the same place, and the
process ends: that is what makes an orchestration framework unnecessary, because
there is no pause the process did not choose.
"""

import sys

from ..config import MAX_CORRECTION_ROUNDS, MAX_TURNS, PROBE_POOL
from ..loop import Stopped, Terminal, run
from ..session import Session
from ..tools.interact import (ask_pool, ask_render_ceiling, ask_stuck,
                              confirm_assumptions, persist,
                              render_stop)
from ..preflight import check as preflight
from .. import metrics
from .common import setup, report, spoken_calls
from ..log import detach_output, open_log, say, tell
from .. import runstate

ROUTING_FREE = """\
Pick the chapter from what is above. If two look plausible, `probe` is how you
tell them apart -- load one and look at the names it defines. That is one turn;
reading files to infer it is many."""

# Pinned by `--chapter`. Routing to an EXISTING chapter is a coordinator's
# instruction, not a finding -- it costs probe turns to rediscover and getting
# it wrong answers about a different aircraft. Creating a chapter is a
# different decision and stays the user's, at the gate.
ROUTING_PINNED = """\
The chapter is already decided: **{chapter}**. Probe it, propose into it, and do
not route elsewhere. If the question genuinely does not belong there, say so in
the proposal's rationale rather than moving it."""

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

{routing}

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

def main(notebook_path, question, carry_queue=None, verbose=True,
         pool=None, ceiling=None, run_id=None, quiet=False,
         answers=None, chapter=None):
    bad = preflight(notebook_path)
    if bad:
        for b in bad:
            tell(f"  {b}")
        return 1

    from ..config import Notebook, new_run_id
    # A NEW run, always: `ask` starts one. `write` resuming afterwards takes the
    # most recent, which is this one, so the two phases share a directory
    # without passing an id between them.
    notebook = Notebook(notebook_path, run_id=run_id or new_run_id())
    runstate.write(notebook, phase="ask", question=question,
                   chapter=None, turn=0, waiting_on=None)
    # ALWAYS detached. There used to be two paths -- stdin at a terminal, or
    # the run directory -- and they differed in behaviour rather than plumbing:
    # an unanswered Specified input killed the attached run with nothing on
    # disk, while the detached one leaves the question where `nb answer`, a
    # second terminal or a coordinator can reach it and the run resumes. The
    # detached path is better on every such row, `POLL` is 1 s so the latency
    # is imperceptible, and one agent is the N=1 case of N agents rather than
    # a mode with its own failure shapes.
    #
    # It also collapses `tell` into `say` for free: `tell` already wrote to the
    # log as well as stdout, and `detach_output` closes the stdout half. The
    # log is the record either way.
    from ..mailbox import Mailbox
    from ..tools.interact import use_mailbox
    use_mailbox(Mailbox(notebook, answers=answers))
    if quiet:
        # Nothing will be drawn over, so say where the run went. Printed BEFORE
        # detaching, because every later `tell` goes only to the log.
        tell(f"  run       {notebook.run_id}")
        tell(f"  detail    uv run --group nb python -m nb watch "
             f"{notebook.root.name} {notebook.run_id}")
    # AND THEN LEAVE THE SESSION. Before `setup()`, which starts the MCP
    # filesystem subprocess, and before the metrics connection: `fork` past
    # either is how a daemon inherits something it cannot use.
    #
    # The board runs in the ORIGINAL process, which is the one still holding
    # the terminal. To whoever typed the command nothing looks different -- a
    # question appears, they answer it -- but there is one mechanism
    # underneath, and closing the window no longer kills the run.
    from ..detach import detach_process
    board = None
    if not quiet:
        from .board import follow
        board = lambda: follow(notebook, only=notebook.run_id)
    detach_process(notebook, parent=board)
    detach_output()
    open_log(notebook, "ask", question)
    run_metrics = metrics.Run(notebook, "ask", question)
    # Asked only at the head of a chain. A queued follow-on, and the write
    # phase, are handed what is left rather than prompted again -- the number
    # agreed here bounds the whole question, not one phase of it.
    #
    # `--pool` and `--ceiling` skip the prompt entirely. A caller who already
    # knows the numbers -- a coordinator, a script, anyone re-running a
    # question -- was being asked them twice a run for no decision.
    if pool is None:
        pool = ask_pool(PROBE_POOL)
    # The render ceiling is granted here too, before anything is built, so the
    # agent designs within it rather than discovering it at render time.
    #
    # `lint._defaults` is the ONLY source of the default, flag or no flag. A
    # second copy of this number in `config.py` disagreed with the notebook
    # once -- 20 s against 200 s, and the notebook won every time -- so the
    # flag overrides the ANSWER and never the source of the default.
    if ceiling is None:
        import lint
        _, default_ceiling = lint._defaults(notebook.root)
        ceiling = ask_render_ceiling(
            default_ceiling or 200.0,
            "declared by this notebook's _notebook.py" if default_ceiling
            else "no notebook default; nb's fallback")
    session = Session(notebook, question, chapter=chapter,
                      carry_queue=carry_queue,
                      metrics=run_metrics, probe_pool=pool)
    # The pin, for `propose` to hold the model to. On the session rather than
    # threaded through, because `propose` already reaches the session for every
    # other thing it checks.
    session.pinned_chapter = chapter
    session.render_ceiling = ceiling

    say(f"  notebook  {notebook.root.name}")
    fs, handlers, make_config = setup(session, phase="ask")
    gate = None
    notebook.run.mkdir(parents=True, exist_ok=True)
    notebook.transcript_path.write_text("")

    contents = [{"role": "user", "parts": [{"text": BRIEF.format(
        question=question, max_turns=MAX_TURNS,
        routing=(ROUTING_PINNED.format(chapter=chapter) if chapter
                 else ROUTING_FREE))}]}]

    def on_turn(n, resp, turn):
        run_metrics.turn(resp)
        if verbose:
            say()          # one blank line per turn, so a turn and its
                           # reasoning read as one block
            calls = spoken_calls(turn)
            say(report(resp, f"turn {n + 1}") +
                (f"  ->  {', '.join(calls)}" if calls else "  ->  (done)"))
        runstate.write(notebook, turn=n + 1, chapter=session.chapter)

    def probe_once():
        """One pass of the loop, returning the proposal it ended with."""
        try:
            run(contents, make_config(), handlers,
                transcript=notebook.transcript_path, max_turns=MAX_TURNS,
                on_turn=on_turn,
                on_stuck=lambda found: ask_stuck(found, "ask"),
                should_stop=lambda: runstate.stop_requested(notebook))
        except Terminal as t:
            return t.payload
        return None

    try:
        try:
            proposal = probe_once()
            if proposal is None:
                raise Terminal(None)     # handled by the `gate is None` path

            # Every assumption, put to the user before anything is built on it.
            # A CORRECTION re-enters the probe rather than falling through to
            # write: `findings` and `working_code` were computed under the old
            # value, and a changed constant may recompute at render time but a
            # changed METHOD cannot. Writing from them would launder a rejected
            # assumption into an unchanged answer, which is worse than never
            # having asked.
            for _ in range(MAX_CORRECTION_ROUNDS):
                corrected = confirm_assumptions(proposal)
                # ALWAYS, not only when corrected: `propose` wrote the file
                # before raising, so the accepted-as-stated case still needs
                # `_assumptions_confirmed` recorded or a resumed `nb write`
                # would ask again.
                persist(proposal, notebook)
                if not corrected:
                    break
                if not session.probe_left:
                    tell(f"\n  Corrected {', '.join(corrected)}, but the probe "
                         f"pool is spent — the proposal on disk was computed "
                         f"under the old value(s) and is not safe to write "
                         f"from.\n  Re-run `nb ask` with a bigger pool.")
                    run_metrics.close("assumption_corrected")
                    return 1
                tell(f"  re-probing — {', '.join(corrected)} corrected, so the "
                     f"answer it found no longer follows")
                contents.append({"role": "user", "parts": [{"text":
                    "The user CORRECTED these assumptions:\n\n"
                    + "\n".join(f"  {i.name} = {i.value}"
                                for i in proposal.inputs
                                if i.name in corrected)
                    + "\n\nYour findings and working code were computed under "
                      "the old values, so they no longer follow. Probe again "
                      "with the corrected ones and propose afresh — do not "
                      "reuse the previous answer."}]})
                again = probe_once()
                if again is None:
                    break
                proposal = again

            t = Terminal(proposal)
            raise t
        except Terminal as t:
            proposal = t.payload
            run_metrics.set(chapter=proposal.chapter,
                            solves=session.solves,
                            solve_seconds=round(session.solve_seconds, 1))
            run_metrics.close("proposed")
            # A new chapter is the one stop that survives on this side of the
            # run: it is a structural commitment later entries build on, far
            # harder to undo than an entry, and it is decided BEFORE any of the
            # work it authorises is paid for. Everything else goes straight on
            # to writing -- there is nothing left to approve once lint, render
            # and the build have passed, and an entry that turns out wrong is
            # corrected by the next entry, never by deletion.
            if proposal.route == "new_chapter":
                # TELEMETRY, not conversation: spend is something to look at,
                # never something to act on, and the per-probe lines already go
                # to the log. Reported here and not on the path that continues
                # into `write`, so one question yields one total rather than
                # each phase reporting a different fraction of it.
                if session.probe_pool:
                    say(f"  budget    {session.probe_spent:.0f} s of "
                        f"{session.probe_pool:.0f} s probe pool used")
                tell(render_stop(proposal, notebook))
                return 0
            gate = proposal
        except Stopped as e:
            run_metrics.close("stopped")
            tell(f"\n  {e}. Nothing was written.")
            return 1
        except RuntimeError as e:
            run_metrics.close("max_turns")
            tell(f"\n  {e}. Nothing was written.")
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
        tell("\n  The loop ended without a proposal. Nothing was written.")
        return 1

    # One command, two conversations. The write phase starts fresh from the
    # proposal inside this same process: it costs ~6% less than carrying the
    # whole probe history forward (measured $0.404 split against $0.429 merged),
    # and it is what the two surviving stops resume from, since nothing persists
    # a conversation across a process boundary.
    tell("")
    from .write import main as write
    # header=False: this process already said which notebook and where the
    # telemetry is. Saying it twice made one question look like two runs.
    return write(notebook_path, verbose=verbose, header=False,
                 run_id=notebook.run_id, quiet=quiet, answers=answers)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], " ".join(sys.argv[2:])))
