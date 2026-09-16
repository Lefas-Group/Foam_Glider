"""
One lock, for rendering.

Measured, not assumed: two `quarto render` calls on one project fail, four
trials out of four, and which of the two fails varies. The error is

    NotFound: utime '…/_freeze/site_libs/quarto-nav/headroom.min.js'
    at copyToProjectFreezer -> freezeLibDir -> renderProject

`_freeze/site_libs/` belongs to the Quarto PROJECT and every render copies into
it, even when rendering a single page. So the lock cannot be finer than one per
notebook: the contended directory is the notebook's.

Nothing else here is locked. A probe reads the chapter's files and, once its
script and figures live in the run directory, writes nothing shared -- and the
median CPU fraction of a phase is 2.3%, so contention is not the problem
serialising would solve.

`fcntl.flock` rather than a lock FILE with a pid in it: the kernel releases it
when the process dies, so a killed agent cannot leave a lock behind. That is the
failure mode hand-rolled locks are made of.
"""

import contextlib
import fcntl
import os
import time


@contextlib.contextmanager
def held(path, timeout=600, poll=0.25):
    """
    Hold an exclusive advisory lock on `path`, creating it if needed.

    Blocks until the lock is free or `timeout` expires; on expiry it proceeds
    WITHOUT the lock rather than failing. A render that goes ahead unlocked may
    hit the race, which the caller retries; a render refused outright loses an
    entry that was otherwise finished. The retry is the cheaper failure.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    deadline = time.time() + timeout
    got = False
    try:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except OSError:
                if time.time() >= deadline:
                    break
                time.sleep(poll)
        if got:
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        yield got
    finally:
        if got:
            with contextlib.suppress(OSError):
                fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def render_lock(notebook):
    """The notebook-wide render lock. One Quarto project, one lock."""
    return held(notebook.scratch / "render.lock")
