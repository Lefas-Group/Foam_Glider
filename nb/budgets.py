"""
What an entry is allowed to cost, and what it actually cost.

Five layers bound a solve, only two of which live here:

  1  SOLVE_BUDGET       in the notebook's `_notebook.py`, wrapping every
                        opti.solve. Load-bearing, and why `probe` injects the
                        scratch preamble rather than taking free-standing code.
  2  budget()           hand-written Python loops only. Cannot stop a C call.
  3  PROBE_BUDGET       `_notebook.py`'s own watchdog, os._exit(9) at 300 s
                        (or PROBE_BUDGET_CHAPTER). Knows why it killed a probe.
  4  subprocess timeout ours, set ABOVE the watchdog so layer 3 speaks first.
  5  ENTRY_CEILING      the whole entry, checked after the fact by lint rule 17.

A signal cannot stop a CasADi solve -- it lands when the C call returns, 1.15 s
measured against a 0.3 s limit. Killing the process can, at the cost of whatever
was in memory, which is why layers 1 and 3 come first and layer 4 is a backstop.
"""

import re

from .config import DEFAULT_ENTRY_CEILING

# `aero: 3 solve(s), 12.4 s, 4133 ms each` -- the trailing clause is omitted at
# zero calls, so it is not part of the match.
AERO_LINE = re.compile(r"^aero: (\d+) solve\(s\), ([\d.]+) s", re.M)

# A bare module-level literal in the chapter's `_budget.py`, not computed.
CEILING = re.compile(r"^ENTRY_CEILING\s*=\s*([\d.]+)", re.M)
SOLVE = re.compile(r"^SOLVE_BUDGET\s*=\s*([\d.]+|None)", re.M)
PROBE = re.compile(r"^PROBE_BUDGET_CHAPTER\s*=\s*([\d.]+)", re.M)


def aero_cost(stdout):
    """
    (solves, seconds) across every aero_report() in a probe's output.

    Summed rather than read once: aero_report resets by default, so a probe that
    prints it per section reports per-section cost. Summing gets the total back
    without asking the probe to remember `reset=False`.
    """
    hits = AERO_LINE.findall(stdout or "")
    return sum(int(n) for n, _ in hits), sum(float(s) for _, s in hits)


def _budget_file(notebook, chapter):
    p = notebook.chapters_dir / chapter / "_budget.py"
    return p.read_text() if p.exists() else ""


def entry_ceiling(notebook, chapter):
    """
    The chapter's ENTRY_CEILING, or None where it declared none.

    Best-effort by design. Only chapters that need a raised ceiling write a
    `_budget.py`, and `_notebook.py`'s DEFAULT_ENTRY_CEILING is documented but
    never read by any code -- so absence means unbounded here, and lint rule 17
    stays the real check.
    """
    m = CEILING.search(_budget_file(notebook, chapter))
    return float(m.group(1)) if m else None


def probe_wall_clock(notebook, chapter):
    """Our subprocess timeout: the chapter's own watchdog, plus headroom."""
    m = PROBE.search(_budget_file(notebook, chapter))
    watchdog = float(m.group(1)) if m else 300.0   # _notebook.py's PROBE_BUDGET
    return watchdog + 60.0


def describe(notebook, chapter):
    """One line for the run log, so the budget in force is visible."""
    txt = _budget_file(notebook, chapter)
    solve = SOLVE.search(txt)
    ceiling = entry_ceiling(notebook, chapter)
    return (f"{chapter}: solve={solve.group(1) if solve else 'default'} "
            f"ceiling={ceiling if ceiling else 'unbounded'} "
            f"probe_timeout={probe_wall_clock(notebook, chapter):.0f}s")
