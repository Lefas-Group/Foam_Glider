"""
`nb open <notebook>` -- the board in a window, the site in a browser.

The first thing a coordinator runs. Driving a programme means watching three
things, and until this existed none of them opened themselves: the BOARD (every
run, its questions and its endings), the SITE (what the answers actually say),
and a watcher per run -- which `nb ask` now opens on its own.

WHY A COMMAND RATHER THAN SOMETHING THE SKILL DOES. `coordinate-design`
declares `allowed-tools: Bash(uv run --group nb python -m nb *)`, so a
coordinator cannot run `open` or `osascript`. If anything is to be put in front
of a person on its behalf, an `nb` subcommand has to be what does it.

WHY THE COORDINATOR NAMES THE NOTEBOOK. The skill's `!`cmd`` lines run when the
skill LOADS, before anyone has said which of the notebook directories is meant,
so anything automatic there would have to guess. A coordinator has to resolve
the notebook before it can run any `nb` command at all -- so asking it to run
this one first is always right and needs no heuristic.

`open_` with the underscore, as `await_`: the bare name shadows a builtin.
"""

import sys

from ..config import Notebook
from ..process import desktop
from ..process.log import tell


def main(argv):
    if not argv or argv[0].startswith("--"):
        tell("usage: uv run --group nb python -m nb open <notebook>")
        return 2
    notebook = Notebook(argv[0])
    if not notebook.root.is_dir():
        tell(f"  no notebook at {notebook.root}")
        return 1

    # THE SITE IS NOT BUILT HERE, and that is deliberate. A project render
    # re-executes any entry whose freeze is missing -- hundreds of seconds of
    # aero solves -- which is exactly why `nb view` keeps it behind `--force`.
    # Routing around that guard from a convenience command is how a coordinator
    # would come to spend ten minutes of solver time on wanting to look at a
    # page. Say what to run instead.
    index = notebook.root / "_site" / "index.html"
    if index.exists():
        desktop.browse(index)
        tell(f"  site      {index}")
    else:
        tell("  site      no _site yet — build it with:")
        tell(f"    uv run --group nb python -m nb view {notebook.root.name}")

    # The board is a live `rich` view and wants a terminal of its own. It is
    # also the thing a coordinator cannot run itself: `nb ask --quiet` exists
    # precisely so the board does NOT take over the calling process.
    desktop.terminal([sys.executable, "-m", "nb", "board", notebook.root.name],
                     cwd=notebook.repo, what="the board")
    tell(f"  board     watching {notebook.root.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
