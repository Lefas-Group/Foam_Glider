"""
`nb watch` -- the detail, live, from another tab.

`say()` stopped reaching the terminal so the conversation could have it to
itself, which makes `_scratch/run/status.log` the only place a run's turn lines,
reasoning and budgets exist while it is happening. This follows that file.

A command rather than "run `tail -f` on this path": the path is notebook-relative
and forty characters long, and this is now the ONLY live view of what a run is
doing, so it should cost one short line to open.

Deliberately not clever. No formatting, no filtering, no curses -- the log is
already written to be read, and anything this added would be a second way of
rendering the same lines, to be kept in step with the first.
"""

import os
import re
import sys
import time

from ..config import Notebook
from ..log import tell


# How long a run may be silent before the watcher says so, when it has not
# declared a deadline of its own. Above the slowest turn measured across 16
# completed runs (54 s at the worst run average, 13 s median), so an honest
# think does not trip it.
DEFAULT_QUIET = 120.0

# Dimming happens HERE, not in the log. The run writes plain text -- the file
# is read by `tail`, by grep, and one day by a coordinator, and escape codes in
# it would be noise to all three. The reader is the one that knows it is
# attached to a terminal, so the reader styles. Same split as the staleness
# warning below.
GUTTER = "│"

PID = re.compile(r"\bpid (\d+)\b")
DEADLINE = re.compile(r"deadline (\d+(?:\.\d+)?) s")


def _alive(pid):
    """True if the process exists, False if not, None if we cannot tell."""
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, owned by someone else
    except OSError:
        return None


def _console():
    """A rich console, or None when rich is unavailable."""
    try:
        from rich.console import Console
    except ImportError:
        return None
    return Console(soft_wrap=True)


def _emit(console, text):
    """
    Print, dimming the model's reasoning so the run's own report stands out.

    Through `rich` rather than by hand. The hand-rolled version emitted
    `\x1b[2m`, which is correct and which macOS Terminal.app ignores, so the
    dimming never appeared and nothing in code review could show that. A library
    that asks the terminal what it supports is the fix; `dim` degrades to a grey
    where faint is unsupported, and to nothing at all when piped.
    """
    if console is None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    for line in text.splitlines():
        if line.lstrip().startswith(GUTTER):
            console.print(line, style="grey50", highlight=False)
        else:
            console.print(line, highlight=False, markup=False)


def _quiet_note(idle, limit, pid):
    live = _alive(pid)
    mins, secs = divmod(int(idle), 60)
    if live:
        # SUSPENDED is not STALLED, and only one of them has an action. A `&`
        # job halted by Ctrl-Z, or by any terminal signal, answers
        # `os.kill(pid, 0)` exactly as a working process does -- so this used to
        # report "alive but not advancing", which is true, useless, and points
        # at the model or the network rather than at the shell. Seen on a
        # detached run with 3.9 s of CPU behind 7m20s of clock.
        from .. import runstate
        if runstate.stopped({"pid": pid}):
            return (f"          ⚠ pid {pid} is STOPPED, not stalled — suspended "
                    f"by a signal, using no CPU.\n"
                    f"            Resume it: fg, or kill -CONT {pid}")
    who = "" if live is None else (
        f" — pid {pid} alive but not advancing" if live
        else f" — pid {pid} is GONE; the run died without a word")
    return (f"          ⚠ {mins}m{secs:02d}s with no new line, past the "
            f"{limit:.0f} s deadline{who}")


def follow(path, from_start=False, poll=0.25):
    """
    Print `path` as it grows, like `tail -f`, and say when it stops growing.

    The staleness warning is the point. `say()` no longer reaches the terminal,
    so a wedged run and a thinking one look identical -- one sat blocked on a
    dead socket for 4h14m and nothing noticed. The RUN emits facts (a timestamp
    on every line, its pid in the header, the deadline of any bounded
    operation); the WATCHER decides when they have stopped arriving. That split
    is why this is not a heartbeat thread inside the run: such a thread would
    keep printing cheerfully while the main thread was stuck.

    Handles a file that does not exist yet -- `nb watch` is usually opened
    BEFORE the run it is watching -- and a file that shrinks, which means a new
    run truncated it.
    """
    handle, size = None, 0
    pid, limit, last, warned = None, None, time.time(), False
    pending = ""
    console = _console()
    try:
        while True:
            if handle is None:
                if not path.exists():
                    time.sleep(poll)
                    continue
                handle = path.open()
                if not from_start:
                    handle.seek(0, 2)       # only what happens from now on
                size = path.stat().st_size

            chunk = handle.read()
            if chunk:
                # Buffer the tail: a read can land mid-line, and styling half a
                # line leaves the escape code unterminated across the split.
                chunk, pending = pending + chunk, ""
                if not chunk.endswith("\n"):
                    chunk, _, pending = chunk.rpartition("\n")
                    chunk += "\n" if chunk else ""
                _emit(console, chunk)
                # The run tells us who it is and what it is waiting for.
                for m in PID.finditer(chunk):
                    pid = int(m.group(1))
                for m in DEADLINE.finditer(chunk):
                    limit = float(m.group(1))
                last, warned = time.time(), False

            idle = time.time() - last
            ceiling = limit if limit else DEFAULT_QUIET
            if idle > ceiling and not warned:
                print(_quiet_note(idle, ceiling, pid), flush=True)
                warned = True               # once per stall, not once a second

            now = path.stat().st_size if path.exists() else 0
            if now < size:                  # truncated: reopen from the top
                handle.close()
                handle, from_start = None, True
                continue
            size = now
            time.sleep(poll)
    except KeyboardInterrupt:
        pass
    finally:
        if handle is not None:
            handle.close()


def main(argv):
    if not argv:
        print("usage: uv run --group nb python -m nb watch <notebook> [--all]")
        return 2
    notebook = Notebook(argv[0], run_id=argv[1] if len(argv) > 1
                        and not argv[1].startswith("--") else None)
    log = notebook.run / "status.log"
    tell(f"  watching   {log}"
         f"{'' if log.exists() else '  (waiting for a run to start)'}")
    follow(log, from_start="--all" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
