# =============================================================================
# Notebook furniture. Not about any aircraft.
#
# One copy for the whole notebook, exec'd by every chapter's _model.qmd shim
# before the chapter's own files. Chapters differ in what they model and how
# they measure it; they do not differ in this, so it does not live in a chapter.
#
# Deliberately NOT listed anywhere in the rendered site: the chapter index
# prints _model.py and _analysis.py only, and api() filters to _analysis.py, so
# neither of these two functions appears in the notebook a reader sees. They are
# plumbing.
#
# The leading underscore keeps Quarto from rendering this file, as with _scratch/.
# =============================================================================
import contextlib
import inspect
import pathlib
import re
import signal
import threading
import time

import aerosandbox as asb
import matplotlib as mpl

# =============================================================================
# One plot style for the whole notebook.
#
# Set here rather than per entry, because a figure's job is to be read against
# the figures around it. Before this, every figure inherited raw matplotlib
# defaults and each width was chosen by hand, so fonts differed once matplotlib
# scaled them and nothing aligned down the page.
#
# C0 is the accent from styles.css, so a curve and the hero number above it are
# the same colour. C3 stays an alarm red -- entries use it for "past the stall",
# and a cycle that quietly reassigned it would repaint that meaning.
#
# NOT set here: `axes.grid` and spine visibility. Entries call ax.grid()
# themselves, and forcing either globally would also reach draw_three_view() and
# the two axis("off") layout figures, which are drawings rather than plots.
# =============================================================================
mpl.rcParams.update({
    "figure.figsize": (7.0, 3.2),
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 10,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "lines.linewidth": 1.8, "grid.alpha": 0.3, "grid.linewidth": 0.6,
    "axes.prop_cycle": mpl.cycler(color=[
        "#14655c",   # C0 teal -- matches --key-accent, the hero colour
        "#b8860b",   # C1 amber
        "#5c6670",   # C2 grey
        "#b3412c",   # C3 alarm red -- keeps its "past the stall" meaning
    ]),
})

# =============================================================================
# What the notebook costs to run.
#
# An AeroBuildup call costs about the same whether it is given one angle of
# attack or six hundred -- alpha is vectorized and rides along nearly free, and
# the price is set by spanwise strip count (5 strips on the BFG, 41 ms; 47 on
# the McEagle-300, 350 ms). So the number of CALLS is the only figure that
# predicts what an entry will cost to render, and a loop is where calls hide.
#
# Nothing counted them until this existed, which is how trim() came to spend
# sixty solves converging a fixed point that settles in twelve -- roughly twenty
# wasted seconds per call, at a dozen call sites, for as long as the chapter has
# existed. Freeze then made it invisible: _freeze/*/execute-results/html.json
# records `hash` and `result` and no timing at all, so once an entry is frozen
# its cost leaves no trace anywhere.
#
# Furniture rather than model: this is about the notebook's running cost, not
# about any aircraft. Keeping it here also keeps it out of the chapter index,
# which renders _model.py and _analysis.py in full -- a reader of the design
# wants the answer, not the bill.
# =============================================================================
aero_cost = {"calls": 0, "seconds": 0.0}


def aero_report(reset=True):
    """
    Print the aero solves run since this was last called, and what they cost.

    Terminal-facing, exactly like api(): _scratch/probe.py prints both on every
    run, which is the moment someone is about to write the helper that spends
    the solves. That is where the number is worth seeing -- not on a rendered
    page, and not in a profiler someone would have to think to reach for.

    Resets by default, so probes that print it repeatedly report per-section
    cost rather than a running total. Pass `reset=False` for the total.
    """
    calls, seconds = aero_cost["calls"], aero_cost["seconds"]
    each = f", {seconds / calls * 1e3:.0f} ms each" if calls else ""
    print(f"aero: {calls} solve(s), {seconds:.1f} s{each}")
    if reset:
        aero_cost.update(calls=0, seconds=0.0)


# =============================================================================
# What a solve is allowed to cost.
#
# aero_cost above records what was spent; this bounds it. The two failures that
# earned this both cost more than an hour: a solver flag that turned one solve
# into ten silent minutes, and a pair of orphaned benchmark processes that ran
# 35 minutes and quietly corrupted the timing they were measuring.
#
# The budget is installed as the DEFAULT on asb.Opti.solve rather than passed at
# each call site, because the thing being defended against is forgetting. Every
# ad-hoc probe in the session that motivated this was a shell heredoc rather
# than _scratch/probe.py -- but every one of them still exec'd this file, so a
# policy here reaches entries, probes and one-liners alike, and a policy in the
# probe scaffold would have reached none of them.
#
# OPT-IN PER CHAPTER, and silent otherwise. A chapter takes the budget by
# binding SOLVE_BUDGET in its _analysis.py; until it does, solve() is untouched
# and behaves exactly as the library ships it. That is what lets a budget be
# added to a notebook whose existing chapters are already frozen: chapters that
# never opted in cannot have their numbers moved by this file. Resolution is at
# CALL time, not import time, because _analysis.py is exec'd into this same
# namespace after this file has already run.
#
# behavior_on_failure="return_last" rides along with the budget and only with
# it: a bound that raises destroys the finding, while one that returns the best
# iterate degrades it into something an entry can report and caveat.
#
# THE BOUND IS COARSE, and pretending otherwise would mislead. IPOPT tests it at
# iteration boundaries only, and an iteration here is mostly OUR function
# evaluations -- NeuralFoil through CasADi -- which max_cpu_time does not even
# count. Measured on chapter 01: a 0.05 s cpu budget still took 3.91 s of wall,
# and a 1.0 s wall budget took 4.89 s. So overshoot is about one iteration, which
# is seconds, not milliseconds. Both limits are set because they fail
# differently: max_cpu_time misses time spent in our callbacks, max_wall_time
# does not, and neither can stop an iteration already in flight. Read the budget
# as "stop at the first iteration boundary past here" -- ample against a 599 s
# runaway, useless as a precise deadline.
# =============================================================================
DEFAULT_SOLVE_BUDGET = 60.0  # seconds per solve; what a new chapter should bind


class BudgetExceeded(RuntimeError):
    """A guarded Python loop ran past its wall-clock budget."""


def _active_budget():
    """The chapter's SOLVE_BUDGET if it took one, else None for unbounded."""
    return globals().get("SOLVE_BUDGET")


@contextlib.contextmanager
def budget(seconds=None, what="this block"):
    """
    Wall-clock guard for a PYTHON loop -- a hand-written rollout or sweep.

    NOT a guard for a solve. A signal is only handled between bytecodes, so it
    cannot interrupt a long call that is sitting inside C: measured, a 0.3 s
    limit on one such call fired at 1.15 s, when the call returned. Solves are
    bounded by max_runtime, which IPOPT enforces from the inside; this covers
    the loops max_runtime cannot see, where an integrator with a bad step size
    can otherwise spin indefinitely.

    Prefer a deterministic step cap where the loop admits one -- a step count
    behaves the same on a loaded machine, and wall clock does not: the same
    solve here measured 533.9 s against a 145 s baseline purely from load.
    This is the backstop for what a step cap did not foresee.

    A no-op when the chapter took no budget, and when not on the main thread,
    where SIGALRM is not delivered.
    """
    if seconds is None:
        seconds = _active_budget()
    if (seconds is None or not hasattr(signal, "SIGALRM")
            or threading.current_thread() is not threading.main_thread()):
        yield
        return

    def _fire(signum, frame):
        raise BudgetExceeded(f"{what} exceeded its {seconds:.0f} s budget")

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


# Guarded because this file is exec'd once per page, and wrapping a wrapper
# would stack a fresh closure on every entry in the notebook.
if not getattr(asb.Opti.solve, "_is_budgeted", False):
    _unbudgeted_solve = asb.Opti.solve

    def _budgeted_solve(self, *args, **kwargs):
        seconds = _active_budget()
        if seconds is not None:
            kwargs.setdefault("max_runtime", seconds)   # -> ipopt.max_cpu_time
            kwargs.setdefault("behavior_on_failure", "return_last")
            # Merged, never assigned: a caller passing its own solver options
            # must not lose them to the budget.
            options = dict(kwargs.get("options") or {})
            options.setdefault("ipopt.max_wall_time", seconds)
            kwargs["options"] = options
        return _unbudgeted_solve(self, *args, **kwargs)

    _budgeted_solve._is_budgeted = True
    asb.Opti.solve = _budgeted_solve


def show_source(*objs):
    """
    Render the source of the shared functions an entry called.

    An entry that calls machinery without showing it has stopped documenting its
    own method, and the notebook exists to be reviewed. This reads the source off
    the live object, so it cannot drift from what actually ran -- the same
    guarantee the chapter index gets by reading its files off disk.

    Per-function, so an entry shows what it used and not the whole file. That is
    why one _analysis.py is enough and a directory of one-function modules would
    buy nothing.

    Requires the shim to compile with the real filename. A bare exec() of source
    text leaves co_filename as "<string>" and inspect.getsource() raises OSError
    -- loudly, at render, rather than quietly emitting nothing.
    """
    print('::: {.callout-note collapse="true"}')
    print("## The method, as called\n")
    print("```python")
    for o in objs:
        print(inspect.getsource(o).rstrip())
        print()
    print("```")
    print(":::")


def superseded_by(stem, reason):
    """
    Banner naming the entry that replaced this one.

    The successor's title and link are read off disk rather than typed, so a
    retitled successor cannot leave a stale label behind -- the same guarantee
    inline expressions give numbers. A stem that matches no file, or more than
    one, raises: a dead forward link is worse than none, because the reader
    trusts it.

    Scoped to the calling chapter, via `_CHAPTER` set by the shim. Globbing
    `chapters/*/` instead finds two files the moment a chapter is duplicated for
    reference, which is exactly what happened the first time this ran.
    """
    chapter = globals().get("_CHAPTER")
    if chapter is None:
        raise RuntimeError("superseded_by() needs _CHAPTER, set by _model.qmd")
    hit = pathlib.Path(chapter) / f"{stem}.qmd"
    if not hit.exists():
        raise FileNotFoundError(f"superseded_by({stem!r}): no {hit}")
    title = re.search(r'^title:\s*"(.+)"$', hit.read_text(), re.M).group(1)
    print('::: {.callout-important}')
    print("## Superseded\n")
    print(f"{reason} See [{title}]({stem}.qmd).")
    print(":::\n")


def footer(*objs):
    """
    The entry's closing cell: the machinery it called, then what it cost to run.

    Cost is wall clock since the shim plus the aero solves behind it -- the
    solve count is what explains the seconds, and `polars()` already counts
    both. Nothing else recorded this: _freeze/*/execute-results/html.json keeps
    a hash and a result and no timing at all, so before this an entry's cost
    left no trace once written.

    Under freeze the line shows the last REAL execution, not the cache hit,
    which is the number worth having.
    """
    if objs:
        show_source(*objs)
    n = aero_cost["calls"]
    cost = f" · {n} aero solve{'s' if n != 1 else ''}" if n else ""
    print(f"[Executed in {time.perf_counter() - _T0:.1f} s{cost}]{{.runtime}}")


def api(filename="_analysis.py"):
    """
    Every function defined in `filename`, with its signature and summary line.

    Terminal-facing: _scratch/probe.py prints this on every run, which is the
    moment someone is about to write a helper. It is deliberately not rendered
    into the site -- a reader of the design does not need a function inventory,
    and the chapter index already lists _analysis.py in full.

    Discovery by introspection rather than by memory. Compiling with real
    filenames gives each function a co_filename to filter on, so this list is the
    code rather than a copy of it and cannot go stale. Filtering to _analysis.py
    also keeps this file's own functions out of the listing.
    """
    for name, obj in sorted(globals().items()):
        if not inspect.isfunction(obj):
            continue
        if obj.__code__.co_filename.endswith(filename):
            summary = (inspect.getdoc(obj) or "").strip().split("\n")[0]
            yield name + str(inspect.signature(obj)), summary
