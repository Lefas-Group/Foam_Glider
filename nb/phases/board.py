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
from .. import coordinator, mailbox, runstate

REFRESH = 0.5
SHOWN = 10         # rows: live runs always, then the most recent finished ones


def _runs(notebook, only=None, cap=True):
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
        # TWO DIFFERENT QUESTIONS, and this line used to lose one of them.
        # `run.json`'s `question` is the DESIGN question the coordinator put to
        # the agent, written once at `nb ask` and kept for the life of the run;
        # `mailbox.pending` is whatever that agent is blocked on right NOW, and
        # is None for every run that is not waiting. Overwriting one with the
        # other left the conversation unable to show what any finished run had
        # been asked -- the asks silently numbered zero.
        state["asked"] = state.get("question")
        state["question"] = mailbox.pending(d)
        out.append(state)
    # Live runs first, whatever their age -- a board that scrolls a waiting
    # agent off the bottom because six finished ones are newer would hide the
    # one thing it exists to show. Finished runs are kept for context and
    # capped, since every run ever is not context.
    if not cap:
        # THE HISTORY WANTS EVERY RUN. The cap below is a TABLE rule -- ten
        # rows is what fits on a screen -- and applying it to the conversation
        # silently truncated the record instead of the view.
        return out
    live = [r for r in out if r["alive"] is not False]
    done = [r for r in out if r["alive"] is False]
    return live + done[:max(0, SHOWN - len(live))]


def _ago(seconds):
    return f"{seconds / 60:.0f}m" if seconds >= 60 else f"{seconds:.0f}s"


def _coordinated(notebook):
    """
    True when a coordinator holds this notebook's programme.

    Declared by the reserved directory EXISTING, not by a timer. Liveness was
    the wrong question to ask about something with no process between turns --
    `coordinator.py` says why -- and a freshness heuristic would put the board
    back in the business of guessing, which is what the flock replaced.
    """
    return coordinator.mailbox_for(notebook).run.is_dir()


def _asking(runs, answered=(), coordinated=False):
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
        if not q:
            continue
        # A RUN's question dies with the run, because a run is one process
        # suspended mid-conversation and an answer written after it exits has
        # no reader. The COORDINATOR has no process between turns at all: its
        # `answer.json` is picked up by a later turn, so the corpse this test
        # exists to protect against cannot occur. Skipping it here would hide
        # the one question on the board that only the human can settle.
        if r["alive"] is False and not coordinator.is_coordinator(r["run"]):
            continue
        # A question is deleted by the RUN, when it reads the answer -- a
        # second later, at its poll interval. The board loops twice in that
        # time, so the file it just answered is still sitting there and it
        # asked again. Both answers were written, and the second one is the
        # dangerous half: land it after the run has posed its NEXT question and
        # it is consumed as the answer to that one instead.
        if (r["run"], q.get("asked_at")) in answered:
            continue
        # ONLY WHAT WAS ESCALATED. With a coordinator holding the programme,
        # every run question is ITS decision -- budgets, assumptions, inherited
        # items, refactors -- and it escalates to the reserved id the ones the
        # direction cannot settle. Prompting the person here for the rest
        # invited exactly the race that lost an answer once already: two
        # writers, one `answer.json`, last write wins and the record names the
        # wrong author. They stay VISIBLE in the table and the conversation;
        # they are simply not this terminal's to answer.
        if coordinated and not coordinator.is_coordinator(r["run"]):
            continue
        out.append(r)
    return out


def _table(runs):
    """
    One row per run. No `phase` column: there is one phase.

    It read `ask` or `write` when a question was two processes with a gate
    between them, and knowing which half you were in was most of knowing what
    was happening. A question is one conversation now, so the column said `run`
    on every row -- and `resume`, on the rare row that was one, which the `for`
    column already tells you by being older than the work.
    """
    from rich.table import Table
    t = Table(box=None, pad_edge=False, expand=True)
    for col, style, justify in (("run", "grey50", "left"),
                                ("chapter", "", "left"),
                                ("turn", "", "right"),
                                ("for", "grey50", "right"),
                                ("waited", "grey50", "right"),
                                ("state", "", "left")):
        t.add_column(col, style=style or None, justify=justify)
    for r in runs:
        if coordinator.is_coordinator(r["run"]):
            # Never `died`. It holds no lock by design, so the liveness test
            # below reads it as dead on every refresh -- which would print the
            # most alarming word on the board, permanently, against the row
            # driving everything else on it.
            state = ("[bold yellow]waiting[/bold yellow]" if r.get("question")
                     else "[cyan]coordinating[/cyan]")
        elif r.get("outcome"):
            # THE OUTCOME WINS OVER LIVENESS. `_ended` calls a run with an
            # outcome finished -- "it said so" -- and prints its ending panel,
            # but this branch asked whether the process had exited yet. For the
            # second or two between `metrics.close()` writing the outcome and
            # the process actually going, the conversation showed a committed
            # entry while the table underneath it still said `running`.
            state = f"[dim]{r['outcome']}[/dim]"
        elif r["alive"] is False:
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
                  str(r.get("turn", "")),
                  _ago(since), _ago(time.time() - asked) if asked else "",
                  state)
    return t


def _question_panel(run):
    from rich.panel import Panel
    from rich.markup import escape
    q = run["question"]
    # EVERY FIELD HERE IS DATA, and rich reads square brackets as style tags.
    # `inherited` labels each item `[specified]` or `[assumed]`, and the panel
    # ate both -- the list rendered as "1.  dihedral: 20 degrees", with the one
    # word saying whether it is a commitment or a guess silently dropped, in
    # the question that asks which of them a fork breaks. Escaped at the edge,
    # so the only markup left in the panel is the markup this function adds.
    # THE PROMPT ASKS; the name is the KEY. `name` is what `--answers` pops and
    # what `waiting_on` reports, and `ask_specified`'s docstring records why it
    # had to become the quantity rather than the banner -- but nothing took
    # over its display job, so this drew `assumptions` where a question
    # belonged and the how-to-reply block carried the framing instead. The
    # fallback keeps a question asked by the old code renderable.
    body = [f"[bold]{escape(q.get('prompt') or q.get('name',''))}[/bold]"]
    if q.get("why"):
        body.append(escape(q["why"]))
    if q.get("options"):
        body.append(f"options: {escape(str(q['options']))}")
    default = q.get("default")
    # What Enter gets you, and what silence gets you. A question with a default
    # is not really asking you to decide -- it is offering you the chance to
    # disagree -- and it should look like it.
    #
    # BLANK IS NOT A VALUE TO ANNOUNCE. `is not None` let the empty string
    # through, so `assumptions` and `inherited` -- the two kinds where "" IS
    # the acceptance -- both drew a dangling `Enter takes ` with nothing after
    # it, under a `why` that had already said "Enter accepts." in full words.
    # `str(...)` rather than a truth test so a real default of 0 survives.
    #
    # `how` SAYS IT BETTER when there is one: "Enter accepts · …" already
    # states what Enter does, so printing `Enter takes ''` under it was the
    # same sentence twice, the second time in a form that named no value.
    if q.get("how"):
        body.append(f"[dim]{escape(q['how'])}[/dim]")
    elif default is not None and str(default).strip():
        body.append(f"[dim]Enter takes {default}[/dim]")
    # The KEY in the title, beside the chapter. It is what you type into
    # `--answers` and what `nb answer` reports, so it has to stay visible --
    # and with a real question on the first line, "asks" was saying nothing.
    where = run.get("chapter") or run["run"]
    return Panel("\n".join(body), title=f"{escape(where)} · {escape(q.get('name',''))}",
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
    """
    A run that has stopped for good: it said so, or it is not alive.

    THE COORDINATOR NEVER ENDS. It holds no lock, so `alive` is False for it
    always, and it never writes an `outcome` -- which together satisfy both
    halves of this test and made the conversation open with a panel reading
    "coordinator — died without a word". `_table` had already learned this;
    the predicate had not, so every other reader of it was wrong in the same
    way. It has no process to stop, which is the whole point of the reserved
    id, so the honest answer here is simply no.
    """
    if coordinator.is_coordinator(run.get("run")):
        return False
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


# How many past exchanges a board replays on opening. The whole conversation
# is the point -- a programme you cannot read back is a programme you cannot
# check -- but a notebook accumulates runs for ever, and a board that opens by
# printing two thousand lines has buried the question it was opened to answer.
# What is dropped is SAID, rather than silently trimmed.
HISTORY = 200


def _qa_line(run, got, replay=False):
    """
    One exchange, whoever answered it.

    THE RECORD IS `run.json`, NOT THIS PROCESS. The board used to print an
    answer only when it had collected the answer itself, so everything settled
    by `--answers`, by `nb answer` from another terminal, or by a coordinator
    -- which is now most of them -- happened invisibly: `inherited` was asked
    and answered and the board showed neither. `_record` has been appending
    every question and its answer, with the source, to `run.json` all along.
    Reading that makes the board a view of the conversation rather than a log
    of its own half of it.
    """
    from rich.markup import escape
    when = time.strftime("%H:%M", time.localtime(got.get("at", 0)))
    where = run.get("chapter") or run.get("run", "?")
    value = (got.get("value") or "").strip()
    # A BLANK IS AN ANSWER, and the most common one: "" accepts an assumption
    # and keeps every inherited item. Printed raw it looked like the board had
    # failed to record anything.
    # REPLAYED ANSWERS ARE CAPPED. A reply can be a paragraph -- refusing a
    # fork and saying why, correcting an assumption with the reasoning -- which
    # is right to see as you type it and is history you have already read when
    # the board reopens. The whole of it stays in `run.json`.
    if replay and len(value) > 150:
        value = value[:150].rstrip() + " …"
    shown = escape(value) if value else "[italic]accepted as stated[/italic]"
    src = got.get("source", "")
    return (f"  [grey50]{when}[/grey50]  {escape(str(where))} · "
            f"[bold]{escape(str(got.get('name', '')))}[/bold]\n"
            f"         [grey50]\u2190[/grey50] {shown}  [grey50]({escape(src)})[/grey50]")


def _ask_line(run):
    """
    The question the coordinator put to one agent.

    NOTHING NEW IS CAPTURED HERE. `run.json` has carried `question` and
    `started` since the registry existed; the conversation simply never read
    them, so the board could show a programme's worth of answers with no
    record of what had been asked.
    """
    from rich.markup import escape
    when = time.strftime("%H:%M", time.localtime(run.get("started", 0)))
    where = run.get("chapter") or run.get("run", "?")
    return (f"  [grey50]{when}[/grey50]  [grey50]\u2192[/grey50] "
            f"{escape(str(where))}   {escape(str(run.get('asked') or ''))}")


def _direction_panel(got):
    """What the user asked for, pinned above the table."""
    from rich.markup import escape
    from rich.panel import Panel
    return Panel(escape(str(got.get("text", ""))), title="DIRECTION",
                 title_align="left", border_style="cyan")


def _events(notebook, only=None):
    """
    The conversation under the current direction, oldest first, and how many
    events an earlier direction has put behind us.

    Each event carries a KEY that identifies it across refreshes, so streaming
    can print what it has not printed before without re-printing what it has.
    """
    out = []
    # THE NEWEST DIRECTION BOUNDS THE CONVERSATION. Work done under a previous
    # one belongs to a previous programme: still on the record, not replayed
    # into a screen opened to watch this one. What is dropped is counted and
    # said, so nobody has to wonder whether the notebook is younger than it is.
    epoch = 0.0
    if not only:
        current = coordinator.current_direction(notebook)
        if current:
            epoch = current.get("at", 0.0)
    if not only:
        for note in coordinator.notes(notebook):
            kind = "direction" if note.get("kind") == "direction" else "note"
            out.append((note.get("at", 0), kind, note,
                        (kind, note.get("at", 0))))
    for r in _runs(notebook, only, cap=False):
        if r.get("asked") and r.get("started"):
            out.append((r.get("started", 0), "ask", r, ("ask", r.get("run"))))
        for got in r.get("answered") or []:
            out.append((got.get("at", 0), "qa", (r, got),
                        ("qa", r.get("run"), got.get("at"), got.get("name"))))
        if _ended(r):
            # `committed.at` is an ISO string for people to read; `updated` is
            # the float this has to sort by.
            out.append((r.get("updated") or 0, "end", r, ("end", r.get("run"))))
    out.sort(key=lambda e: e[0])
    # STRICTLY AFTER: the epoch direction itself is pinned above the table, so
    # printing it into the scrollback as well would say it twice. A direction
    # that arrives LATER is an event like any other -- it marks the pivot in
    # the narrative, and becomes the epoch for the next board.
    kept = [e for e in out if e[0] > epoch]
    return kept, len(out) - len(kept)


def _screen(notebook, runs, pinned, coordinated=False):
    """
    What stays on screen: the direction, then the table.

    PINNED rather than printed once. The direction is the frame every question
    below it is chosen to serve, so it is current state in the same sense the
    table is -- and a session long enough to need the reminder is exactly the
    session that has scrolled the top of the scrollback away.
    """
    from rich.console import Group
    parts = [] if pinned is None else [_direction_panel(pinned)]
    parts.append(_table(runs))
    # SAY WHEN A QUESTION IS NOT YOURS. Deferring run questions to the
    # coordinator is right, but done silently it is the failure this whole
    # mailbox exists to prevent: a run sits `waiting`, nobody at the board
    # realises they could answer it, the coordinator turns out not to be
    # running, and the question expires. Naming the count and the way to take
    # it back costs one line.
    if coordinated:
        held = [r for r in runs if r.get("question")
                and not coordinator.is_coordinator(r["run"])]
        if held:
            from rich.text import Text
            parts.append(Text(
                f"  {len(held)} waiting on the coordinator — "
                f"`nb board {notebook.root.name} --all` to answer here",
                style="grey50"))
    if len(parts) == 1:
        return parts[0]
    return Group(*parts)


def _ending_line(run):
    """
    How a run finished, in one line, for replay.

    AN ENDING IS NEWS ONCE. The full panel carries the entry's prose, its
    figure and its budgets -- right for something that finishes while you are
    watching, and 33 lines apiece when six of them are replayed into a screen
    you just opened. Measured: two endings were 36 of 73 history lines, which
    pushed the rest of the conversation off the top of a 50-line terminal and
    left the board looking like it had nothing to say.
    """
    from rich.markup import escape
    colour, word = ENDINGS.get(run.get("outcome") or "",
                               ("red", run.get("outcome") or "died"))
    when = time.strftime("%H:%M", time.localtime(run.get("updated", 0)))
    where = run.get("chapter") or run.get("run", "?")
    said = run.get("answer") or word
    sha = (run.get("committed") or {}).get("sha")
    return (f"  [grey50]{when}[/grey50]  [{colour}]\u25cf[/{colour}] "
            f"{escape(str(where))}   {escape(str(said))}"
            + (f"  [grey50]{sha}[/grey50]" if sha else ""))


def _print_event(console, kind, payload, replay=False):
    """
    One conversation event, in the form its kind deserves.

    `replay` is the history being redrawn on open, where an ending is a line
    rather than the whole entry -- see `_ending_line`.
    """
    if kind == "note":
        console.print(_note_line(payload))
    elif kind == "direction":
        console.print(_direction_panel(payload))
    elif kind == "ask":
        console.print(_ask_line(payload))
    elif kind == "qa":
        console.print(_qa_line(*payload, replay=replay))
    elif replay:
        console.print(_ending_line(payload))
    else:
        console.print(_ending_panel(payload))


def _note_line(note):
    """
    One decision from the coordinator, for the scrollback.

    NOT A PANEL and not a pane. A panel is for something that wants you or
    tells you an outcome; a note is narration, and bordering it would give it
    the same weight as the question it is explaining. A pane would be worse:
    this module keeps the conversation in the scrollback and the table at the
    bottom precisely so the order survives, and notes read as causes of the
    questions that follow them -- which is exactly what a separately scrolling
    pane destroys.
    """
    from rich.markup import escape
    when = time.strftime("%H:%M", time.localtime(note.get("at", 0)))
    return f"  [grey50]\u25c6 {when}[/grey50]  {escape(note.get('text', ''))}"


def follow(notebook, only=None, answer_all=False):
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
        return _follow_plain(notebook, console, only, answer_all)

    # TRANSIENT. The table is the current state, not a record of it: left
    # behind, every question pushes another copy of it into the scrollback and
    # the history becomes unreadable at exactly the point there are enough
    # agents to need it. Erased on stop, the scrollback holds the CONVERSATION
    # -- each question, each answer, in order -- and the table lives at the
    # bottom of the screen where it belongs.
    answered = set()          # (run, asked_at) -- see `_asking`
    coordinated = _coordinated(notebook) and not answer_all
    # THE CONVERSATION SO FAR, before the live region starts. This used to
    # begin at NOW: a board opened mid-programme showed an empty screen with a
    # table under it, and everything already asked and answered -- the record
    # of what the programme had decided -- was reachable only by reading JSON
    # by hand. Printed into the scrollback, so the terminal's own scroll is
    # the history control and this module needs no pager.
    seen = set()
    echoed = set()            # exchanges shown as they were typed -- see below
    past, behind = _events(notebook, only)
    if behind:
        console.print(f"  [grey50]\u2026 {behind} events under an earlier "
                      f"direction, not replayed[/grey50]")
    if len(past) > HISTORY:
        console.print(f"  [grey50]\u2026 {len(past) - HISTORY} earlier events "
                      f"not shown[/grey50]")
        past = past[-HISTORY:]
    for _at, kind, payload, key in past:
        seen.add(key)
        _print_event(console, kind, payload, replay=True)
    if past:
        console.print()
    with Live(console=console, refresh_per_second=4, transient=True) as live:
        try:
            while True:
                runs = _runs(notebook, only)
                asking = _asking(runs, answered, coordinated)
                pinned = (None if only
                          else coordinator.current_direction(notebook))
                live.update(_screen(notebook, runs, pinned, coordinated),
                            refresh=True)

                # ENDINGS, once each, printed with the live region STOPPED
                # and not restarted until they are all out. Restarting between
                # them redraws the table straight over the panel just written
                # -- the table appeared inside the entry, between the figure
                # caption and the panel's bottom border. The question panel
                # above already carries this lesson: "the panel is written at a
                # clean cursor with nothing live below it, so it cannot be
                # overdrawn -- which is what happened when the display was
                # restarted over the top of it."
                #
                # A board attached to ONE run also leaves when that run does,
                # so the restart is skipped entirely on the way out: it used to
                # spin on a table of a finished run until somebody pressed
                # Ctrl-C, and `nb ask` forks this as the parent, so that was
                # every run.
                fresh = [e for e in _events(notebook, only)[0]
                         if e[3] not in seen]
                leaving = bool(only) and runs and all(_ended(r) for r in runs)
                if fresh or leaving:
                    live.stop()
                    for _at, kind, payload, key in fresh:
                        seen.add(key)
                        if kind == "qa":
                            r, got = payload
                            sig = (r.get("run"), got.get("name"),
                                   (got.get("value") or "").strip())
                            if sig in echoed:
                                echoed.discard(sig)
                                continue
                        _print_event(console, kind, payload)
                    if leaving:
                        return 0
                    live.start()

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
                    # ECHOED NOW, RECORDED IN A MOMENT. The run writes this
                    # exchange into `run.json` a poll from now and `_events`
                    # would print it a second time; the two halves cannot share
                    # a key, because the record is stamped when it lands and
                    # the echo cannot know that time. They do share who was
                    # asked, what, and the reply -- enough to drop the
                    # duplicate once, and only once.
                    echoed.add((run["run"], run["question"].get("name"),
                                reply.strip()))
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


def _follow_plain(notebook, console, only=None, answer_all=False):
    """No cursor to steer: print the table only when a row changes."""
    last, shown = None, _seen_already(notebook, only)
    # The same rule as the interactive path: with a coordinator holding the
    # programme, only what it escalated is the person's to answer. Here it is
    # advice rather than a prompt, and advice to answer someone else's question
    # is still how two writers end up on one `answer.json`.
    coordinated = _coordinated(notebook) and not answer_all
    # Printed once rather than pinned: there is no cursor to hold a region in
    # place here, which is why this path exists at all.
    pinned = None if only else coordinator.current_direction(notebook)
    if pinned:
        console.print(_direction_panel(pinned))
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
                for r in _asking(runs, coordinated=coordinated):
                    console.print(_question_panel(r))
                    console.print(
                        f"  answer with: nb answer {notebook.root.name} "
                        f"{r['run']} \"<value>\"")
                last = key
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        return 0


def main(argv):
    if not argv or argv[0].startswith("--"):
        tell("usage: uv run --group nb python -m nb board <notebook> [--all]")
        tell("  --all   answer every waiting question, not only what a "
             "coordinator escalated")
        return 2
    notebook = Notebook(argv[0])
    # `--all` TAKES THE PROGRAMME BACK. The reserved directory is what says a
    # coordinator holds this notebook, and it is never removed -- so without
    # this, one coordinated session would leave the board unable to answer a
    # run question ever again, which is the opposite of the independence this
    # module exists for.
    answer_all = "--all" in argv
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
    return follow(notebook, answer_all=answer_all)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
