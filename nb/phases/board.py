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


def _runs(notebook, only=None):
    """
    Every run, newest first, with its state and whether it is alive.

    `only` narrows to one run id. `nb ask` attaches a board to the run it just
    started, and a board showing nine other runs there answers a question
    nobody asked -- the whole table is what `nb board` is for.
    """
    out = []
    for d in notebook.runs():
        if only and d.name != only:
            continue
        state = runstate.read(d)
        if not state:
            continue
        state["dir"] = d
        state["alive"] = runstate.alive(d)
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
    if q.get("default") is not None:
        # What Enter gets you, and what silence gets you. A question with a
        # default is not really asking you to decide -- it is offering you the
        # chance to disagree -- and it should look like it.
        body.append(f"[dim]Enter takes {q['default']}[/dim]")
    return Panel("\n".join(body), title=f"{run.get('chapter') or run['run']} asks",
                 border_style="yellow")


# What an ending looks like. `committed` is the one worth reading in full; the
# rest are told in a line, because what a reader needs from them is which one it
# was and where the work is.
ENDINGS = {
    "committed":              ("green",  "committed"),
    "committed_refactor":     ("green",  "committed, with an accepted refactor"),
    "no_entry":               ("yellow", "ended without opening an entry"),
    "lint_failed":            ("red",    "lint would not come clean"),
    "build_failed":           ("red",    "the page would not build"),
    "ceiling_changed":        ("red",    "the entry changed its granted ceiling"),
    "refactor_moved_answers": ("yellow", "a refactor moved sibling answers"),
    "chapter_locked":         ("yellow", "another run owns the chapter"),
    "already_written":        ("yellow", "the chapter already holds this question"),
    "max_turns":              ("red",    "out of turns"),
    "no_answer":              ("yellow", "a question went unanswered"),
    "stopped":                ("yellow", "stopped"),
    "commit_failed":          ("red",    "the commit failed"),
}


def _ending_panel(run):
    """
    How a run FINISHED, including what its entry concluded.

    THE POINT OF THE WHOLE SYSTEM WAS LANDING IN A LOG FILE. This drew a table
    from `run.json` and question panels from `question.json`, and never read
    `status.log` -- which is where `tell()` writes once a run detaches, and
    every run detaches. So the rendered entry, with its real numbers, was
    printed by the run into a file nothing displayed, and the README's promise
    that "the terminal carries the conversation -- the questions, the
    milestones, the finished entry" was true of the first two.

    It reads `run.json` rather than the log, because the run now records
    `answer` and `prose` there, off the freeze. So this needs no parsing, and
    a coordinator reads exactly the same fields.
    """
    from rich.panel import Panel
    outcome = run.get("outcome") or "died"
    colour, said = ENDINGS.get(outcome, ("red", "died without a word"))
    body = []
    answer = run.get("answer")
    prose = run.get("prose")
    if answer:
        body.append(f"[bold]{answer}[/bold]\n")
        # `_readable` already joins the hero pair into the prose, so showing
        # both puts the answer on screen twice. Dropped by VALUE, which is the
        # half the two spellings share -- the panel says "5.38 — Best L/D" and
        # the prose "5.38  Best L/D".
        value = answer.split("\u2014")[0].strip()
        if prose and value:
            prose = "\n".join(l for l in prose.splitlines()
                               if l.strip() != value and
                               not (l.strip().startswith(value) and
                                    len(l.strip()) < len(answer) + 4))
    if prose:
        import re
        body.append(re.sub(r"\n{3,}", "\n\n", prose).strip())
    for f in (run.get("findings") or [])[:6]:
        rule = f" [dim](rule {f['rule']})[/dim]" if f.get("rule") else ""
        body.append(f"  \u2022 {f.get('message', '')}{rule}")
    if run.get("failure"):
        body.append(run["failure"][:600])
    if not body:
        # The footer already says where the entry is, so repeating the stem
        # here fills a panel with the one thing beside it.
        body.append("[dim]nothing was recorded[/dim]")
    # WHERE THE WORK IS, under every ending that left some. A commit is found
    # by its sha; everything else left an entry on disk and the next question
    # is always where.
    sha = (run.get("committed") or {}).get("sha")
    foot = sha or (f"chapters/{run['chapter']}/{run['stem']}.qmd"
                   if run.get("stem") and run.get("chapter") else None)
    return Panel("\n".join(body), border_style=colour,
                 title=f"{run.get('chapter') or run['run']} \u2014 {said}",
                 subtitle=f"[dim]{foot}[/dim]" if foot else None)


def _ended(run):
    """A run that has stopped for good: it said so, or it is not alive."""
    return bool(run.get("outcome")) or run.get("alive") is False


def _seen_already(notebook, only):
    """
    Endings that predate this board, so it announces only what ends while it
    is watching.

    A whole-notebook board would otherwise open by printing a panel for every
    run that ever finished -- nine of them here. `_runs` keeps finished runs
    for context and caps them, which is right for a table and wrong for a panel
    each.

    EMPTY WHEN FOLLOWING ONE RUN. `nb ask` forks the board before the child has
    written an outcome, so this is normally empty anyway -- but a run that dies
    in its first second would be pre-seeded as already-seen and the board would
    exit having shown nothing at all. Both entry points take this, which they
    did not when the rule lived in one of them: the piped path fell through to
    `_follow_plain` and went silent.
    """
    if only:
        return set()
    return {r["run"] for r in _runs(notebook, only) if _ended(r)}


def follow(notebook, only=None):
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
        return _follow_plain(notebook, console, only)

    # TRANSIENT. The table is the current state, not a record of it: left
    # behind, every question pushes another copy of it into the scrollback and
    # the history becomes unreadable at exactly the point there are enough
    # agents to need it. Erased on stop, the scrollback holds the CONVERSATION
    # -- each question, each answer, in order -- and the table lives at the
    # bottom of the screen where it belongs.
    answered = set()          # (run, asked_at) -- see `_asking`
    shown = _seen_already(notebook, only)
    with Live(console=console, refresh_per_second=4, transient=True) as live:
        try:
            while True:
                runs = _runs(notebook, only)
                asking = _asking(runs, answered)
                live.update(_table(runs), refresh=True)

                # ENDINGS, once each. Stopped before printing for the same
                # reason the question panel is: a panel written under a live
                # region is overdrawn by the next refresh.
                for r in runs:
                    if _ended(r) and r["run"] not in shown:
                        shown.add(r["run"])
                        live.stop()
                        console.print(_ending_panel(r))
                        live.start()
                # A board attached to ONE run leaves when that run does. It
                # used to spin on a table of a finished run until somebody
                # pressed Ctrl-C -- and `nb ask` forks this as the parent, so
                # that was every run.
                if only and runs and all(_ended(r) for r in runs):
                    live.stop()
                    return 0

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
                    asked_at = run["question"].get("asked_at")
                    answered.add((run["run"], asked_at))
                    # Stamped with the question ON SCREEN, not with whatever is
                    # on disk by the time the write lands -- the run may have
                    # moved on while the reply was being typed, and that is the
                    # case `replying_to` exists for.
                    mailbox.answer(Notebook(notebook.root, run_id=run["run"]),
                                   reply, replying_to=asked_at)
                    # The permanent record of what you said, since the panel
                    # above it is permanent too and an answer without its
                    # question is no use when you scroll back.
                    console.print(f"  [grey50]{run['run']} ←[/grey50] {reply}\n")
                    live.start()
                    continue

                time.sleep(REFRESH)
        except KeyboardInterrupt:
            return 0


def _follow_plain(notebook, console, only=None):
    """No cursor to steer: print the table only when a row changes."""
    last, shown = None, _seen_already(notebook, only)
    try:
        while True:
            runs = _runs(notebook, only)
            key = [(r.get("run"), r.get("phase"), r.get("turn"),
                    r.get("outcome"), bool(r.get("question"))) for r in runs]
            for r in runs:
                if _ended(r) and r["run"] not in shown:
                    shown.add(r["run"])
                    console.print(_ending_panel(r))
            if only and runs and all(_ended(r) for r in runs):
                return 0
            if key != last:
                console.print(_table(runs))
                for r in _asking(runs):
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
             f'"<question>"')
        return 1
    return follow(notebook)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
