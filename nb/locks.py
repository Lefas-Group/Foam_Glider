"""
Two locks: one for rendering, one for writing a chapter.

Measured, not assumed: two `quarto render` calls on one project fail, four
trials out of four, and which of the two fails varies. The error is

    NotFound: utime '…/_freeze/site_libs/quarto-nav/headroom.min.js'
    at copyToProjectFreezer -> freezeLibDir -> renderProject

`_freeze/site_libs/` belongs to the Quarto PROJECT and every render copies into
it, even when rendering a single page. So the lock cannot be finer than one per
notebook: the contended directory is the notebook's.

That was the only lock for a while, on the reasoning that a probe reads the
chapter's files and, once its script and figures live in the run directory,
writes nothing shared -- and the median CPU fraction of a phase is 2.3%, so
contention is not the problem serialising would solve. True of the ASK phase
and false of the WRITE phase, which edits `_model.py`, `_analysis.py` and the
chapter's entries in place. `claim_chapter` closes that, and says why.

A probe is still unlocked, and still should be.

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


# The fds of every lock this process has CLAIMED, kept alive deliberately. A
# claim is held until the process exits, so there is nothing to close and no
# context manager to thread through a function with a dozen return points --
# the kernel releases it on exit, including a SIGKILL, which is the same
# property that made `flock` right for the render lock.
_claimed = []


def claim(path):
    """
    Take `path` exclusively for the life of this process, or refuse at once.

    Returns None when the lock is ours and the holder's pid (as text) when it
    is not. Unlike `held` it neither waits nor proceeds unlocked, because the
    two failures are not alike: a contended RENDER is a few seconds of waiting
    and a retry, while a contended CHAPTER is another agent editing the same
    `_analysis.py` -- which no amount of waiting makes safe, and which is worth
    refusing early, while the proposal is still on disk to resume from.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # A path this process already claimed is still ours. Without this the
    # second call would report US as the holder and refuse: `flock` is per open
    # file description, so a fresh `open` of the same file contends with the fd
    # already held, same process or not.
    if any(fh.name == str(path) for fh in _claimed):
        return None
    fh = open(path, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.seek(0)
        holder = fh.read().strip()
        fh.close()
        return holder or "another process"
    fh.seek(0)
    fh.truncate()
    fh.write(f"{os.getpid()}\n")
    fh.flush()
    _claimed.append(fh)
    return None


def claim_chapter(notebook, chapter):
    """
    One writer per chapter, for the length of a write phase.

    Measured, on 2026-09-18: two runs entered `04-thinner-foam` five minutes
    apart and spent seventeen minutes editing one `_analysis.py` between them.
    One edited the other's entry file; one spent four turns investigating a
    function the other had written; and the refactor gate then reported
    `simulate_throw_3dof changed … declare_refactor was not called` against the
    run that had not touched it -- the declaration is run-scoped state, the
    check compares the chapter on disk, and with two writers those stop being
    the same thing. Neither run committed.

    The render lock could not have caught it. That one serialises one Quarto
    project because `_freeze/site_libs/` is shared; this one serialises the
    SOURCE, which nothing else was protecting. Per chapter rather than per
    notebook on purpose: two agents on two chapters was the point of the
    parallelism, and they contend only at the render, which is already locked.
    """
    return claim(notebook.scratch / f"chapter-{chapter}.lock")
