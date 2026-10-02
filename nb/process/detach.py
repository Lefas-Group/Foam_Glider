"""
Leave the terminal for good -- what `--detach` used to claim, for every run.

It used to detach only the CONVERSATION: questions went to the run directory
instead of stdin, and `tell()` stopped reaching stdout. The PROCESS stayed
exactly where it was -- in the shell's session, holding the controlling
terminal, in a process group the shell's job control owns. Everything the
terminal can do to a process, it could still do to a run:

  * no prompt comes back unless you remember `&`, and the reflex when it does
    not is Ctrl-Z, which suspends the run. Seen three times;
  * a background group that READS the terminal is sent SIGTTIN, which stops
    the whole group. Every subprocess inherited stdin until recently, so any
    of them could do it -- a run froze mid-probe and recorded
    "15 s granted · 5596 s used" across the suspension;
  * closing the window SIGHUPs it.

A run that has left the session cannot be reached by any of them, and the
prompt comes back on its own, so `&` stops being something to remember.

The double fork is the standard daemon shape and both halves earn their place.
The first lets whoever is waiting on us -- the shell, and the `uv run` wrapper
between it and us -- reap a child and return, which is what hands the prompt
back. `setsid` then makes a new session with no controlling terminal. The
second fork leaves the process a non-leader of that session, so it can never
acquire a terminal later by opening one.

CALLED EARLY, before anything with a thread, a socket or a child process
behind it. The MCP filesystem server, the metrics connection and the agent
loop all come afterwards; none would survive being forked out from under, and
`fork()` in a threaded process is how that goes wrong quietly.
"""

import os
import sys


def detach_process(notebook=None, parent=None):
    """
    Become a daemon. Returns True in the surviving child; never returns in the
    parents, which `os._exit` without running exit handlers or flushing
    buffers a second time.

    False means the platform has no `fork` and the caller stays attached --
    degraded, exactly as before, rather than refusing to run.

    `parent`, if given, runs in the ORIGINAL process -- the one still holding
    the terminal -- instead of exiting immediately, and its return value
    becomes that process's exit code. That is where the board belongs: the
    terminal is the one thing the daemon cannot have, and the board is the one
    thing that needs it. It must not be spawned from the child, which has no
    terminal and was forked past the point where threads and sockets are safe.

    By the time this is called the run has already published `run.json`
    (`runstate.write` precedes it in `ask`), so a board starting here always
    has a run to find.
    """
    if not hasattr(os, "fork"):
        return False

    # Anything already buffered belongs to the CALLER's terminal. Flush before
    # forking or both halves inherit the buffer and print it twice.
    sys.stdout.flush()
    sys.stderr.flush()

    if os.fork() > 0:
        # The shell (and the `uv run` wrapper between it and us) is waiting on
        # THIS pid, so whatever happens here is what the user sees. Exiting
        # hands the prompt straight back; running the board hands it back when
        # they leave the board.
        os._exit((parent() or 0) if parent is not None else 0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)

    # stdin to /dev/null; stdout and stderr to a FILE, not /dev/null. The
    # window between here and `open_log` is short but it is not empty, and a
    # run that dies in it would otherwise vanish with no message anywhere --
    # the one failure this system has always tried hardest to make impossible.
    # A traceback from a threaded crash later lands here too, where `say()`
    # cannot reach.
    fd_in = os.open(os.devnull, os.O_RDONLY)
    os.dup2(fd_in, 0)
    if fd_in > 2:
        os.close(fd_in)
    if notebook is not None:
        notebook.run.mkdir(parents=True, exist_ok=True)
        fd_out = os.open(str(notebook.run / "stderr.log"),
                         os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    else:
        fd_out = os.open(os.devnull, os.O_WRONLY)
    os.dup2(fd_out, 1)
    os.dup2(fd_out, 2)
    if fd_out > 2:
        os.close(fd_out)

    # THE PID CHANGED. `run.json` was written by the process that has just
    # exited, and until something rewrites it the board reads a dead pid and
    # draws a starting run as `died`. `runstate.write` overwrites the pid and
    # restamps `pid_at` whenever it differs, so this one call is enough.
    if notebook is not None:
        from . import runstate
        runstate.write(notebook)
    return True
