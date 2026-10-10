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

import re
import sys
import time

from ..config import Notebook
from ..process import coordinator, desktop
from ..process.log import tell


# How long a run may be silent before the watcher says so, when it has not
# declared a deadline of its own. Above the slowest turn measured across 16
# completed runs (54 s at the worst run average, 13 s median), so an honest
# think does not trip it.
DEFAULT_QUIET = 120.0

# How long an `--until-done` watcher stays after the run it follows has ended.
# It exists so a window opened per run does not have to be closed by hand; the
# grace period exists because the last thing a run says -- the commit sha, or
# why it stopped -- is the thing most worth reading, and a window that vanishes
# as it arrives is worse than one that lingers.
#
# FIVE SECONDS, not thirty. The outcome line is one line and it is already on
# screen when the countdown starts, so the grace period only has to cover the
# glance -- and the window is not the place that line is kept anyway: it is in
# `run.json` and in the log, both readable long after. Thirty seconds was long
# enough that a handful of `nb ask`s left a drift of windows waiting to go,
# which is the pile-up `--until-done` exists to prevent.
LINGER = 5.0

# Dimming happens HERE, not in the log. The run writes plain text -- the file
# is read by `tail`, by grep, and one day by a coordinator, and escape codes in
# it would be noise to all three. The reader is the one that knows it is
# attached to a terminal, so the reader styles. Same split as the staleness
# warning below.
GUTTER = "│"

PID = re.compile(r"\bpid (\d+)\b")
DEADLINE = re.compile(r"deadline (\d+(?:\.\d+)?) s")


def _alive(run_dir):
    """
    True if the run still holds its lock, False if not.

    DELEGATED to `runstate.alive` rather than reimplemented. This was a second
    copy of the same `os.kill(pid, 0)`, and it went stale the moment the first
    learned that a ZOMBIE answers that call exactly as a live process does --
    so `nb watch` would still say "alive but not advancing" about a process
    that had already exited. One implementation, one place to teach, and that
    lesson is why it takes the RUN rather than a pid now.
    """
    if run_dir is None:
        return None
    from ..process import runstate
    return runstate.alive(run_dir)


def _console():
    """A rich console, or None when rich is unavailable."""
    try:
        from rich.console import Console
    except ImportError:
        return None
    return Console(soft_wrap=True)


# THE BOARD'S VOCABULARY, so the two views read as one system. A person follows
# a programme by looking at both -- the board for which runs exist and how they
# ended, a watcher for what one of them is doing -- and until this table existed
# the second was undifferentiated grey text beside the first's coloured panels.
#
# Borrowed deliberately rather than invented: green is a thing that worked,
# yellow a thing that wants a person, red a failure, cyan the structural
# announcements, grey50 metadata. That is exactly `board.ENDINGS` and the
# styles around it, and the point is that `commit` here is the same green as
# `committed` there.
KINDS = {
    # The backbone of a transcript, and the one line a reader scans for. Bold
    # with no colour of its own: the first cut made it grey50 with the rest of
    # the metadata, which left the most important line on the screen the
    # dimmest thing on it.
    "turn":     "default",
    "commit":   "green",
    "answer":   "green",
    "waiting":  "yellow",
    "ask":      "yellow",
    "stuck":    "yellow",
    "inputs":   "yellow",
    "refactor": "yellow",
    "lint":     "cyan",
    "render":   "cyan",
    "site":     "cyan",
    "page":     "cyan",
    "check":    "cyan",
    "notebook": "cyan",
    "chapter":  "cyan",
    "entry":    "cyan",
}
# Everything else -- budget, kernel, models -- is metadata about how the run is
# going rather than about what it is doing or what it decided.
KIND_DEFAULT = "grey50"

LINE = re.compile(r"^(\d{2}:\d{2}:\d{2})  (\S+)(\s+)(.*)$")
BANNER = re.compile(r"^[═─]{8,}$")
#: A gutter line: its indent, then the reasoning to re-flow.
THINKING = re.compile(r"^(\s*)" + re.escape(GUTTER) + r" ?(.*)$")


def _emit(console, text):
    """
    Print the log, styled to match the board.

    Through `rich` rather than by hand. The hand-rolled version emitted
    `\x1b[2m`, which is correct and which macOS Terminal.app ignores, so the
    dimming never appeared and nothing in code review could show that. A library
    that asks the terminal what it supports is the fix; `dim` degrades to a grey
    where faint is unsupported, and to nothing at all when piped.

    STYLING ONLY, NEVER REWRITING -- with one exception, below. The same file
    is read by `tail`, by `grep` and by a coordinator, so the writer keeps it
    plain and the reader decides how it looks: the split the telemetry rests
    on. Nothing here changes a character of a status line; it colours the
    three parts of one that already exist.

    THE EXCEPTION IS REASONING, which arrives as one long line per paragraph
    and is WRAPPED HERE, to this console. It used to be wrapped by the writer
    at a fixed 66 columns, which is a third of the terminal a board is usually
    opened in -- and a writer cannot know the width of a reader it has never
    met. `log.py::thought` records the trade.
    """
    if console is None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    import textwrap

    from rich.text import Text
    for line in text.splitlines():
        # The model's reasoning, which the run gutters. Dim, so the run's own
        # report stands out of it.
        if line.lstrip().startswith(GUTTER):
            # Re-flowed to this terminal, with the file's own indent kept so
            # every physical line carries the gutter -- which is the whole
            # point of the gutter. Taken from the line rather than from a
            # constant, so a log written by an older run still lines up.
            m = THINKING.match(line)
            indent, body = (m.group(1), m.group(2)) if m else ("", line)
            room = max(24, console.width - len(indent) - len(GUTTER) - 2)
            for part in textwrap.wrap(body, width=room) or [""]:
                console.print(f"{indent}{GUTTER} {part}",
                              style="grey50", highlight=False, markup=False)
            continue
        if BANNER.match(line.strip()):
            console.print(line, style="cyan", highlight=False, markup=False)
            continue
        m = LINE.match(line)
        if not m:
            # MCP chatter and anything else unstamped: present, and not worth
            # a reader's attention.
            console.print(line, style="grey50", highlight=False, markup=False)
            continue
        stamp, kind, gap, rest = m.groups()
        out = Text()
        out.append(stamp + "  ", style="grey50")
        out.append(kind, style=f"bold {KINDS.get(kind, KIND_DEFAULT)}")
        out.append(gap)
        out.append(rest)
        console.print(out, highlight=False)


def _quiet_note(idle, limit, run_dir, pid):
    live = _alive(run_dir)
    mins, secs = divmod(int(idle), 60)
    if live:
        # SUSPENDED is not STALLED, and only one of them has an action. A `&`
        # job halted by Ctrl-Z, or by any terminal signal, answers
        # `os.kill(pid, 0)` exactly as a working process does -- so this used to
        # report "alive but not advancing", which is true, useless, and points
        # at the model or the network rather than at the shell. Seen on a
        # detached run with 3.9 s of CPU behind 7m20s of clock.
        from ..process import runstate
        if runstate.stopped({"pid": pid}):
            return (f"          ⚠ pid {pid} is STOPPED, not stalled — suspended "
                    f"by a signal, using no CPU.\n"
                    f"            Resume it: fg, or kill -CONT {pid}")
    who = "" if live is None else (
        f" — pid {pid} alive but not advancing" if live
        else f" — pid {pid} is GONE; the run died without a word")
    return (f"          ⚠ {mins}m{secs:02d}s with no new line, past the "
            f"{limit:.0f} s deadline{who}")


def follow(path, from_start=False, poll=0.25, until_done=False,
           close_window=False):
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

    `until_done` makes this RETURN, which it otherwise never does. `nb ask`
    opens one of these per run, so without it the windows accumulate forever.
    The run's own `run.json` is the authority -- an `outcome` is written exactly
    once, by the run, when it is finished with -- rather than guessing from the
    log's content or from the pid going away, which also happens when a run is
    killed mid-question and has nothing to report.
    """
    from ..process import runstate
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
                print(_quiet_note(idle, ceiling, path.parent, pid), flush=True)
                warned = True               # once per stall, not once a second

            now = path.stat().st_size if path.exists() else 0
            if now < size:                  # truncated: reopen from the top
                handle.close()
                handle, from_start = None, True
                continue
            size = now

            if until_done:
                state = runstate.read(path.parent) or {}
                if state.get("outcome"):
                    # One more read first: the outcome is written before the
                    # last lines are flushed, so returning on the instant would
                    # cut off the commit line this window exists to show.
                    time.sleep(poll)
                    rest = handle.read()
                    if rest:
                        _emit(console, rest if rest.endswith("\n") else rest + "\n")
                    tell(f"\n  run ended ({state['outcome']}) — "
                         f"closing in {LINGER:.0f}s")
                    time.sleep(LINGER)
                    if close_window:
                        # Launched here rather than after `follow` returns so
                        # it is on the one path that means "the run ended" --
                        # a Ctrl-C or a dead log should leave the window up.
                        desktop.close_own_window()
                    return
            time.sleep(poll)
    except KeyboardInterrupt:
        pass
    finally:
        if handle is not None:
            handle.close()


def main(argv):
    if not argv:
        print("usage: uv run --group nb python -m nb watch <notebook> [run] "
              "[--all] [--until-done]")
        print("  --all           from the first line, not from now")
        print("  --until-done    stop once the run records an outcome")
        print("  --close-window  …and close the window this is running in")
        return 2
    notebook = Notebook(argv[0], run_id=argv[1] if len(argv) > 1
                        and not argv[1].startswith("--") else None)
    log = notebook.run / "status.log"
    # THE COORDINATOR NEVER WRITES AN `outcome`, so `--until-done` would wait
    # for one for ever -- it holds no lock and has no ending, by design (see
    # `process/coordinator.py`). Its log is still worth following: detached
    # behind `nb designer` the terminal belongs to the board, and this is the
    # only place its turns are visible. Said plainly rather than silently
    # ignored, because a flag that does nothing is worse than one refused.
    until_done = "--until-done" in argv
    if coordinator.is_coordinator(notebook.run_id) and until_done:
        tell("  --until-done does nothing for the coordinator: it records "
             "no outcome, having no process to end.")
        until_done = False
    tell(f"  watching   {log}"
         f"{'' if log.exists() else '  (waiting for a run to start)'}")
    # `--close-window` IS SEPARATE FROM `--until-done` and is passed only by
    # the spawner in `nb run`. Someone who types `nb watch --until-done` in a
    # terminal of their own wants the watcher to stop, not their window to
    # vanish underneath them.
    follow(log, from_start="--all" in argv, until_done=until_done,
           close_window="--close-window" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
