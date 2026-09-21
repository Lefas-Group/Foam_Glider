"""
probe -- run a question against the chapter's model.

Takes a QUESTION, not code. That is the whole point: `_notebook.py` installs
SOLVE_BUDGET as the default on asb.Opti.solve, and a probe that wrote
`import aerosandbox` directly would run outside it. A budget the model can skip
by forgetting is not a budget, so the preamble is injected rather than asked for.

Writes into the RUN's own directory, `_scratch/runs/<id>/probe.py`, and runs
with that as the cwd. It used to be one shared `_scratch/_nb_probe.py`, written
and then executed -- so two agents probing within a second of each other and one
would run the other's code, attribute the answer to the wrong question, and say
nothing. A per-run path removes the race without a lock: a probe reads the
chapter's files and writes only here.

The cwd matters as much as the path. A probe that saves a figure writes a
relative filename, so it lands beside its own script rather than in a shared
`_scratch/`. `_probe_base`'s `sys.path` insert is absolute, so it survives the
move.
"""

import os
import subprocess
import textwrap
import time

from .. import budgets
from ..log import say
from ..text import tail

# `_probe_base` lives in `_scratch/`, one level above the run directory the
# script now sits in, so it has to be put on the path explicitly -- the cwd no
# longer finds it. Absolute, because the probe's own cwd is the run directory
# and a relative hop would break the moment anything changed it.
PREAMBLE = (
    "# Written by `nb`. The chapter is loaded and the solve budget is armed.\n"
    "import sys; sys.path.insert(0, {scratch!r})\n"
    "from _probe_base import *  # noqa: F403,F401\n"
    "\n"
)


def _inputs_notice(notebook, chapter):
    """
    What this chapter has already been given, and the one question about it.

    Asking is voluntary and stopped happening: `ask_specified` fired in 3 of 8
    recorded runs and half the proposals declared no inputs at all, which meant
    `confirm_assumptions` returned early and the correction loop behind it never
    ran. The model is poor at judging WHETHER to ask and fine at reading a list,
    so this turns the judgement into a lookup and puts it where the lookup is
    cheap.

    Says nothing when the chapter declares nothing -- two of thirteen chapters
    written so far, both predating the callouts. A notice with no numbers in it
    is furniture.
    """
    from ..inputs import declared
    if not chapter:
        return ""
    spec, asm = declared(notebook, chapter)
    if not (spec or asm):
        return ""
    return (f"\n[This chapter declares {spec} Specified and {asm} Assumed "
            f"item(s), in chapters/{chapter}/index.qmd. Which does THIS "
            f"question change? A changed Specified item is `ask_specified`, "
            f"now, before the next probe -- not saved for the proposal. A new "
            f"assumption is yours to make and to record. Neither is a reason "
            f"to re-state the ones you inherit.]")


def run_probe(notebook, chapter, question, session=None, budget_s=None):
    """Execute `question` as Python with the chapter preloaded. Returns stdout."""
    # `_probe_base` falls back to the first chapter alphabetically when
    # NB_CHAPTER is unset, and says so only on stderr. Swallowed into tool
    # output that is easy to miss, which is how a probe comes to answer
    # confidently about the wrong aircraft. Refuse instead.
    known = notebook.chapters()
    if chapter not in known:
        return (f"no chapter {chapter!r}. Pass one of: {', '.join(known)}.\n"
                f"The chapter decides which model is loaded, so it is never "
                f"optional and never guessed.")

    run_dir = notebook.run
    run_dir.mkdir(parents=True, exist_ok=True)
    script = notebook.probe_script
    script.write_text(PREAMBLE.format(scratch=str(notebook.scratch))
                      + textwrap.dedent(question).strip() + "\n")

    env = dict(os.environ, NB_CHAPTER=chapter)
    # Fallback only: with a session the grant below tightens this. One place
    # owns the headroom over the watchdog.
    timeout = budgets.probe_wall_clock()

    # The run's pool, divided by the agent. `_notebook.py` reads
    # NB_PROBE_BUDGET ahead of the chapter's own limit, so the watchdog inside
    # the probe enforces exactly what was granted -- and our subprocess timeout
    # sits above it, so the watchdog still gets to say WHY it killed something.
    granted = None
    if session is not None:
        granted, left = session.take_probe_budget(budget_s)
        if granted is not None and left is not None and left <= 0:
            # PHASE-SPECIFIC, because the way out differs and naming the wrong
            # one is worse than naming none. "Propose now" in the write phase
            # points at a tool that does not exist there -- seen in a run whose
            # write phase inherited 13 s of pool, exhausted it on the second
            # probe, and was told twice to do something it could not.
            writing = getattr(session, "phase", None) == "write"
            say(f"  budget    probe pool EXHAUSTED — "
                f"{session.probe_pool:.0f} s spent; "
                f"{'no more probing' if writing else 'forcing a proposal'}")
            if writing:
                return ("probe pool exhausted -- the whole question's probe "
                        "wall clock is spent, and the write phase shares one "
                        "pool with the probe that preceded it. There is no "
                        "more probing to be had. Work from the entry, the "
                        "chapter's files and the render output; if you "
                        "genuinely cannot proceed without measuring something, "
                        "say so with `ask_specified`.")
            return ("probe pool exhausted -- this run has spent all the probe "
                    "wall clock it was given. Propose now with what you have, "
                    "and say in `rationale` what you did not get to.")
        if granted:
            env["NB_PROBE_BUDGET"] = f"{granted:.1f}"
            timeout = budgets.probe_wall_clock(granted)

    started = time.perf_counter()
    try:
        # stdin=DEVNULL, deliberately. `capture_output` redirects stdout and
        # stderr and says nothing about stdin, so a probe inherited the
        # TERMINAL's -- and a background process group that reads the terminal
        # is sent SIGTTIN, which stops the whole group, this process included.
        # A run launched with `&` would then freeze mid-probe with no error,
        # no CPU, and a wall-clock timer still counting: observed once at
        # "15 s granted, 5596 s used".
        #
        # A probe has no business reading the operator's keyboard in any case.
        # DEVNULL turns "silently suspend the run" into "EOF", which anything
        # reading stdin already has to handle.
        r = subprocess.run(["uv", "run", "python", script.name],
                           cwd=run_dir, env=env, capture_output=True,
                           stdin=subprocess.DEVNULL,
                           text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            out += f"\n[exit {r.returncode}]"
    except subprocess.TimeoutExpired as e:
        # `_notebook.py`'s own watchdog should have fired first and said why;
        # reaching here means it did not. Partial output is still worth having.
        got = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
        out = got + (f"\n[killed at {timeout:.0f}s -- outlived the probe's own "
                     f"watchdog, which should have fired first and said why]")

    if session is not None:
        used = time.perf_counter() - started
        session.record_probe(used)
        # ONCE, after the first probe. Not before probing, where the model has
        # not loaded the chapter and is being asked to classify inputs at the
        # moment it knows least; and not at `propose`, where the pool may be
        # spent and the whole probe already ran against a placeholder. By here
        # it has loaded the vehicle and run one query against it, and has spent
        # one probe rather than all of them.
        #
        # It costs NO TURN, because it rides a tool result the run was getting
        # anyway -- the same shape as the ENTRY_CEILING notice below, which
        # already tells the model to go and ask.
        if session.probes == 1 and session.phase == "ask":
            notice = _inputs_notice(notebook, chapter or session.chapter)
            out += notice
            # AND TO THE LOG. The notice goes to the model inside a tool
            # result, which `status.log` does not carry and `transcript.jsonl`
            # does not either -- that file records model turns, not what was
            # handed to them. So in the first live run there was no way to
            # confirm it had fired at all, which is how a prompt silently stops
            # working. The budget line beside it has said both all along.
            if notice:
                say(f"  inputs    {notice.strip()[1:-1].split('.')[0]} — "
                    f"asked once, on the first probe")
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
        ceiling = getattr(session, "render_ceiling", None)
        if ceiling and session.solve_seconds > ceiling:
            out += (f"\n[ENTRY_CEILING: {session.solve_seconds:.0f} s of solves "
                    f"already, against the {ceiling:.0f} s granted for this "
                    f"entry's render. Propose now with what you have, or "
                    f"ask_specified whether to raise it -- that is the user's "
                    f"call, and the entry records the answer.]")

    return tail(out)
