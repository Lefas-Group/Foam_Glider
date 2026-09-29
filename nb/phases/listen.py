"""
`nb listen <notebook> [--timeout N]` -- block until a run needs the
coordinator, then say which one and why.

THE INVERSE OF `nb await`, and the half that was missing. `await` blocks until
the HUMAN answers a question the coordinator escalated; nothing blocked until a
RUN asks the coordinator something. So a coordinator with detached runs had no
way to wait, and hand-rolled a poll loop instead -- which in a harness whose
shell calls only return their output when they EXIT means polling `run.json`
every 40 s and reading the result once, minutes later.

That is not a slow watcher, it is a blind one, and the deadlines are shorter
than the blindness: a question carrying a default takes it after
`mailbox.DEFAULTED_WAIT` (5 min). Measured, on 2026-09-29: run
20260929-093246-f82c asked `inherited` for chapter 06, the coordinator's loop
did not surface it for nine minutes, and the answer went in the record as
`"source": "default (unanswered)"`. Chapter 06 forked from 03-no-cosmetics
keeping `01-first-chapter/wing-position: Wing leading edge at x=0.25 m` -- in
the one chapter whose premise is that the wing position is FREE, and whose
entry reports 26.8 cm. The number was right and the record around it was not.

MEANT TO BE BACKGROUNDED, for the same reason `await_.py` is: the coordinator
has no process between turns, so something has to hold the wait, and a
backgrounded command's EXIT is what wakes it.

TWO THINGS MAKE A RUN THE COORDINATOR'S PROBLEM, and this waits for either,
because both were what the abandoned poll loop was watching for:

  asks   a live run has a question on disk        -> answer it
  ends   a run reached an `outcome`, or died      -> read it, choose the next

A question already pending when the wait starts is reported AT ONCE. An ending
is only reported if it happens WHILE listening: a notebook with a hundred
finished runs would otherwise return instantly for ever, which is a wait that
cannot be used twice.

THE RESERVED COORDINATOR ID IS SKIPPED. `runs/coordinator/` is where the
coordinator's own escalation to the human sits; reporting it here would wake
the coordinator with its own question, and `nb await` is the command for that
side. `coordinator.is_coordinator` is the single place that test lives.

Exit 0 and something is printed; exit 1 and the wait timed out; exit 2 on
usage. A caller that checks the status before reading gets events and nothing
else -- the same contract `await_.py` states, for the same reason.
"""

import sys
import time

from ..config import Notebook
from ..log import tell
from .. import coordinator, mailbox, runstate

POLL = 2.0
# Long enough to outlive the longest question a run can hold (`mailbox.WAIT`,
# an hour), so a listener started just before a Specified input is asked is
# still there when it expires. `coordinator.TIMEOUT` is four hours for the
# mirror-image reason; this one has nothing to gain past the second hour.
TIMEOUT = 7200.0


def _deadline(q):
    """
    When this question expires, DERIVED -- `question.json` does not carry it.

    `Mailbox.ask` picks the wait from the question, not from the caller: one
    with a `default` waits `DEFAULTED_WAIT` and then takes it, one without
    waits `WAIT` and then stops the run with the question still on disk. The
    single call site that passes `wait=` explicitly (`tools/interact.py`, the
    NO PROGRESS question) passes `stuck.ASK_WAIT`, which is `DEFAULTED_WAIT`,
    and that question carries a default -- so this is exact today and an
    estimate by construction. It is worth deriving anyway: "148 s left, then it
    takes 1.5 m" is the difference between answering a question and reading
    about it afterwards.
    """
    asked = q.get("asked_at")
    if not asked:
        return None
    return asked + (mailbox.DEFAULTED_WAIT if q.get("default") is not None
                    else mailbox.WAIT)


def _event(run_dir):
    """
    What this run needs from the coordinator right now, or None.

    Order matters: a question is checked BEFORE liveness. A run holds its lock
    while it waits, so a live run with a question is the normal case -- but a
    run killed while blocked leaves the question behind, and reporting that as
    `asks` would send the coordinator to `nb answer`, which refuses a reply to
    a run that is not there. It is an ENDING: the work is on disk and
    `nb resume` is what picks it up.
    """
    state = runstate.read(run_dir)
    alive = runstate.alive(run_dir)
    q = mailbox.pending(run_dir)
    if q and alive is not False:
        return "asks", state, q
    if state.get("outcome"):
        return "ends", state, None
    if alive is False and state.get("phase") and not state.get("outcome"):
        return "died", state, None
    return None


def _report(notebook, kind, run_dir, state, q):
    """One block per event, in the shape the coordinator acts on."""
    run = state.get("run", run_dir.name)
    where = state.get("chapter") or "?"
    if kind == "asks":
        left = _deadline(q)
        left = "" if left is None else f"  {max(0.0, left - time.time()):.0f}s left"
        fate = ("then takes its default" if q.get("default") is not None
                else "then the run stops, question on disk")
        tell(f"  asks      {run}  {where}")
        tell(f"    {q.get('kind', '?')}: {q.get('name', '?')}{left} — {fate}")
        if q.get("how"):
            tell(f"    {q['how']}")
        tell(f"    nb answer {notebook.root.name} {run} \"<value>\"")
        tell(f"    {run_dir / 'question.json'}")
    elif kind == "ends":
        tell(f"  ends      {run}  {where}  outcome={state['outcome']}")
        if state.get("answer"):
            tell(f"    {state['answer']}")
    else:
        tell(f"  died      {run}  {where}  turn {state.get('turn')} — "
             f"no outcome; `nb resume` if there is work on disk")


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb listen <notebook> "
             "[--timeout <seconds>]")
        return 2
    notebook = Notebook(argv[0])
    timeout = TIMEOUT
    if "--timeout" in argv and argv.index("--timeout") + 1 < len(argv):
        try:
            timeout = float(argv[argv.index("--timeout") + 1])
        except ValueError:
            pass

    # WHAT WAS ALREADY OVER, before the wait began. Endings are only news if
    # they happen while listening; questions are news whenever they are found,
    # because an unanswered one is live work however long it has been sitting.
    seen = set()
    for d in notebook.runs():
        if coordinator.is_coordinator(d.name):
            continue
        got = _event(d)
        if got and got[0] in ("ends", "died"):
            seen.add(d.name)

    deadline = time.time() + timeout
    while True:
        events = []
        for d in notebook.runs():
            if coordinator.is_coordinator(d.name) or d.name in seen:
                continue
            got = _event(d)
            if got:
                events.append((got[0], d) + got[1:])
        if events:
            # Questions first: they are the ones with a clock on them.
            events.sort(key=lambda e: e[0] != "asks")
            for kind, d, state, q in events:
                _report(notebook, kind, d, state, q)
            return 0
        if time.time() >= deadline:
            break
        time.sleep(POLL)

    span = (f"{timeout:.0f} s" if timeout < 60
            else f"{timeout / 60:.0f} min")
    tell(f"  nothing asked in {span}. Listen again to keep waiting.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
