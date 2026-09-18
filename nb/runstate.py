"""
`run.json` -- what a run IS, while it is still running.

`nb-metrics.db` records a run when it `close()`s, so a running agent has no row
at all: the db is history and cannot answer "what is happening right now". With
one agent that gap was covered by the pid in `status.log`'s header, which
`nb watch` parses to tell a wedged run from a dead one. With eight it is not.

So each run publishes a small document, rewritten at every phase transition:

    {"run": "20260916-a3f2", "pid": 81234, "chapter": "04-thinner-foam",
     "question": "how stable is it?", "phase": "ask", "turn": 7,
     "started": 1758030000.0, "waiting_on": null}

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
        current.setdefault("pid", os.getpid())
        current.setdefault("started", time.time())
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
    import subprocess
    try:
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    st = r.stdout.strip()
    return st.startswith("T") if st else None


def alive(state):
    """True if the pid exists, False if not, None if we cannot tell."""
    pid = state.get("pid")
    if not pid:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
