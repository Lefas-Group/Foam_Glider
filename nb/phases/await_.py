"""
`nb await <notebook> [--timeout N]` -- block until the human answers, then
print the answer on stdout.

MEANT TO BE BACKGROUNDED. The coordinator has no process between turns, so
something has to hold the wait; a backgrounded command does, and its EXIT is
what wakes the coordinator to relay the answer to the run that needs it. Run in
the foreground it is capped by the harness instead, which is why posting the
question is a separate command that has already succeeded by the time this
starts.
"""

import sys

from ..config import Notebook
from ..log import tell
from .. import coordinator, mailbox


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb await <notebook> "
             "[--timeout <seconds>]")
        return 2
    notebook = Notebook(argv[0])
    timeout = coordinator.TIMEOUT
    if "--timeout" in argv and argv.index("--timeout") + 1 < len(argv):
        try:
            timeout = float(argv[argv.index("--timeout") + 1])
        except ValueError:
            pass
    nb = coordinator.mailbox_for(notebook)
    q = mailbox.pending(nb.run)
    if not q:
        tell("  the coordinator is not waiting on anything")
        return 2
    got = coordinator.wait(notebook, timeout=timeout)
    if got is None:
        tell(f"  no answer in {timeout / 60:.0f} min — {q.get('name')!r} is "
             f"still on the board. Wait again to keep it open.")
        return 1
    # THE ANSWER ALONE, on the only path that returns 0. `tell` writes to
    # stdout too, so "just read stdout" is safe because of the exit code, not
    # because the streams are separated: every other path here reports through
    # `tell` and returns non-zero without printing an answer. A caller that
    # checks the status before reading gets the answer and nothing else.
    print(got)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
