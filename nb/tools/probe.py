"""
probe -- run a question against the chapter's model.

Takes a QUESTION, not code. That is the whole point: `_notebook.py` installs
SOLVE_BUDGET as the default on asb.Opti.solve, and a probe that wrote
`import aerosandbox` directly would run outside it. A budget the model can skip
by forgetting is not a budget, so the preamble is injected rather than asked for.

Writes `_scratch/_nb_probe.py` rather than `_scratch/probe.py`: the latter is the
name a PERSON uses for their own scratch file, and clobbering it mid-session
would be its own small disaster. Nothing scaffolds it any more -- it is simply a
name this tool stays off. The leading underscore keeps ours out of project
renders, like everything else in `_scratch/`.
"""

import os
import subprocess
import textwrap
import time

from .. import budgets
from ..log import say
from ..text import tail

PREAMBLE = (
    "# Written by `nb`. The chapter is loaded and the solve budget is armed.\n"
    "from _probe_base import *  # noqa: F403,F401\n"
    "\n"
)


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

    scratch = notebook.scratch
    scratch.mkdir(parents=True, exist_ok=True)
    script = scratch / "_nb_probe.py"
    script.write_text(PREAMBLE + textwrap.dedent(question).strip() + "\n")

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
            say(f"  budget    probe pool EXHAUSTED — "
                f"{session.probe_pool:.0f} s spent; forcing a proposal")
            return ("probe pool exhausted -- this run has spent all the probe "
                    "wall clock it was given. Propose now with what you have, "
                    "and say in `rationale` what you did not get to.")
        if granted:
            env["NB_PROBE_BUDGET"] = f"{granted:.1f}"
            timeout = budgets.probe_wall_clock(granted)

    started = time.perf_counter()
    try:
        r = subprocess.run(["uv", "run", "python", script.name],
                           cwd=scratch, env=env, capture_output=True,
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
