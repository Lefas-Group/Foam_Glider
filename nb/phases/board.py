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
        state["question"] = mailbox.pending(d)
        out.append(state)
    # Live runs first, whatever their age -- a board that scrolls a waiting
    # agent off the bottom because six finished ones are newer would hide the
    # one thing it exists to show. Finished runs are kept for context and
    # capped, since every run ever is not context.
    live = [r for r in out if r["alive"] is not False]
    done = [r for r in out if r["alive"] is False]
    return live + done[:max(0, SHOWN - len(live))]


def _table(runs):
    from rich.table import Table
    t = Table(box=None, pad_edge=False, expand=True)
    for col, style, justify in (("run", "grey50", "left"),
                                ("chapter", "", "left"),
                                ("phase", "", "left"),
                                ("turn", "", "right"),
                                ("for", "grey50", "right"),
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
        elif r.get("question"):
            state = "[bold yellow]waiting[/bold yellow]"
        else:
            state = "[green]running[/green]"
        since = time.time() - (r.get("updated") or r.get("started") or time.time())
        t.add_row(r.get("run", "?"), r.get("chapter") or "—",
                  r.get("phase", "?"), str(r.get("turn", "")),
                  f"{since / 60:.0f}m" if since >= 60 else f"{since:.0f}s",
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
    with Live(console=console, refresh_per_second=4, transient=False) as live:
        try:
            while True:
                runs = _runs(notebook)
                asking = [r for r in runs if r.get("question")]

                # The panel is part of the LIVE RENDERABLE, not printed beneath
                # it. Printing it separately and then restarting the display put
                # the table's region over the panel's body, so every question
                # arrived showing its title and nothing else -- you answered
                # `PROBE TIME POOL` without seeing the units, the default or the
                # options. Inside the group it is drawn by the same refresh that
                # draws the table, and cannot be overdrawn by it.
                group = _table(runs)
                if asking:
                    from rich.console import Group
                    group = Group(group, "", _question_panel(asking[0]))
                live.update(group, refresh=True)

                if asking:
                    # Park the display before prompting: a refreshing region
                    # repaints over the line being typed into. `transient=False`
                    # leaves the table and panel on screen while input is taken.
                    run = asking[0]
                    live.stop()
                    try:
                        reply = console.input(
                            f"  [{len(asking)} waiting] > ")
                    except (EOFError, KeyboardInterrupt):
                        console.print("  left unanswered")
                        return 0
                    mailbox.answer(Notebook(notebook.root, run_id=run["run"]),
                                   reply)
                    live.start()
                    continue

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
