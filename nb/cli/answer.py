"""
`nb answer <notebook> [run] "<value>"` -- reply to a waiting run.

The scripted half of the mailbox, and the reason `nb board` can be a view rather
than a supervisor: an answer is one file, so it can come from the board, from a
second terminal, from a shell script, or from a coordinator agent, and the run
cannot tell which.

With no run id it answers the only run that is waiting, and refuses if more than
one is -- guessing which agent a reply was meant for is the one mistake here
that would be silent.
"""

import sys

from ..config import Notebook
from ..process.log import tell
from ..process import coordinator, mailbox, runstate


def waiting(notebook):
    """Runs with an outstanding question, newest first."""
    out = []
    for d in notebook.runs():
        q = mailbox.pending(d)
        if q:
            out.append((d.name, q, d))
    return out


def main(argv):
    # WHO IS ANSWERING, said rather than assumed. `mailbox.answer` defaulted
    # `by` to "user" and nothing ever overrode it, so a decision the
    # COORDINATOR made -- approving a chapter, accepting an assumption -- was
    # recorded as the user's and the board captioned it "you". That is the one
    # thing a record of what the user agreed to must never do. A person typing
    # this at a terminal is still the default, because they are the one who
    # cannot pass a flag.
    by = "user"
    if "--by" in argv:
        i = argv.index("--by")
        if i + 1 < len(argv):
            by = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        tell('usage: uv run --group nb python -m nb answer <notebook> '
             '[<run>] "<value>" [--by coordinator]')
        return 2
    notebook = Notebook(argv[0])
    pend = waiting(notebook)
    if not pend:
        tell("  nothing is waiting for an answer")
        return 1

    if len(argv) >= 3:
        run_id, value = argv[1], " ".join(argv[2:])
        if run_id not in {r for r, _, _ in pend}:
            tell(f"  run {run_id!r} is not waiting. Waiting: "
                 f"{', '.join(r for r, _, _ in pend)}")
            return 1
    elif len(pend) > 1:
        tell(f"  {len(pend)} runs are waiting — name one:")
        for r, q, st in pend:
            tell(f"    {r}  {st.get('chapter') or '—'}  {q.get('name','')}")
        return 1
    else:
        run_id, value = pend[0][0], argv[1]

    q, d = next((q, d) for r, q, d in pend if r == run_id)
    # A question file OUTLIVES the process that wrote it: the run deletes it
    # only when it reads the answer, so a run that died mid-question leaves one
    # on disk for ever. `nb board` learned to skip those; this did not, and
    # answered them cheerfully -- writing a file nothing will ever read and
    # reporting success for it. Refused rather than warned: the reply is
    # addressed to a corpse either way, and a warning that scrolls past is how
    # you come back an hour later to find the run never moved.
    # THE RESERVED ID HAS NO PROCESS TO BE ALIVE, so the corpse test below
    # would refuse every answer the coordinator is waiting for. See
    # `coordinator.py`: its question is read by a later TURN rather than by a
    # suspended reader, so there is nothing to address an answer to in vain.
    if not coordinator.is_coordinator(run_id) and runstate.alive(d) is False:
        tell(f"  run {run_id} is not running — its question outlived it.")
        tell("  Nothing would read the answer. Drop the run with:")
        tell(f"    uv run --group nb python -m nb clean {notebook.root.name} "
             f"{run_id}")
        return 1
    path = mailbox.answer(Notebook(notebook.root, run_id=run_id), value,
                          by=by, replying_to=q.get("asked_at"))
    tell(f"  answered  {q.get('name','')} -> {value}")
    tell(f"            {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
