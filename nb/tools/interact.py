"""
The three tools that talk to the human, and the one that ends the run.

`ask_specified` and `consult` block on stdin. No machinery is needed for that:
the process is alive and you are at the terminal. This is the dividend from
having no orchestration framework -- under one, each of these needed its own
graph node, because a `while` loop containing an interrupt replays prior
iterations exponentially on resume, which also capped how often it was
reasonable to ask. Here the cap is only good manners.
"""

import json
import sys

from ..loop import Refactor, Terminal
from ..schema import Input, Proposal
from ..log import say, tell


def _prompt(banner, body, hint):
    # tell, not say: a question is the one thing a run cannot continue without,
    # so it belongs on the stream a reader is guaranteed to be watching.
    # One rule, one blank line, the question, then the caret with its hint on
    # the same line -- a hint on a line of its own read as another instruction
    # to follow rather than as a label for the box you type in.
    tell(f"\n{'─' * 72}\n{banner}\n{'─' * 72}")
    tell(body)
    sys.stdout.write(f"\n  [{hint}] > " if hint else "\n  > ")
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        say()
        raise SystemExit("cancelled at the prompt")
    if line == "":
        # EOF. There is deliberately no unattended mode: a Specified input is
        # asked every time, so with nobody to ask the run stops rather than
        # assuming. Failing loudly here is the whole point of the rule.
        say("  answered   (stdin closed)")
        raise SystemExit(
            "\n  stdin closed with a question outstanding. `nb ask` needs a "
            "terminal:\n  a Specified input is asked every time, never assumed.")
    # The ANSWER, in the log. The question was already there and the answer was
    # not, so the record showed a run pausing five minutes at a prompt and gave
    # no way to see what it was told -- which is the half that explains
    # everything after it.
    say(f"  answered   {line.strip() or '(default)'}")
    return line.strip()


# What counts as handing the decision back. Named because `propose` needs the
# same test: an input the user DELEGATED is owned by the agent, and recording it
# as theirs would put words in their mouth -- "the user specified: you decide".
DELEGATED = ("you decide", "your call", "you choose", "")


def ask_budget(title, body, default):
    """
    A number the USER grants before the run starts, with a safe default.

    Deliberately NOT `_prompt`, which raises on EOF and on a blank line because
    "a Specified input is asked every time, never assumed". That rule is about
    inputs that change WHAT IS BEING BUILT, where a default would be a silent
    design decision. A budget is not one: it changes only how long a wrong turn
    may run, it has a defensible default, and a coordinator that pipes a
    question and nothing else should get that default rather than a dead run.
    So EOF, Enter and anything unparseable all fall through to `default`.
    """
    tell(f"\n{'─' * 72}\n{title}\n{'─' * 72}")
    tell(body + "\n")
    sys.stdout.write(f"  [{default:.0f}] > ")
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        raise SystemExit("cancelled at the prompt")
    try:
        value = float(line.strip())
    except ValueError:
        say(f"  answered   {default:.0f} (default)")
        return default
    if value <= 0:
        say(f"  answered   {default:.0f} (default; {value} is not usable)")
        return default
    say(f"  answered   {value:.0f}")
    return value


def ask_pool(default):
    """Probe wall clock for the whole question. The AGENT divides this one."""
    return ask_budget(
        "PROBE TIME POOL",
        "  Seconds of exploring, for the whole question.",
        default)


def ask_render_ceiling(default):
    """
    Seconds ONE render of the entry may take. The agent does NOT divide this.

    Granted rather than negotiated: the agent writes this number into the entry
    as ENTRY_CEILING and `write` refuses to commit an entry that changed it. A
    run that genuinely needs more asks through `ask_specified`, the same
    escalation the probe pool uses -- which is what keeps one number in force
    instead of two that can disagree.

    It is a PER-RENDER ceiling, not a pool: the write phase may render several
    times behind lint and verify retries, and each attempt gets the same
    deadline, because the number describes what one render of this entry ought
    to cost. It is also what rule 17 checks against the recorded seconds.
    """
    return ask_budget(
        "ENTRY RENDER BUDGET",
        "  Seconds of solving the entry may take. Overrun is killed.",
        default)


def persist(proposal, notebook):
    """
    Re-write proposal.json, preserving the private `_` fields already on disk.

    `propose` writes the file and THEN raises, so anything the gate changes
    afterwards -- a corrected assumption -- exists only in memory, and the write
    phase re-reads the file. Without this the confirmation would have looked
    like it worked and changed nothing that mattered.
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
    path.write_text(json.dumps(out, indent=2) + "\n")


def confirm_assumptions(proposal):
    """
    Show every assumption the probe made, and take corrections.

    Returns the names corrected, so the caller knows whether the proposal still
    stands. Assumptions were never confirmed before: `ask_specified` covers
    inputs where a different answer changes WHAT IS BEING BUILT, and an
    assumption is the other kind -- "assume and say what it costs". That is
    defensible for the cost, and silent about the premise, so "point-mass with
    fixed alpha" went into the record unexamined and an entry was built on it.

    BATCHED, not asked one at a time, because per-assumption asking makes the
    model judge which of its assumptions are load-bearing -- the judgement rule
    4 exists because it gets it wrong -- and interrupts a run that has nothing
    wrong with it. Here the user sees the whole set at once, including the ones
    the model would not have thought to raise.

    EOF and a blank line ACCEPT, following `ask_budget` rather than `_prompt`:
    this is a confirmation with a safe default, not a question that must be
    answered, and raising on EOF would kill every piped run.
    """
    assumed = [i for i in proposal.inputs if i.owner == "assumed"]
    if not assumed:
        return []

    tell(f"\n{'─' * 72}\nASSUMPTIONS — confirm, or correct any\n{'─' * 72}")
    for n, i in enumerate(assumed, 1):
        tell(f"  {n}. {i.name}: {i.value or i.why}")
    tell('\n  Enter accepts. Correct one with "1: 12 mm".')
    sys.stdout.write("> ")
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        raise SystemExit("cancelled at the prompt")
    answer = (line or "").strip()
    if not answer:
        say("  answered   (accepted as stated)")
        return []

    corrected = []
    for part in answer.split(";"):
        head, _, value = part.partition(":")
        try:
            i = assumed[int(head.strip()) - 1]
        except (ValueError, IndexError):
            tell(f"  ignored    {part.strip()!r} — expected \"N: value\"")
            continue
        # The same shape `ask_specified` produces, so nothing downstream has to
        # learn a second one: the user answered it, so they own it, and an input
        # they chose is Specified by definition.
        i.kind, i.owner, i.value = "specified", "user", value.strip()
        i.why = "corrected at the prompt"
        corrected.append(i.name)
        say(f"  answered   {i.name} -> {i.value}")
    return corrected


def ask_specified(session, name, why, kind="specified", options=""):
    """
    A Specified input: a different answer changes WHAT WE ARE BUILDING.

    Asked immediately rather than batched into the proposal. The skill batches
    them because in a chat interface the run is stopping anyway and the round
    trip is the cost; here the process is alive, so asking early is strictly
    better -- the rest of the probe then runs against the real value instead of
    a placeholder. A static margin discovered at turn 3 should not be guessed
    for twenty more turns.
    """
    # The SAME validator `propose` runs, at the moment of asking rather than
    # twenty turns later. It catches two things here. A `derivable` admitted as
    # such is refused outright -- that is rule 4, and the model has just told us
    # it could compute the answer. And `why` is held to rule 8's ten words now,
    # rather than after the whole proposal is assembled around it.
    Input(name=name, kind=kind, owner="user", value=None, why=why)

    body = f"  {name}\n  {why}"
    if options:
        body += f"\n  options: {options}"
    answer = _prompt("SPECIFIED INPUT NEEDED", body,
                     "answer, or 'you decide'")
    session.record_answer(name, answer)
    if answer.lower() in DELEGATED:
        return ("Delegated. Decide it yourself if it is answerable in a "
                "sentence, and record it with owner='agent' and your reason. "
                "If answering it needs computation, it is a question in its own "
                "right: probe it, answer it, then come back to the original.")
    return f"The user answered: {answer}"


def consult(session, question, why):
    """Open-ended guidance. Not a Specified input, not a route decision."""
    if session.consults_left <= 0:
        return ("Consult budget spent. Decide it yourself and say so in the "
                "proposal's rationale.")
    session.consults += 1
    answer = _prompt("GUIDANCE", f"  {question}\n  ({why})",
                     f"your view ({session.consults_left} left)")
    return f"The user said: {answer}"


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

    unasked = [i.name for i in proposal.inputs
               if i.kind == "specified" and i.owner == "user"
               and i.name not in session.asked]
    if unasked:
        raise ValueError(
            f"These are recorded as Specified with owner='user' but were never "
            f"put through ask_specified: {', '.join(unasked)}. Ask them, or "
            f"record owner='agent' with your reason if you decided them.")

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
    # done here for the same reason `carry_queue` is merged below, because a
    # model asked to copy a list forward will sometimes improve it instead.
    recorded = {i.name for i in proposal.inputs}
    for name, value in session.asked.items():
        if name in recorded:
            continue
        delegated = str(value).strip().lower() in DELEGATED
        proposal.inputs.append(Input(
            name=name, kind="specified",
            owner="agent" if delegated else "user",
            value=None if delegated else str(value),
            why="delegated by the user" if delegated else "asked during the probe"))

    # Questions owed from an earlier ask, appended without disturbing any the
    # model added itself. Done here rather than in the prompt because it is
    # bookkeeping, and a model asked to copy a list forward will sometimes
    # improve it instead.
    for q in session.carry_queue:
        if q not in proposal.queue:
            proposal.queue.append(q)

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
        f"  continue  uv run --group nb python -m nb write {notebook.root.name}",
        "─" * 72,
        "",
    ])
