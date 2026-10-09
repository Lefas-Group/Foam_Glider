"""
What the coordinator reads before its first turn.

Same shape as `agent/prefix.py` and for the same reason: everything that does
not change during the session goes above everything that does, so the implicit
cache matches a growing byte prefix rather than being invalidated each turn.
The doctrine page is a committed file, not generated, for exactly the reason
`tools/api.py` gives about `aerosandbox-api.md` -- a prefix assembled
differently on each invocation never matches itself.

NO LOOKUP TOOL. `agent/prefix.py` carries two always-in-prefix references and
the rest behind `read_reference`; that split earns its place there because the
run has fourteen tools and a context shaped by probe output. Here the whole set
is ~2.7k tokens, so a lookup tool could only ever cost a turn to fetch what
could have been free -- and `tools/refs.py` is explicit that a page in the
prefix must be absent from the enum, never in both.

WHICH pages, though, does differ: setting an aircraft up and running a
programme need different halves, and `doctrine.py` owns that grouping so the
`nb doctrine` command hands Claude Code exactly what the prefix embeds.
"""

from ..process import coordinator
from ..domain import manifest

from . import doctrine

HEAD = """\
You are the COORDINATOR of an aircraft design programme in a Quarto lab
notebook called `nb`. You decide what to ask; background runs do the work and
publish it. You are talking to nobody -- there is no human in this
conversation. The user watches the BOARD, so `note` is how you are heard and
`escalate` is how you ask.

Work in tool calls, not in prose. A turn that only thinks has cost a turn.
"""

TAIL = """\
# How this session ends

Do what the direction asks, then call `finish` with a summary. If the direction
is open-ended, do a sensible amount and finish rather than running forever --
the user can always start you again, and a new session picks the programme up
from the manifest and the notes.

If you need something only the user can decide, `escalate` and `wait`. Never
guess at it, and never stop without saying why.
"""


NEW_AIRCRAFT = """\
# There is no notebook at `{name}` yet

So this session STARTS AN AIRCRAFT, and the order is forced:

1. `search` and `fetch` the manufacturer's pages. Read the figures off the
   page yourself -- search summaries get them wrong. `read_plan_page` if there
   is a plan sheet; page one is usually a specification table.
2. `source` what each page gave you, **and what it failed to give you**. An
   unknown you name is one the run declares; one you leave silent is one it
   invents and attributes.
3. `new` -- the brief, built from what you found. Published dimensions are
   `spec`. Things the geometry must produce are `target`. `assume` is for
   facts about the aeroplane, never instructions to the run.
4. Photographs: `search`, `fetch`, `read_image` every candidate, then
   `add_photo` the ones that give you DIFFERENT ANGLES.
5. `mask`, then `overlay` every single one and LOOK, then `reference` until
   it is clean.
6. `reconstruct` the first chapter.

You cannot `new` twice. Research first; the brief is not editable afterwards.
"""


def build(notebook, direction="", name=""):
    """The system instruction: doctrine, then this notebook as it stands."""
    # SETUP OR STEADY STATE decides which pages, and `doctrine.py` owns
    # that split so `nb doctrine` hands Claude Code the same grouping.
    who = "setup" if notebook is None else "coordinate"
    parts = [HEAD, doctrine.text(who)]
    if notebook is None:
        parts.append(NEW_AIRCRAFT.format(name=name or "the given directory"))
        if direction:
            parts.append(f"## What the user has asked for\n\n{direction}\n")
        parts.append(TAIL)
        return "\n".join(parts)

    current = coordinator.current_direction(notebook) or {}
    notes = coordinator.notes(notebook)[-12:]
    parts.append(f"# This notebook\n\n`{notebook.root.name}`\n")

    # THE DIRECTION IN FORCE, which is the epoch of the programme rather than a
    # caption: work done under a previous one stays on the record and is not
    # replayed. A new session with a new direction records it and starts there.
    if direction:
        parts.append(f"## What the user has asked for NOW\n\n{direction}\n\n"
                     "Record this with `direction` before your first `ask`.\n")
    elif current.get("text"):
        parts.append(f"## The direction in force\n\n{current['text']}\n")

    # COLD START IS THE NORMAL CASE. The coordinator has no process between
    # sessions and no transcript worth resuming, so continuity comes from the
    # manifest and its own notes -- the same substitute for memory the runs
    # have always used. `domain/manifest.py` says why.
    parts.append("## The chapters, and every entry so far\n\n"
                 + manifest.build(notebook) + "\n")

    # A QUESTION YOU ASKED IN A PREVIOUS SESSION, which this one would
    # otherwise never learn about. `wait` collects the reply, but only if it
    # is called -- and a cold-started coordinator has no reason to call it
    # before launching something. Observed: a session escalated for more
    # reference photographs, blocked, and was killed; the question and then
    # its answer sat on disk with nothing to read them.
    from ..process import mailbox
    mail = coordinator.mailbox_for(notebook)
    outstanding = mailbox.pending(mail.run)
    if outstanding:
        answered = mail.answer_path.exists()
        parts.append(
            "## You have a question outstanding with the user\n\n"
            f"**{outstanding.get('name')}** — "
            f"{outstanding.get('prompt', '')}\n\n"
            + ("**They have answered it.** Call `wait` NOW, before anything "
               "else, to collect the reply.\n"
               if answered else
               "No reply yet. `wait` blocks for it, and costs nothing.\n"))
    if notes:
        lines = "\n".join(f"- {n.get('kind', 'note')}: {n.get('text', '')}"
                          for n in notes)
        parts.append("## Your most recent notes, from earlier sessions\n\n"
                     + lines + "\n")
    parts.append(TAIL)
    return "\n".join(parts)
