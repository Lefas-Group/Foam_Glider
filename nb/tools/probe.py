"""
probe -- run a question against the chapter's model.

Takes a QUESTION, not code. That is the whole point: `_notebook.py` installs
SOLVE_BUDGET as the default on asb.Opti.solve, and a probe that wrote
`import aerosandbox` directly would run outside it. A budget the model can skip
by forgetting is not a budget, so the chapter is loaded for it rather than by it.

RUNS IN THE RUN'S KERNEL, so names outlive the probe that made them. That is
`kernel.py`'s job and its docstring carries the reasoning; what matters here is
what it changed in this file. Gone: writing `_scratch/runs/<id>/probe.py` and
spawning `uv run python` over it, the stdin=DEVNULL guard that a background run
needed to avoid SIGTTIN, the subprocess timeout stacked above an in-process
watchdog, and the salvage branch that tried to recover output from a killed
probe -- iopub has already delivered it.

Unchanged, because they operate on the output and the session rather than on how
the code ran: the inputs notice, the scope hint, the budget line, the
ENTRY_CEILING notice, and `budgets.aero_cost`.
"""

import textwrap

from . import kernel
from .. import budgets
from ..log import say
from ..text import tail


def _inputs_notice(notebook, chapter):
    """
    What this chapter has already been given, ITEM BY ITEM, and the one
    question about it.

    Asking is voluntary and stopped happening: `ask_specified` fired in 3 of 8
    recorded runs and half of them declared no inputs at all. The model
    is poor at judging WHETHER to ask and fine at reading a list, so this turns
    the judgement into a lookup and puts it where the lookup is cheap.

    IT USED TO SEND ONLY A COUNT -- "this chapter declares 1 Specified and 2
    Assumed item(s)" -- which asks the model to decide which of three things
    its question changes without showing it the three things. They are in the
    prefix, but "go and find them" is the step that does not happen. The items
    are 40 tokens; they ride a tool result the run was getting anyway.

    The IDS are here because they are the handle: `ask_specified(replaces=...)`
    takes one, and so does `_fork.yml`'s `replaces:`.

    Says nothing when the chapter declares nothing -- a notice with no items in
    it is furniture.
    """
    from ..inputs import committed
    if not chapter:
        return ""
    rows = committed(notebook, chapter)
    if not rows:
        return ""
    # `where` is the handle already: what `ask_specified(replaces=...)` and
    # `_fork.yml`'s `overwrites:` both take, prefixed by the ancestor when the
    # item is inherited rather than this chapter's own. `short` keeps an id
    # whole -- it IS the handle, and `foam-thick` is not one -- and reduces an
    # entry stem to its date, which places it against the entries the prefix
    # already lists.
    from ..inputs import short
    listing = "\n".join(
        f"    [{k}] {t}" + (f"   ({h})" if h else "")
        for k, t, w in rows for h in [short(w, chapter)])
    return (f"\n[chapters/{chapter} is already committed to these -- from its "
            f"_inputs.yml and from the entries already written in it. Every "
            f"entry here inherits them and none restates them:\n\n{listing}\n\n"
            f"Does THIS question change one of them? A changed SPECIFIED item "
            f"is `ask_specified` now, before the next probe, with "
            f"`replaces=\"<id>\"` where one is shown. A changed ASSUMED item is "
            f"yours: assume the new value, `declare_input` it with "
            f"source='guessed', and say which it replaces in the entry. "
            f"Changing none of them is the common answer and needs nothing -- "
            f"and asking again for one already listed is the mistake this "
            f"exists to prevent.]")


# The chapter's modules, as a probe keeps trying to import them.
_SCOPE_MODULES = ("_analysis", "_model", "_notebook")


def _scope_hint(out):
    """
    One line appended to a failed probe that tried to IMPORT the chapter, or
    referenced one of its names as though it had.

    Measured 2026-09-29: three of the four opening turns across two runs, on two
    different models, were lost to `ModuleNotFoundError: No module named
    '_analysis'`. The rule is already stated twice -- in this tool's own schema
    ("The chapter's names are in scope; do not import it") and as rule 29 -- and
    was ignored both times. A third statement of a rule that is already present
    and already ignored is not a fix; saying it at the moment it is violated is,
    because that is when the model is looking.

    Deliberately NOT a rewrite of the traceback: the traceback is the evidence,
    and a tool that edits what the interpreter said teaches the model to
    distrust its own output.
    """
    if not any(f"'{m}'" in out or f"named {m}" in out for m in _SCOPE_MODULES):
        return ""
    return ("\n[the chapter is already exec'd into this probe -- `_model.py` and "
            "`_analysis.py` are NOT importable modules here (rule 29). Drop the "
            "import and use the name directly; `api()` at the top of the probe "
            "output lists what is in scope.]")


def run_probe(notebook, chapter, question, session=None, budget_s=None,
              reset=False):
    """Execute `question` as Python with the chapter preloaded. Returns stdout."""
    # Refused before a kernel is started, not defaulted around. The old
    # bootstrap fell back to the first chapter alphabetically and said so only
    # on stderr, which is how a probe comes to answer confidently about the
    # wrong aircraft; `probe_init` therefore has no fallback at all, and this is
    # the check that lets it have none.
    known = notebook.chapters()
    if chapter not in known:
        return (f"no chapter {chapter!r}. Pass one of: {', '.join(known)}.\n"
                f"The chapter decides which model is loaded, so it is never "
                f"optional and never guessed.")

    # Fallback only: with a session the grant below tightens this.
    deadline = budgets.probe_wall_clock()

    granted = None
    if session is not None:
        granted, left = session.take_probe_budget(budget_s)
        if granted is not None and left is not None and left <= 0:
            # THE WAY OUT DIFFERS by whether the entry is open, and naming the
            # wrong one is worse than naming none: "propose now" was once sent
            # to a run in the write phase, which had no such tool, twice. The
            # test used to be the phase; there is one phase now, so it is the
            # thing the phase stood for -- has `open_entry` run.
            writing = bool(session.stem)
            say(f"  budget    probe pool EXHAUSTED — "
                f"{session.probe_pool:.0f} s spent; "
                f"{'no more probing' if writing else 'open the entry'}")
            if writing:
                return ("probe pool exhausted -- the whole question's probe "
                        "wall clock is spent, and writing shares one pool with "
                        "the probing that preceded it. There is no more "
                        "probing to be had. Work from the entry, the chapter's "
                        "files and the render output; if you genuinely cannot "
                        "proceed without measuring something, say so with "
                        "`ask_specified`.")
            return ("probe pool exhausted -- this run has spent all the probe "
                    "wall clock it was given. Call `open_entry` now with what "
                    "you have, and say in the entry what you did not get to.")
        if granted:
            deadline = budgets.probe_wall_clock(granted)

    out, restarted, used = kernel.probe(notebook, chapter,
                                        textwrap.dedent(question).strip(),
                                        deadline, reset=reset)
    # FIRST, before a line of output. Everything below it was computed in a
    # namespace that did not exist a moment ago, and a restart the model reads
    # AFTER the numbers is a restart it has already drawn conclusions past.
    if restarted:
        out = (f"[kernel restarted -- {restarted}. Nothing is held from earlier "
               f"probes; anything this probe needed from one is gone.]\n" + out)
    # A traceback is an ordinary result here -- the kernel survives it and the
    # names it had are still there -- so there is no exit status to report. The
    # scope hint still fires on the one it exists for.
    if "Traceback" in out or "Error" in out:
        out += _scope_hint(out)

    if session is not None:
        session.record_probe(used)
        # ONCE, after the first probe. Not before probing, where the model has
        # not loaded the chapter and is being asked to classify inputs at the
        # moment it knows least; and not at the end, where the pool may be
        # spent and the whole probe already ran against a placeholder. By here
        # it has loaded the vehicle and run one query against it, and has spent
        # one probe rather than all of them.
        #
        # It costs NO TURN, because it rides a tool result the run was getting
        # anyway -- the same shape as the ENTRY_CEILING notice below, which
        # already tells the model to go and ask.
        if session.probes == 1 and not session.stem:
            notice = _inputs_notice(notebook, chapter or session.chapter)
            out += notice
            # AND TO THE LOG. The notice goes to the model inside a tool
            # result, which `status.log` does not carry and `transcript.jsonl`
            # does not either -- that file records model turns, not what was
            # handed to them. So in the first live run there was no way to
            # confirm it had fired at all, which is how a prompt silently stops
            # working. The budget line beside it has said both all along.
            if notice:
                say(f"  inputs    put {len(notice.splitlines())} line(s) of "
                    f"chapters/{chapter}'s commitments to the model — once, "
                    f"on the first probe")
        left = session.probe_left
        if left is not None:
            # To the MODEL, so the next `budget_s` is informed rather than
            # guessed. Reported after the probe ran, because "used" is the half
            # that tells it whether its own estimate was any good.
            out += (f"\n[probe budget: {granted:.0f} s granted, "
                    f"{used:.0f} s used; {left:.0f} s of the run's pool left. "
                    f"Budget the next probe with `budget_s`.]")
            # And to the TERMINAL. The turn line above says a probe ran; it
            # cannot say what it cost, because `on_turn` fires before the
            # handler does. This is the only place that knows all three numbers.
            say(f"  budget    probe {granted:.0f} s granted · {used:.0f} s used"
                f" · {left:.0f} s of {session.probe_pool:.0f} s pool left")
        solves, seconds = budgets.aero_cost(out)
        session.record_cost(solves, seconds)
        # The ceiling in force is the one the USER granted at the prompt, not
        # anything the chapter carries -- chapters no longer carry budgets.
        ceiling = session.render_ceiling
        if ceiling and session.solve_seconds > ceiling:
            out += (f"\n[ENTRY_CEILING: {session.solve_seconds:.0f} s of solves "
                    f"already, against the {ceiling:.0f} s granted for this "
                    f"entry's render. Open the entry now with what you have, "
                    f"or ask_specified whether to raise it -- that is the "
                    f"user's call, and the entry records the answer.]")

    # WHAT THE KERNEL IS HOLDING, last, because it is the line that decides
    # whether any of this pays for itself. The saving is model-directed: a
    # kernel that carries `s1_orig` forward buys nothing if the next probe
    # re-solves for it anyway, and the model has no other way to know the
    # namespace survived. Naming the cost -- a solve -- rather than the
    # mechanism, because that is the part it is budgeting against.
    #
    # A RESTART IS SAID FIRST AND SEPARATELY. Everything above it was computed
    # in a namespace that no longer exists, and a restart the model cannot see
    # is a result it cannot trust.
    names = kernel.held(notebook)
    if names:
        shown = ", ".join(names[:8])
        more = f" (+{len(names) - 8} more)" if len(names) > 8 else ""
        out += (f"\n[kernel holds {len(names)} name(s) from earlier probes in "
                f"this run: {shown}{more}. Reuse them -- re-deriving one costs "
                f"its solves again. `reset=True` starts clean.]")

    return tail(out)
