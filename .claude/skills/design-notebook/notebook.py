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
import builtins
import faulthandler
import inspect
import os
import pathlib
import re
import sys
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
# OPT-OUT, NOT OPT-IN, and the difference is the whole point. The first version
# of this required a chapter to bind SOLVE_BUDGET before any limit applied --
# which made the budget unforgettable at the call site while leaving it
# forgettable at the chapter, so a new chapter that simply never bound it ran
# with no protection at all. Forgetting is the failure this exists to defend
# against, so forgetting must land in the protected state.
#
# Three ways, and the middle one is why chapters can be exempt without a
# grandfather list anywhere:
#
#     SOLVE_BUDGET = 90.0   raised by agreement; the reason goes in index.qmd
#     SOLVE_BUDGET = None   deliberately unbounded
#     (not bound at all)    DEFAULT_SOLVE_BUDGET
#
# None takes exactly the branch an absent budget took before this file existed:
# no solver arguments are injected and solve() is called straight through. That
# is what lets a chapter whose pages are already frozen stay bit-for-bit as it
# was, as a visible line someone chose rather than an absence nobody noticed.
#
# Resolution is at CALL time, not import time, because _analysis.py is exec'd
# into this same namespace after this file has already run.
#
# THE BUDGET DOES NOT SET behavior_on_failure, and an earlier version's doing so
# was the worst bug this file has had. With return_last as the default, a solve
# that ran out of time handed back its last iterate and the entry published it as
# an answer: one chapter's figures came out 11.22 s, then 9.50 s, then 8.92 s
# from identical code, the last of them reporting Maximum_WallTime_Exceeded to
# nobody. A budget that swallows its own failure is worse than no budget.
#
# So a truncated solve RAISES. A probe that wants the iterate in order to
# diagnose one asks for it -- behavior_on_failure="return_last" -- and an entry,
# which publishes, does not get that by accident. The budget must be sized above
# what the entry's own configuration needs, measured there and not on a cheaper
# proxy; sized properly it never binds, and the question never arises.
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
# Two limits, because they catch different things and neither substitutes for
# the other. SOLVE_BUDGET bounds ONE opti.solve() call, at runtime, and its
# effect is a degraded answer. ENTRY_CEILING bounds one entry's TOTAL wall time,
# after the fact via lint rule 17, and its effect is a failed lint.
#
# A per-solve budget is blind to most of what makes an entry slow, measured on
# this notebook: one entry spends 112.8 s across 3070 aero solves in a marched
# rollout, with no single solve anywhere near a minute; another spends 599 s
# across four multistart solves that individually might pass and collectively do
# not; and problem construction -- 3.5 s of a 9.3 s call here -- sits outside
# every solver limit that exists. Only a total catches those.
#
# Both are starting points, not verdicts, and both read three ways: a number
# overrides, None opts out, absence takes the default. Raising either is the
# user's decision and belongs in the chapter's index.qmd as Specified.
DEFAULT_SOLVE_BUDGET = 60.0    # seconds for any one solve
DEFAULT_ENTRY_CEILING = 200.0  # seconds for one entry, checked by lint rule 17


def solve_budget():
    """
    The budget in force, for a chapter index to quote in its Specified callout.

    Public because `SOLVE_BUDGET` itself may not exist: a chapter that takes the
    notebook default never binds the name, so an index quoting it directly would
    fail to render on exactly the chapters that thought least about the cost.
    Returns None when the chapter is deliberately unbounded.
    """
    return _active_budget()


def _active_budget():
    """
    The budget in force: what the chapter bound, or the default if it bound none.

    Membership rather than .get(), because binding None is a real answer here --
    "deliberately unbounded" -- and must not be confused with having said nothing.
    """
    if "SOLVE_BUDGET" in globals():
        return globals()["SOLVE_BUDGET"]
    return DEFAULT_SOLVE_BUDGET


# Guarded because this file is exec'd once per page, and wrapping a wrapper
# would stack a fresh closure on every entry in the notebook.
if not getattr(asb.Opti.solve, "_is_budgeted", False):
    _unbudgeted_solve = asb.Opti.solve

    def _budgeted_solve(self, *args, **kwargs):
        seconds = _active_budget()
        if seconds is not None:
            kwargs.setdefault("max_runtime", seconds)   # -> ipopt.max_cpu_time
            # Merged, never assigned: a caller passing its own solver options
            # must not lose them to the budget.
            options = dict(kwargs.get("options") or {})
            options.setdefault("ipopt.max_wall_time", seconds)
            kwargs["options"] = options
        return _unbudgeted_solve(self, *args, **kwargs)

    _budgeted_solve._is_budgeted = True
    asb.Opti.solve = _budgeted_solve


# =============================================================================
# What a PROBE is allowed to cost.
#
# The budget above bounds opti.solve() and nothing else, so a script can still
# spend minutes in graph construction, marched rollouts and multistarts. One
# probe ran ten minutes before an external timeout killed it, and the session
# that motivated this spent more wall clock in scratch than in every render
# combined.
#
# ARMED HERE RATHER THAN IN THE PROBE SCAFFOLD, because the scaffold only
# reaches probes that import it -- and not one probe in that session did. They
# were all ad-hoc heredocs. What every one of them DID do is exec this file, to
# reach the model at all, so this is the only place a limit catches them.
#
# A watchdog THREAD, not a signal: a signal is handled between bytecodes and so
# cannot interrupt a long call sitting inside C. Measured, a 0.3 s SIGALRM
# against one such call fired at 1.15 s, on return; a threading.Timer fired at
# 0.61 s from inside the same call.
#
# Never armed under a kernel. Quarto's jupyter engine runs every entry in one,
# and a render that legitimately takes an hour must not be shot in the head --
# entries are governed by ENTRY_CEILING and lint rule 17 instead.
# =============================================================================
# NOT settable from the environment, and that is the whole design. An earlier
# version read NOTEBOOK_PROBE_BUDGET, and across the session that followed it was
# overridden on EVERY SINGLE probe -- 1200 s, 1800 s, 3600 s -- so the limit never
# once took effect. Two things made that inevitable and both are fixed here: the
# override was one token at the front of a command line, and the kill message
# helpfully named the variable to set. A guard that documents its own bypass at
# the moment it fires is not a guard; it is a speed bump with a detour sign.
#
# Raising it is a decision for the user, taken in a chapter's _budget.py and
# declared in its index.qmd under Specified, exactly as SOLVE_BUDGET is. Hitting
# this limit is meant to STOP the work and produce a choice -- is this solve worth
# it, can it be made cheaper, or should more time be asked for -- rather than a
# reflex.
PROBE_SILENCE = 120.0  # s of no output before the traceback says where it is
PROBE_BUDGET = 300.0   # s a scratch probe may run; raise only in _budget.py

_IN_KERNEL = "ipykernel" in sys.modules or hasattr(builtins, "__IPYTHON__")

def _probe_budget():
    """
    The probe budget in force: the chapter's, else this file's default.

    Read at CHECK time, not at arm time, because _budget.py is exec'd after this
    file -- so a chapter that raised the limit has not been seen yet when the
    watchdog starts. The watchdog therefore polls rather than sleeping once.
    """
    value = globals().get("PROBE_BUDGET_CHAPTER")
    return PROBE_BUDGET if value is None else value


if not _IN_KERNEL and not globals().get("_probe_guard_armed"):
    _probe_guard_armed = True
    _probe_t0 = time.perf_counter()

    def _probe_too_long():
        # Deliberately does NOT say how to raise the limit. Naming the escape
        # hatch here is what turned the previous version into a formality.
        print(f"\n[probe killed at {time.perf_counter() - _probe_t0:.0f} s, over "
              f"its {_probe_budget():.0f} s budget.\n"
              f" This is a stop, not a speed bump. Choose one:\n"
              f"   - decide the answer is not worth this much compute;\n"
              f"   - make it cheaper -- fewer nodes, a held design, one arm "
              f"instead of a sweep;\n"
              f"   - ask the user for more time, and record it in the chapter's "
              f"_budget.py.]", file=sys.stderr, flush=True)
        faulthandler.dump_traceback(file=sys.stderr)
        os._exit(9)

    # faulthandler says WHERE it is stuck, from its own thread, so it reports
    # from inside a C call too. The timer says ENOUGH.
    #
    # Once, not repeating: a solve that legitimately runs for minutes would
    # otherwise dump a traceback every couple of minutes, and the point is to
    # distinguish "working" from "hung", which one report already does.
    faulthandler.dump_traceback_later(PROBE_SILENCE, repeat=False, file=sys.stderr)

    def _probe_watch():
        while True:
            time.sleep(15.0)
            if time.perf_counter() - _probe_t0 > _probe_budget():
                _probe_too_long()

    # Polling, so a chapter that raises the limit in _budget.py is seen even
    # though that file is exec'd after this one. A daemon thread, so a probe that
    # finishes early is never held open by it.
    _probe_thread = threading.Thread(target=_probe_watch, daemon=True)
    _probe_thread.start()


def md_table(header, rows):
    """
    Print a labelled markdown table from an `output: asis` cell.

    Furniture rather than analysis: entries kept re-typing the same three lines
    of pipe-printing, which is duplicated logic by any measure and is what rule 2
    is for. Right-aligns every column after the first, since the first holds row
    labels and the rest hold numbers.

    Rule 15 caps a table at 3x4 or 4x3 excluding the header, and this does not
    enforce that -- the linter reads the rendered output, which is the only place
    a table built by print() can be counted.

    Args:
        header: column titles; the first is usually "" for the label column.
        rows: sequence of row tuples, already formatted as strings.
    """
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|")
    for row in rows:
        print("| " + " | ".join(str(c) for c in row) + " |")


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
