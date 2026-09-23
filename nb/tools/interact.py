"""
The three tools that talk to the human, and the one that ends the run.

Every one of them goes through the MAILBOX: the question is written to the run
directory and the run waits for a file in reply. There is no stdin path any
more. It was not a second transport for the same behaviour -- EOF on the
attached path raised and killed the run with the question recorded nowhere,
while a question on disk is answerable from the board, a second terminal, a
script or a coordinator, and the run resumes either way.

No orchestration framework is needed for any of it. Under one, each of these
needed its own graph node, because a `while` loop containing an interrupt
replays prior iterations exponentially on resume -- which also capped how often
it was reasonable to ask. Here the cap is only good manners.
"""

import json
import re

from ..loop import Refactor, Terminal
from ..schema import Input, Proposal
from ..log import say, tell


# Set by `ask` and `write` before anything can be asked. Every run has one:
# terminal and nothing below changes -- the single-user path is untouched.
MAILBOX = None


def use_mailbox(mailbox):
    global MAILBOX
    MAILBOX = mailbox


def ask_stuck(found, phase):
    """
    Route the stuck-detector's finding the same way every other question goes,
    and hand back the text to put to the model.

    It does NOT reuse `_prompt`, for one reason: `_prompt` treats EOF as fatal,
    because a Specified input must never be assumed. This question is the
    opposite -- "carry on" is the safe answer, so stdin closing, a Ctrl-C, or
    nobody being there must all mean carry on. A detector that can kill an
    unattended run when it guesses wrong would be worse than no detector.
    """
    from .. import stuck

    def asker(why, options, default):
        tell(f"\n{'─' * 72}\nNO PROGRESS — {phase} phase\n{'─' * 72}")
        tell(f"  {why}")
        tell(f"  waiting up to {stuck.ASK_WAIT / 60:.0f} min — "
             f"{MAILBOX.notebook.question_path}")
        return MAILBOX.ask("stuck", "NO PROGRESS", why, options,
                           default=default, wait=stuck.ASK_WAIT)

    return stuck.escalate(found, phase, asker)


def _prompt(banner, name, body):
    """
    A question with no safe default: it is asked, and the run waits.

    Through the mailbox, always. There used to be a stdin branch for a run at a
    terminal, and it was not merely a different transport -- EOF there raised,
    killing the run with the question recorded nowhere. Here the question stays
    on disk and the run is resumable, which is what makes `nb answer`, a second
    terminal and a coordinator interchangeable.

    `name` is the QUANTITY, not the banner. It used to be the banner, so every
    Specified input in the system shared one mailbox key: `question.json` said
    `"name": "SPECIFIED INPUT NEEDED"` whatever was being asked, the board's
    panel and `run.json`'s `waiting_on` could not say WHICH input a run was
    blocked on, and `--answers` could pre-answer exactly one of them, since
    `Mailbox.ask` pops by name. The quantity was in the caller's hand all along.
    """
    tell(f"\n{'─' * 72}\n{banner}\n{'─' * 72}")
    tell(body)
    tell(f"  waiting for an answer — {MAILBOX.notebook.question_path}")
    return MAILBOX.ask("specified", name, body)


# What counts as handing the decision back. Named because `propose` needs the
# same test: an input the user DELEGATED is owned by the agent, and recording it
# as theirs would put words in their mouth -- "the user specified: you decide".
DELEGATED = ("you decide", "your call", "you choose", "")


def ask_budget(title, body, default, source=""):
    """
    A number the USER grants before the run starts, with a safe default.

    Deliberately NOT `_prompt`, which has no default at all because "a
    Specified input is asked every time, never assumed". That rule is about
    inputs that change WHAT IS BEING BUILT, where a default would be a silent
    design decision. A budget is not one: it changes only how long a wrong turn
    may run, it has a defensible default, and a coordinator that supplies
    nothing should get that default rather than a dead run. So a timeout, a
    blank reply and anything unparseable all fall through to `default`.
    """
    # The default AND where it came from. Two numbers were being shown
    # identically and they are not the same kind of thing: the pool is a
    # constant in `config.py`, the ceiling belongs to the notebook and is read
    # out of its own `_notebook.py`. Which one you are overriding changes what
    # overriding it means.
    body = f"{body}\n  {default:.0f} s unless you say otherwise" + (
        f" — {source}" if source else "")
    tell(f"\n{'─' * 72}\n{title}\n{'─' * 72}")
    tell(body + "\n")
    got = MAILBOX.ask("budget", title, body, default=default)
    try:
        value = float(str(got).strip())
    except ValueError:
        value = 0.0
    value = value if value > 0 else default
    say(f"  answered   {value:.0f}")
    return value


def ask_pool(default, source="config.PROBE_POOL"):
    """Probe wall clock for the whole question. The AGENT divides this one."""
    return ask_budget(
        "PROBE TIME POOL",
        "  Seconds of exploring, for the whole question.",
        default, source)


def ask_render_ceiling(default, source=""):
    """
    Seconds ONE render of the entry may take. The agent does NOT divide this.

    Granted rather than negotiated: the agent writes this number into the entry
    as ENTRY_CEILING and `write` refuses to commit an entry that changed it. A
    run that genuinely needs more asks through `ask_specified`, the same
    escalation the probe pool uses -- which is what keeps one number in force
    instead of two that can disagree.

    It is a PER-RENDER ceiling, not a pool: the write phase may render several
    times behind lint and build retries, and each attempt gets the same
    deadline, because the number describes what one render of this entry ought
    to cost. It is also what rule 17 checks against the recorded seconds.
    """
    return ask_budget(
        "ENTRY RENDER BUDGET",
        "  Seconds of solving the entry may take. Overrun is killed.",
        default, source)


def persist(proposal, notebook, corrections=None):
    """
    Re-write proposal.json, preserving the private `_` fields already on disk.

    `propose` writes the file and THEN raises, so anything the gate changes
    afterwards -- a corrected assumption -- exists only in memory, and the write
    phase re-reads the file. Without this the confirmation would have looked
    like it worked and changed nothing that mattered.

    `corrections` is [(name, was, now)] and goes into `_corrections`, which the
    write phase turns into one line of its brief. It is the whole mechanism
    that replaced the re-probe loop: a corrected VALUE does not need a fresh
    probe, because rule 1 makes the entry recompute at render time -- what it
    needs is for the model to know the finding it was handed was computed
    under the old number.
    """
    path = notebook.proposal_path
    private = {}
    if path.exists():
        try:
            private = {k: v for k, v in json.loads(path.read_text()).items()
                       if k.startswith("_")}
        except ValueError:
            pass
    out = proposal.model_dump()
    out.update(private)
    out["_assumptions_confirmed"] = True
    if corrections:
        out["_corrections"] = [
            {"name": n, "was": w, "now": v} for n, w, v in corrections]
    path.write_text(json.dumps(out, indent=2) + "\n")


# A correction that rejects the APPROACH rather than the value. Anything else
# after "N:" is a new value.
REDO = re.compile(r"^\s*redo\b[\s:,.\u2014-]*", re.I)


def confirm_assumptions(proposal):
    """
    Show every assumption the probe made, and take corrections.

    Returns (corrected, rejected). `corrected` is [(name, was, now)] for values
    the user changed, already applied to `proposal.inputs`; `rejected` is
    [(name, why)] for assumptions whose whole APPROACH they refused.

    Assumptions were never confirmed before: `ask_specified` covers inputs
    where a different answer changes WHAT IS BEING BUILT, and an assumption is
    the other kind -- "assume and say what it costs". That is defensible for
    the cost, and silent about the premise, so "point-mass with fixed alpha"
    went into the record unexamined and an entry was built on it.

    THE TWO ANSWERS ARE DIFFERENT KINDS OF THING, and the split is what let the
    re-probe loop go. A corrected VALUE is safe to carry forward: rule 1 forces
    every number in prose to be a `{python}` expression, so the entry
    RECOMPUTES at render time, and the write phase given the new value produces
    a genuinely correct entry -- the stale `findings` are context it is told to
    distrust. A rejected APPROACH is not: `working_code` cannot be adapted to a
    method that was not probed, so the run ends and the question is re-asked.

    The old loop re-probed both, three rounds deep, because nothing could tell
    them apart. The person correcting it can, so they say which. In 67 recorded
    runs the loop never once executed.

    BATCHED, not asked one at a time, because per-assumption asking makes the
    model judge which of its assumptions are load-bearing -- the judgement rule
    4 exists because it gets it wrong -- and interrupts a run that has nothing
    wrong with it. Here the user sees the whole set at once, including the ones
    the model would not have thought to raise.

    EOF and a blank line ACCEPT, following `ask_budget` rather than `_prompt`:
    this is a confirmation with a safe default, not a question that must be
    answered, and raising on EOF would kill every piped run.
    """
    assumed = [i for i in proposal.inputs if i.source == "guessed"]
    if not assumed:
        return [], []

    listing = "\n".join(f"{n}. {i.name}: {i.value or i.why}"
                        for n, i in enumerate(assumed, 1))
    how = ('  Enter accepts.\n'
           '  Correct a VALUE with        "1: 2.5e-4"\n'
           '  Reject the APPROACH with   "1: redo — needs 3-DOF, not point-mass"'
           '   (ends the run)')
    tell(f"\n{'─' * 72}\nASSUMPTIONS — confirm, correct a value, or reject one"
         f"\n{'─' * 72}")
    for line in listing.splitlines():
        tell(f"  {line}")
    tell(f"\n{how}")
    # A confirmation with a safe default: accepting is the right answer if
    # nobody replies, so an unattended run is never stranded by one.
    answer = MAILBOX.ask("assumptions", "assumptions",
                         f"{listing}\n\n{how}", default="").strip()
    if not answer:
        say("  answered   (accepted as stated)")
        return [], []

    # A reply that names no assumption at all is APPROVAL, not a malformed
    # correction. "Enter accepts" is what the prompt says, and people type the
    # word instead: `happy` was answered on 2026-09-18 and logged as
    # `ignored 'happy' — expected "N: value"`. The outcome was right by
    # accident -- nothing parsed, so nothing was corrected -- but the run
    # recorded a rejection of an approval, which is the one thing a record of
    # what the user agreed to must never do. Only a reply that looks like it is
    # TRYING to correct something is held to the format, so a typo in "1: 12mm"
    # is still caught rather than silently read as consent.
    if not any(part.partition(":")[0].strip().isdigit()
               for part in answer.split(";")):
        say(f"  answered   (accepted as stated — {answer!r})")
        return [], []

    corrected, rejected = [], []
    for part in answer.split(";"):
        head, _, value = part.partition(":")
        try:
            i = assumed[int(head.strip()) - 1]
        except (ValueError, IndexError):
            tell(f"  ignored    {part.strip()!r} — expected \"N: value\" or "
                 f"\"N: redo — why\"")
            continue
        value = value.strip()
        if REDO.match(value):
            why = REDO.sub("", value).strip() or "no reason given"
            rejected.append((i.name, why))
            say(f"  answered   {i.name} REJECTED — {why}")
            continue
        # The same shape `ask_specified` produces, so nothing downstream has to
        # learn a second one: the user answered it, so they own it, and an input
        # they chose is Specified by definition.
        was = i.value or i.why
        i.source, i.value = "asked", value
        i.why = "corrected at the prompt"
        corrected.append((i.name, was, value))
        say(f"  answered   {i.name} -> {i.value}")
    return corrected, rejected


def confirm_inherited(proposal, notebook):
    """
    Show what a NEW chapter carries forward, and take strikes. Returns
    (kept, struck), each [(kind, item, from_chapter)].

    BOTH halves, because both are read. The kept set is what the new chapter's
    index may state without claiming anybody was asked; the struck set is what
    the fork BREAKS, which is the one thing the computation cannot know and the
    only reason this is a question at all. Returning only `kept` meant the
    write phase was told neither: the answer was persisted to `proposal.json`
    and read by nothing, so striking an item changed a log line and nothing
    else.

    At the new-chapter stop because that stop already exists and already halts
    the run: `render_stop` told the user a chapter was being committed to and
    showed them its name, its title and a resume command -- nothing about what
    it INHERITS, which is the substance of the commitment.

    The list is COMPUTED (see `inputs.inherited`), so this is a review rather
    than a question. What the computation cannot know is whether the fork
    breaks an item: forking the 3 mm chapter back to 5 mm inherits "foam
    thickness: 3 mm", which is exactly wrong and exactly the thing to strike.

    GROUPED BY ANCESTOR, nearest first, because the set operation and the
    semantics disagree and the presentation is the only place that can say so.
    `inherited()` UNIONS every ancestor's declarations; what the notebook
    actually means is OVERRIDE -- a later chapter that revisited a subject has
    settled it. Flattened into one numbered list, chapter 06 was offered
    "Foam thickness: 3 mm" (from 04) and "Foam 5 mm, 174.4 g/m² sheet
    throughout" (from 01) as thirteen peers, along with "Fuselage neglected"
    that 02 had already contradicted by adding one, and NACA4405 sections that
    04 had already replaced.

    None of that is resolvable mechanically: measured on those thirteen items,
    keying on the bold label and letting a nearer ancestor shadow a further one
    shadows NOTHING, because the labels are descriptions rather than subjects
    -- "Foam thickness" and "Foam 5 mm, 174.4 g/m²" name the same quantity and
    share no key. So the ordering carries the meaning instead: the nearest
    ancestor is at the top, the furthest at the bottom, and the header says
    which way the arrow points. The reader resolves the conflict, which is what
    they were being asked to do anyway -- now with the information to do it.

    Batched and defaulted, following `confirm_assumptions` rather than
    `_prompt`: accepting is the right answer when nobody replies, and a gate
    that can strand an unattended run is worse than one that occasionally
    carries an item too many.
    """
    from ..inputs import inherited
    items, superseded = inherited(notebook, proposal.chapter)
    if not items:
        return [], []

    # NUMBERED GLOBALLY, grouped for reading. The numbers are what a strike
    # names, so they run straight through the groups -- renumbering within each
    # would make "3" ambiguous the moment there were two groups.
    lines, seen = [], None
    for n, (kind, item, src) in enumerate(items, 1):
        if src != seen:
            seen = src
            where = ("nearest" if n == 1 else
                     "furthest" if n + sum(1 for k in items[n:] if k[2] == src)
                     == len(items) else "")
            lines.append(f"\n  from {src}{f'  ({where})' if where else ''}")
        lines.append(f"    {n:2}. [{kind}] {item}")
    body = "\n".join(lines).lstrip("\n")
    how = ('  A NEARER chapter overrides a further one: where two items name the\n'
           '  same quantity, the one higher up is the one in force.\n\n'
           '  Enter keeps all of it. Strike what this fork breaks — "3" or "3; 5".')

    tell(f"\n{'─' * 72}\nINHERITED — nearest ancestor first"
         f"\n{'─' * 72}")
    for line in body.splitlines():
        tell(line)
    # RESOLVED, not hidden. These are items an ancestor declared and a later
    # ancestor replaced, so they are not carried forward -- but a list that
    # silently shrank would be a list nobody could check.
    if superseded:
        tell(f"\n  already superseded, so not carried:")
        for kind, item, src, by in superseded:
            tell(f"      [{kind}] {item}")
            tell(f"          {src} → replaced by {by}")
    tell(f"\n{how}")
    answer = MAILBOX.ask("inherited", "inherited", f"{body}\n\n{how}",
                         default="").strip()
    if not answer:
        say(f"  answered   (all {len(items)} carried forward)")
        return items, []
    struck = set()
    for part in answer.replace(",", ";").split(";"):
        head = part.strip().split(":")[0].strip()
        if head.isdigit() and 1 <= int(head) <= len(items):
            struck.add(int(head) - 1)
        elif part.strip():
            tell(f"  ignored    {part.strip()!r} — expected a number")
    kept = [x for n, x in enumerate(items) if n not in struck]
    for n in sorted(struck):
        say(f"  answered   struck {items[n][1]}")
    return kept, [items[n] for n in sorted(struck)]


def ask_specified(session, name, why, kind="specified", options="",
                  replaces=""):
    """
    A Specified input: a different answer changes WHAT WE ARE BUILDING.

    Asked immediately rather than batched into the proposal. The skill batches
    them because in a chat interface the run is stopping anyway and the round
    trip is the cost; here the process is alive, so asking early is strictly
    better -- the rest of the probe then runs against the real value instead of
    a placeholder. A static margin discovered at turn 3 should not be guessed
    for twenty more turns.

    `replaces` names an item the CHAPTER already declares, by its id. It is the
    difference between asking cold and asking about a change: the question the
    user sees then carries the value in force, which is the one thing they need
    to answer it. Nothing in the system asked to CHANGE an existing commitment
    before this -- `ask_specified` was for new inputs, the first-probe notice
    nudged with a count, and `confirm_assumptions` ran the other way round, so
    an entry could be written under an assumption its own question invalidated
    and nothing would stand between that and a commit.
    """
    # CLASSIFY BEFORE ASKING, checked here rather than twenty turns later. A
    # `derivable` admitted as such is refused outright -- that is rule 4, and
    # the model has just told us it could compute the answer. `kind` is a tool
    # parameter and not a field of `Input`: it is a gate on the ASK, and once
    # the question has been put the only thing worth recording is where the
    # answer came from.
    if kind == "derivable":
        raise ValueError(
            f"'{name}' is derivable -- the model or the plans already contain "
            f"it. Compute it; do not ask (rule 4).")
    if kind == "unknown":
        raise ValueError(
            f"'{name}' is unknown, not Specified: a different answer changes "
            f"how ACCURATELY it is modelled, not what is being built. Assume "
            f"it, record it with source='guessed', and say what it costs.")
    # `why` is held to rule 8's ten words now, not after the whole proposal is
    # assembled around it.
    Input(name=name, source="asked", value=None, why=why)

    body = f"  {name}\n  {why}"
    if replaces:
        import lint
        ids = lint.input_ids(session.notebook.root, session.chapter or "")
        if replaces not in ids:
            raise ValueError(
                f"replaces={replaces!r} is not an id declared by "
                f"chapters/{session.chapter}. Its ids are: "
                + (", ".join(sorted(ids)) if ids else "(it declares nothing)")
                + ". Name the item you are changing, or omit `replaces` if "
                  "this is a new input.")
        # THE VALUE IN FORCE, in the question. Asking "static margin?" of
        # someone who set it to 10% four chapters ago is asking them to go and
        # look it up.
        body = (f"  {name}\n  {why}\n\n  This CHANGES what "
                f"chapters/{session.chapter} is committed to:\n"
                f"    {replaces}: {ids[replaces]}")
    if options:
        body += f"\n  options: {options}"
    answer = _prompt("SPECIFIED INPUT NEEDED", name, body)
    session.record_answer(name, answer)
    if replaces:
        # For the write phase: what this answer displaces, and where.
        session.replaced[name] = (session.chapter, replaces)
    if answer.lower() in DELEGATED:
        return ("Delegated. Decide it yourself if it is answerable in a "
                "sentence, and record it with source='decided' and your reason. "
                "If answering it needs computation, it is a question in its own "
                "right: probe it, answer it, then come back to the original.")
    return f"The user answered: {answer}"


def declare_refactor(session, function, why):
    """
    Record the model's own account of why a shared function changed.

    Kept OFF the gate's evidence: the diff decides, this only says what the
    change was meant to be. The two together are what a reader needs -- the
    gate used to print neither, so "`_analysis.py:optimize_glider_unswept_c4`
    changed" was the whole explanation for holding an entry back.
    """
    session.refactor_notes[function] = " ".join(why.split())
    return (f"Recorded. It is shown beside the diff of {function} when the "
            f"chapter is re-proved.")


def request_refactor(session, chapter, why):
    """
    Declare that the entry cannot be written without changing the vehicle.

    Reached only after a write to `_model.py` was refused, so by here the agent
    has tried the cheap path. Terminal, like `propose`: the decision is whether
    to pay for re-proving every sibling entry, and that is not the agent's to
    make.
    """
    err = Refactor(why)
    err.chapter, err.why = chapter, why
    err.entries = len(session.notebook.entries(chapter))
    raise err


def propose(session, **fields):
    """
    The single terminal tool. Validates, writes proposal.json, ends the run.

    Route, inputs and proposal arrive together. The integrity check below is the
    one thing the schema cannot do on its own: a Specified input claiming the
    user answered it has to correspond to an ask that actually happened.
    """
    fields.setdefault("question", session.question)
    proposal = Proposal.model_validate(fields)

    # The `--chapter` pin, enforced rather than suggested. The brief asks; this
    # is what makes it a pin. A flag that only advises is a flag that reports
    # the wrong chapter half the time, which is the misroute it exists to stop.
    pinned = getattr(session, "pinned_chapter", None)
    if pinned and proposal.chapter != pinned:
        raise ValueError(
            f"This run is pinned to chapters/{pinned}/ and you proposed "
            f"{proposal.chapter!r}. Propose into {pinned}. If the question "
            f"genuinely does not belong there, propose into it anyway and say "
            f"so in the rationale -- moving it is the caller's decision, not "
            f"yours.")

    # An empty `inputs` list is a CLAIM or an omission, and nothing could tell
    # them apart. Measured: four of eight recorded runs proposed with no inputs
    # at all, which meant `confirm_assumptions` hit its early exit and the
    # correction loop behind it -- the one that re-probes rather than writing
    # from a rejected premise -- never ran. It did not decline to fire; nothing
    # asked it to.
    #
    # Refused the way the claimable-stub check below is refused: a ValueError
    # the model reads and acts on, not a schema error. The escape is explicit,
    # because an entry that genuinely inherits everything is common and its
    # reason belongs on the record.
    if not proposal.inputs and not proposal.inputs_none_because.strip():
        raise ValueError(
            "`inputs` is empty and nothing says why. Every question either "
            "needed something Specified (a different answer changes WHAT IS "
            "BEING BUILT -- ask it with ask_specified), assumed something new "
            "(a different answer changes HOW ACCURATELY it is modelled -- "
            "record it with source='guessed'), or inherited "
            "everything the chapter already declares. If it is the last, say "
            "so in `inputs_none_because` in one line. Do not invent an input "
            "to satisfy this.")

    unasked = [i.name for i in proposal.inputs
               if i.source == "asked" and i.name not in session.asked]
    if unasked:
        raise ValueError(
            f"These are recorded as source='asked' but were never put through "
            f"ask_specified: {', '.join(unasked)}. Ask them, or record "
            f"source='decided' with your reason if you chose them yourself.")

    # A scaffolded chapter still carrying its placeholder is a SLOT, and filling
    # it is a chapter-level decision however the route is labelled. Without this
    # a run routes `entry` into `01-first-chapter`, fills it correctly, and
    # leaves the placeholder directory name -- which entry stems and freeze paths
    # then bake in permanently. Checked here rather than in the schema because
    # only the notebook knows which chapter is a stub, and raising sends the
    # model a message it can act on instead of wasting the ask.
    if proposal.chapter == session.notebook.claimable_stub() and not (
            proposal.chapter_title and proposal.chapter_defines):
        raise ValueError(
            f"chapters/{proposal.chapter}/ is an empty scaffold, not a chapter "
            f"yet -- its name is a placeholder and its _model.py is bare. You "
            f"are the first entry in it, so name it: give chapter_title (what "
            f"the chapter holds, e.g. 'Trimmed glide' -- NOT this question) and "
            f"chapter_defines (the aero method, the section, what is left out). "
            f"The directory is renamed to match before you write.")

    # Measured, not guessed: aero_report() prints the solves the probe just ran.
    proposal.render_cost_s = round(session.solve_seconds, 1)

    # Every input the user ACTUALLY answered, whether or not the model listed
    # it. The check above catches the opposite error -- claiming an ask that
    # never happened -- but nothing caught an ask that happened and went
    # unrecorded, so "replace the current model", the answer that caused a whole
    # chapter to exist, reached the entry nowhere. Which questions were put to
    # the user is a fact about the run, not a judgement, so it is bookkeeping:
    # done here rather than asked of the model, because a model asked to copy
    # a list forward will sometimes improve it instead.
    recorded = {i.name for i in proposal.inputs}
    for name, value in session.asked.items():
        if name in recorded:
            continue
        delegated = str(value).strip().lower() in DELEGATED
        proposal.inputs.append(Input(
            name=name, source="decided" if delegated else "asked",
            value=None if delegated else str(value),
            why="delegated by the user" if delegated else "asked during the probe"))

    session.notebook.run.mkdir(parents=True, exist_ok=True)
    # `_pool_left` is written beside the proposal, not into it: the write phase
    # -- resumed in-process or from the terminal hours later -- needs to know
    # what is left of the pool the user agreed to, and a Proposal FIELD would
    # show up in the `propose` tool schema as a number the model is invited to
    # choose for itself. The underscore says so to a reader editing the file.
    out = proposal.model_dump()
    if session.probe_left is not None:
        out["_pool_left"] = round(session.probe_left, 1)
        # The GRANT as well as the remainder, so the write phase can report the
        # question's total spend against the number the user actually typed.
        # Reporting against the remainder made one question read as two budgets.
        out["_pool_total"] = round(session.probe_pool, 1)
    # The render ceiling the USER granted, carried across to the write phase so
    # the entry can declare the number it was given rather than one of its own.
    if getattr(session, "render_ceiling", None) is not None:
        out["_render_ceiling"] = session.render_ceiling
    # What an `ask_specified(replaces=...)` answer displaces. Private, like the
    # budgets: it is a fact about the run, not a field the model fills in.
    if getattr(session, "replaced", None):
        out["_replaces"] = [{"name": n, "chapter": c, "id": i}
                            for n, (c, i) in session.replaced.items()]
    session.notebook.proposal_path.write_text(json.dumps(out, indent=2) + "\n")
    raise Terminal(proposal)


def render_stop(proposal, notebook):
    """
    Why the run stopped, what saying yes commits to, and how to continue.

    This replaced a box that printed the proposal -- title, chapter, cost,
    figures, inputs -- and then `nb write <notebook>`. Everything in it was
    true and none of it said the run had STOPPED or why, so the reason had to
    be inferred from the contents, and inferred wrongly: the guess was that a
    new chapter forces a whole-chapter re-render. It does not. A new chapter
    has no siblings, and `check` re-renders siblings only when `_model.py`
    moves. The stop is a structural commitment, not a spend.

    The proposal itself is still on disk, and is still the thing to read and
    edit. What the terminal owes is the decision, which is not the same
    document.
    """
    return "\n".join([
        "",
        "─" * 72,
        "STOPPED — this needs a NEW CHAPTER",
        "─" * 72,
        f"  {proposal.chapter}",
        f'  "{proposal.title}"',
        "",
        "  Later entries build on its _model.py — changing it then means",
        "  re-solving all of them. That commitment is yours, not the entry.",
        "",
        f"  proposal  {notebook.proposal_path}",
        "",
        # A COMMAND ON ITS OWN LINE, never in the right-hand column. Every
        # other row of that column is information, so a command there reads as
        # information too and gets copied whole -- label and all. `continue` is
        # the worst possible label for it: zsh's loop keyword, so the paste
        # fails with "continue: too many arguments", which says nothing about
        # the real mistake. Observed, four times in a row.
        "  continue:",
        f"    uv run --group nb python -m nb resume {notebook.root.name}",
        "─" * 72,
        "",
    ])
