"""
`nb listen <notebook> [--timeout N]` -- block until a run needs the
coordinator, then say which one and why.

THE INVERSE OF `nb await`, and the half that was missing. `await` blocks until
the HUMAN answers a question the coordinator escalated; nothing blocked until a
RUN asks the coordinator something. So a coordinator with detached runs had no
way to wait and hand-rolled a poll loop instead -- which, in a harness whose
shell calls only return their output when they EXIT, means polling `run.json`
every 40 s and reading the whole batch once, minutes later.

That is not a slow watcher, it is a blind one, and the deadlines are shorter
than the blindness: a question carrying a default takes it after
`mailbox.DEFAULTED_WAIT` (5 min). Measured, 2026-09-29: run
20260929-093246-f82c asked `inherited` for chapter 06, the coordinator's loop
did not surface it for nine minutes, and the record reads
`"source": "default (unanswered)"`. Chapter 06 forked from 03-no-cosmetics
keeping `01-first-chapter/wing-position: Wing leading edge at x=0.25 m` -- in
the one chapter whose premise is that the wing position is FREE, and whose
entry reports 26.8 cm. The number was right and the record around it was not.

MEANT TO BE BACKGROUNDED, for the reason `await_.py` is: the coordinator has no
process between turns, so something has to hold the wait, and a backgrounded
command's EXIT is what wakes it.

THREE THINGS MAKE A RUN THE COORDINATOR'S PROBLEM, and this waits for any:

  asks   a live run has a question on disk      -> `nb answer`
  ends   a run reached an `outcome`             -> read it, choose the next
  died   the lock is gone and no outcome        -> `nb resume`, or `nb clean`

SINCE WHEN IS A DURABLE FACT, not this process's memory. A first version
snapshotted the finished runs at startup and suppressed them, which is right
within one call and wrong between two: the coordinator's runs end BETWEEN its
turns, so the ending it most needs was the one every fresh `listen` had just
decided was old news. The watermark therefore lives in the coordinator's own
`run.json`, through `coordinator.touch` -- the same reserved id that already
holds its escalations and its log -- and is stamped on the way out. A notebook
whose first-ever `listen` finds forty finished runs reports none of them and
starts the clock, because "everything that ever happened" is what `nb board` is
for.

THE WATERMARK HOLDS BACK `ends` AND NOTHING ELSE. An ending is read once and
then it is history. A QUESTION and a DEATH are outstanding work: nothing will
change either of them until the coordinator acts, so suppressing one for being
old hides the very case that has been ignored longest. They are reported every
time, which makes the wait return at once while either stands -- the correct
pressure, and a converging one, because `nb answer`, `nb resume` and `nb clean`
each end it. Measured on RADICAL-GLIDER: 27 runs, every one carrying an
`outcome`, so `died` fires for none of them.

Exit 0 and events are printed; exit 1 and the wait timed out; exit 2 on usage.
A caller that checks the status before reading gets events and nothing else --
the contract `await_.py` states, for the same reason.
"""

import sys
import time

from ..config import Notebook
from ..process.log import tell
from ..process import coordinator, mailbox, runstate

POLL = 2.0
# Long enough to outlive the longest question a run can hold (`mailbox.WAIT`,
# an hour), so a listener started just before a Specified input is asked is
# still there when it expires. `coordinator.TIMEOUT` is four hours for the
# mirror-image reason; this side has nothing to gain past the second hour.
TIMEOUT = 7200.0


def _deadline(q):
    """
    When this question expires, DERIVED -- `question.json` does not carry it.

    `Mailbox.ask` picks the wait from the question rather than from the caller:
    one with a `default` waits `DEFAULTED_WAIT` and then takes it, one without
    waits `WAIT` and then stops the run with the question still on disk. The
    single call site that passes `wait=` explicitly (`tools/interact.py`, the
    NO PROGRESS question) passes `stuck.ASK_WAIT`, which IS `DEFAULTED_WAIT`,
    and that question carries a default -- so this is exact today and an
    estimate by construction. Worth deriving anyway: "298 s left, then it takes
    its default" is the difference between answering a question and reading
    about it afterwards.
    """
    asked = q.get("asked_at")
    if not asked:
        return None
    return asked + (mailbox.DEFAULTED_WAIT if q.get("default") is not None
                    else mailbox.WAIT)


def _event(run_dir):
    """
    What this run needs from the coordinator, as (kind, state, question).

    A QUESTION IS CHECKED BEFORE LIVENESS, and the order is the point. A run
    holds its lock while it waits, so a live run with a question is the normal
    case -- but a run killed while blocked leaves its question behind, and
    calling that `asks` would send the coordinator to `nb answer`, which
    refuses a reply to a run that is not there. That one is an ENDING: the work
    is on disk and `nb resume` is what picks it up.

    `alive` is None when it cannot be told, which is not the same as dead and
    is treated as alive -- guessing the other way would drop a real question.
    """
    state = runstate.read(run_dir)
    alive = runstate.alive(run_dir)
    q = mailbox.pending(run_dir)
    if q and alive is not False:
        return "asks", state, q
    if state.get("outcome"):
        return "ends", state, None
    if alive is False and state.get("phase"):
        return "died", state, None
    return None


def _report(notebook, kind, run_dir, state, q):
    """One block per event, in the shape the coordinator acts on."""
    run = state.get("run", run_dir.name)
    where = state.get("chapter") or "?"
    if kind == "asks":
        due = _deadline(q)
        left = "" if due is None else f"  {max(0.0, due - time.time()):.0f}s left"
        fate = ("then takes its default" if q.get("default") is not None
                else "then the run stops, question on disk")
        tell(f"  asks      {run}  {where}")
        tell(f"    {q.get('kind', '?')}: {q.get('name', '?')}{left} — {fate}")
        if q.get("why"):
            tell(f"    {' '.join(str(q['why']).split())[:300]}")
        if q.get("how"):
            tell(f"    {q['how']}")
        tell(f'    nb answer {notebook.root.name} {run} "<value>"')
    elif kind == "ends":
        tell(f"  ends      {run}  {where}  outcome={state['outcome']}")
        if state.get("answer"):
            tell(f"    {state['answer']}")
    else:
        tell(f"  died      {run}  {where}  turn {state.get('turn')} — no "
             f"outcome; `nb resume` if there is work on disk")


def scan(notebook, since, was_alive=None):
    """
    One pass over the runs: `(scan_at, [(kind, dir, state, question), …])`.

    EXTRACTED so the coordinator agent waits on the same predicate this command
    does. A second implementation of "what makes a run my problem" is how the
    agent and the terminal come to disagree about whether anything is waiting --
    and the watermark rule below is subtle enough that it would happen.

    `was_alive` is the caller's set, carried across passes so a run that was
    seen running and is now gone can be told from one that was never there.
    """
    was_alive = set() if was_alive is None else was_alive
    scan_at = time.time()
    events = []
    for d in notebook.runs():
        if coordinator.is_coordinator(d.name):
            continue
        got = _event(d)
        if not got:
            if runstate.alive(d):
                was_alive.add(d.name)
            continue
        kind, st, q = got
        if kind == "asks":
            was_alive.add(d.name)
        if kind in ("asks", "died") or float(st.get("updated") or 0) > since:
            events.append((kind, d, st, q))
    # Questions first: they are the ones with a clock on them.
    events.sort(key=lambda e: e[0] != "asks")
    return scan_at, events


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

    # The watermark, and the clock it starts. A notebook that has never been
    # listened to reports no history: `since` is now, not zero.
    state = coordinator.touch(notebook)
    since = float(state.get("listened_at") or time.time())

    # A DEATH IS NOT STAMPED ANYWHERE -- `run.json`'s `updated` is the last
    # thing the process WROTE, which for a killed run is whenever it last
    # wrote, not when it stopped -- which is the other half of why `died` is
    # not watermarked: there is no honest timestamp to compare against.
    was_alive = set()
    deadline = time.time() + timeout
    while True:
        scan_at, events = scan(notebook, since, was_alive)
        if events:
            for kind, d, st, q in events:
                _report(notebook, kind, d, st, q)
            coordinator.touch(notebook, listened_at=scan_at)
            return 0
        if time.time() >= deadline:
            break
        time.sleep(POLL)

    coordinator.touch(notebook, listened_at=scan_at)
    span = f"{timeout:.0f} s" if timeout < 60 else f"{timeout / 60:.0f} min"
    tell(f"  nothing asked in {span}. Listen again to keep waiting.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
