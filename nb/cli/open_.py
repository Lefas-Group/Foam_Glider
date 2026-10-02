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

import json
import sys
import time

from ..config import Notebook
from ..process import desktop, serve
from ..process.log import tell


def main(argv):
    if not argv or argv[0].startswith("--"):
        tell("usage: uv run --group nb python -m nb open <notebook> "
             "[--all] [--stop]")
        tell("  --all    let this board answer every waiting question, not "
             "only what a coordinator escalated")
        tell("  --stop   shut the site server down")
        return 2
    notebook = Notebook(argv[0])
    # THE SERVER OUTLIVES THE COMMAND, so there has to be a way to end it. It
    # is idle and costs a loopback socket, so leaving one running is harmless;
    # this is for when you want the port back or are done with the notebook.
    if "--stop" in argv:
        tell(f"  site      {'stopped' if serve.stop(notebook) else 'was not running'}")
        return 0
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
    if not index.exists():
        tell("  site      no _site yet — build it with:")
        tell(f"    uv run --group nb python -m nb view {notebook.root.name}")
    else:
        # SERVED, NOT OPENED AS A FILE, so one tab can follow a whole session.
        # No browser dedupes a URL it already has -- measured, Chrome went 21
        # tabs to 22 to 23 on the same `file://` -- and asking one what it has
        # open needs an API only macOS exposes. A page that refreshes itself
        # needs no such API, and the server is what lets it: see
        # `process/serve.py`. Static files only; nothing re-executes.
        port = serve.start(notebook)
        if port and serve.watching(notebook, port):
            # ALREADY IN FRONT OF SOMEONE. The open tab polls every second, so
            # the server knowing it is there is the portable answer to "is this
            # already open?" -- the question no browser will answer and macOS
            # only answers for two of them. Nothing to do: the tab is current
            # by construction.
            tell(f"  site      http://127.0.0.1:{port}/  (already open)")
        elif port:
            desktop.browse_url(f"http://127.0.0.1:{port}/")
            tell(f"  site      http://127.0.0.1:{port}/  (refreshes itself)")
        else:
            desktop.browse(index)      # no server; a plain tab is still a view
            tell(f"  site      {index}")

    # The board is a live `rich` view and wants a terminal of its own. It is
    # also the thing a coordinator cannot run itself: `nb ask --quiet` exists
    # precisely so the board does NOT take over the calling process.
    board = [sys.executable, "-m", "nb", "board", notebook.root.name]
    if "--all" in argv:
        board.append("--all")
    desktop.terminal(board, cwd=notebook.repo, what="the board")
    tell(f"  board     watching {notebook.root.name}"
         + ("  (answering everything)" if "--all" in argv else ""))
    _say_if_held(notebook, "--all" in argv)
    return 0


# How long a coordinator can say nothing before its hold is worth mentioning.
# Not a timeout: nothing here decides who may answer. `board._coordinated` is
# deliberately "the reserved directory EXISTS", with no timer, because liveness
# is the wrong question to ask about something with no process between turns.
# This only decides when to TELL somebody, which is a different question and a
# safe one to answer with a clock.
STALE_HOLD_S = 2 * 3600


def _say_if_held(notebook, answering_all):
    """
    Say when the board being opened cannot answer, and why.

    THE FAILURE THIS EXISTS FOR, measured: a coordinator session ended two days
    ago and its reserved directory stayed, because nothing removes it. Every
    run question in the notebook is therefore "the coordinator's", so the board
    shows them and declines to answer them -- correctly, by its own rules. With
    no coordinator left to answer, each one sat until it defaulted. A NO
    PROGRESS question went that way three runs running.

    The board already says `--all` beside each question it will not take. What
    it cannot say is that nobody is coming, and `--all` cannot be added to a
    board that is already running. So it is said here, where the board is
    launched and the flag can still be passed.
    """
    if answering_all:
        return
    state = notebook.scratch / "runs" / "coordinator" / "run.json"
    try:
        got = json.loads(state.read_text())
    except (OSError, ValueError):
        return                            # nobody holds it; the board is free
    idle = time.time() - max(got.get("updated", 0), got.get("listened_at", 0),
                             got.get("started", 0))
    tell(f"  held      a coordinator holds {notebook.root.name}; this board "
         f"shows its questions but will not answer them")
    if idle > STALE_HOLD_S:
        tell(f"            and it has said nothing for {idle / 3600:.0f} h — "
             f"if it is gone, reopen with --all or those questions will "
             f"default unanswered")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
