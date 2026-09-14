"""
What a probe actually cost, and how long one may run.

Four layers bound a solve, only one of which lives here:

  1  SOLVE_BUDGET       declared by the ENTRY and installed as the default on
                        asb.Opti.solve by `_notebook.py`. Load-bearing, and why
                        `probe` injects the scratch preamble rather than taking
                        free-standing code: a budget the model can skip by
                        forgetting is not a budget.
  2  PROBE_BUDGET       `_notebook.py`'s own watchdog, os._exit(9) at the grant
                        in $NB_PROBE_BUDGET, else 300 s. Knows why it killed a
                        probe, and says so.
  3  subprocess timeout probe_wall_clock() below, set ABOVE layer 2 so that
                        watchdog speaks first -- a timeout only knows that time
                        ran out.
  4  ENTRY_CEILING      granted by the user at the prompt. Drives an actual
                        render deadline (`lint.render_deadline`), and is checked
                        against the recorded seconds afterwards by rule 17.

A signal cannot stop a CasADi solve -- it lands when the C call returns, 1.15 s
measured against a 0.3 s limit. Killing the process can, at the cost of whatever
was in memory, which is why layers 1 and 2 come first and layer 3 is a backstop.

This module used to read a chapter's `_budget.py` for all of the above. That file
is gone: budgets belong to the entry, so the ceiling comes from the session's
grant and the probe timeout from the grant for that probe.
"""

import re

# `aero: 3 solve(s), 12.4 s, 4133 ms each` -- the trailing clause is omitted at
# zero calls, so it is not part of the match.
AERO_LINE = re.compile(r"^aero: (\d+) solve\(s\), ([\d.]+) s", re.M)

# Headroom over the watchdog. It polls every 15 s, so it can overrun its own
# grant by up to that much before firing; 60 s clears that with room for the
# interpreter to start and the preamble to exec.
WATCHDOG_HEADROOM = 60.0
DEFAULT_PROBE_BUDGET = 300.0        # _notebook.py's PROBE_BUDGET


def aero_cost(stdout):
    """
    (solves, seconds) across every aero_report() in a probe's output.

    Summed rather than read once: aero_report resets by default, so a probe that
    prints it per section reports per-section cost. Summing gets the total back
    without asking the probe to remember `reset=False`.
    """
    hits = AERO_LINE.findall(stdout or "")
    return sum(int(n) for n, _ in hits), sum(float(s) for _, s in hits)


def probe_wall_clock(granted=None):
    """
    Our subprocess timeout for one probe: its own watchdog, plus headroom.

    Takes the GRANT rather than a chapter. The watchdog inside the probe honours
    $NB_PROBE_BUDGET, which is what the agent asked for out of the pool, so a
    15 s probe is killed at ~15 s and has no business holding a 360 s subprocess
    timeout -- which is what it got while this read a chapter-level file that no
    longer exists.
    """
    watchdog = DEFAULT_PROBE_BUDGET if not granted else float(granted)
    return watchdog + WATCHDOG_HEADROOM
