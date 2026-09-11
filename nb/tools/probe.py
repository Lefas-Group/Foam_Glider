"""
probe -- run a question against the chapter's model.

Takes a QUESTION, not code. That is the whole point: `_notebook.py` installs
SOLVE_BUDGET as the default on asb.Opti.solve, and a probe that wrote
`import aerosandbox` directly would run outside it. A budget the model can skip
by forgetting is not a budget, so the preamble is injected rather than asked for.

Writes `_scratch/_nb_probe.py` rather than `_scratch/probe.py`: the latter is the
human's own scratch file, gitignored but very much in use. The leading underscore
keeps it out of project renders, like everything else in `_scratch/`.
"""

import os
import subprocess
import textwrap

from .. import budgets
from ..text import tail

PREAMBLE = (
    "# Written by `nb`. The chapter is loaded and the solve budget is armed.\n"
    "from _probe_base import *  # noqa: F403,F401\n"
    "\n"
)


def run_probe(notebook, chapter, question, session=None):
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
    timeout = budgets.probe_wall_clock(notebook, chapter)

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
        out = got + f"\n[killed at {timeout:.0f}s -- outlived the chapter watchdog]"

    if session is not None:
        solves, seconds = budgets.aero_cost(out)
        session.record_cost(solves, seconds)
        ceiling = budgets.entry_ceiling(notebook, chapter)
        if ceiling and session.solve_seconds > ceiling:
            out += (f"\n[ENTRY_CEILING: {session.solve_seconds:.0f} s of solves "
                    f"against this chapter's {ceiling:.0f} s ceiling. Propose now, "
                    f"or ask_specified whether to raise it -- that is a human call, "
                    f"recorded in index.qmd.]")

    return tail(out)
