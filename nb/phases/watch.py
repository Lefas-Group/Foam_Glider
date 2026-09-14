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

import sys
import time

from ..config import Notebook
from ..log import tell


def follow(path, from_start=False, poll=0.25):
    """
    Print `path` as it grows, like `tail -f`.

    Handles a file that does not exist yet -- `nb watch` is usually opened
    BEFORE the run it is watching, which is the whole point of having it -- and
    a file that shrinks, which means a new run truncated it.
    """
    handle, size = None, 0
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
                sys.stdout.write(chunk)
                sys.stdout.flush()

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
        print("usage: python -m nb watch <notebook> [--all]")
        return 2
    notebook = Notebook(argv[0])
    log = notebook.run / "status.log"
    tell(f"  watching   {log}"
         f"{'' if log.exists() else '  (waiting for a run to start)'}")
    follow(log, from_start="--all" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
