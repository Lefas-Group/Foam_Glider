"""
`run.json` -- what a run IS, while it is still running.

`nb-metrics.db` records a run when it `close()`s, so a running agent has no row
at all: the db is history and cannot answer "what is happening right now". With
one agent that gap was covered by the pid in `status.log`'s header, which
`nb watch` parses to tell a wedged run from a dead one. With eight it is not.

So each run publishes a small document, rewritten at every phase transition:

    {"run": "20260916-a3f2", "pid": 81234, "pid_at": 1758030000.0,
     "chapter": "04-thinner-foam", "question": "how stable is it?",
     "phase": "ask", "turn": 7, "started": 1758030000.0, "waiting_on": null}

`started` belongs to the RUN and survives a resume; `pid` and `pid_at` belong to
the PROCESS currently working on it, and both move when a resume takes over.

`nb board` draws its table from these, and a coordinator agent reads the same
files -- one registry, not two mechanisms. `waiting_on` names a pending question
so "who is blocked" is answerable without opening every run directory.

Written with a temp file and `os.replace`, which is atomic on POSIX: a reader
polling every 250 ms must never catch a half-written document. This is the one
place in the system where a reader and a writer are guaranteed to race.
"""

import json
import os
import pathlib
import time


def write(notebook, **fields):
    """Merge `fields` into the run's state document. Never raises."""
    state = notebook.run_state
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        current = read(notebook)
        current.update(fields)
        current.setdefault("run", notebook.run_id)
        current.setdefault("started", time.time())
        # THE PID IS OVERWRITTEN, never `setdefault`ed. A resume is a NEW
        # process writing into the run directory the old one left, and
        # setdefault kept the dead pid: `nb board` drew a working run as
        # `died`, `nb watch` said "the run died without a word" about a run
        # advancing in front of you, and -- the expensive one -- `nb clean`'s
        # "never drop a live run" protection saw a corpse and would have
        # dropped it. Verified: a second process writing this file reported the
        # first one's pid.
        #
        # `started` still belongs to the RUN, which is what the board's `for`
        # column means, so the pid gets its own stamp for the age test in
        # `_is_ours` -- a resumed process is younger than its run by design,
        # and comparing it against `started` would call every resume an
        # impostor.
        if current.get("pid") != os.getpid():
            current["pid"] = os.getpid()
            current["pid_at"] = time.time()
        current.setdefault("pid_at", current["started"])
        current["updated"] = time.time()
        tmp = state.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(current, indent=1) + "\n")
        os.replace(tmp, state)
        return current
    except OSError:
        # Telemetry must never be able to fail a run. A board that cannot see a
        # run is a worse outcome than a run that stops, but only slightly, and
        # the run is the thing with the value in it.
        return {}


def read(notebook_or_dir):
    """The state document, or {} if absent or mid-write."""
    d = getattr(notebook_or_dir, "run", notebook_or_dir)
    try:
        return json.loads((d / "run.json").read_text())
    except (OSError, ValueError):
        return {}


def request_stop(notebook, why="", by="user"):
    """
    Ask a run to stop, by leaving a file it will find.

    A SIGNAL was the obvious alternative and is worse. SIGTERM's default handler
    ends the process where it stands: no `finally`, so the MCP server is not shut
    down, no metrics row, and no `outcome` -- which means the board would render
    a deliberate stop as `died`, the one state it exists to distinguish. A file
    the run notices leaves it to exit through its own door, recording what
    happened on the way out.

    The cost is that it is COOPERATIVE: a run inside a long probe or a render
    will not notice until that returns. `kill` is still there for a run that has
    genuinely stopped listening.
    """
    d = getattr(notebook, "run", notebook)
    d.mkdir(parents=True, exist_ok=True)
    (d / "stop.json").write_text(json.dumps(
        {"why": why, "by": by, "asked_at": time.time()}, indent=1) + "\n")
    return d / "stop.json"


def stop_requested(notebook_or_dir):
    """The stop request for a run, or None."""
    d = getattr(notebook_or_dir, "run", notebook_or_dir)
    try:
        return json.loads((d / "stop.json").read_text())
    except (OSError, ValueError):
        return None


def _ps(pid, *fields):
    """
    One `ps` line for `pid`, split on whitespace, or [] if it is not there.

    EACH field gets its own `-o name=`. `-o "stat=,etime="` suppresses only the
    LAST header, so the line comes back as `STAT SN 00:00` and every index is
    off by one -- which silently disabled the zombie test here, since `"STAT"`
    does not start with Z.
    """
    import subprocess
    argv = ["ps"]
    for f in fields:
        argv += ["-o", f"{f}="]
    argv += ["-p", str(pid)]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    return r.stdout.split()


def _stat(pid):
    """The process's `ps` STAT letters, or "" if it is not there."""
    got = _ps(pid, "stat")
    return got[0] if got else ""


LOCK = "run.lock"


def hold(notebook):
    """
    Take this run's liveness lock, for the life of the process.

    Called once, in the child, immediately after the fork. Everything that asks
    "is this run still going?" asks whether this lock is still held.
    """
    from .locks import claim
    return claim(notebook.run / LOCK)


def alive(run_dir):
    """
    True if the run still holds its lock, False if it does not.

    THE KERNEL IS THE WITNESS. This used to be pid archaeology: `os.kill(pid, 0)`
    to see whether a process existed, a `ps` call to tell a ZOMBIE from a live
    process (a zombie answers `kill(0)` exactly as a live one does), and then
    `_is_ours` -- comparing that process's uptime against the run's `pid_at`
    with a 120-second slack, because pids are RECYCLED and a run directory
    outlives its process. Ninety-three lines and two magic constants to work
    out something the operating system already knows.

    `locks.py` has said so all along: "fcntl.flock rather than a lock FILE with
    a pid in it: the kernel releases it when the process dies, so a killed
    agent cannot leave a lock behind. That is the failure mode hand-rolled
    locks are made of." Two modules here hand-rolled one anyway, and each grew
    a heuristic to patch exactly the failure that sentence predicts.

    A flock has none of it. It is released on exit, on SIGKILL, and when a
    zombie is reaped; it is per-file, so pid reuse cannot confuse it; and the
    probe is one syscall rather than a subprocess -- which `nb board` makes 2N
    of a second, refreshing twice a second across N runs.

    NO LOCK FILE MEANS DEAD. A live run takes it before it can do anything
    else, including asking a question, so a run without one either never
    started or predates this. Both are things to clean up rather than wait for.
    """
    import fcntl
    # A Notebook is not a run directory, and passing one used to raise inside
    # `pathlib` with a message about `__fspath__` -- three call sites away from
    # the mistake. `nb stop` shipped with exactly that.
    p = pathlib.Path(getattr(run_dir, "run", run_dir)) / LOCK
    if not p.exists():
        return False
    try:
        fh = open(p, "a+")
    except OSError:
        return None                 # cannot tell; do not guess
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fh, fcntl.LOCK_UN)
        return False                # nobody was holding it
    except OSError:
        return True                 # somebody is
    finally:
        fh.close()


def stopped(state):
    """
    True if the process exists but is SUSPENDED (`STAT` T), False if running.

    `os.kill(pid, 0)` cannot tell these apart -- a stopped process answers it
    exactly as a running one does -- so without this a job halted by Ctrl-Z, or
    by any terminal signal reaching a `&` job, shows as `running` on the board
    and as a stall in `nb watch`, which is the one diagnosis that leads nowhere.
    Observed: a detached run at 3.9 s of CPU over 7m20s elapsed, reported as a
    deadline overrun.

    `ps` rather than /proc, because this is a mac. None when it cannot be told.
    """
    pid = state.get("pid")
    if not pid:
        return None
    st = _stat(pid)
    return st.startswith("T") if st else None
