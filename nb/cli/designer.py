"""
`nb designer <notebook>` -- the board, with a coordinator behind it.

ONE COMMAND, AND THE BOARD IS THE HOME. Starting a programme used to mean
carrying the direction on the command line, watching turn lines scroll past in
the terminal the coordinator had taken, and opening the board separately in
another window. The board was already where a person watches and answers from;
it just was not where anything BEGAN.

So: this creates the aircraft if it does not exist, puts the direction on the
board as a question, forks the coordinator into the background, and gives the
terminal to the board. Everything the human decides arrives in one place.

NOTHING HERE IS NEW MACHINERY, which is most of the argument for it:

  * `detach_process(notebook, parent=...)` runs `parent` in the process that
    still holds the terminal, and says in its own docstring that the board is
    what belongs there. `nb ask --quiet` has worked this way all along.
  * `board._asking()` already prompts for the RESERVED id and nothing else
    when a coordinator is present -- run questions stay visible and are not
    this terminal's to answer. The direction is just another escalation.
  * `coord/prefix.py` already opens a cold session with "You have a question
    outstanding with the user ... call `wait` NOW", so the agent collects the
    answer before it does anything else.

`nb coordinate` STAYS, and is not a worse version of this. It is the headless
entry: a cron job or a script has no terminal to give the board and must not be
handed one.
"""

import sys

from ..config import Notebook
from ..process import coordinator
from ..process.log import tell


def _skeleton(name):
    """
    The least that lets a board exist: `chapters/` and the mailbox.

    THE BOOTSTRAP, and the reason `nb new` had to learn that an empty
    directory is not an occupied one. The board reads `_scratch/runs/`, and
    `Notebook()` refuses a root without `chapters/` -- so for a NEW aircraft
    there was nowhere to ask the direction until research had finished and
    `nb new` had run, which is minutes of nothing on screen.

    Both are directories `nb new` creates itself moments later, so this builds
    no state it owns: it reserves the shape, and `new` fills it.
    """
    import pathlib
    root = pathlib.Path(name)
    fresh = not (root / "chapters").is_dir()
    (root / "chapters").mkdir(parents=True, exist_ok=True)
    nb = Notebook(root)
    coordinator.touch(nb)          # makes _scratch/runs/coordinator/
    return nb, fresh


def main(argv):
    if not argv or argv[0].startswith("--"):
        tell("usage: uv run --group nb python -m nb designer <notebook> "
             "[--max-turns N] [--all]")
        return 2
    name = argv[0]
    nb, fresh = _skeleton(name)

    # ASKED ON THE BOARD, not here. Posting returns at once and the board
    # prompts for it, so the question is already waiting when the view opens.
    # Skipped when a direction is pinned and the user gave none: that session
    # is picking the programme up, and `prefix.build` says so.
    if not coordinator.current_direction(nb):
        coordinator.post(
            nb, "direction",
            prompt=("What should this programme do? One or two sentences --"
                    + (" which aircraft, and what to find out about it."
                       if fresh else " what to work on next.")),
            why=("Nothing is pinned above this notebook yet, and a programme "
                 "with no recorded reason is one nobody can read back."))

    tell(f"  designer  {name}" + ("  (new aircraft)" if fresh else ""))
    tell(f"  detail    uv run --group nb python -m nb watch {name} coordinator")

    # THE FORK IS FIRST, before a client, a thread or a socket exists --
    # `process/detach.py` is explicit that forking past any of those is how it
    # goes wrong quietly. `cli/run.py::_start` is the template: the board is
    # the `parent`, because the terminal is the one thing the daemon cannot
    # have and the board is the one thing that needs it.
    from ..process.detach import detach_process
    from .board import follow
    answer_all = "--all" in argv

    def board():
        return follow(nb, answer_all=answer_all)

    if not detach_process(None, parent=board):
        # No `fork` on this platform. Run the session in front of the person
        # rather than pretending; they can open the board themselves.
        tell("  (no fork here -- running in the foreground; "
             f"open the board with `nb board {name}`)")
        from .coordinate import coordinate
        return coordinate(name, max_turns=_turns(argv))

    # The child. Its stdout is /dev/null from here -- `status.log` is its
    # voice, and the board is the person's.
    from ..process.log import detach_output
    detach_output()
    from .coordinate import coordinate
    return coordinate(name, max_turns=_turns(argv), banner=False)


def _turns(argv):
    from ..config import MAX_TURNS
    if "--max-turns" in argv:
        i = argv.index("--max-turns") + 1
        if i < len(argv):
            try:
                return int(float(argv[i]))
            except ValueError:
                pass
    return MAX_TURNS


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
