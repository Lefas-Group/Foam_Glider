"""
`nb escalate <notebook> "<name>" --prompt "…"` -- put a question to the human.

The coordinator answers what the direction settles and escalates what it does
not. This is the second half: a Specified input nobody has chosen yet is not
the coordinator's to invent, so it goes to the board at the reserved id and
waits there like any other question.

POSTS AND RETURNS. `nb await` does the waiting -- see `coordinator.post` for
why the two are not one command.
"""

import sys

from ..config import Notebook
from ..log import tell
from .. import coordinator


def _opt(argv, flag):
    return (argv[argv.index(flag) + 1]
            if flag in argv and argv.index(flag) + 1 < len(argv) else "")


def main(argv):
    if len(argv) < 2:
        tell('usage: uv run --group nb python -m nb escalate <notebook> '
             '"<name>" --prompt "<question>" [--why "<context>"] '
             '[--options "<a|b>"] [--default "<value>"]')
        return 2
    notebook = Notebook(argv[0])
    rest = argv[1:]
    name = next((a for a in rest if not a.startswith("--")), "")
    if not name:
        tell("  a question needs a name -- it is the key an answer is "
             "recorded under")
        return 2
    default = _opt(rest, "--default")
    q = coordinator.post(notebook, name,
                         prompt=_opt(rest, "--prompt"),
                         why=_opt(rest, "--why"),
                         options=_opt(rest, "--options"),
                         default=default or None)
    tell(f"  asked     {name!r} — {q['prompt']}")
    tell("  waiting for an answer at the board. To collect it:")
    tell(f"    uv run --group nb python -m nb await {notebook.root.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
