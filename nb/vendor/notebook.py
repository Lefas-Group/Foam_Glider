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

# ---------------------------------------------------------------- shadow guard
# `_model.qmd` EXECS this file into the PAGE's globals rather than importing it
# -- every chapter names its model `_model`, so real imports would collide in
# sys.modules -- which means the functions below have the entry's namespace as
# their __globals__. An entry writing `time = h / opt_sink` therefore left
# footer() reading a float:
#
#     AttributeError: 'float' object has no attribute 'perf_counter'
#
# ...raised from this file, which rule 11 pins byte-identical and the entry's
# author cannot edit. Lint rule 27 refuses that rebinding at lint time; these
# aliases mean a miss degrades instead of crashing. The two are independent on
# purpose -- neither is a reason to skip the other.
#
# The public names stay exactly as they are: entries use `time` and `pathlib`
# legitimately, and the point is to stop them mattering HERE.
_time, _pathlib, _re, _inspect, _os = time, pathlib, re, inspect, os
# An ALIAS, not a copy: `_model.qmd` zeroes the counter through the public name
# with aero_cost.update(...), and that must be the dict footer() reads.
_aero_cost = aero_cost
# DEFAULT_SOLVE_BUDGET and PROBE_BUDGET are deliberately NOT aliased. They are
# floats: rebinding one yields a wrong limit, not a traceback, so there is no
# crash for an alias to prevent -- and rule 27 refuses the rebinding anyway. A
# chapter raising its own limit uses different names (SOLVE_BUDGET_CHAPTER,
# raised only by the per-probe grant in $NB_PROBE_BUDGET, which this does not
# touch.


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
    calls, seconds = _aero_cost["calls"], _aero_cost["seconds"]
    each = f", {seconds / calls * 1e3:.0f} ms each" if calls else ""
    print(f"aero: {calls} solve(s), {seconds:.1f} s{each}")
    if reset:
        _aero_cost.update(calls=0, seconds=0.0)


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
# Measured, not guessed: every entry in glider-notebook executes in 2.0-9.5 s,
# so 200 s bounded nothing. The ceiling is the render DEADLINE now, directly and
# with no slack, and headroom nobody chose is time a wedged render burns before
# anyone notices. An entry that needs more asks at the prompt -- an expensive
# entry should be a decision, not an inheritance.
#
# The solve budget stays BELOW the ceiling. A solve cannot outlive the render
# containing it (rule 28), so defaults that broke that rule would put every
# entry taking both of them in violation the moment it was written.
DEFAULT_SOLVE_BUDGET = 15.0    # seconds for any one solve
DEFAULT_ENTRY_CEILING = 20.0   # seconds for one entry, checked by lint rule 17


def solve_budget():
    """
    The budget in force. DEPRECATED, and nothing should call it.

    It exists for a chapter index to quote, from when budgets were chapter-level.
    They are the entry's now (rules 18 and 28), and an index that renders this
    couples its own output to a number that has nothing to do with the chapter:
    change the budget and `check` reports the index as a changed value, which
    holds an unrelated entry at the refactor gate. Lint rejects it in an index.

    Kept only because `_notebook.py` is compared byte-for-byte against the
    vendored copy (rule 11), so deleting it would put every notebook that has
    not been re-vendored in violation of a rule it currently passes.

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
            # WALL TIME ONLY OUTSIDE A KERNEL -- that is, in a probe and not in
            # a render. The two are different failures.
            #
            # In a probe, being killed for overrunning the wall budget IS the
            # budget working: the agent asked for 15 s, took longer, is told
            # so, raises `budget_s` and re-probes. Cheap and self-correcting.
            #
            # In a render it is destructive for a reason that has nothing to do
            # with budgets. A failed render is handed to the model as an error
            # to FIX, so a solve slowed by a neighbour -- or by a background
            # compile -- presents as a bug in an entry that is correct, and the
            # model may edit it to fix a race. The retry then renders cleanly
            # and the spurious edit ships.
            #
            # The headroom is already thin without any parallelism: the
            # heaviest entries render in 11-13 s against a 15 s SOLVE_BUDGET.
            # A render stays bounded by max_cpu_time above and by the render
            # deadline outside it, so nothing here is unbounded.
            if not globals().get("_IN_KERNEL"):
                options.setdefault("ipopt.max_wall_time", seconds)
            kwargs["options"] = options
        # COUNTED HERE, because this is the only place every solve passes
        # through. `aero_cost` was initialised, read by aero_report() and by
        # footer(), reset by _model.qmd -- and written by nothing, so it read
        # zero forever. Five consumers believed it: proposal.render_cost_s
        # (which the write brief sizes SOLVE_BUDGET from), every
        # metrics.solve_seconds row, the probe's overspend warning, footer()'s
        # solve count, and aero_report() itself -- which told a probe that had
        # just optimised an aircraft that it had run no solves at all.
        #
        # try/finally, so a solve that RAISES still counts: an infeasible
        # problem or a budget kill cost the time either way, and the run worth
        # seeing is exactly the one that overran.
        _t0 = _time.perf_counter()
        try:
            return _unbudgeted_solve(self, *args, **kwargs)
        finally:
            _aero_cost["calls"] += 1
            _aero_cost["seconds"] += _time.perf_counter() - _t0

    _budgeted_solve._is_budgeted = True
    asb.Opti.solve = _budgeted_solve

# The counter lives on the WRAPPER, not in page globals. `aero_cost` is rebound
# by every exec of this file, but the wrapper is installed once and closes over
# whichever namespace installed it -- so if one process ever execs this for two
# pages, the wrapper would count into the first page's dict while the second
# page read its own, empty one. Sharing one dict makes the reset in _model.qmd
# mean "zero it for this page", which is what it is written to mean.
if hasattr(asb.Opti.solve, "_cost"):
    aero_cost = asb.Opti.solve._cost
else:
    asb.Opti.solve._cost = aero_cost
_aero_cost = aero_cost


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
# Raising it is a decision for the user, made by granting a bigger probe pool at
# the prompt, out of which the agent budgets each probe. Hitting this limit is
# meant to STOP the work and produce a choice -- is this solve worth it, can it be
# made cheaper, or should more time be asked for -- rather than a reflex.
PROBE_SILENCE = 120.0  # s of no output before the traceback says where it is
PROBE_BUDGET = 300.0   # s a scratch probe may run, absent a per-probe grant

_IN_KERNEL = "ipykernel" in sys.modules or hasattr(builtins, "__IPYTHON__")

if _IN_KERNEL:
    # Jupyter echoes a cell's last expression. A figure cell ending in
    # `airplane.draw_three_view(axs=axs, show=False)` therefore published
    #   array([[<Axes3D: zlabel='$z_g$ [m]'>, ...]], dtype=object)
    # into a rendered entry, directly under the figure it had just drawn.
    #
    # Suppressing the echo costs nothing that is used: print() is untouched,
    # which is how md_table emits a table, and inline figures are flushed by
    # the matplotlib backend's post-execute hook rather than by the repr.
    # Checked across every freeze in both notebooks before this went in --
    # every cell-output-display block is an image, so nothing anywhere relies
    # on last-expression display.
    #
    # Here rather than in a lint rule because the rule could only fire AFTER a
    # render had already paid for the entry, and the fix would be the same
    # every time.
    try:
        get_ipython().ast_node_interactivity = "none"   # noqa: F821
    except (NameError, AttributeError):
        pass

def _probe_budget():
    """
    The probe budget in force: this probe's grant, else the default.

    Read at CHECK time rather than at arm time. The watchdog therefore polls,
    which also keeps it honest if the environment changes under it.

    $NB_PROBE_BUDGET wins when set, and is how a run divides a POOL of probe
    wall clock between its own probes: a listing probe asks for ten seconds, a
    multistart for four hundred, out of one total that bounds the run. Before
    it, every probe got the same 300 s -- pointless rope for the cheap one,
    a kill for the expensive one, and no bound at all on how MANY probes a run
    could take. Same channel as $NB_CHAPTER, for the same reason: switching it
    edits no file.

    Env var, else the default. There is no chapter override: budgets belong to
    the entry now, and a probe runs before any entry exists -- the grant is the
    only thing that can speak for it.
    """
    env = _os.environ.get("NB_PROBE_BUDGET")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return PROBE_BUDGET


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
              f"   - ask the user for more time, with a bigger budget_s or a "
              f"bigger pool.]", file=sys.stderr, flush=True)
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

    # Polling rather than a single sleep, so the limit is re-read as the probe
    # runs. A daemon thread, so a probe that finishes early is never held open.
    _probe_thread = threading.Thread(target=_probe_watch, daemon=True)
    _probe_thread.start()


def md_table(header, rows):
    """
    Print a labelled markdown table from an `output: asis` cell.

    Furniture rather than analysis: entries kept re-typing the same three lines
    of pipe-printing, which is duplicated logic by any measure and is what rule 2
    is for. Right-aligns every column after the first, since the first holds row
    labels and the rest hold numbers.

    Rule 15 caps a table at 6x4 excluding the header, and this does not
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
        print(_inspect.getsource(o).rstrip())
        print()
    print("```")
    print(":::")


def _committed(path):
    """That file's contents at HEAD, or None. Used only by `cite`."""
    import subprocess
    try:
        r = subprocess.run(["git", "show", f"HEAD:./{path}"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def cite(chapter, entry, label=""):
    """
    The answer another entry published, quoted rather than retyped.

    Entries fan out because they compare against each other, and until now
    comparison meant TRANSCRIPTION: chapter 06 carries `sink_rate_manual = 0.400`
    hand-assigned from chapter 02, and lint can only warn about it. A transcribed
    number is correct when it is written and silent when the chapter it came from
    re-renders.

    What comes back is the cited entry's HERO VALUE, as that page published it --
    the one value it exists to produce. One citable value per entry is the same
    grain as one question per entry, and it means there is no second thing to
    name, register or keep in step.

    Read from the FREEZE, which is committed, so citing costs nothing: no model
    is imported and no solve runs. A string, not a float, because quoting is what
    this is for -- the units and the precision are the cited page's decision, and
    reformatting them here would let two pages disagree about the same number.

        prev = cite("02-fuselage-model", "2026-09-14-01-how-does-modeling-…")
        # -> "0.400 m/s"

    Raises rather than returning a placeholder. A citation that cannot resolve is
    a page about to publish a claim it cannot support, and the render is the last
    place anyone is looking.

    INVALIDATION IS check.py'S JOB: discarding a chapter's freeze also discards
    every page citing it, so a re-render of the cited entry forces a re-render
    here. Without that this would be transcription with extra steps.
    """
    import json

    frozen = (pathlib.Path("_freeze/chapters") / chapter / entry
              / "execute-results" / "html.json")
    blob = frozen.read_text() if frozen.exists() else _committed(frozen)
    # The fallback is not belt-and-braces, it is the common case under `check`:
    # check DISCARDS the freezes it is about to rebuild, so a citing page very
    # often renders while the page it quotes has no working-tree freeze at all.
    # The committed copy is what "published" means, and `check` renders a second
    # time afterwards so the final answer is the freshly rebuilt one.
    if blob is None:
        raise ValueError(
            f"cite({chapter!r}, {entry!r}): nothing frozen at {frozen}, and "
            f"nothing committed there either. Check the chapter and entry stem "
            f"-- a citation can only quote a page that has already published "
            f"its answer.")
    try:
        md = json.loads(blob)["result"]["markdown"]
    except (ValueError, KeyError) as e:
        raise ValueError(f"cite({chapter!r}, {entry!r}): unreadable freeze "
                         f"({type(e).__name__})") from None
    # value/label pairs, in page order. An entry USUALLY publishes one -- one
    # question, one answer -- but a before/after comparison legitimately
    # publishes two, and the first version of this returned whichever came
    # first. On the first real citation that was 0.36 where 0.40 was meant: a
    # wrong number, published silently, which is the whole failure `cite()`
    # exists to end. So ambiguity is an error, never a guess.
    unescape = lambda t: t.replace("\\", "")
    heroes = [(unescape(v), unescape(l)) for v, l in re.findall(
        r"\[([^\]]+)\]\{\.hero-value\}\s*\n\[([^\]]*)\]\{\.hero-label\}", md)]
    if not heroes:
        raise ValueError(
            f"cite({chapter!r}, {entry!r}): that entry publishes no hero value, "
            f"so it has no single answer to quote. Cite an entry whose `.hero` "
            f"block carries the number you want.")
    if label:
        hit = [v for v, l in heroes if l == label]
        if not hit:
            raise ValueError(
                f"cite({chapter!r}, {entry!r}, {label!r}): no hero has that "
                f"label. It publishes: "
                + ", ".join(f"{v!r} ({l!r})" for v, l in heroes))
        return hit[0]
    if len(heroes) > 1:
        raise ValueError(
            f"cite({chapter!r}, {entry!r}): that entry publishes "
            f"{len(heroes)} values — "
            + ", ".join(f"{v!r} ({l!r})" for v, l in heroes)
            + ". Name the one you mean with label=...")
    return heroes[0][0]


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
    elapsed = _time.perf_counter() - _T0
    # ONE line: what this page cost, each figure beside the limit it was given.
    # It was two -- a runtime line and a budget line -- which meant reading the
    # same three numbers in two places to answer "did it fit?".
    #
    # Read from the page's own namespace: this file is exec'd into it, so
    # `globals()` here IS the entry. A clause appears only if the number behind
    # it exists, so a hand-written entry declaring nothing prints just the time.
    #
    # `lint.RUNTIME_SECONDS` and `RUNTIME_SOLVES` parse this line -- rule 17,
    # `write._render_cost` and `freezediff`'s mask all go through them. Change
    # the wording here and change it there.
    g = globals()
    ceiling = g.get("ENTRY_CEILING")
    parts = [f"Rendered in {elapsed:.1f} s"
             + (f" (limit {ceiling:.0f} s)" if ceiling else "")]

    n = _aero_cost["calls"]
    if n:
        cap = g.get("SOLVE_BUDGET")
        parts.append(f"{n} aero solve{'s' if n != 1 else ''}"
                     + (f" (budget {cap:.0f} s each)" if cap else ""))

    pool, spent = g.get("PROBE_POOL"), g.get("PROBE_SPENT")
    if spent is not None:
        parts.append(f"explored in {spent:.0f} s"
                     + (f" (limit {pool:.0f} s)" if pool else ""))

    print(f"[{' · '.join(parts)}]{{.runtime}}")


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
        if not _inspect.isfunction(obj):
            continue
        if obj.__code__.co_filename.endswith(filename):
            summary = (_inspect.getdoc(obj) or "").strip().split("\n")[0]
            yield name + str(_inspect.signature(obj)), summary


# =============================================================================
# The chapter index's two generated blocks.
#
# Here rather than in the page, because there is one implementation instead of
# one per chapter. The page cell is `chapter_inputs("NN-name")` and nothing
# else, so a model rewriting an index cannot half-copy the logic, and rule 11
# pins this file byte-identical across notebooks.
#
# WHY THE CALLOUTS ARE DATA NOW. They used to be hand-written markdown in
# `index.qmd`: a numbered list under `## New user specifications`. That made a
# chapter's standing commitments unreadable to anything but a regex, and it made
# them unmarkable -- when a later chapter replaced one, nothing could say so on
# the page where it was declared, because a Python cell cannot reach back into
# markdown that is already written. The fix was a generated line listing what
# had been revisited, and it put every item on the page TWICE: measured on this
# notebook, both affected chapters had all of their items doubled.
#
# So the items live in `_inputs.yml` beside the model, with an id each, and the
# page renders them. A superseded item then simply moves into its own callout,
# once, with the chapter that replaced it attached -- and a chapter whose
# commitments have all been replaced renders no "new" callouts at all, which is
# the true statement about it.
# =============================================================================

# `- <id>: <text>` inside a block. The id is a slug so that a colon inside the
# TEXT -- "**Tail: H 100×30 mm**" -- cannot be mistaken for the separator.
_ROW = _re.compile(r"^\s*-\s*([a-z0-9][a-z0-9-]*)\s*:\s*(.+?)\s*$")


def _blocks(path):
    """
    `{key: [(id, text), ...]}` for a flat `key:` / `- id: text` file.

    Shared by `_inputs.yml` and `_fork.yml`'s `supersedes:`, which are the same
    shape on purpose: one thing to learn, and one parser to be wrong in.
    """
    out, current = {}, None
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        row = _ROW.match(line)
        if row and current is not None:
            out[current].append((row.group(1),
                                 row.group(2).strip().strip('"').strip("'")))
            continue
        key = _re.match(r"^(\w+):\s*$", line)
        if key:
            current = key.group(1)
            out.setdefault(current, [])
            continue
        current = None              # a `key: value` line ends the block
    return out


def _chapter_title(chapter):
    index = _pathlib.Path("chapters") / chapter / "index.qmd"
    try:
        m = _re.search(r'^title:\s*"(.+)"\s*$', index.read_text(), _re.M)
    except OSError:
        return chapter
    return m.group(1) if m else chapter


def _superseded(chapter):
    """{id: chapter that replaced it} for items THIS chapter declared."""
    out = {}
    for d in sorted(_pathlib.Path("chapters").iterdir()):
        if not d.is_dir() or d.name == chapter:
            continue
        for parent, item_id in _blocks(d / "_fork.yml").get("supersedes", []):
            if parent == chapter:
                out[item_id] = d.name
    return out


def chapter_lineage(chapter):
    """Where this chapter's vehicle came from, and what it replaced."""
    fork = _pathlib.Path("chapters") / chapter / "_fork.yml"
    try:
        text = fork.read_text()
    except OSError:
        return
    parent = _re.search(r"^parent:\s*(.+?)\s*$", text, _re.M)
    if parent:
        print(f"Forked from [{_chapter_title(parent.group(1))}]"
              f"(../{parent.group(1)}/).\n")


def chapter_inputs(chapter):
    """
    The chapter's three input callouts, rendered from `_inputs.yml`.

    An item that a later chapter supersedes moves OUT of its own callout and
    into `## Superseded`, with a link to the chapter that replaced it. It is
    stated once either way. A callout with nothing in it is not printed, which
    is rule 32 by construction rather than by checking.
    """
    items = _blocks(_pathlib.Path("chapters") / chapter / "_inputs.yml")
    gone = _superseded(chapter)
    live = {k: [(i, t) for i, t in items.get(k, []) if i not in gone]
            for k in ("specified", "assumed")}
    dead = [(i, t, gone[i]) for k in ("specified", "assumed")
            for i, t in items.get(k, []) if i in gone]

    for key, style, heading in (
            ("specified", "callout-tip", "New user specifications"),
            ("assumed", "callout-note", "New assumptions")):
        if not live[key]:
            continue
        print(f"::: {{.{style}}}")
        print(f"## {heading}\n")
        for n, (_, text) in enumerate(live[key], 1):
            print(f"{n}. {text}")
        print(":::\n")

    if dead:
        print("::: {.callout-important collapse=true}")
        print("## Superseded\n")
        for n, (_, text, by) in enumerate(dead, 1):
            print(f"{n}. {text} — replaced by "
                  f"[{_chapter_title(by)}](../{by}/).")
        print(":::\n")
