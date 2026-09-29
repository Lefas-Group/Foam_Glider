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
    "coordinator — died without a word". It has no process to stop, which is
    the whole point of the reserved id, so the honest answer here is no.
    """
    if coordinator.is_coordinator(run.get("run")):
        return False
    return bool(run.get("outcome")) or run.get("alive") is False


HISTORY = 200


def _stamp(at):
    return time.strftime("%H:%M", time.localtime(at or 0))


# Left is the agents, centre is the coordinator, right is you. Placing a box
# by its AUTHOR turns a flat log into a conversation you can follow by shape
# alone -- which side a box sits on says who spoke before a word is read.
AGENT, COORD, USER = "left", "center", "right"
# And a colour each, so the side and the hue say the same thing. An agent's
# box keeps the colour of its OUTCOME -- green committed, red failed -- which
# is information the other two do not have to carry.
COORD_COLOUR, USER_COLOUR = "grey50", "cyan"


def _place(console, panel, side):
    """Put a panel on its author's side, at a width that leaves the gap visible."""
    from rich.align import Align
    panel.width = max(46, int(console.width * 0.78))
    return Align(panel, side)


def _panel(author, context, body, colour, at=None):
    """
    One conversation event, in a box titled by WHO SENT IT.

    THE AUTHOR IS THE FIRST THING ON THE BOX, in bold and in that author's
    colour. Titles used to open with the chapter, so an answer you typed and
    an entry an agent committed began with the same words in the same green
    and could only be told apart by reading to the end -- where the sender was
    spelled out on a line of its own, under a blank one. Two lines per box to
    say something the title can carry for nothing.
    """
    from rich.markup import escape
    from rich.panel import Panel
    from rich.text import Text
    from rich import box as _box
    title = Text(str(author), style=f"bold {colour}")
    tail = "  ·  ".join(x for x in (context, _stamp(at) if at else "") if x)
    if tail:
        title.append(f"  ·  {tail}", style="grey50")
    return Panel(escape(str(body)), title=title, title_align="left",
                 border_style=colour, box=_box.ROUNDED, padding=(0, 1))


def _note_panel(note):
    """A decision by the coordinator: why the next question is the next one."""
    return _panel("coordinator", "", note.get("text", ""), COORD_COLOUR,
                  note.get("at"))


def _ask_panel(run):
    """
    The question the coordinator put to one agent.

    NOTHING NEW IS CAPTURED HERE. `run.json` has carried `question` and
    `started` since the registry existed; the conversation simply never read
    them, so the board could show a programme's worth of answers with no
    record of what had been asked.
    """
    return _panel("coordinator",
                  f"asked {run.get('chapter') or run.get('run', '?')}",
                  run.get("asked") or "", COORD_COLOUR, run.get("started"))


# What each kind of gate is asking, for records written before the question
# carried its own `prompt`. Not a second copy of the wording in `interact.py`:
# that one is what the agent puts to a person live, this one is what a reader
# of the history needs to understand a decision already taken.
WAS_ASKED = {
    "assumptions": "Are these assumptions sound?",
    "inherited":   "Does this fork break any of these?",
    "chapter":     "Create a new chapter for this?",
    "refactor":    "Allow this change?",
    "stuck":       "No progress — carry on?",
    "budget":      "How long may it run?",
}


def _gate_panel(run, got):
    """
    The agent's question, as it was put, beside the answer it got.

    HALF THE CONVERSATION WAS MISSING. The board showed every answer and no
    question: `you · _analysis.py · allowed — alpha_max defaults to None` with
    nothing saying what had been proposed, or which assumptions were being
    confirmed, or what chapter was being asked for. `_record` has kept the
    question's `why` all along and now keeps its `prompt` too, so the box that
    prompted a decision can sit next to it.
    """
    body = (got.get("prompt")
            or WAS_ASKED.get(got.get("kind"))
            or f"What is the {got.get('name', '')}?")
    why = (got.get("why") or "").strip()
    if why and why != body:
        body = f"{body}\n\n{why}"
    # The clock on the QUESTION is when it was put, not when it was answered.
    return _panel(run.get("chapter") or run.get("run", "?"),
                  got.get("name", ""), body, "yellow",
                  got.get("asked_at") or got.get("at"))


def _qa_panel(run, got, replay=False):
    """
    One exchange, titled by whoever answered it.

    THE RECORD IS `run.json`, NOT THIS PROCESS. The board used to print an
    answer only when it had collected the answer itself, so everything settled
    by `--answers`, by `nb answer` from another terminal, or by a coordinator
    -- which is now most of them -- happened invisibly: `inherited` was asked
    and answered and the board showed neither. `_record` has been appending
    every question and its answer, with the source, to `run.json` all along.
    """
    where = run.get("chapter") or run.get("run", "?")
    value = (got.get("value") or "").strip()
    # REPLAYED ANSWERS ARE CAPPED. A reply can be a paragraph -- refusing a
    # fork and saying why, correcting an assumption with the reasoning -- which
    # is right to see as you type it and is history you have already read when
    # the board reopens. The whole of it stays in `run.json`.
    if replay and len(value) > 220:
        value = value[:220].rstrip() + " \u2026"
    src = got.get("source", "")
    mine = src == "user"
    # A BLANK IS AN ANSWER, and the most common one: "" accepts an assumption
    # and keeps every inherited item. Printed raw it looked like the board had
    # failed to record anything.
    # THE CHAPTER IS ON THE QUESTION, not repeated here. The gate box directly
    # above names it; saying it again pushed the source and the clock off the
    # end of the title and into the border.
    del where
    return _panel("you" if mine else "coordinator",
                  got.get("name", "")
                  + ("" if mine or src in ("", "user") else f"  \u00b7  {src}"),
                  value or "accepted as stated",
                  USER_COLOUR if mine else COORD_COLOUR, got.get("at"))


def _ending_line(run):
    """
    How a run finished, for replay: the box without the entry inside it.

    AN ENDING IS NEWS ONCE. The full panel carries the entry's prose, its
    figure and its budgets -- right for something that finishes while you are
    watching, and 33 lines apiece when six of them are replayed into a screen
    you just opened. Measured: two endings were 36 of 73 history lines.
    """
    colour, word = ENDINGS.get(run.get("outcome") or "",
                               ("red", run.get("outcome") or "died"))
    sha = (run.get("committed") or {}).get("sha")
    # THE COLOUR ALREADY SAYS `committed`. Spelling it out as well pushed the
    # title past the width of the box and the last characters of the timestamp
    # were eaten by the border. An ending that is NOT a commit still says so,
    # because that is the case where the word carries something green does not.
    context = "  ·  ".join(
        x for x in (word if run.get("outcome") != "committed" else "", sha) if x)
    return _panel(run.get("chapter") or run.get("run", "?"), context,
                  run.get("answer") or word, colour, run.get("updated"))


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
        for note in coordinator.notes(notebook):
            kind = "direction" if note.get("kind") == "direction" else "note"
            out.append((note.get("at", 0), kind, note,
                        (kind, note.get("at", 0))))
    for r in _runs(notebook, only, cap=False):
        if r.get("asked") and r.get("started"):
            out.append((r.get("started", 0), "ask", r, ("ask", r.get("run"))))
        for got in r.get("answered") or []:
            # TWO EVENTS PER EXCHANGE, each at its own time: the agent asked
            # at `asked_at` and was answered at `at`, and those can be minutes
            # apart with the coordinator's notes written in between. Records
            # made before `asked_at` existed fall back to an instant before the
            # answer, which is where they used to sit anyway.
            out.append((got.get("asked_at") or got.get("at", 0) - 1e-3,
                        "gate", (r, got),
                        ("gate", r.get("run"), got.get("at"), got.get("name"))))
            out.append((got.get("at", 0), "qa", (r, got),
                        ("qa", r.get("run"), got.get("at"), got.get("name"))))
        if _ended(r):
            # `committed.at` is an ISO string for people to read; `updated` is
            # the float this has to sort by.
            out.append((r.get("updated") or 0, "end", r, ("end", r.get("run"))))
    out.sort(key=lambda e: e[0])
    # ONE DECISION, ONE BOX. An escalation is recorded twice by design: once
    # against the coordinator, where the person actually answered it, and again
    # against the run when it is relayed there -- 17 seconds apart, same name,
    # same value, and indistinguishable to a reader. The RUN's copy is the one
    # kept: it names the chapter the answer was used in, which is what anyone
    # reading the programme back wants to know. The coordinator's survives
    # only when no relay followed it, which is the case where it is the whole
    # record of what was decided.
    relayed = {(g.get("name"), (g.get("value") or "").strip())
               for at, k, pay, _key in out
               if k == "qa" and not coordinator.is_coordinator(pay[0].get("run"))
               for g in [pay[1]]}
    out = [e for e in out
           if not (e[1] in ("qa", "gate")
                   and coordinator.is_coordinator(e[2][0].get("run"))
                   and (e[2][1].get("name"),
                        (e[2][1].get("value") or "").strip()) in relayed)]
    # STRICTLY AFTER: the epoch direction itself is pinned above the table, so
    # printing it into the scrollback as well would say it twice. A direction
    # that arrives LATER is an event like any other -- it marks the pivot in
    # the narrative, and becomes the epoch for the next board.
    kept = [e for e in out if e[0] > epoch]
    return kept, len(out) - len(kept)


def _print_event(console, kind, payload, replay=False):
    """
    One conversation event, in the form its kind deserves.

    `replay` is the history being redrawn on open, where an ending is its
    headline rather than the whole entry -- see `_ending_line`.
    """
    if kind == "note":
        console.print(_place(console, _note_panel(payload), COORD))
    elif kind == "direction":
        console.print(_direction_panel(payload))
    elif kind == "ask":
        # The coordinator's question, not the agent's: it chose what to ask.
        console.print(_place(console, _ask_panel(payload), COORD))
    elif kind == "gate":
        console.print(_place(console, _gate_panel(*payload), AGENT))
    elif kind == "qa":
        # Placed by WHO ANSWERED. The question came from an agent; the answer
        # is the person's when they typed it and the coordinator's when it came
        # from `--answers` or from a default nobody overrode.
        side = USER if payload[1].get("source") == "user" else COORD
        console.print(_place(console, _qa_panel(*payload, replay=replay), side))
    elif replay:
        console.print(_place(console, _ending_line(payload), AGENT))
    else:
        console.print(_place(console, _ending_panel(payload), AGENT))


def follow(notebook, only=None, answer_all=False):
    """
    The conversation, printed as it happens. Ctrl-C to leave.

    NO LIVE REGION, AND NO TABLE. Both are gone, and the reasons they went are
    worth keeping. The table showed what each run was doing right now, redrawn
    four times a second; pinned under a growing conversation it fought the
    terminal's own scrollback -- scrolling up to read what happened snapped you
    back to the bottom on the next refresh -- and most of its rows were runs
    that had already finished and already said so above. The direction was
    pinned for the same reason and cost the same thing.

    What is left is a log: the direction, then every question, answer, decision
    and ending in the order they happened, each in its own box. It scrolls like
    any other program's output, which means the terminal you already have is
    the history control. `nb watch` is still there for a single run's detail.

    The cost, stated: between events nothing moves. A run thinking for four
    minutes looks the same as a run that has died, and the table used to tell
    those apart by its turn counter. `nb board` is the CONVERSATION now; the
    liveness question belongs to `nb watch <nb> <run>`.
    """
    from rich.console import Console

    console = Console()
    interactive = console.is_terminal
    coordinated = _coordinated(notebook) and not answer_all
    answered, seen, echoed, told = set(), set(), set(), set()
    shown_q = set()           # questions printed live -- see the loop below

    past, behind = _events(notebook, only)
    if behind:
        console.print(f"  [grey50]\u2026 {behind} events under an earlier "
                      f"direction, not replayed[/grey50]")
    # THE DIRECTION FIRST, once, at the top of the scrollback. Everything under
    # it was chosen to serve it, so it reads as the head of the conversation
    # rather than a caption that has to be kept on screen.
    current = None if only else coordinator.current_direction(notebook)
    if current:
        console.print(_direction_panel(current))
    if len(past) > HISTORY:
        console.print(f"  [grey50]\u2026 {len(past) - HISTORY} earlier events "
                      f"not shown[/grey50]")
        past = past[-HISTORY:]
    for _at, kind, payload, key in past:
        seen.add(key)
        _print_event(console, kind, payload, replay=True)

    try:
        while True:
            runs = _runs(notebook, only)
            for _at, kind, payload, key in _events(notebook, only)[0]:
                if key in seen:
                    continue
                seen.add(key)
                if kind == "gate":
                    r, got = payload
                    # Shown live a moment ago as a pending question; the record
                    # would print it again the instant it is answered.
                    if (r.get("run"), got.get("name")) in shown_q:
                        shown_q.discard((r.get("run"), got.get("name")))
                        continue
                if kind == "qa":
                    r, got = payload
                    sig = (r.get("run"), got.get("name"),
                           (got.get("value") or "").strip())
                    # ECHOED WHEN TYPED, RECORDED A MOMENT LATER. The two
                    # halves cannot share a key -- the record is stamped when
                    # it lands and the echo cannot know that time -- so they
                    # are matched on who was asked, what, and the reply.
                    if sig in echoed:
                        echoed.discard(sig)
                        continue
                _print_event(console, kind, payload)

            if bool(only) and runs and all(_ended(r) for r in runs):
                return 0

            asking = _asking(runs, answered, coordinated)
            if coordinated:
                # SAY WHEN A QUESTION IS NOT YOURS, once each. Deferring run
                # questions to the coordinator is right; doing it silently is
                # the failure this mailbox exists to prevent -- a run waits,
                # nobody here realises they could answer it, the coordinator
                # turns out not to be running, and the question expires.
                for r in _asking(runs):
                    if coordinator.is_coordinator(r["run"]):
                        continue
                    key = (r["run"], (r.get("question") or {}).get("asked_at"))
                    if key in told:
                        continue
                    told.add(key)
                    # THE QUESTION ITSELF, not a note that one exists. It is
                    # the coordinator's to answer, but watching the programme
                    # means seeing what the agents are stuck on.
                    console.print(_place(console, _question_panel(r), AGENT))
                    shown_q.add((r["run"], (r.get("question") or {}).get("name")))
                    console.print(
                        f"  [grey50]for the coordinator \u2014 `--all` to "
                        f"answer it here[/grey50]")

            if asking and interactive:
                run = asking[0]
                console.print(_place(console, _question_panel(run), AGENT))
                shown_q.add((run["run"], run["question"].get("name")))
                try:
                    reply = console.input(f"  [{len(asking)} waiting] > ")
                except (EOFError, KeyboardInterrupt):
                    console.print("  left unanswered")
                    return 0
                asked_at = run["question"].get("asked_at")
                answered.add((run["run"], asked_at))
                echoed.add((run["run"], run["question"].get("name"),
                            reply.strip()))
                # Stamped with the question ON SCREEN, not with whatever is on
                # disk by the time the write lands -- the run may have moved on
                # while the reply was being typed, and that is the case
                # `replying_to` exists for.
                mailbox.answer(Notebook(notebook.root, run_id=run["run"]),
                               reply, replying_to=asked_at)
                console.print(f"  [grey50]{run['run']} \u2190[/grey50] {reply}\n")
                continue
            elif asking:
                # Piped or redirected: say what is waiting and how to answer it
                # from a terminal, rather than blocking on a stdin that is not
                # a person.
                for r in asking:
                    key = ("piped", r["run"],
                           (r.get("question") or {}).get("asked_at"))
                    if key in told:
                        continue
                    told.add(key)
                    console.print(_question_panel(r))
                    console.print(f"  answer with: nb answer "
                                  f"{notebook.root.name} {r['run']} \"<value>\"")

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
