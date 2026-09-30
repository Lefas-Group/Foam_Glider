"""
`nb direction <notebook> "<text>"` -- what the user asked for.

THE FRAME FOR EVERYTHING ELSE. A programme is a sequence of questions, and the
only thing that makes it one programme rather than a pile of entries is the
direction they were chosen to serve. The board pins it above the table, and
takes it as the start of the conversation: work done under a PREVIOUS direction
in the same notebook is still on the record and is no longer replayed.

Recorded before the first `nb ask`, so nothing in the programme predates the
reason for it.
"""

import sys

from ..config import Notebook
from ..process.log import tell
from ..process import coordinator


def main(argv):
    if len(argv) < 2:
        tell('usage: uv run --group nb python -m nb direction <notebook> '
             '"<what the user asked for>"')
        # Showing the one in force is the common reason to call this bare.
        if argv:
            got = coordinator.current_direction(Notebook(argv[0]))
            if got:
                tell(f"\n  in force: {got['text']}")
        return 2
    text = coordinator.direction(Notebook(argv[0]), " ".join(argv[1:]))
    if not text:
        tell("  a direction needs some words")
        return 2
    tell(f"  direction {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
