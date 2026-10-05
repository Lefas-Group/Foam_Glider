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
import inspect
import os
import pathlib
import re
import sys
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
# DEFAULT_SOLVE_BUDGET is deliberately NOT aliased. It is a float: rebinding it
# yields a wrong limit, not a traceback, so there is no crash for an alias to
# prevent -- and rule 27 refuses the rebinding anyway. An entry raising its own
# limit binds SOLVE_BUDGET, which `_active_budget` reads by membership.
#
# PROBE_BUDGET used to sit beside it. A probe's wall clock is `nb`'s to enforce
# now: it holds the deadline and kills the kernel, so nothing in this file has a
# probe limit to rebind.


def aero_report(reset=True):
    """
    Print the aero solves run since this was last called, and what they cost.

    Terminal-facing, exactly like api(): a probe calls both, which is the
    moment someone is about to write the helper that spends the solves. That
    is where the number is worth seeing -- not on a rendered page, and not in
    a profiler someone would have to think to reach for.

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
# than the probe scaffold -- but every one of them still exec'd this file, so a
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
            # WALL TIME IN A PROBE, NOT IN A RENDER. The two are different
            # failures.
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
            if not globals().get("_IS_RENDER"):
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
# Am I a RENDER, or a PROBE?
#
# These are different failures and the file has to tell them apart. It used to
# ask "am I in a kernel", which WAS the same question while probes ran in their
# own process -- a kernel meant Quarto's jupyter engine and nothing else. Probes
# run in a kernel too now, so that proxy answers "render" for both and silently
# disarms the wall clock on the one that needs it.
#
# `nb` sets NB_PROBE when it starts a probe kernel. Nothing else sets it, and a
# render never does, so the two are distinguished by WHAT THEY ARE rather than
# by how they happen to be hosted.
#
# The probe's own watchdog used to live here: a thread that called os._exit(9)
# at $NB_PROBE_BUDGET. It is gone, because the process it policed is gone. `nb`
# holds the deadline and kills the kernel, which is the same hard stop -- a
# signal cannot interrupt a CasADi solve sitting in C, measured at 1.15 s
# against a 0.3 s limit, so killing the process was always the mechanism. What
# stays here is PROBE_SILENCE, armed by `nb`'s init cell rather than by this
# file: saying WHERE a probe is stuck is worth keeping and does not depend on
# who decides to end it.
# =============================================================================
PROBE_SILENCE = 120.0  # s of no output before the traceback says where it is

_IN_KERNEL = "ipykernel" in sys.modules or hasattr(builtins, "__IPYTHON__")
_IN_PROBE = bool(os.environ.get("NB_PROBE"))
# A render is a kernel that is NOT a probe. Written this way round deliberately:
# an unknown host defaults to "not a render", which errs towards enforcing a
# limit rather than towards silently dropping one.
_IS_RENDER = _IN_KERNEL and not _IN_PROBE

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
    # BOTH hosts, render and probe alike. A probe in its own process had no
    # echo to suppress, so leaving it on for probe kernels would be a new
    # behaviour arriving by accident -- and a probe that ends in a bare
    # `opt_plane` would dump an Airplane repr over its own output.
    #
    # Here rather than in a lint rule because the rule could only fire AFTER a
    # render had already paid for the entry, and the fix would be the same
    # every time.
    try:
        get_ipython().ast_node_interactivity = "none"   # noqa: F821
    except (NameError, AttributeError):
        pass


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

    Terminal-facing: a probe calls this, which is the
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

# `- <key>: <value>` inside a block. The key is a slug, optionally a
# `chapter/id` pair, so that a colon inside the VALUE -- "**Tail: H 100x30
# mm**" -- cannot be mistaken for the separator.
# The value is OPTIONAL: `overwrites:` rows often need no reason, because
# the New callouts below already say what replaced the item.
_ROW = _re.compile(r"^\s*-\s*([a-z0-9][a-z0-9/-]*)\s*(?::\s*(.*?))?\s*$")


def _blocks(path):
    """
    `{key: [(k, v), ...]}` for a flat `key:` / `- k: v` file, scalars included.

    Shared by `_inputs.yml` and `_fork.yml`, which are the same shape on
    purpose: one thing to learn, and one parser to be wrong in.
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
                                 (row.group(2) or "").strip().strip('"').strip("'")))
            continue
        kv = _re.match(r"^(\w+):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val:
                out[key] = val.strip('"').strip("'")
                current = None
            else:
                current = key
                out.setdefault(current, [])
            continue
        current = None
    return out


def _page_title(path, fallback):
    """The `title:` from a page's front matter, or `fallback`."""
    try:
        m = _re.search(r'^title:\s*"(.+)"\s*$', path.read_text(), _re.M)
    except OSError:
        return fallback
    return m.group(1) if m else fallback


def _chapter_title(chapter):
    return _page_title(_pathlib.Path("chapters") / chapter / "index.qmd", chapter)


def _ordinal(n):
    """1st, 2nd, 3rd, 4th -- and 11th through 13th, which break the pattern."""
    tail = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(
        n % 10, "th")
    return f"{n}{tail}"


def _entries_of(chapter):
    """The chapter's entries, chronological. Dated `.qmd` files, sorted."""
    d = _pathlib.Path("chapters") / chapter
    try:
        return sorted(p for p in d.glob("*.qmd") if _STEM.match(p.name))
    except OSError:
        return []


# An item declared by an ENTRY rather than by the chapter. `2026-09-23-01-...`
_STEM = _re.compile(r"^\d{4}-\d{2}-\d{2}-")
_ITEM = _re.compile(r"^\s*\d+\.\s+(.*(?:\n(?!\s*\d+\.).*)*)", _re.M)
# Any callout, with its heading, so the title test is a lookup rather than a
# pattern to keep in step with `lint.INPUT_TITLES`.
_CALLOUT = _re.compile(r"^::: *\{\.callout-[\w-]+\}[^\n]*\n##\s*([^\n]+)\n(.*?)^:::",
                       _re.S | _re.M)
_INPUT_TITLES = ("specified", "assumed", "new user specifications",
                 "new assumptions", "initial user specifications",
                 "initial assumptions")


def _item_text(chapter, item_id):
    """
    One item's prose, by handle.

    TWO KINDS OF HANDLE, because there are two places an item can be declared.
    A chapter's own commitments live in `_inputs.yml` as `- <id>: <text>` and
    the handle is the id. An assumption a single ENTRY made lives in that
    entry's callout and has no id, so the handle is the entry's stem -- which
    is unique within the chapter and is what the register already reports.

    Without the second, an `overwrites:` row naming an entry-level assumption
    rendered as its own filename. A fork that moves the wings breaks "Wing
    position: near mid-fuselage", and that assumption is exactly the sort that
    lives in an entry: it was made once, while building the vehicle the fork
    copied.

    An entry that declared several returns them joined, because the handle
    names the declaration and not one line of it -- and a fork that breaks an
    entry's premise usually breaks the set.
    """
    b = _blocks(_pathlib.Path("chapters") / chapter / "_inputs.yml")
    for key in ("specified", "assumed"):
        for i, t in (b.get(key) or []):
            if i == item_id:
                return t
    if _STEM.match(item_id):
        f = _pathlib.Path("chapters") / chapter / f"{item_id}.qmd"
        try:
            text = f.read_text()
        except OSError:
            return item_id
        found = [" ".join(m.split())
                 for title, body in _CALLOUT.findall(text)
                 if title.strip().lower() in _INPUT_TITLES
                 for m in _ITEM.findall(body)]
        if found:
            return "; ".join(found)
    return item_id


def chapter_lineage(chapter):
    """
    Where this chapter's vehicle came from, and from WHEN.

    `_fork.yml` records `at_entry:` -- how many entries the parent had written
    when the copy was taken -- and that is the one fact that places a fork in
    its parent's history. It decides what this chapter inherited, and it was
    recorded and then shown nowhere: the line said only which chapter, so a
    reader could not tell whether the fork predated the parent's most
    interesting entry or followed it.

    LINKED TO THE `.qmd`, NOT THE DIRECTORY. It used to print `(../<parent>/)`,
    a bare directory that Quarto does not rewrite -- so the link resolved to
    nothing and the only working route to the parent was the sidebar. Quarto
    rewrites a link whose target is a source file, which is also why rule 10
    has entries cite each other by `.qmd`.
    """
    fork = _pathlib.Path("chapters") / chapter / "_fork.yml"
    try:
        text = fork.read_text()
    except OSError:
        return
    m = _re.search(r"^parent:\s*(.+?)\s*$", text, _re.M)
    if not m:
        return
    parent = m.group(1).strip()
    line = f"Forked from [{_chapter_title(parent)}](../{parent}/index.qmd)"

    at = _re.search(r"^at_entry:\s*(\d+)\s*$", text, _re.M)
    entries = _entries_of(parent)
    if at and entries:
        # CLAMPED: a recorded count can outrun the parent if an entry was
        # removed, and a link to an entry that is not there is worse than no
        # link. The front page's lineage diagram clamps the same number for the
        # same reason.
        n = max(1, min(int(at.group(1)), len(entries)))
        e = entries[n - 1]
        line += (f", after its {_ordinal(n)} entry — "
                 f"[{_page_title(e, e.stem)}](../{parent}/{e.name})")
    print(line + ".\n")


def notebook_inputs():
    """
    The notebook's brief, from `_inputs.yml` at its root.

    Same file format as a chapter's, and the same renderer, because it is the
    same entity one level up. It used to be hand-written markdown here and YAML
    in the chapters, so `inputs.py` carried a regex that had to know three
    historical heading names to read either.

    INITIAL, not New: everything below inherits these, and nothing supersedes
    them. A fork that departs from the brief is not a fork -- it is a different
    aircraft, which is a different notebook.
    """
    _render_inputs(_pathlib.Path("_inputs.yml"),
                   "Initial user specifications", "Initial assumptions")


def _render_inputs(path, spec_heading, assumed_heading):
    items = _blocks(path)
    for key, style, heading in (
            ("specified", "callout-tip", spec_heading),
            ("assumed", "callout-note", assumed_heading)):
        rows = items.get(key) or []
        if not rows:
            continue
        print(f"::: {{.{style}}}")
        print(f"## {heading}\n")
        for n, (_, text) in enumerate(rows, 1):
            print(f"{n}. {text}")
        print(":::\n")


def chapter_inputs(chapter):
    """
    The chapter's callouts: what it OVERWROTE, then what it newly declares.

    EVERY LEVEL LOOKS BACKWARD ONE STEP, and this is the whole of it. A chapter
    always renders its own specifications and assumptions -- they are its
    premise, and they stay exactly as true as they ever were; `forking.md`'s
    criterion for a chapter existing at all is that "the old answer stays valid
    under its own stated assumptions".

    The first version pointed FORWARD: a later chapter replacing an item put a
    `Superseded` stamp on the page that DECLARED it. That says the chapter is
    stale, which contradicts the reason it was kept -- and on this notebook it
    emptied two chapters of their callouts entirely, because every one of their
    items had been departed from.

    The second printed a PAIR, `was -> now`. The `now` half was already in the
    New callout below, so chapter 02 said "Fuselage: 5 mm foam, doubled up"
    twice on one page -- and the pair was a fiction: "Fuselage neglected" was
    replaced by the whole fuselage model, three items, and a 1:1 link had to
    pick one of them arbitrarily.

    So: only the OLD item, on the page that overwrote it. What replaced it is
    the New callouts, entire. No "see <chapter>" link either -- `Forked from`
    is directly above and the heading already names the chapter.
    """
    fork = _blocks(_pathlib.Path("chapters") / chapter / "_fork.yml")

    # Grouped by the chapter that DECLARED the item, not by the parent: 04
    # forks from 03 but overwrites 01's items.
    # TWO SOURCES, ONE CALLOUT. `_fork.yml` records what this chapter broke in
    # an ANCESTOR, which is what forking means; `_inputs.yml` records what a
    # later entry here superseded in an earlier one, which needs no fork and no
    # approval -- an assumption is the writer's to revise. They are the same
    # fact at two scales, so they render together.
    #
    # A bare handle with no `/` is one of THIS chapter's own -- an entry stem,
    # since a chapter item would simply have been rewritten rather than
    # overwritten.
    own = _blocks(_pathlib.Path("chapters") / chapter / "_inputs.yml")
    gone = {}
    for target, why in ((fork.get("overwrites") or [])
                        + (own.get("overwrites") or [])):
        src, _, item_id = target.partition("/")
        if not item_id:
            src, item_id = chapter, src
        gone.setdefault(src, []).append((_item_text(src, item_id), why))
    for src, rows in gone.items():
        print("::: {.callout-warning}")
        print("## Overwritten" + ("" if src == chapter
                                  else f" from {_chapter_title(src)}") + "\n")
        for n, (text, why) in enumerate(rows, 1):
            print(f"{n}. {text}" + (f" — {why}" if why else ""))
        print(":::\n")

    _render_inputs(_pathlib.Path("chapters") / chapter / "_inputs.yml",
                   "New user specifications", "New assumptions")

    _render_active(chapter)


def _render_active(chapter):
    """
    One collapsed callout: what this chapter was given, by whoever gave it.

    A chapter index renders `_inputs.yml` and the items it overwrote, and both
    are one step deep -- so a reader of 03-no-cosmetics saw one specification
    where ten were in force, and the only route to the other nine was to open
    three ancestors and read their entries. The model never had that problem:
    `probe._inputs_notice` has handed every run the resolved set since
    `ask_specified` started firing, on the reasoning that "go and find them" is
    the step that does not happen. This is that list, for the human.

    ANCESTORS ONLY, and the chronology is why. This chapter's own entry-level
    assumptions were in here briefly, and they do not belong: entries are
    dated and read downwards, so an assumption the fourth entry introduced is
    not a premise of the page. Listing it at the top would claim the chapter
    held it from the start. An ANCESTOR's is different -- including the
    entry-level ones declared before the fork, which `_lineage`'s `at_entry`
    cutoff selects -- because those are premises of the vehicle this chapter
    copied.

    THE BRIEF IS AMONG THEM, keyed `brief/<handle>`, because the notebook root
    is the oldest ancestor rather than a separate kind of thing. A root
    chapter used to render nothing here at all -- `_active.yml` held the
    chapter chain only, so `01-...` showed a reader no constraints while seven
    were in force. An earlier fix read the root `_inputs.yml` separately and
    printed a second callout; that is gone, because once the brief is in the
    chain `_active.yml` already contains it and one list says what two did.

    NOT MERGED INTO THE NEW CALLOUTS, which is the rest of the design. Roughly
    half of these are assumptions one ancestral entry made; listing them under
    this chapter's "New assumptions" would claim it declared them.

    SPLIT BY KIND, NOT BY SOURCE, and headed to match the callouts above it --
    "Inherited user specifications" against "New user specifications". A reader
    asking what this page is held to wants Specified apart from Assumed: one
    was given, the other guessed, and that is what changes how much weight a
    number carries. Which ancestor each came from is the key in `_active.yml`
    and is not printed -- it answered a question nobody reading the page was
    asking, and put a handle on every row.

    NO LEAD-IN SENTENCE. The title says where these came from and the headings
    say what they are; a line of prose under it restated both.

    Reads `_active.yml`, which `nb` regenerates on every commit -- this file
    executes at Quarto render time with no `nb` importable, so it cannot walk
    the chain itself. No file renders nothing, which is right for a chapter
    that predates the generator.
    """
    rows = _blocks(_pathlib.Path("chapters") / chapter / "_active.yml")
    # The handle is the KEY and is never printed -- it is there so `_blocks`
    # can parse this like every other inputs file, and so provenance survives
    # in the source for anyone who goes looking.
    groups = [(heading, [t for _handle, t in (rows.get(key) or [])])
              for key, heading in (("specified", "Inherited user specifications"),
                                   ("targets", "Inherited targets"),
                                   ("assumed", "Inherited assumptions"))]
    total = sum(len(items) for _, items in groups)
    if not total:
        return
    print('::: {.callout-note collapse="true"}')
    print(f"## In force here, from earlier ({total})\n")
    for heading, items in groups:
        if not items:
            continue
        print(f"**{heading}**\n")
        for n, text in enumerate(items, 1):
            print(f"{n}. {text}")
        print()
    print(":::\n")


# =============================================================================
# COMPARING THE MODEL WITH A PHOTOGRAPH OF THE REAL AIRCRAFT.
#
# The targets gate checks a reconstruction against published NUMBERS. It says
# nothing about shape, and the gap is wide: one airframe reproduced all eight
# published figures to 0.40% while missing its power pod entirely and lofting
# a smooth pod where the real aircraft is a slab-sided box. Both faults were
# obvious the moment the model was drawn over a photograph.
#
# Furniture, not aircraft. `probe_init` execs this file into every probe and
# `_model.qmd` execs it at render time, so one copy serves the agent while it
# works and the entry once it commits -- and the entry's overlay recomputes
# on every render, so it cannot go stale against an edited `_model.py`.
#
# WHAT WAS TRIED AND DISCARDED, so none of it is rebuilt:
#
#   * LANDMARK CORRESPONDENCE (name five points in both, solve). Five
#     correspondences against seven pose parameters is barely determined; the
#     fit spent the slack on perspective and put the camera 0.25 m from a
#     622 mm aircraft. It scored a flattering 21 px residual and looked worse
#     than a pose guessed by eye.
#   * SILHOUETTE OVERLAP (maximise IoU). Overlap is flat before the shapes
#     meet, so there is no gradient to follow, and saturates after, so the
#     last millimetres barely score. It also answers a different question
#     from the eye: on one photograph it tilted the aircraft 21 degrees to
#     cover a thumb that was inside the mask.
#   * INTERIOR EDGE MATCHING (pull model panel lines onto photo edges).
#     Measured: only 22% of a photograph's strong edges are interior at all,
#     and most of those are shading or paint -- invasion stripes and roundels
#     the model has no way to explain. Weighting them wrecked the fit.
#
# What survives is chamfer distance on the outline, which descends smoothly
# from anywhere and asks only that edges meet edges.
# =============================================================================

# Per-component colours, from the plot cycle above so a reader sees one
# palette across the whole notebook. Violet is the fifth and has no plot
# counterpart; five components is as many as these aircraft have.
_PART_COLOURS = [(20, 101, 92), (184, 134, 11), (92, 102, 112),
                 (179, 65, 44), (120, 70, 150)]


def _rotation(elev, azim, roll=0.0):
    """
    World -> camera basis, matching matplotlib's `view_init(elev, azim, roll)`.

    Verified against `proj3d.proj_transform` at 0.00 px, so a pose fitted
    here can be handed straight to `view_init` and the render agrees.
    """
    import numpy as _np
    e, a, r = _np.radians([elev, azim, roll])
    eye = _np.array([_np.cos(e)*_np.cos(a), _np.cos(e)*_np.sin(a), _np.sin(e)])
    fwd = -eye
    up0 = _np.array([0.0, 0.0, 1.0])
    if abs(_np.dot(fwd, up0)) > 0.999:          # looking down the pole
        up0 = _np.array([0.0, 1.0, 0.0])
    right = _np.cross(fwd, up0); right /= _np.linalg.norm(right)
    up = _np.cross(right, fwd)
    R = _np.stack([right, up, -fwd])
    if r:
        c, s = _np.cos(r), _np.sin(r)
        R = _np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]) @ R
    return R


def _project(points, params, centre=None):
    """
    Model points -> image pixels. `params` is (elev, azim, roll, scale, tx,
    ty, distance); `distance` None is orthographic.

    PERSPECTIVE IS NOT OPTIONAL for a close photograph. Fitting a hand-held
    product shot of a 622 mm aircraft orthographically left 65 px of residual
    on a 480 px span -- the near wingtip genuinely is larger than the far
    one, and no rigid orthographic pose can place both.
    """
    import numpy as _np
    elev, azim, roll, scale, tx, ty, dist = params
    p = _np.asarray(points, float)
    c = _np.asarray(centre if centre is not None else p.mean(axis=0), float)
    cam = (p - c) @ _rotation(elev, azim, roll).T
    x, y = cam[:, 0], cam[:, 1]
    if dist is not None:
        depth = _np.clip(1.0 - cam[:, 2] / dist, 1e-3, None)
        x, y = x / depth, y / depth
    return _np.stack([scale*x + tx, -scale*y + ty], axis=1)


def _raster(pts, faces, params, size, centre=None):
    """
    Projected faces as a boolean mask of `size` = (w, h).

    NO MATPLOTLIB IN THE LOOP. An earlier version rendered a figure per trial
    and thresholded the PNG: slow, and twice it thresholded the axes
    background pane instead of the aircraft, so every pose scored identically
    and the search looked broken when it was blind.
    """
    import numpy as _np
    from PIL import Image as _Image, ImageDraw as _ImageDraw
    q = _project(pts, params, centre)
    im = _Image.new("L", size, 0)
    dr = _ImageDraw.Draw(im)
    for f in faces:
        dr.polygon([tuple(q[i]) for i in f], fill=255)
    return _np.asarray(im) > 127


def _parts_of(airplane):
    """[(pts, faces)] per wing and fuselage, in declaration order."""
    import numpy as _np
    out = []
    for comp in list(airplane.wings) + list(airplane.fuselages):
        pts, faces = comp.mesh_body(method="quad")
        out.append((_np.asarray(pts, float), faces))
    return out


def _depth_order(parts, params, centre):
    """Component indices, nearest the camera first."""
    import numpy as _np
    R = _rotation(params[0], params[1], params[2])
    return sorted(range(len(parts)),
                  key=lambda i: -float(((parts[i][0] - centre) @ R.T)[:, 2].mean()))


def _fit_pose(parts, mask, hint=None, work=220):
    """
    Camera pose by symmetric chamfer distance between outlines.

    SYMMETRIC: model-to-photo alone shrinks the model onto a corner of the
    subject, photo-to-model alone inflates it to cover everything.

    SCREENED MULTI-START: 36 seeds are scored, and only the best four are
    descended on. Running a full Nelder-Mead from every seed spent its time
    polishing basins that could not win -- 156 s against 13 s for the same
    optimum.
    """
    import numpy as _np
    from scipy.optimize import minimize as _minimize
    from scipy import ndimage as _nd
    from PIL import Image as _Image

    h, w = mask.shape
    sc = work / max(h, w)
    tw, th = max(1, int(w*sc)), max(1, int(h*sc))
    tgt = _np.asarray(_Image.fromarray(mask.astype(_np.uint8)*255)
                      .resize((tw, th), _Image.NEAREST)) > 127
    tgt_edge = tgt & ~_nd.binary_erosion(tgt)
    dt = _nd.distance_transform_edt(~tgt_edge)
    allp = _np.vstack([p for p, _ in parts])
    centre = allp.mean(axis=0)
    diag = float(_np.hypot(tw, th))

    def unpack(v):
        # Scale and translation are carried in FULL-RESOLUTION pixels and
        # converted here. Omitting that conversion once put the model
        # hundreds of pixels off a 220 px canvas, so every silhouette came
        # back empty and the cost sat at the diagonal for every input.
        d = 0.4 + 19.6/(1.0 + _np.exp(-v[6]))
        return (v[0], v[1], v[2], abs(v[3])*sc, v[4]*sc, v[5]*sc, d)

    def cost(v):
        p = unpack(v)
        m = None
        for pts, faces in parts:
            mi = _raster(pts, faces, p, (tw, th), centre)
            m = mi if m is None else (m | mi)
        if m is None or not m.any():
            return diag
        me = m & ~_nd.binary_erosion(m)
        if not me.any():
            return diag
        return 0.5*(dt[me].mean()
                    + _nd.distance_transform_edt(~me)[tgt_edge].mean())

    ys, xs = _np.nonzero(mask)
    s0 = max(_np.ptp(xs), _np.ptp(ys)) / _np.ptp(allp, axis=0).max()
    cx, cy = xs.mean(), ys.mean()

    if hint is not None:
        roll0 = float(hint[2]) if len(hint) > 2 else 0.0
        starts = [[float(hint[0]), float(hint[1]), roll0, s0, cx, cy, 0.0]]
    else:
        starts = [[e0, float(a0), 0.0, s0, cx, cy, 0.0]
                  for a0 in range(0, 360, 30) for e0 in (15.0, 40.0, 65.0)]
    scored = sorted(((cost(_np.array(v)), v) for v in starts),
                    key=lambda t: t[0])

    # AN EXPLICIT SIMPLEX, because the default one silently freezes any
    # parameter seeded at zero. Nelder-Mead builds its first simplex by
    # scaling each coordinate 5%, and a coordinate that is exactly 0.0 gets
    # an ABSOLUTE step of 0.00025 instead. Roll and the distance logit are
    # both seeded at 0.0, so both were nominally free and numerically
    # pinned: every fit on every photograph returned roll 0.000 and a
    # distance stuck at the sigmoid midpoint. Measured on the Mustang -- a
    # roll sweep at the fitted angles moved the cost from 56.9 to 54.1,
    # improvement the optimiser could not reach.
    steps = _np.array([5.0, 10.0, 5.0, 0.05*max(s0, 1e-9),
                       0.05*max(abs(cx), 1.0), 0.05*max(abs(cy), 1.0), 0.75])

    def _descend(x0, **opts):
        x0 = _np.asarray(x0, dtype=float)
        sim = _np.vstack([x0] + [x0 + st*_np.eye(7)[i]
                                 for i, st in enumerate(steps)])
        return _minimize(cost, x0, method="Nelder-Mead",
                         options=dict(initial_simplex=sim, **opts))

    best, bestv = None, 1e9
    for _, v in scored[:4]:
        r = _descend(v, maxiter=900, xatol=.5, fatol=1e-3)
        if r.fun < bestv:
            best, bestv = r, r.fun
    r = _descend(best.x, maxiter=4000, xatol=1e-2, fatol=1e-5)
    v, val = (r.x, r.fun) if r.fun < bestv else (best.x, bestv)
    e, a, ro, s, tx, ty, d = unpack(v)
    return (e, a % 360, ro, s/sc, tx/sc, ty/sc, d), val/sc, centre


# How far the chamfer residual may run, as a fraction of the subject's
# longest dimension, before the overlay is declared untrustworthy. 2.5% is
# roughly 12 px on these photographs; a good fit sits near 1%.
_POSE_DOUBTFUL = 0.025


def compare_to_photo(airplane, name, hint=None, fill=0.22):
    """
    Draw the model over a photograph of the real aircraft. -> (rgb, note)

    Each component gets its own colour: filled where it faces the camera,
    solid on its visible outline, faint where it sits behind something else.
    That is the drawing-office convention and it is the one that reads --
    dropping hidden lines fragments each component into pieces, while drawing
    them at full weight puts the power pod up beside the canopy and invents a
    fault that is not there.

    NO SCORE IS RETURNED, deliberately. A higher overlap does not mean a
    better model: the fit that maximised it scored 0.792 and ran the outline
    through the fuselage. A number on the result is a number that gets
    chased, and chasing this one makes the model worse. The note reports the
    POSE, and flags when the pose is too poor to read anything from.

    `hint=(elev, azim)` or `(elev, azim, roll)` RESEEDS the search; the
    chamfer still does the fitting from there. Reach for it whenever the
    outline is displaced as a whole -- every component out in the same
    direction is a pose error, one component wrong while the others sit
    right is a shape error -- and not only when the note says DOUBTFUL, a
    fit can be the best one available and still be worth a second seed from
    somewhere else.

    There is still no way to SET a pose outright. Judging a camera angle by
    eye is the one part of this a reader does badly: an eyeball estimate was
    21 degrees out in elevation on a photograph that then fitted cleanly. A
    hint says where to look, and the photograph decides.
    """
    import numpy as _np
    from PIL import Image as _Image
    from scipy import ndimage as _nd

    root = _pathlib.Path(_os.environ.get("NB_ROOT", "."))
    ref = root / "_reference"
    img_path = next((p for p in sorted(ref.glob(f"{name}.*"))
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
                     and not p.name.endswith(".mask.png")), None)
    mask_path = ref / f"{name}.mask.png"
    if img_path is None or not mask_path.exists():
        have = ", ".join(sorted(p.stem for p in ref.glob("*.mask.png"))) or "none"
        raise FileNotFoundError(
            f"no photograph and mask for {name!r} in _reference/. "
            f"Masks present: {have}. A photograph without a mask cannot be "
            f"compared against -- that is the coordinator's to cut.")

    photo = _np.asarray(_Image.open(img_path).convert("RGB")).astype(float)
    mask = _np.asarray(_Image.open(mask_path).convert("L")) > 127
    H, W = mask.shape

    parts = _parts_of(airplane)
    params, resid, centre = _fit_pose(parts, mask, hint=hint)

    out = photo.copy()
    covered = _np.zeros((H, W), bool)
    for i in _depth_order(parts, params, centre):
        m = _raster(parts[i][0], parts[i][1], params, (W, H), centre)
        col = _np.array(_PART_COLOURS[i % len(_PART_COLOURS)], float)
        vis, hid = m & ~covered, m & covered
        if vis.any():
            out[vis] = (1 - fill)*out[vis] + fill*col
        edge = _nd.binary_dilation(m & ~_nd.binary_erosion(m), _np.ones((2, 2)))
        ve, he = edge & ~covered, edge & covered
        if he.any():
            out[he] = 0.70*out[he] + 0.30*col
        if ve.any():
            out[ve] = 0.05*out[ve] + 0.95*col
        covered |= m

    ys, xs = _np.nonzero(mask)
    extent = max(_np.ptp(xs), _np.ptp(ys))
    ok = resid <= _POSE_DOUBTFUL * extent
    # ROLL IS IN THE NOTE because it is what a hint usually needs to carry:
    # an overlay that is displaced as a whole is most often rotated in the
    # image plane, and the reader cannot reseed a number it was never shown.
    note = (f"{name} — camera elev {params[0]:.1f}° azim {params[1]:.1f}° "
            f"roll {params[2]:.1f}°, {params[3]:.0f} px/m. ")
    note += ("Pose: good." if ok else
             "Pose: DOUBTFUL — the outline does not track the aircraft. "
             "Read nothing from this overlay; reseed with "
             "hint=(elev, azim, roll), or ask for a better photograph.")
    return out.astype(_np.uint8), note


def show_comparison(airplane, name, hint=None, fill=0.22, ax=None):
    """`compare_to_photo` onto matplotlib axes, for an entry. -> the note."""
    import matplotlib.pyplot as _plt
    rgb, note = compare_to_photo(airplane, name, hint=hint, fill=fill)
    if ax is None:
        _, ax = _plt.subplots(figsize=(7.0, 7.0*rgb.shape[0]/rgb.shape[1]))
    ax.imshow(rgb)
    ax.set_axis_off()
    return note
