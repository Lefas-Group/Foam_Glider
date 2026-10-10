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

import pathlib

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


OWN_AIRCRAFT = """\
# There is no notebook at `{name}` yet, and the user has already supplied it

So this session STARTS AN AIRCRAFT -- one THEY designed and built. They ran
`nb intake` first, so two things are already on disk and are not yours to
compose:

- **the photographs**, in `_reference/`, each with the description THEY wrote
  of where the camera was:{photos}
- **the figures they measured**, in full, below. `new` merges these into the
  brief itself, so you do not retype them as `spec` -- and must not: a row
  typed twice is a row that can disagree with itself. There is nothing to go
  and read; this is all of it.
{measured}
The order is therefore SHORT, and three of the usual steps are already done:

1. `source` and `fetch` what the MATERIALS are -- foam areal density, and the
   mass of every motor, ESC, servo, propeller and battery named. This is the
   research that is still yours, and the page says why it is the half that
   fails silently.
2. `new`. Add only what the user did not: an `assume` row for the airfoil, a
   `target` ONLY if a figure they gave you implies one. Do not invent a target
   to fill the block.
3. `mask`, then `overlay` EVERY photograph and look, then `reference` until it
   is clean.
4. `reconstruct` the first chapter.

Do NOT `search` for a product page or for photographs. There is no
manufacturer; the aeroplane is on the user's bench. If the spread has a gap,
`escalate` a reshoot -- naming the camera position you want -- and `wait`.

You cannot `new` twice.
"""


def _intake(name):
    """
    `_reference/INTAKE.yml` at `name`, parsed, or None.

    READ OFF DISK RATHER THAN PASSED IN, because the session that reaches here
    may be days after the intake: `nb coordinate` is told a directory name and
    nothing else, and the file is the handover. `shared.parse_inputs` is the
    same reader `cli/new.py` uses on it, so the prefix cannot describe rows the
    brief will not receive.
    """
    from ..contract import shared
    from ..tools import figures

    return shared.parse_inputs(
        pathlib.Path(name) / figures.REFERENCE_DIR / "INTAKE.yml") or None


def _setup_page(name, held):
    """Which setup order this session is on, and what it already holds."""
    where = name or "the given directory"
    if not held:
        return NEW_AIRCRAFT.format(name=where)
    photos = [t for _, t in (held.get("photos") or [])]
    rows = [t for k in ("specified", "targets", "assumed")
            for _, t in (held.get(k) or [])]
    # NAMED, NOT COUNTED. The whole risk of this branch is a model that
    # researches an aircraft it was handed -- so the handed thing is put in
    # front of it in full, rather than as a number it has to go and look up.
    return OWN_AIRCRAFT.format(
        name=where,
        photos=("\n  " + "\n  ".join(f"`{s}` -- {t}"
                                     for s, t in (held.get("photos") or []))
                if photos else " none yet, so this half is still yours."),
        measured=("\n" + "\n".join(f"      {r}" for r in rows) + "\n"
                  if rows else "\n"))


def build(notebook, direction="", name=""):
    """The system instruction: doctrine, then this notebook as it stands."""
    # A SKELETON IS NOT AN AIRCRAFT. `nb designer` creates `chapters/` so the
    # board has somewhere to live before anything is scaffolded, and
    # `Notebook()` accepts any root that has one -- so this read "there is a
    # notebook" and handed the model the steady-state pages for a directory
    # with nothing in it. `_notebook.py` is what `nb new` produces, so its
    # absence is the honest test. Measured on ft-warthog, where the model was
    # given the coordinate pages, found an empty manifest, called `new`, was
    # refused, and escalated from a dead end.
    from ..coord.tools import _scaffolded
    if not _scaffolded(notebook):
        notebook = None
    # SETUP OR STEADY STATE decides which pages, and `doctrine.py` owns
    # that split so `nb doctrine` hands Claude Code the same grouping.
    who = "setup" if notebook is None else "coordinate"
    parts = [HEAD, doctrine.text(who)]
    if notebook is None:
        # SUPPLIED OR RESEARCHED, and they are different jobs. A session told
        # to "search and fetch the manufacturer's pages" for an aircraft the
        # user designed themselves has no first step it can take -- there is no
        # manufacturer -- and the measured ordering failure is what happens
        # next: it searches anyway, finds a different aeroplane, and either
        # escalates from a dead end or builds that one.
        held = _intake(name) if name else None
        parts.append(_setup_page(name, held))
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
        # A NOTE MAY BE SEVERAL LINES now that it can be a summary of where
        # the programme stands, so continuations are indented to stay inside
        # their bullet -- flush left they read as the end of the list.
        lines = "\n".join(
            "- {}: {}".format(n.get("kind", "note"),
                              str(n.get("text", "")).replace("\n", "\n  "))
            for n in notes)
        parts.append("## Your most recent notes, from earlier sessions\n\n"
                     + lines + "\n")
    parts.append(TAIL)
    return "\n".join(parts)
