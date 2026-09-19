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


def _seconds(etime):
    """`[[dd-]hh:]mm:ss` as seconds. Parsed right to left, so the optional
    halves need no cases of their own."""
    days, _, rest = etime.rpartition("-")
    try:
        parts = [int(x) for x in rest.split(":")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts[-3:]
    return ((int(days) if days else 0) * 86400) + h * 3600 + m * 60 + sec


def _elapsed(pid):
    """Seconds since the process started, or None if it cannot be told."""
    got = _ps(pid, "etime")
    return _seconds(got[0]) if got else None


# How much younger than its run a process may look and still be believed. `ps`
# rounds `etime` to the second and `started` is written a moment after the
# process begins, so the two disagree by a little, always in the same
# direction. Generous on purpose: this test exists to catch a pid that is
# YEARS out, not to adjudicate seconds.
PID_SLACK = 120.0


def _is_ours(state, elapsed=None):
    """
    False when the pid exists but cannot be this run's process.

    A run directory outlives its process, and pids are recycled -- 99998 of
    them on a mac, which a busy week gets through. Inherit one and the board
    calls a finished run `running` for ever, `nb clean` refuses to drop it
    because it looks alive, and the board will sit offering to answer a
    question on its behalf.

    Told apart by AGE: a process that has been up for less time than the pid
    has been recorded cannot be the process that recorded it. Nothing else is
    needed -- the impostor is almost always far younger, since it got the pid
    only after ours released it.

    Against `pid_at` and not `started`: a resumed run keeps the run's start
    time and takes a new process, so `started` would make every resume look
    like an impostor. Runs written before `pid_at` existed fall back to
    `started`, which is right for them -- they never resumed.
    """
    pid = state.get("pid")
    started = state.get("pid_at") or state.get("started")
    if not started or not pid:
        return True                  # nothing to check against; do not guess
    up = _elapsed(pid) if elapsed is None else elapsed
    if up is None:
        return True
    return up + PID_SLACK >= (time.time() - started)


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


def alive(state):
    """True if the pid exists, False if not, None if we cannot tell."""
    pid = state.get("pid")
    if not pid:
        return None
    try:
        os.kill(pid, 0)
        # Two ways a live-looking pid is not a live run, both checked only on
        # the path that would otherwise say yes, so the cheap test still
        # carries the common case.
        #
        # A ZOMBIE answers os.kill exactly as a live process does, and is not
        # alive in any sense that matters: it has exited, and it lingers only
        # until its parent shell reaps it. Seen straight after killing a
        # suspended run -- the process was <defunct> and the board would have
        # gone on calling it `running`.
        #
        # And the pid may belong to someone else entirely: see `_is_ours`.
        #
        # ONE `ps` call for both. `nb board` re-reads every run twice a second,
        # so a second subprocess here is 2N of them per second for a fact that
        # arrives in the same line as the first.
        got = _ps(pid, "stat", "etime")
        if not got:
            return False             # gone between the kill() and the ps
        if got[0].startswith("Z"):
            return False
        return _is_ours(state, _seconds(got[1]) if len(got) > 1 else None)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
