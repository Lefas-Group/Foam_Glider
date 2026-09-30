"""
What a probe actually cost, and how long one may run.

Three layers bound a solve, only one of which lives here:

  1  SOLVE_BUDGET       declared by the ENTRY and installed as the default on
                        asb.Opti.solve by `_notebook.py`. Load-bearing, and why
                        `probe` loads the chapter for the model rather than
                        taking free-standing code: a budget the model can skip
                        by forgetting is not a budget.
  2  probe deadline     probe_wall_clock() below, held by `kernel.py`, which
                        kills the kernel at the grant. Knows why it killed a
                        probe, and says so.
  3  ENTRY_CEILING      granted by the user at the prompt. Drives an actual
                        render deadline (`lint.render_deadline`), and is checked
                        against the recorded seconds afterwards by rule 17.

There were four. Layer 2 used to be a watchdog thread INSIDE the probe, calling
os._exit(9), with a subprocess timeout stacked above it as a backstop -- two
timers and an env var between them, because the process that had to die and the
code that knew the pool were different processes. Probes run in the run's
kernel now, so one timer in `nb` does both jobs.

What has not changed is why the stop is a kill rather than a signal: a signal
cannot stop a CasADi solve -- it lands when the C call returns, 1.15 s measured
against a 0.3 s limit. Killing the process can, at the cost of whatever was in
memory. That cost is now the kernel's namespace, which is exactly why a killed
probe restarts it rather than resuming into one whose state nobody can vouch
for.

This module used to read a chapter's `_budget.py` for all of the above. That file
is gone: budgets belong to the entry, so the ceiling comes from the session's
grant and the probe timeout from the grant for that probe.
"""

import re

# `aero: 3 solve(s), 12.4 s, 4133 ms each` -- the trailing clause is omitted at
# zero calls, so it is not part of the match.
AERO_LINE = re.compile(r"^aero: (\d+) solve\(s\), ([\d.]+) s", re.M)

DEFAULT_PROBE_BUDGET = 300.0        # what an ungranted probe may take


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
    The deadline for one probe: exactly what was granted.

    It used to add 60 s of headroom, because it bounded a subprocess sitting
    above a watchdog thread that polled every 15 s and needed room to fire and
    speak first. There is one timer now and it is this one, so headroom would
    only be time the pool was charged for and the model was not told about.

    Kernel startup is NOT in here. It happens once per run, not once per probe,
    and `kernel.STARTUP_S` bounds it separately -- charging the first probe for
    loading the chapter would make its `budget_s` estimate wrong for every probe
    after it.
    """
    return DEFAULT_PROBE_BUDGET if not granted else float(granted)
