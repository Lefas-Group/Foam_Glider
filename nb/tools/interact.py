"""
The tools that talk to the human, and the three that move the run forward.

`fork_chapter`, `declare_input` and `open_entry` replaced `propose`, which was
a fifteen-field document the model filled in at the end and a second process
read back. None of that survived contact: 44% of the whole tool surface was one
declaration, most of it doctrine already in the system instruction; four of
eight recorded runs reached it having declared no inputs at all, because a list
you complete last is a list you forget; and the process boundary underneath it
cost five minutes of human round-trip on a run whose compute was sixteen.

What the document was actually FOR was four refusals -- a pinned chapter, an
unclaimed stub, an empty input list, an input claiming an ask that never
happened. Those are still here, re-homed to the call where each becomes true.

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

from ..schema import Input
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


# What counts as handing the decision back. Named because `_collect_inputs`
# needs the same test: an input the user DELEGATED is owned by the agent, and
# recording it as theirs would put words in their mouth -- "the user specified:
# you decide".
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

    It is a PER-RENDER ceiling, not a pool: a run may render several times
    behind lint and build retries, and each attempt gets the same
    deadline, because the number describes what one render of this entry ought
    to cost. It is also what rule 17 checks against the recorded seconds.
    """
    return ask_budget(
        "ENTRY RENDER BUDGET",
        "  Seconds of solving the entry may take. Overrun is killed.",
        default, source)


# A correction that rejects the APPROACH rather than the value. Anything else
# after "N:" is a new value.
REDO = re.compile(r"^\s*redo\b[\s:,.\u2014-]*", re.I)


def confirm_assumptions(session):
    """
    Show every assumption the probe made, and take corrections.

    Returns (corrected, rejected). `corrected` is [(name, was, now)] for values
    the user changed, already applied to `session.inputs`; `rejected` is
    [(name, why)] for assumptions whose whole APPROACH they refused.

    Assumptions were never confirmed before: `ask_specified` covers inputs
    where a different answer changes WHAT IS BEING BUILT, and an assumption is
    the other kind -- "assume and say what it costs". That is defensible for
    the cost, and silent about the premise, so "point-mass with fixed alpha"
    went into the record unexamined and an entry was built on it.

    THE TWO ANSWERS ARE DIFFERENT KINDS OF THING, and saying which is the
    user's half of it. A corrected VALUE is safe to carry straight forward:
    rule 1 forces every number in prose to be a `{python}` expression, so the
    entry RECOMPUTES at render time and the new value is simply used.

    A rejected APPROACH used to END THE RUN, because the probe's findings had
    been computed under the old premise and the conversation that produced them
    was already gone. It does not any more: `open_entry` hands the rejection
    back as a refusal and the run carries on, because the conversation IS still
    alive -- "the user rejected the point-mass assumption, probe again with
    trim" is something the model can act on. The three-round re-probe loop that
    was deleted for never firing in 67 runs is free here, and it is free
    precisely because there is no longer a boundary to re-probe across.

    BATCHED, not asked one at a time, because per-assumption asking makes the
    model judge which of its assumptions are load-bearing -- the judgement rule
    4 exists because it gets it wrong -- and interrupts a run that has nothing
    wrong with it. Here the user sees the whole set at once, including the ones
    the model would not have thought to raise.

    EOF and a blank line ACCEPT, following `ask_budget` rather than `_prompt`:
    this is a confirmation with a safe default, not a question that must be
    answered, and raising on EOF would kill every piped run.
    """
    assumed = [i for i in session.inputs.values() if i.source == "guessed"]
    if not assumed:
        return [], []

    listing = "\n".join(f"{n}. {i.name}: {i.value or i.why}"
                        for n, i in enumerate(assumed, 1))
    how = ('  Enter accepts.\n'
           '  Correct a VALUE with        "1: 2.5e-4"\n'
           '  Reject the APPROACH with   "1: redo — needs 3-DOF, not point-mass"'
           '   (sends it back to probe)')
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


def confirm_inherited(notebook, chapter, parent=None):
    """
    Show what a NEW chapter carries forward, and take strikes. Returns
    (kept, struck), each [(kind, item, from_chapter)].

    A CHAPTER WITH NO ANCESTOR IS SHOWN THE BRIEF AND ASKED NOTHING. With no
    parent, `inherited()` falls back to the notebook's own `_inputs.yml`, and
    offering those for striking is an offer that cannot be honoured twice over.
    Mechanically: resolving a strike calls `lint.input_ids(root, "<notebook>")`,
    which looks for `chapters/<notebook>/_inputs.yml`, finds nothing and matches
    no id -- so the strike was silently discarded, and rule 31 now refuses the
    `overwrites:` row it would have written. In principle: the brief is never
    overwritten, because a design that departs from it is a different aircraft
    and so a different notebook, not a fork. So it is shown as CONTEXT -- the
    reader still needs to see what the new chapter is being held to -- and the
    run is not stopped for an answer nobody can act on.

    BOTH halves, because both are read. The kept set is what the new chapter's
    index may state without claiming anybody was asked; the struck set is what
    the fork BREAKS, which is the one thing the computation cannot know and the
    only reason this is a question at all. Returning only `kept` meant the
    model was told neither: the answer was persisted and read by nothing, so
    striking an item changed a log line and nothing else.

    At `fork_chapter`, beside the approval, because that is the only moment
    both halves are known and it is the one place the run already stops. The
    approval names the chapter and its title; what it INHERITS is the substance
    of the commitment, and it used to be shown nowhere.

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
    from ..inputs import ancestry, inherited
    items, superseded = inherited(notebook, chapter, parent)
    if not items:
        return [], []

    if not ancestry(notebook, chapter, parent):
        tell(f"\n{'─' * 72}\nTHE BRIEF — true of the whole aircraft, and "
             f"inherited as it stands\n{'─' * 72}")
        for kind, item, src in items:
            tell(f"    [{kind}] {item}")
        tell("\n  This chapter has no parent, so it carries the notebook's own "
             "brief.\n  Nothing here is strikeable: a design that departs from "
             "it is a different\n  aircraft, and so a different notebook.")
        return items, []

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

    Asked immediately rather than batched up for the end. The skill batches
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
    # `why` is held to rule 8's ten words now, not twenty turns later.
    Input(name=name, source="asked", value=None, why=why)

    # ALREADY SETTLED, and asking again puts the same question to the user
    # twice. Measured on the X-Wing chapter: a static margin was asked,
    # answered and recorded in one entry, and asked again -- verbatim -- two
    # entries later, because the register a run is shown held only
    # `_inputs.yml`, and the answer had landed in an entry's callout. Both
    # tiers are read now; this is the backstop for when the model reads them
    # and asks anyway.
    #
    # NOT when `replaces` is given: that IS the deliberate change, and naming
    # the item is how you say so.
    from ..inputs import settled
    already = None if replaces else settled(
        session.notebook, session.chapter, name)
    if already:
        _kind, text, where = already
        # `where` is an `_inputs.yml` id, an entry stem, or the chapter itself
        # when a frozen notebook keeps its items as index callouts. Only the
        # first is something `replaces=` can name. Told apart by the date
        # prefix every entry stem carries, not by guessing at the string: an id
        # may legally start with a digit.
        import lint
        this_id = (None if lint.ENTRY_FILE.match(where) or where == session.chapter
                   else where)
        raise ValueError(
            f"chapters/{session.chapter} has already settled this. In force:\n"
            f"    {text}\n"
            f"  recorded " + (f"as `{this_id}` in _inputs.yml"
                              if this_id else f"by entry {where}") + ".\n"
            f"Use that value -- it is a commitment this chapter has already "
            f"put to the user, and asking again asks them the same question "
            f"twice. If THIS question genuinely changes it, that is a "
            f"different call: "
            + (f"ask again with replaces=\"{this_id}\"."
               if this_id else
               "record the new value with `declare_input` and say in your "
               "entry that it corrects the earlier one, naming and linking "
               "that entry (rule 10).")
            + " If you only need to state it, it is already stated and you "
              "inherit it.")
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


def approve_refactor(session, filename, moved, siblings):
    """
    A shared function just changed. Ask before the chapter is re-proved.

    Returns None to proceed, or the refusal to hand back to the model.

    THIS REPLACED `request_refactor`, which asked the model to predict that it
    needed a refactor and then declare it. It was never once called in 75
    recorded runs, and it could not have been: it was reachable only after a
    `_model.py` write was refused, and that guard has never fired. The system
    can now see the refactor happen, so nothing has to be predicted -- the same
    correction `guards.py` made when it stopped asking for `render_cost_s` and
    started measuring it.

    UNDEFAULTED, like the new-chapter approval and for the same reason: this is
    a commitment to spend, and a defaulted question would spend it for you
    after five minutes of silence. Walk away and the run leaves the question on
    disk and exits, resumable; be at the keyboard and it costs a keystroke.

    `--allow-refactor` pre-authorises it, which is what a resumed run carries,
    and one approval covers the rest of the run -- a fix that touches two
    functions is one decision, not two.
    """
    listing = ", ".join(moved)
    body = "\n".join([
        f"  {filename}   {listing}",
        "",
        f"  {siblings} sibling entr{'y' if siblings == 1 else 'ies'} in "
        f"chapters/{session.chapter} reach this code.",
        "  Saying yes means re-solving them to prove their answers did not",
        "  move — minutes — and you will be shown anything that did.",
        "",
        '  Enter (or anything else) allows it. "no — <why>" puts the file back.',
    ])
    tell(f"\n{'─' * 72}\nREFACTOR — a function the chapter already uses has "
         f"changed\n{'─' * 72}")
    tell(body)
    tell(f"  waiting for an answer — {MAILBOX.notebook.question_path}")
    answer = str(MAILBOX.ask("refactor", filename, body) or "").strip()
    if answer.lower().startswith(("no", "n ", "reject", "don't", "do not")):
        say(f"  refactor  REFUSED — {filename} restored")
        return (f"refused: the user will not re-prove chapters/"
                f"{session.chapter} for this. {answer}\n"
                f"{filename} has been RESTORED to what it was, so your edit to "
                f"{listing} is gone. Write this entry against the chapter as it "
                f"stands -- ADDING a function to _analysis.py is always allowed "
                f"and is how a chapter grows, so a new helper beside the old one "
                f"is usually the way through. If the entry genuinely cannot be "
                f"written without changing that function, stop and say why.")
    say(f"  refactor  allowed — {filename}:{listing}"
        + (f" — {answer}" if answer else ""))
    tell(f"  refactor  allowed — the chapter will be re-proved before commit")
    return None


def _new_chapter_approval(notebook, parent, chapter, title, defines):
    """
    The one stop that survives. Undefaulted, so nobody is needed for it to end
    safely.

    A chapter is a structural commitment later entries build on -- far harder
    to undo than an entry, which a `git revert` removes -- and it is decided
    BEFORE any of the work it authorises is paid for.

    `default=None` is the whole safety of it. A defaulted question takes its
    default after DEFAULTED_WAIT and carries on; an undefaulted one waits the
    full hour and then raises SystemExit with the question still on disk --
    which is exactly what the old process-ending stop did. Walk away and you
    get the old outcome, resumable. Be at the keyboard and you pay a keystroke
    instead of a second command.

    A "no" is NOT the end of the run. The conversation is alive, so a refusal
    goes back as a tool error the model reads and acts on -- write the entry
    into the chapter it was given, or say why it cannot. Ending the process on
    a refusal would throw away the probe that justified the request.
    """
    body = "\n".join([
        f"  {chapter}", f'  "{title}"', "",
        f"  defines   {' '.join(defines.split())[:400]}",
    ] + ([f"  forked    from {parent}, whose _model.py it copies"]
         if parent else ["  the notebook's first named chapter"]) + [
        "",
        "  Later entries build on its _model.py — changing it then means",
        "  re-solving all of them. That commitment is yours, not the entry's.",
        "",
        '  Enter (or anything else) creates it. "no — <why>" sends it back.',
    ])
    tell(f"\n{'─' * 72}\nNEW CHAPTER — approve before it is created"
         f"\n{'─' * 72}")
    tell(body)
    tell(f"  waiting for an answer — {MAILBOX.notebook.question_path}")
    answer = str(MAILBOX.ask("chapter", chapter, body) or "").strip()
    if answer.lower().startswith(("no", "n ", "reject", "don't", "do not")):
        return answer
    say(f"  answered   approved{f' — {answer}' if answer else ''}")
    return None


def fork_chapter(session, name, title, defines):
    """
    The question needs a chapter that does not exist yet. Make one from this one.

    ONE JOB, where `open_chapter` had six. The run already knows which chapter
    it is in -- `--chapter` is required and the lock was claimed before the
    first token -- so the pin check, the lock and the module snapshot are all
    gone from here, and the common case (an entry in the chapter you were
    given) needs no tool call at all. That was turn 1 of every run.

    THE PARENT IS ALWAYS THE ASSIGNED CHAPTER, never a parameter. The question
    was asked about that aircraft, so that is where the design comes from, and
    a lineage that is derived cannot be mis-declared -- `forked_from` was a
    free-text field naming any chapter, and 05-fully-optimized shows what a
    missing declaration costs: the lineage diagram drew two unconnected trees
    and the notebook read as two projects.

    `create_chapter` stays out of the model's hands. This is a declaration of
    intent that the system acts on -- the distinction `tools/__init__.py` has
    always drawn, and the reason `create_chapter` was never a tool: it could
    only ever return `rejected: already exists`, and it made ownership
    ambiguous on the one path that is structurally irreversible.
    """
    from ..locks import claim_chapter
    from ..tools.guards import bodies
    from ..tools.scaffold import create_chapter
    notebook = session.notebook
    name = str(name or "").strip().strip("/")
    if not (title.strip() and defines.strip()):
        raise ValueError(
            "A new chapter needs `title` (what the CHAPTER holds, e.g. "
            "'Trimmed glide' -- not this question) and `defines` (the aero "
            "method, the section, what is left out). Those are what the index "
            "states, and they are the one place those assumptions live.")
    if session.stem:
        raise ValueError(
            f"The entry is already open at {session.chapter}/{session.stem}.qmd. "
            f"A fork decided after the filename is allocated is a different "
            f"question -- finish this entry, and ask the next one against the "
            f"chapter it belongs in.")

    parent = session.chapter
    refused = _new_chapter_approval(notebook, parent, name, title, defines)
    if refused:
        raise ValueError(
            f"The user REFUSED a new chapter: {refused}\n"
            f"Do not ask again. Write this entry into chapters/"
            f"{session.chapter} as the vehicle stands -- a new objective, "
            f"different bounds, a finer sweep or any new measurement of the "
            f"same aircraft all belong there -- or stop and say why it cannot "
            f"be written without a new chapter.")

    # THE STRIKE IS THE SUPERSESSION, resolved here because this is the only
    # moment both halves are known: the ancestor an item came from, and the
    # fact that this chapter breaks it. `create_chapter` writes it straight
    # into `_fork.yml` under `overwrites:`.
    kept, struck = confirm_inherited(notebook, name, parent=parent or None)
    struck_ids = []
    if struck:
        import lint
        for _kind, item, src in struck:
            for _id, _text in lint.input_ids(notebook.root, src).items():
                if _text == item:
                    struck_ids.append((src, _id))
    session.inherited_kept, session.inherited_struck = kept, struck

    name, msg = create_chapter(notebook, name, title, defines,
                               fork_from=parent, overwrites=struck_ids)
    tell(f"  chapter   {msg.splitlines()[0]}")
    if msg.startswith("rejected"):
        raise ValueError(msg)

    holder = claim_chapter(notebook, name)
    if holder:
        raise ValueError(
            f"chapters/{name} was created but is held by another run (pid "
            f"{holder}). Stop here and say so.")
    session.chapter = name
    session.chapter_msg = msg
    # A NEW BASELINE. The one taken at startup belongs to the parent; this
    # chapter's `_model.py` is a fresh copy, and the gate must compare against
    # what was COMMITTED here, which for a new chapter is nothing.
    d = notebook.chapters_dir / name
    session.before_bodies = {n: bodies(d / n)
                             for n in ("_model.py", "_analysis.py")}
    session.siblings = len(notebook.entries(name))
    from .. import runstate
    runstate.write(notebook, chapter=name)
    if session.metrics is not None:
        session.metrics.set(chapter=name)
    say(f"  chapter   {name} created and claimed")
    return msg + _inherited_note(session)


def _inherited_note(session):
    """What the user agreed the new chapter carries, for the model to honour."""
    kept, struck = session.inherited_kept, session.inherited_struck
    if not (kept or struck):
        return ""
    lines = ["", "The user reviewed what this chapter inherits. NEAREST "
             "ANCESTOR FIRST: where two items name the same quantity, the one "
             "listed earlier is the one in force, because the chapter that "
             "declared it revisited the subject later."]
    if kept:
        lines += ["", "STILL TRUE, inherited — do NOT restate these in this "
                  "chapter's index, its _inputs.yml or in entry prose. They "
                  "are already stated one level up, and repeating them is what "
                  "rule 39 and the Specified/Assumed callouts exist to prevent:"]
        lines += [f"  [{k}] {i}   (from {s})" for k, i, s in kept]
    if struck:
        # RECORDED ONLY WHERE THERE IS AN ID. `overwrites:` rows are
        # `<chapter>/<id>` and resolve through the parent's `_inputs.yml`, so a
        # standing commitment can be pointed at and an assumption one ENTRY
        # made cannot -- it has no id to name. Both are struck; only the first
        # renders as "Overwritten from …". Saying otherwise would tell the
        # model its work was done when half of it was not.
        import lint
        lines += ["", "STRUCK — the user says this chapter BREAKS these, so "
                  "they do NOT carry forward. Where this chapter needs its own "
                  "value for one of them, that value is NEW and goes in this "
                  "chapter's `_inputs.yml`:"]
        rows, loose = [], []
        for k, i, s_ in struck:
            ids = lint.input_ids(session.notebook.root, s_)
            (rows if any(t == i for t in ids.values()) else loose).append(
                f"  [{k}] {i}   (was from {s_})")
        if rows:
            lines += ["", "Recorded in `_fork.yml` under `overwrites:`, which "
                      "lists them on this chapter's page as no longer holding:"]
            lines += rows
        if loose:
            lines += ["", "These were assumptions a single ENTRY made, so they "
                      "have no id and nothing can point at them. Nothing was "
                      "recorded for them: state what is true HERE in this "
                      "chapter's `_inputs.yml`, and say in your entry that it "
                      "corrects the earlier one, naming and linking that entry "
                      "(rule 10):"]
            lines += loose
    return "\n".join(lines)


def declare_input(session, name, value="", source="guessed", why="",
                  replaces=""):
    """
    One input, recorded at the moment it is assumed.

    Mirrors `ask_specified`, which is called the instant an input is found
    rather than saved for the end, and for the same measured reason: FOUR OF
    EIGHT recorded runs reached `propose` having declared no inputs at all,
    which is what a list you complete last looks like. A static margin
    discovered at turn 3 should not be guessed for twenty more turns, and it
    should not go unrecorded for twenty more either.

    It RECORDS; it does not ask. The batched confirmation survives at
    `open_entry`, because the reason for batching was about asking:
    per-assumption asking makes the model judge which of its assumptions are
    load-bearing, which is the judgement rule 4 exists because it gets wrong.

    A DICT keyed by name, so declaring the same quantity twice corrects it
    rather than listing it twice -- which is what a probe that revises its own
    assumption three turns later would otherwise produce.

    `replaces` names something the chapter is ALREADY committed to, by the
    handle the register reports. Assumptions are the model's to revise without
    asking anyone -- that is what separates them from specifications, which
    `ask_specified` puts to the user -- but revising one silently left the
    register holding both: a chapter that assumed 5 m/s in one entry and 8 m/s
    in a later one told the next run it assumed two different velocities, with
    no way to tell which was in force. `_fork.yml`'s `overwrites:` fixed
    exactly this between CHAPTERS; this is the same fact between entries.
    """
    name = " ".join(str(name).split())
    if source == "asked" and not session.was_asked(name):
        raise ValueError(
            f"'{name}' is recorded as source='asked' but was never put through "
            f"ask_specified. Ask it, or record source='decided' with your "
            f"reason if you chose it yourself.")
    # `why` is held to rule 8's ten words now, not after a whole document is
    # assembled around it. `Input` raises on eleven.
    item = Input(name=name, value=str(value) or None, source=source,
                 why=" ".join(str(why).split()))
    if replaces:
        from ..inputs import committed, short
        rows = committed(session.notebook, session.chapter)
        hit = next((r for r in rows if r[2] == replaces), None)
        if hit is None:
            raise ValueError(
                f"replaces={replaces!r} is not something "
                f"chapters/{session.chapter} is committed to. The handles are "
                f"listed beside each item after your first probe; they are "
                f"either an `_inputs.yml` id or `<chapter>/<handle>` for "
                f"something inherited. In force here: "
                + ", ".join(sorted(short(r[2], session.chapter) or "-"
                                   for r in rows))
                + ". Omit `replaces` if this is a new input.")
        if hit[0] == "Specified":
            raise ValueError(
                f"{replaces!r} is a SPECIFIED item -- the user chose it:\n"
                f"    {hit[1]}\n"
                f"Changing it is theirs, not yours. Put it to them with "
                f"`ask_specified(name=..., why=..., replaces=\"{replaces}\")`, "
                f"which carries the value in force into the question. "
                f"`declare_input(replaces=...)` revises an ASSUMPTION, which "
                f"needs nobody.")
        session.replaced_assumptions[replaces] = (
            hit[1], " ".join(str(why).split()))
        say(f"  input     {replaces} no longer holds — "
            f"{' '.join(str(name).split())} replaces it")

    # KEYED NORMALISED, valued with the name as written. Re-declaring a
    # quantity corrects it, and "Static margin" after "static margin" is a
    # correction, not a second input.
    key = session.key(name)
    again = key in session.inputs
    session.inputs[key] = item
    say(f"  input     {'revised' if again else 'recorded'} {name} "
        f"[{source}]{f' = {item.value}' if item.value else ''}")
    out = (f"{'Revised' if again else 'Recorded'}: {name} [{source}]. "
           f"{len(session.inputs)} input(s) so far. It goes in the entry's "
           f"`## {'Specified' if source != 'guessed' else 'Assumed'}` callout "
           f"when you write it.")
    if replaces:
        out += (f"\n\n{replaces} no longer holds. Record that in "
                f"`{session.chapter}/_inputs.yml` under `overwrites:`, as "
                f"`- {replaces}: <why, in a few words>` -- otherwise the next "
                f"entry is told this chapter is committed to both values and "
                f"cannot tell which. It renders on the chapter's page as "
                f"\"Overwritten\", and the entry you are writing should say in "
                f"prose that it corrects the earlier one, linking it (rule 10).")
    return out


def _collect_inputs(session):
    """
    Every input the user ACTUALLY answered, whether or not the model declared
    it.

    The `unasked` check catches the opposite error -- claiming an ask that
    never happened -- and nothing caught an ask that happened and went
    unrecorded, so "replace the current model", the answer that caused a whole
    chapter to exist, reached the entry nowhere. Which questions were put to
    the user is a fact about the run, not a judgement, so it is bookkeeping:
    done here rather than asked of the model, because a model asked to copy a
    list forward will sometimes improve it instead.
    """
    for name, value in session.asked.items():
        if session.key(name) in session.inputs:
            continue
        delegated = str(value).strip().lower() in DELEGATED
        session.inputs[session.key(name)] = Input(
            name=name, source="decided" if delegated else "asked",
            value=None if delegated else str(value),
            why="delegated by the user" if delegated else "asked during the probe")


def open_entry(session, title, inputs_none_because=""):
    """
    Probing is over; this is the question. The one hard gate in the run.

    It allocates the filename and RETURNS IT, which is what keeps the
    `YYYY-MM-DD-NN-slug` convention without a filename protocol: the model does
    not choose the stem, it is told it. It also returns the write brief, so the
    instructions for writing arrive at the moment writing starts, with the
    probe that produced the answer still above them -- rather than as the
    opening statement of a fresh conversation that had never seen the aircraft.

    Everything here is a refusal the model can act on and then retry. Nothing
    here ends the run.
    """
    from .. import briefs, runstate
    from ..phases.write import _stem
    import datetime
    notebook = session.notebook
    title = " ".join(str(title).split())

    if session.stem:
        return (f"The entry is already open at "
                f"{session.chapter}/{session.stem}.qmd. Write it.")

    # RULE 26, BEFORE IT BECOMES A FILENAME. Lint checks the title after the
    # fact, by which point the stem, the freeze path and the sidebar entry have
    # all been built from it -- and a brief pasted in whole gives a
    # 70-character stem nobody can read.
    words = title.split()
    if not title.endswith("?") or len(words) > 18 or not words:
        raise ValueError(
            f"The title is the question THIS entry answers: ONE question "
            f"ending in '?', 18 words at most (rule 26) -- aim for about "
            f"eight. Yours is {len(words)} word(s) and does not "
            f"end in a question mark. REPHRASE "
            f"the ask: strip anything that holds for the whole chapter, "
            f"because that lives in its index.qmd, and turn a brief into a "
            f"question. 'optimise a glider for trimmed glide. It is "
            f"constructed of foam 5mm thick…' is a brief; 'Which planform "
            f"gives the lowest sink rate?' is its question. It becomes the "
            f"entry title, the sidebar text and the filename.")

    _collect_inputs(session)
    # An empty `inputs` list is a CLAIM or an omission, and nothing could tell
    # them apart. The escape is explicit, because an entry that genuinely
    # inherits everything is common and its reason belongs on the record.
    if not session.inputs and not inputs_none_because.strip():
        raise ValueError(
            "You have declared no inputs and said nothing about it. Every "
            "question either needed something Specified (a different answer "
            "changes WHAT IS BEING BUILT -- ask it with `ask_specified`), "
            "assumed something new (a different answer changes HOW ACCURATELY "
            "it is modelled -- record it with `declare_input`, "
            "source='guessed'), or inherited everything the chapter already "
            "declares. If it is the last, say so in `inputs_none_because` in "
            "one line. Do not invent an input to satisfy this.")
    session.inputs_none_because = inputs_none_because.strip()

    unasked = [i.name for i in session.inputs.values()
               if i.source == "asked" and not session.was_asked(i.name)]
    if unasked:
        raise ValueError(
            f"These are recorded as source='asked' but were never put through "
            f"ask_specified: {', '.join(unasked)}. Ask them, or record "
            f"source='decided' with your reason if you chose them yourself.")

    # Measured, not guessed: `aero_report()` prints what the probe's solves
    # actually took. Asked of the model, this field came back 0.0.
    session.render_cost_s = round(session.solve_seconds, 1)

    corrected, rejected = confirm_assumptions(session)
    if rejected:
        # NOT THE END OF THE RUN any more. The conversation is alive, so the
        # rejection is something to act on rather than something to restart
        # from: re-probe under the method the user named, then open the entry
        # again. This is the re-probe loop that was deleted for never firing,
        # available for free because there is no longer a boundary to re-probe
        # across.
        tell(f"\n  {'─' * 70}\n  ASSUMPTION REJECTED — the entry is NOT open"
             f"\n  {'─' * 70}")
        for name, why in rejected:
            tell(f"  {name}: {why}")
        return ("The entry was NOT opened. The user rejected the APPROACH "
                "behind these assumptions, not the numbers:\n\n"
                + "\n".join(f"  {n}: {w}" for n, w in rejected)
                + "\n\nEverything you computed under them is stale -- a "
                  "corrected value would recompute at render time, but a "
                  "rejected method does not. Probe again using the method they "
                  "named, revise the assumption with `declare_input`, then "
                  "call `open_entry` again. If you believe the rejection is "
                  "mistaken, stop and say why rather than re-opening with the "
                  "same premise.")
    if corrected:
        tell("  corrected " + "; ".join(f"{n}: {w} → {v}"
                                        for n, w, v in corrected))

    today = datetime.date.today().isoformat()
    stem = _stem(notebook, session.chapter, title, today)
    # THE CHAPTER ALREADY HOLDS THIS QUESTION under another date. `_stem`
    # reuses a same-day file, which covers a resume on the same day and nothing
    # else; this covers the rest. [14:] is the SLUG -- ten date characters, a
    # dash, the two-digit within-day counter and a dash -- so a duplicate that
    # happened to be the second entry of its day still matches the first entry
    # of another.
    twin = next((e for e in notebook.entries(session.chapter)
                 if e.stem[14:] == stem[14:] and e.stem != stem), None)
    if twin:
        raise ValueError(
            f"chapters/{session.chapter}/ already holds this question, as "
            f"{twin.name}. Writing it would put a second copy under today's "
            f"date. If that entry is wrong, the fix is a NEW question that "
            f"supersedes it -- one that states the old value, the new one and "
            f"why they differ -- never a duplicate. Stop and say so.")

    session.stem = stem
    session.entry_title = title
    session.entry_path = (notebook.chapters_dir / session.chapter
                          / f"{stem}.qmd")
    # SIBLINGS, which this entry is not one of: the refactor gate re-proves
    # them only if there are any, and counting the entry itself on a resume
    # gated it against a baseline that cannot exist.
    session.siblings = len([e for e in notebook.entries(session.chapter)
                            if e.stem != stem])
    if session.metrics is not None:
        session.metrics.set(chapter=session.chapter, entry_stem=stem)
    # THE WHOLE OF CRASH RECOVERY. `run.json` is already written atomically,
    # already survives the process and is already read by the board, `nb answer`
    # and `nb clean`; four more fields is all `proposal.json` was ever doing
    # that nothing else does.
    runstate.write(notebook, chapter=session.chapter, stem=stem, title=title,
                   question=session.question,
                   pool_left=(round(session.probe_left, 1)
                              if session.probe_left is not None else None),
                   pool_total=(round(session.probe_pool, 1)
                               if session.probe_pool else None),
                   ceiling=session.render_ceiling)
    say(f"  entry     {session.chapter}/{stem}.qmd")

    import lint as _lint
    default_solve, default_ceiling = _lint._defaults(notebook.root)
    ceiling = session.render_ceiling
    total = session.probe_pool or 0.0
    left = session.probe_left if session.probe_left is not None else 0.0
    listing = "\n".join(
        f"  [{'Specified' if i.source != 'guessed' else 'Assumed'}] {i.name}"
        f"{f': {i.value}' if i.value else ''} — {i.why}"
        for i in session.inputs.values())
    return briefs.WRITE.format(
        chapter=session.chapter, stem=stem, today=today,
        ceiling=f"{(ceiling if ceiling is not None else default_ceiling or 200.0):.1f}",
        solve=f"{(default_solve or 60.0):.1f}",
        pool=f"{total:.1f}", spent=f"{max(0.0, total - left):.1f}",
        cost=f"{session.render_cost_s:.1f}", left=f"{left:.0f}",
        inputs=(f"What you recorded, which is what the callouts state:\n\n"
                f"{listing}" if listing else
                f"You recorded no inputs: {session.inputs_none_because}"))
