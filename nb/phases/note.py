"""
`nb note <notebook> "<text>"` -- one line of the programme, for the board.

WHAT THE COORDINATOR DECIDED, where a human can see it. The runs publish
themselves: `run.json` says what each is doing and `status.log` carries its
reasoning. The coordinator publishes nothing -- it is a Claude Code session, and
its thinking lives in a transcript under `~/.claude/projects/` in a format with
no stability contract, sixteen megabytes long, that nothing in this system can
read. So the board could show every run in the programme and not one word of
why any of them was asked.

Narrated rather than scraped, for the same reason `_record` keeps answers in
`run.json`: a curated line the coordinator chose to write is worth more than a
transcript nobody can parse, and it costs one command per decision.
"""

import sys

from ..config import Notebook
from ..log import tell
from .. import coordinator


def main(argv):
    if len(argv) < 2:
        tell('usage: uv run --group nb python -m nb note <notebook> "<text>"')
        return 2
    text = coordinator.note(Notebook(argv[0]), " ".join(argv[1:]))
    if not text:
        tell("  nothing to note")
        return 2
    tell(f"  noted     {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
