"""
`nb board` -- N agents, one terminal.

A VIEW, not a supervisor. It owns no agent: it reads each run's `run.json` and
`status.log`, and answers a pending question by writing `answer.json`. Kill it
mid-question and the agent is still waiting; restart it and the question is
still there; answer from another terminal with `nb answer` and this one need not
be running at all. That independence is the whole design — it is what lets a
coordinator agent replace the person here without the agents changing.

`rich` does the rendering. The hand-rolled alternative was tried in `watch.py`
and shipped a bug nobody could see: `\\x1b[2m` is correct and macOS Terminal.app
ignores it, so the dimming simply never appeared. A library that asks the
terminal what it supports is worth one dependency.

What it does NOT touch is `status.log`, which stays plain text. `tail`, `grep`,
this board and a coordinator all read the same file, and the writer/reader split
the telemetry rests on depends on it staying unstyled.

Testing note: `rich` strips styling when stdout is not a terminal, but honours
`FORCE_COLOR` above its own detection. Some harnesses set it, so a pipe test can
appear to fail when the library is behaving correctly -- clear the variable
before concluding anything.
"""

import sys
import time

from ..config import Notebook
from ..log import tell
from .. import mailbox, runstate

REFRESH = 0.5
SHOWN = 10         # rows: live runs always, then the most recent finished ones


def _runs(notebook):
    """Every run, newest first, with its state and whether it is alive."""
    out = []
    for d in notebook.runs():
        state = runstate.read(d)
        if not state:
            continue
        state["dir"] = d
        state["alive"] = runstate.alive(state)
        state["stopped"] = runstate.stopped(state) if state["alive"] else False
        state["question"] = mailbox.pending(d)
        out.append(state)
    # Live runs first, whatever their age -- a board that scrolls a waiting
    # agent off the bottom because six finished ones are newer would hide the
    # one thing it exists to show. Finished runs are kept for context and
    # capped, since every run ever is not context.
    live = [r for r in out if r["alive"] is not False]
    done = [r for r in out if r["alive"] is False]
    return live + done[:max(0, SHOWN - len(live))]


def _ago(seconds):
    return f"{seconds / 60:.0f}m" if seconds >= 60 else f"{seconds:.0f}s"


def _asking(runs, answered=()):
    """
    The runs actually waiting on an answer -- LIVE ones only, not yet answered.

    A question file outlives the process that wrote it: the run deletes it when
    it reads the answer, so a run that died mid-question leaves one behind
    forever. Prompting for that never ends -- answering writes a file nothing
    will ever read, the question is still there on the next pass, and the board
    asks again -- and the answer is silently addressed to a corpse.
    """
    out = []
    for r in runs:
        q = r.get("question")
        if not q or r["alive"] is False:
            continue
        # A question is deleted by the RUN, when it reads the answer -- a
        # second later, at its poll interval. The board loops twice in that
        # time, so the file it just answered is still sitting there and it
        # asked again. Both answers were written, and the second one is the
        # dangerous half: land it after the run has posed its NEXT question and
        # it is consumed as the answer to that one instead.
        if (r["run"], q.get("asked_at")) in answered:
            continue
        out.append(r)
    return out


def _table(runs):
    from rich.table import Table
    t = Table(box=None, pad_edge=False, expand=True)
    for col, style, justify in (("run", "grey50", "left"),
                                ("chapter", "", "left"),
                                ("phase", "", "left"),
                                ("turn", "", "right"),
                                ("for", "grey50", "right"),
                                ("waited", "grey50", "right"),
                                ("state", "", "left")):
        t.add_column(col, style=style or None, justify=justify)
    for r in runs:
        if r["alive"] is False:
            # `outcome` is written by metrics.close(), so its absence means the
            # run never reached an ending the system chose: it crashed, was
            # killed, or the machine slept through its deadline. That is the one
            # state worth a colour, and it used to be indistinguishable from a
            # clean commit.
            out = r.get("outcome")
            state = (f"[dim]{out}[/dim]" if out else "[red]died[/red]")
        elif r.get("stopped"):
            # Suspended, not working. `os.kill(pid, 0)` cannot tell the
            # difference, so this used to read `running` while the process
            # burned no CPU at all -- and the `for` column kept counting up,
            # which looks exactly like a wedged run.
            state = "[magenta]stopped[/magenta]"
        elif r.get("question"):
            state = "[bold yellow]waiting[/bold yellow]"
        else:
            state = "[green]running[/green]"
        since = time.time() - (r.get("updated") or r.get("started") or time.time())
        # `for` is time since the run last did ANYTHING; `waited` is time since
        # the question was put. They are usually the same number while a run is
        # blocked, and they stop being the same the moment they matter: a run
        # that answered one question and is now asking another shows a fresh
        # `waited` against a long `for`. The question carries its own asked_at,
        # so this is the real figure rather than an inference from the last
        # state write.
        q = r.get("question") or {}
        asked = q.get("asked_at")
        t.add_row(r.get("run", "?"), r.get("chapter") or "—",
                  r.get("phase", "?"), str(r.get("turn", "")),
                  _ago(since), _ago(time.time() - asked) if asked else "",
                  state)
    return t


def _question_panel(run):
    from rich.panel import Panel
    q = run["question"]
    body = [f"[bold]{q.get('name','')}[/bold]"]
    if q.get("why"):
        body.append(q["why"])
    if q.get("options"):
        body.append(f"options: {q['options']}")
    return Panel("\n".join(body), title=f"{run.get('chapter') or run['run']} asks",
                 border_style="yellow")


def follow(notebook):
    """Draw the table, surface questions, and take answers. Ctrl-C to leave."""
    from rich.console import Console
    from rich.live import Live

    console = Console()
    if not console.is_terminal:
        # A Live region needs a cursor to move. Piped or redirected there is
        # none, so every refresh prints the whole table again and the output
        # grows by a table a second. Fall back to printing only when something
        # actually changes -- useful for a log, and it cannot scroll the thing
        # you are reading off the top.
        return _follow_plain(notebook, console)

    # TRANSIENT. The table is the current state, not a record of it: left
    # behind, every question pushes another copy of it into the scrollback and
    # the history becomes unreadable at exactly the point there are enough
    # agents to need it. Erased on stop, the scrollback holds the CONVERSATION
    # -- each question, each answer, in order -- and the table lives at the
    # bottom of the screen where it belongs.
    answered = set()          # (run, asked_at) -- see `_asking`
    with Live(console=console, refresh_per_second=4, transient=True) as live:
        try:
            while True:
                runs = _runs(notebook)
                asking = _asking(runs, answered)
                live.update(_table(runs), refresh=True)

                if asking:
                    run = asking[0]
                    # Stop first (which erases the table), THEN print. The panel
                    # is written at a clean cursor with nothing live below it,
                    # so it cannot be overdrawn -- which is what happened when
                    # the display was restarted over the top of it.
                    live.stop()
                    console.print(_question_panel(run))
                    try:
                        reply = console.input(f"  [{len(asking)} waiting] > ")
                    except (EOFError, KeyboardInterrupt):
                        console.print("  left unanswered")
                        return 0
                    answered.add((run["run"], run["question"].get("asked_at")))
                    mailbox.answer(Notebook(notebook.root, run_id=run["run"]),
                                   reply)
                    # The permanent record of what you said, since the panel
                    # above it is permanent too and an answer without its
                    # question is no use when you scroll back.
                    console.print(f"  [grey50]{run['run']} ←[/grey50] {reply}\n")
                    live.start()
                    continue

                time.sleep(REFRESH)
        except KeyboardInterrupt:
            return 0


def _follow_plain(notebook, console):
    """No cursor to steer: print the table only when a row changes."""
    last = None
    try:
        while True:
            runs = _runs(notebook)
            key = [(r.get("run"), r.get("phase"), r.get("turn"),
                    r.get("outcome"), bool(r.get("question"))) for r in runs]
            if key != last:
                console.print(_table(runs))
                for r in _asking(runs):
                    if True:
                        console.print(_question_panel(r))
                        console.print(
                            f"  answer with: nb answer {notebook.root.name} "
                            f"{r['run']} \"<value>\"")
                last = key
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        return 0


def main(argv):
    if not argv:
        tell("usage: uv run --group nb python -m nb board <notebook>")
        return 2
    notebook = Notebook(argv[0])
    try:
        import rich  # noqa: F401
    except ImportError:
        tell("  `nb board` needs rich: uv sync --group nb")
        return 1
    runs = _runs(notebook)
    if not runs:
        tell(f"  no runs yet under {notebook.scratch / 'runs'}")
        tell(f"  start one with: python -m nb ask {notebook.root.name} "
             f'"<question>" --detach')
        return 1
    return follow(notebook)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
