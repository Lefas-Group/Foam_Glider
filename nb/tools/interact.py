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
    tell(f"\n{'─' * 72}\n{banner}\n{'─' * 72}")
    tell(body)
    tell(f"\n{hint}")
    sys.stdout.write("> ")
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
        raise SystemExit(
            "\n  stdin closed with a question outstanding. `nb ask` needs a "
            "terminal:\n  a Specified input is asked every time, never assumed.")
    return line.strip()


def ask_pool(default):
    """
    How much probe wall clock this question may spend, asked once.

    Deliberately NOT `_prompt`, which raises on EOF and on a blank line because
    "a Specified input is asked every time, never assumed". That rule is about
    inputs that change WHAT IS BEING BUILT, where a default would be a silent
    design decision. A spend cap is not one: it changes only how long a wrong
    turn is allowed to run, it has a defensible default, and a coordinator that
    pipes a question and nothing else should get that default rather than a
    dead run. So both EOF and Enter fall through to `default`.

    The pool covers the whole QUESTION -- ask, write, and anything the queue
    adds -- not one phase. Before this, each phase claimed its own, so a single
    question could spend twice what the constant said and a queue of four could
    spend eight times.
    """
    tell(f"\n{'─' * 72}\nPROBE TIME POOL\n{'─' * 72}")
    tell("  Total probe wall clock for this question, in seconds. The agent\n"
         "  divides it across its own probes. Enter accepts the default.\n")
    sys.stdout.write(f"  [{default:.0f}] > ")
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        raise SystemExit("cancelled at the prompt")
    try:
        value = float(line.strip())
    except ValueError:
        return default            # EOF, Enter, or something that is not a number
    return value if value > 0 else default


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
    answer = _prompt(f"SPECIFIED INPUT NEEDED", body,
                     "Your answer (or 'you decide' to delegate it):")
    session.record_answer(name, answer)
    if answer.lower() in ("you decide", "your call", "you choose", ""):
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
    answer = _prompt("GUIDANCE", f"  {question}\n  (asking because: {why})",
                     f"Your view ({session.consults_left} consult(s) left):")
    return f"The user said: {answer}"


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
        "  Why you: every later entry in the chapter builds on its _model.py,",
        "  and changing it afterwards means re-solving all of them to prove",
        "  the answers held. That is the commitment, not this one entry.",
        "",
        f"  proposal  {notebook.proposal_path}",
        f"  continue  python -m nb write {notebook.root.name}",
        "─" * 72,
        "",
    ])
