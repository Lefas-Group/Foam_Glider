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

from ..loop import Terminal
from ..schema import Proposal


def _prompt(banner, body, hint):
    print(f"\n{'─' * 72}\n{banner}\n{'─' * 72}")
    print(body)
    print(f"\n{hint}")
    sys.stdout.write("> ")
    sys.stdout.flush()
    try:
        line = sys.stdin.readline()
    except KeyboardInterrupt:
        print()
        raise SystemExit("cancelled at the prompt")
    if line == "":
        # EOF. There is deliberately no unattended mode: a Specified input is
        # asked every time, so with nobody to ask the run stops rather than
        # assuming. Failing loudly here is the whole point of the rule.
        raise SystemExit(
            "\n  stdin closed with a question outstanding. `nb ask` needs a "
            "terminal:\n  a Specified input is asked every time, never assumed.")
    return line.strip()


def ask_specified(session, name, why, options=""):
    """
    A Specified input: a different answer changes WHAT WE ARE BUILDING.

    Asked immediately rather than batched into the proposal. The skill batches
    them because in a chat interface the run is stopping anyway and the round
    trip is the cost; here the process is alive, so asking early is strictly
    better -- the rest of the probe then runs against the real value instead of
    a placeholder. A static margin discovered at turn 3 should not be guessed
    for twenty more turns.
    """
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

    # Measured, not guessed: aero_report() prints the solves the probe just ran.
    proposal.render_cost_s = round(session.solve_seconds, 1)

    session.notebook.run.mkdir(parents=True, exist_ok=True)
    session.notebook.proposal_path.write_text(
        json.dumps(proposal.model_dump(), indent=2) + "\n")
    raise Terminal(proposal)


def render_proposal(proposal, notebook):
    """What the gate shows: the title, the figures, and the cost. Nothing else."""
    out = [
        "",
        "═" * 72,
        "PROPOSAL",
        "═" * 72,
        f"  title     {proposal.title}",
        f"  chapter   {proposal.chapter}" +
        ("   [NEW CHAPTER]" if proposal.route == "new_chapter" else ""),
        f"  cost      {proposal.render_cost_s:.1f} s of solves",
    ]
    if proposal.figures:
        for f in proposal.figures:
            out.append(f"  figure    {f}")
    else:
        out.append("  figure    none")
    if proposal.inputs:
        out.append("")
        for i in proposal.inputs:
            out.append(f"  {i.kind:9s} {i.name} = {i.value}  ({i.owner}: {i.why})")
    if proposal.queue:
        out.append("")
        out.append(f"  {len(proposal.queue)} further question(s) queued:")
        out += [f"      {q}" for q in proposal.queue]
    out += [
        "",
        f"  written to {notebook.proposal_path}",
        "",
        "  Review it, edit it if you like, then:  nb write "
        f"{notebook.root.name}",
        "═" * 72,
        "",
    ]
    return "\n".join(out)
