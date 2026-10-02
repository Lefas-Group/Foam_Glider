"""
Putting something in front of a person: a browser tab, or a terminal window.

The ONLY module that knows a desktop exists. Everything else in `nb` writes to
a file or to stdout, which is what makes a run detachable and what lets the
board, `tail`, `grep` and a coordinator all read the same `status.log`. Opening
a window is the one thing that cannot be done that way, so it is done here and
nowhere else.

WHY THIS IS IN `nb` AND NOT IN THE SKILL. The `coordinate-design` skill declares
`allowed-tools: Bash(uv run --group nb python -m nb *)`, so a coordinator cannot
run `open`, `osascript` or anything else. If a window is to be opened on its
behalf, an `nb` subcommand has to be the thing that opens it.

NEITHER FUNCTION IS LOAD-BEARING. A run that cannot open a browser still
commits, and a watcher that cannot get a window still exists -- `nb watch` is
one line away. So both degrade to saying what they would have run, and neither
raises. Nothing here is on a path where failing loudly would help.
"""

import os
import shlex
import shutil
import subprocess
import webbrowser

from .log import tell


def browse_url(url):
    """
    Open a URL. The half of `browse` that is not about a file on disk.

    Split out because `nb open` serves the site over http so that one tab can
    refresh itself, while a fallback with no server still has only a path.
    """
    try:
        if webbrowser.open(url):
            return True
    except Exception:                      # noqa: BLE001 -- see module docstring
        pass
    tell(f"  browser   could not open a browser; the page is at {url}")
    return False


def browse(path):
    """
    Open a local file in the default browser. Returns whether it went.

    `webbrowser` IS THE PORTABLE ANSWER and is stdlib: it knows macOS's `open`,
    Linux's `xdg-open`/`gio`/`kfmclient` and the Windows shell, and it takes a
    `file://` URL on all of them. Shelling out to `/usr/bin/open` would have
    been a macOS branch for something that needs no branch at all.
    """
    if not path.exists():
        tell(f"  browser   nothing at {path}")
        return False
    try:
        if webbrowser.open(path.resolve().as_uri()):
            return True
    except Exception:                      # noqa: BLE001 -- see module docstring
        pass
    tell(f"  browser   could not open a browser; the page is at {path}")
    return False


# HOW TO RUN A COMMAND IN A NEW TERMINAL, in the order to try.
#
# There is no portable answer to this the way `webbrowser` is the portable
# answer above, so it is a probe rather than a platform branch: each entry says
# how to recognise its terminal and how to hand it a shell command, and the
# first one present wins.
#
# THE MULTIPLEXER COMES FIRST, and not by accident. Someone already inside tmux
# wants a new tmux window, not a new OS window floating behind their editor --
# and the people most likely to have no graphical terminal at all are exactly
# the people working inside one.
#
# `$TERMINAL` sits above the hard-coded list because a person who has set it has
# already answered this question for themselves.
def _tmux(cmd, cwd):
    return ["tmux", "new-window", "-c", str(cwd), cmd]


def _applescript(cmd, cwd):
    # Terminal.app takes a SCRIPT, not an argv, so the shell line is built here
    # and then escaped for AppleScript's own string syntax -- backslashes first,
    # or the quotes escaped after it would have their backslashes doubled.
    script = f"cd {shlex.quote(str(cwd))} && {cmd}"
    script = script.replace("\\", "\\\\").replace('"', '\\"')
    # ZOOMED, not native fullscreen. Both the board and a transcript are wide:
    # the board lays run panels side by side and the log's turn lines run past
    # eighty columns, so a default-sized window wraps both into porridge.
    #
    # `zoomed` fills the screen and leaves the window in its space. macOS's
    # real fullscreen would need a `ctrl-cmd-f` keystroke through System
    # Events, which wants accessibility permission and moves the window to a
    # space of its own -- a thing you then have to swipe back from to see
    # anything else, which is the opposite of what a view you glance at wants.
    #
    # `do script` returns the tab it made; zooming ITS window rather than
    # `front window` is what keeps two of these opened in quick succession from
    # both zooming whichever happened to be in front.
    return ["osascript",
            "-e", 'tell application "Terminal"',
            "-e", f'set t to do script "{script}"',
            "-e", "set zoomed of (window 1 whose tabs contains t) to true",
            "-e", "activate",
            "-e", "end tell"]


def _dash_dash(binary):
    """`gnome-terminal --working-directory=X -- bash -lc '…'` and its kin."""
    def build(cmd, cwd):
        return [binary, f"--working-directory={cwd}", "--", "bash", "-lc", cmd]
    return build


def _dash_e(binary):
    """`xterm -e bash -lc '…'` -- the older convention, with no cwd flag."""
    def build(cmd, cwd):
        return [binary, "-e", "bash", "-lc", f"cd {shlex.quote(str(cwd))} && {cmd}"]
    return build


def _terminals():
    """(name, argv-builder) pairs to try, in order."""
    out = []
    if os.environ.get("TMUX"):
        out.append(("tmux", _tmux))
    out.append(("osascript", _applescript))
    chosen = os.environ.get("TERMINAL")
    if chosen:
        out.append((chosen, _dash_e(chosen)))
    out += [("gnome-terminal", _dash_dash("gnome-terminal")),
            ("kitty", _dash_dash("kitty")),
            ("wezterm", _dash_e("wezterm")),
            ("alacritty", _dash_e("alacritty")),
            ("konsole", _dash_e("konsole")),
            ("x-terminal-emulator", _dash_e("x-terminal-emulator")),
            ("xterm", _dash_e("xterm"))]
    return out


def terminal(argv, cwd, what=""):
    """
    Run `argv` in a terminal window of its own. Returns whether one opened.

    `argv` is a list and is quoted here, so a caller never builds a shell
    string. `cwd` matters: every `nb` command is run from the repo root and
    `uv run` resolves the project from it.

    Says what it would have run when nothing is found, which is the state the
    coordinator was in before any of this existed -- a printed command to paste.
    """
    cmd = " ".join(shlex.quote(str(a)) for a in argv)
    for name, build in _terminals():
        if shutil.which(name) is None:
            continue
        try:
            subprocess.run(build(cmd, cwd), check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            continue                        # try the next one
    tell(f"  window    no terminal found for {what or 'this'}; run it yourself:")
    tell(f"    cd {cwd} && {cmd}")
    return False
