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
#
# -----------------------------------------------------------------------------
# THE POSE FITTER CHANGED ON 2026-10-09, and entries committed before that date
# were fitted by the old one. `_notebook.py` is NOT in rule 12's staleness list
# (`_model.py`, `_analysis.py`, `_model.qmd`, `_inputs.yml`, `_fork.yml`), so
# nothing marks those entries stale and freeze will keep serving their published
# numbers -- which is deliberate, and why this note exists instead.
#
# If a hero value moves when you force a re-render, this is why. Affected, all
# predating the change: f16-viper's three fit-dependent entries, tubby-b-17's
# two, mustang-mkr2's one.
#
# What changed in `_fit_pose`, each measured and none of it cosmetic:
#   * cold fitting now descends in FOUR QUADRANTS (elevation sign x azimuth
#     half) and keeps the lowest CONVERGED cost. One descent from the best
#     screened seed chose between hemispheres on a score that cannot rank;
#     measured on the Little Piggy, that found the right basin 1 time in 3.
#   * the cold seed grid covers both hemispheres, (-65..65) rather than
#     (15, 40, 65) -- every seed used to sit above an aircraft that is usually
#     photographed from below.
#   * elevation is bounded +/-85 rather than -30/+85.
#   * a `pose=` hint is intersected with the physical band. It was not, so a
#     -75 deg hint returned a fitted -100 deg.
#   * azimuth is exempt from the railed verdict, being cyclic. See `_rails`.
#   * `compare_to_photo` now compares the fitted side against the reference
#     `.txt` and says so when they disagree. Top and bottom are a genuine
#     degeneracy on a near-planar airframe and the residual cannot break the
#     tie; the description can, and was the one check nobody performed.
#
# Cost: a cold fit is ~46 s against ~12 s. A hinted fit is unchanged at ~13 s.
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


def show_method(summary):
    """
    One or two sentences on what the entry's code does, above the source.

    ITS OWN BOX, collapsed, rather than a line of prose on the page. The entry's
    visible text is about the AIRCRAFT and is capped for it; a paragraph about
    the code would compete for those words, and the thing it explains -- the
    collapsed source below -- is itself folded. So the two fold together: a
    reader deciding whether to open forty lines of optimiser setup reads the
    sentence first, and a reader who only wants the answer sees neither.

    Printed by `footer(..., method=...)` and not called directly from an entry;
    it is separate only so that the heading and the fold live beside
    `show_source`'s, which is the box it introduces.
    """
    print('::: {.callout-note collapse="true"}')
    print("## What the code does\n")
    print(" ".join(str(summary).split()))
    # BLANK LINE AFTER THE FENCE, because the next thing printed is another
    # `:::` opening. Pandoc reads two fences on consecutive lines as one block
    # trying to close and open at once, and the source box then renders inside
    # this one.
    print(":::\n")


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


def footer(*objs, method=""):
    """
    The entry's closing cell: the machinery it called, then what it cost to run.

    `method` is the model's own sentence about the code it wrote, in its own
    collapsed box directly above the source (rule 47). FOLDED, like the source
    it introduces: an entry's visible prose is about the aircraft, and a reader
    who wants to know how the number was got opens one box and finds a sentence
    before the code rather than forty lines of optimiser setup.

    A KEYWORD, so that `rendered_by_footer` -- which collects positional
    arguments only -- cannot mistake it for a function the entry rendered, and
    so that adding one to an entry that already lints changes nothing else
    about it.

    Cost is wall clock since the shim plus the aero solves behind it -- the
    solve count is what explains the seconds, and `polars()` already counts
    both. Nothing else recorded this: _freeze/*/execute-results/html.json keeps
    a hash and a result and no timing at all, so before this an entry's cost
    left no trace once written.

    Under freeze the line shows the last REAL execution, not the cache hit,
    which is the number worth having.
    """
    if method and method.strip():
        show_method(method)
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
        m = re.search(r'^title:\s*"(.+)"\s*$', path.read_text(), _re.M)
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
    m = re.search(r"^parent:\s*(.+?)\s*$", text, _re.M)
    if not m:
        return
    parent = m.group(1).strip()
    line = f"Forked from [{_chapter_title(parent)}](../{parent}/index.qmd)"

    at = re.search(r"^at_entry:\s*(\d+)\s*$", text, _re.M)
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


def _parts_of(airplane, resolution=None):
    """[(pts, faces)] per wing and fuselage, in declaration order.

    `resolution` decimates the mesh. AeroSandbox defaults to 36, which on a
    twin-boom model is 1774 faces at 26.4 ms per raster; resolution 8 is 402
    faces at 6.8 ms -- **3.9x faster**. Measured on another aircraft, three
    seeds at each resolution put the fitted geometry well inside seed noise
    (objective 1.896% +/- 0.017 against 1.877% +/- 0.022), so the cheap mesh
    costs nothing that can be detected.

    The cost is faces, not pixels: four times the raster area is 14% more
    time, while four times the faces is four times the time.
    """
    import numpy as _np
    out = []
    for comp in list(airplane.wings) + list(airplane.fuselages):
        if resolution is None:
            pts, faces = comp.mesh_body(method="quad")
        elif comp in airplane.wings:
            pts, faces = comp.mesh_body(method="quad",
                                        chordwise_resolution=int(resolution))
        else:
            pts, faces = comp.mesh_body(method="quad",
                                        tangential_resolution=max(4, int(resolution)))
        out.append((_np.asarray(pts, float), faces))
    return out


#: Mesh resolution for FITTING -- a geometry fit, and the pose fit behind
#: every overlay. What a person looks at is still drawn at full resolution,
#: where the cost is paid once rather than thousands of times.
#:
#: The pose fit used the full mesh until it was measured on the F-16 Viper,
#: against both of its photographs:
#:
#:     view           mesh    faces    time   residual   pose
#:     threequarter   full     1989   61.8 s     2.55%   elev 16.0 azim 202.8
#:     threequarter   8         449   25.0 s     2.57%   elev 16.8 azim 203.8
#:     underside      full     1989   47.6 s     3.69%   elev 41.0 azim 127.4
#:     underside      8         449   18.1 s     3.60%   elev 41.1 azim 127.6
#:
#: 2.5x faster for a pose within a degree and a residual within 0.09 points,
#: with the fitted scale identical to the pixel. That is worth having: on the
#: run that prompted this, a cold fit at 30-60 s meant the pool bought about
#: six of them, three probes were killed inside one, and the entry shipped an
#: overlay the tool had flagged as not the best basin because another search
#: was unaffordable.
_FIT_RESOLUTION = 8


def _depth_order(parts, params, centre):
    """Component indices, nearest the camera first."""
    import numpy as _np
    R = _rotation(params[0], params[1], params[2])
    return sorted(range(len(parts)),
                  key=lambda i: -float(((parts[i][0] - centre) @ R.T)[:, 2].mean()))


def _time_left(reserve=5.0):
    """
    Seconds before this probe is killed, or None outside a probe.

    THE KILL IS ENFORCED FROM OUTSIDE and used to be invisible from in here, so
    a long fit could only end one way: at the wall, with everything it had
    computed thrown away. Measured -- a reconstruction spent two 300 s probes
    inside `fit_geometry`, was killed on both, and then abandoned fitting and
    set the fuselage width and root chord by eye.

    `kernel.py` now puts `_PROBE_DEADLINE_S` in the namespace before the
    probe's own code runs, so a search can bound itself and RETURN WHAT IT HAS
    instead of losing it. `reserve` keeps back enough to print the result,
    because a fit that converges and is killed while formatting has still lost.

    None at render time and in a plain `python` process, where there is no
    deadline and nothing should be truncated on account of one.
    """
    import time as _t
    end = globals().get("_PROBE_DEADLINE_S")
    if end is None:
        return None
    return max(0.0, float(end) - _t.monotonic() - reserve)


def _rails(v, lo, hi):
    """
    Which pose parameters sat on a bound. Azimuth is exempt.

    Pulled out of `_fit_pose` so the quadrant-scan trigger and the verdict it
    reports cannot disagree about what "on a bound" means.

    AZIMUTH IS EXEMPT because it is CYCLIC: cold it is bounded 0..360 and those
    are the same camera, so measuring linear distance to each end flagged
    anything within 2% of 360 deg -- 7.2 deg -- of the seam. That is every
    nose-on and tail-on view. Measured on the Little Piggy `ahead-below` frame,
    whose azimuth lands at 0.3-1.6 deg on every seed: even its CORRECT 6.17%
    fit was stamped POSE NOT CONVERGED, after which `compare_to_photo` says
    "read nothing", `completeness` refuses and `fit_geometry` marks the seed ON
    A BOUND. A seam is not a wall.

    It stays bounded rather than being made periodic because the normalisation
    in `_fit_pose` needs a finite box; only the VERDICT was wrong.
    """
    return [n for n, x_, l_, h_ in zip(
                ("elev", "azim", "roll", "scale", "tx", "ty", "distance"),
                v, lo, hi)
            if n != "azim"
            and min(abs(x_ - l_), abs(x_ - h_)) < 0.02*(h_ - l_)]


def _fit_pose(parts, mask, pose=None, work=220, seed=1, budget=None,
              pinned=False):
    """
    Camera pose by symmetric chamfer distance between outlines.

    SYMMETRIC: model-to-photo alone shrinks the model onto a corner of the
    subject, photo-to-model alone inflates it to cover everything.

    SCREENED MULTI-START: 72 seeds are scored and ONE is descended on. It was
    36 scored and the best four descended, under Nelder-Mead -- running a full
    descent from every seed spent its time polishing basins that could not win,
    156 s against 13 s for the same optimum. The CMA rewrite reduced that to
    `scored[0]` and this line went on claiming four for a while; it is one.

    The screen covers both hemispheres now. It cannot RANK -- a raw seed's
    score says nothing, because its scale and translation come from the mask
    bounding box -- so its only job is to put the single descent somewhere
    plausible, and it used to have nowhere below the aircraft to put it.

    `seed` IS THE CMA SEED, and it is the only thing that makes a second run
    a second OPINION. It was fixed at 1, so re-running a cold fit returned a
    bit-identical answer and "try another seed" was advice no caller could
    act on. `compare_to_photo` now varies it to confirm its own result.

    `pinned` TAKES THE ANGLES AS GIVEN and searches only what is left: scale,
    the two translations and perspective distance. A `pose` otherwise NARROWS
    the search to +/-25 deg and still pays a full 7-DOF descent, which is the
    same ~10 s whether the caller knows the camera or is guessing at it.

    Measured on the FT A-10 Warthog, 2026-10-10: a reconstruction spent 703 s
    of its 819 s probe pool on camera fits, 22 of its 44 probes, and ran
    `fit_geometry` ONCE on ONE constant. Most of those fits re-derived a
    camera the previous probe had already printed -- the notes came back
    within a tenth of a degree of each other -- because there was no way to
    say "this one, do not look again". Pinned is that way.

    IT IS NOT A FIT AND MUST NOT READ AS ONE. Four free parameters cannot
    disagree with an asserted camera; they can only place it. So a pinned
    result is never confirmed, never cached as though it had been searched,
    and says POSE PINNED in the note.
    """
    import numpy as _np
    from scipy.optimize import minimize as _minimize
    from scipy import ndimage as _nd
    from PIL import Image as _Image

    # A PIN WITH NOTHING TO PIN TO is a cold search wearing the word, and it
    # would report POSE PINNED over a camera nobody asserted. Refused here
    # rather than ignored, because the note is what a reader trusts.
    if pinned and pose is None:
        raise ValueError(
            "pinned=True needs a pose to pin to. Pass pose=(elev, azim, roll) "
            "from a note you have already read, or drop pinned and let it fit.")

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

    if pose is not None:
        roll0 = float(pose[2]) if len(pose) > 2 else 0.0
        starts = [[float(pose[0]), float(pose[1]), roll0, s0, cx, cy, 0.0]]
    else:
        # BOTH HEMISPHERES. These were (15, 40, 65) -- every seed ABOVE the
        # aircraft -- while the bounds below run to -30. The comment under them
        # claims CMA "carries no implicit camera-is-above assumption in a
        # hand-picked elevation range", and that was true of the bounds and
        # false of the seeds sitting on top of them.
        #
        # Measured on the Little Piggy, whose `ahead-below` frame is shot from
        # underneath: the cold fit returned elev +85 (the ceiling) at 7.20% on
        # two CMA seeds in three, against a true basin at 6.17%. Model aircraft
        # in flight are mostly photographed from below, so the old grid had the
        # prior exactly backwards. Raising `sigma0` does not help -- 0.25, 0.40
        # and 0.55 all found the good basin 1 time in 3 -- because the problem
        # is where the search STARTS, not how far it steps.
        starts = [[e0, float(a0), 0.0, s0, cx, cy, 0.0]
                  for a0 in range(0, 360, 30)
                  for e0 in (-65.0, -40.0, -15.0, 15.0, 40.0, 65.0)]
    scored = sorted(((cost(_np.array(v)), v) for v in starts),
                    key=lambda t: t[0])

    # CMA-ES, NOT A SEED GRID. The grid this replaced screened 36 starts by
    # raw cost and failed every cold start on an oblique view -- 42 to 65 deg
    # elevation against a true 24. Forty times more seeds did not help: a raw
    # seed's score says nothing, because its scale and translation come from
    # the mask bounding box. CMA-ES needs no grid, carries no implicit
    # "camera is above the aircraft" assumption in a hand-picked elevation
    # range, and has no zero-seeded-simplex trap (Nelder-Mead gives a
    # coordinate seeded at exactly 0.0 an absolute step of 2.5e-4, which
    # silently pinned roll and distance on every fit).
    import cma as _cma
    # SYMMETRIC IN ELEVATION. It was -30/+85, which cannot reach a camera more
    # than 30 deg below the aircraft -- and an in-flight photograph of a model
    # is usually taken from below. +/-85 rather than +/-90 because azimuth and
    # roll become the same rotation at the pole, so a whole line of solutions
    # scores identically and the optimiser wanders along it.
    lo = _np.array([-85.0,   0.0, -30.0, 0.3*s0, cx-250, cy-250, -7.0])
    hi = _np.array([ 85.0, 360.0,  30.0, 3.0*s0, cx+250, cy+250,  7.0])
    # A POSE NARROWS THE SEARCH, it does not merely seed it. +/-25 deg around
    # what the caller asserted, which is why a WRONG pose is worse than none:
    # it trades a global search for a local one centred off-target. Measured
    # on the F-16 studio view, perturbing a converged pose by 5 deg elevation
    # and 5 of azimuth returned 8.89% against a 2.05% cold baseline.
    #
    # CLAMPED TO THE PHYSICAL BAND, which it was not. The window was the hint
    # +/-25 with no intersection, so a -75 deg hint searched -100..-50 and
    # returned a fitted -100 -- past straight-down, meaningless, and reported
    # without comment. Re-seeding from a railed +84.8 was the same fault the
    # other way: a window of 59.8..109.8, converging to +110. Azimuth is NOT
    # clamped because it is cyclic; it wraps.
    if pose is not None:
        lo[0], hi[0] = (max(lo[0], float(pose[0])-25),
                        min(hi[0], float(pose[0])+25))
        lo[1], hi[1] = float(pose[1])-25, float(pose[1])+25
        # A ROLL ASSERTION MOVES ITS BAND TOO. Roll is bounded +/-30 deg cold,
        # so one outside that was clipped back to +/-30 and the number the
        # caller passed never reached the search -- silently ignored, which is
        # worse than refused.
        if len(pose) > 2:
            lo[2], hi[2] = float(pose[2])-25, float(pose[2])+25
    # WHICH PARAMETERS THE DESCENT MAY TOUCH. Everything, or -- pinned -- only
    # the four that place an asserted camera: scale, the two translations and
    # perspective distance. The frozen entries come from `start`, which for a
    # `pose` is built out of that pose above, so the angles the caller named
    # are carried through untouched rather than re-found.
    _free = _np.array((3, 4, 5, 6) if pinned else (0, 1, 2, 3, 4, 5, 6), int)

    def _descend(lo, hi, start, secs=None):
        """
        One CMA descent inside [lo, hi], over `_free`. -> (params7, cost)

        `secs` bounds its wall clock, so it returns its best-so-far instead of
        being killed with the run's work inside it. None outside a probe, where
        there is no deadline and nothing should be truncated on account of one.
        """
        full = _np.clip(_np.array(start, float),
                        lo + 1e-6*(hi-lo), hi - 1e-6*(hi-lo))
        l_, h_ = lo[_free], hi[_free]
        def _x(u):
            out = full.copy()
            out[_free] = l_ + _np.clip(u, 0, 1)*(h_ - l_)
            return out
        u0 = (full[_free] - l_)/(h_ - l_)
        opts = {"bounds": [0, 1], "popsize": 18, "maxiter": 400,
                "tolfun": 2e-2, "tolfunhist": 2e-3, "verbose": -9,
                "seed": seed}
        if pinned:
            # A SMALLER PROBLEM WANTS A SMALLER SEARCH. Scale, the two
            # translations and distance are near-convex once the angles are
            # fixed -- the bounding-box seed is already close and there are
            # no mirror basins left to escape, because the mirrors live in
            # the angles. The 7-DOF settings spend their population exploring
            # a landscape that is no longer there.
            #
            # Measured on the FT A-10 Warthog's three views: at popsize 18 /
            # maxiter 400 a pinned fit took 5.0-9.5 s against 10-46 s
            # searched, which is the right direction and nowhere near the
            # ~1 s a redraw should cost. The residuals it returns are
            # unchanged to a few hundredths of a point.
            opts.update(popsize=8, maxiter=120, tolfun=5e-2, tolfunhist=5e-3)
        if secs is not None:
            opts["timeout"] = max(2.0, float(secs))
        es = _cma.CMAEvolutionStrategy(u0, 0.25, opts)
        es.optimize(lambda u: cost(_x(_np.asarray(u))))
        return _x(es.result.xbest), es.result.fbest

    budget = _time_left() if budget is None else budget
    per = None if budget is None else budget/4.0
    # NOT ENOUGH TIME TO SCAN: spend it all on ONE descent instead. Four
    # quadrants each given a couple of seconds is four fits that have not
    # converged, which is worse than one that has -- and the floor inside
    # `_descend` means four tiny slices still overrun a small grant. Measured:
    # with a 40 s probe this spent 80 s before the fix and was killed.
    if pose is not None or (per is not None and per < 8.0):
        v, val = _descend(lo, hi, scored[0][1], budget)
    else:
        # FOUR QUADRANTS, JUDGED BY CONVERGED COST. One descent from the best
        # SCREENED seed is what this used to do, and the screen cannot rank:
        # a raw seed's score says nothing because its scale and translation
        # come from the mask bounding box, which is why "forty times more
        # seeds did not help". So the choice between hemispheres was made by
        # the one number here that is meaningless.
        #
        # Measured, and this is why the cheap fix was not enough: simply
        # seeding below as well as above moved WHICH arbitrary seed won, and
        # on the F-16 that traded a 2.05% studio fit for a 5.20% one in the
        # wrong hemisphere. Converged cost is the only signal worth choosing
        # on, so run the descent in each region and compare the results.
        #
        # Four and not more: top/bottom and nose/tail are the two mirrors a
        # near-planar airframe actually confuses, and they are INDEPENDENT --
        # applying both lands on the antipodal camera, which measured worst or
        # joint-worst on four views of four because it mirrors the
        # silhouette's handedness while the mask does not mirror with it.
        # A CONDITIONAL SCAN WAS TRIED AND COST MORE THAN IT SAVED. Running
        # one descent first and scanning only when it railed or came back
        # DOUBTFUL sounds cheaper; measured on the F-16 it fired on both views
        # anyway and spent 57 s against 46 s, because a descent from an
        # arbitrary screened seed over the full box usually does rail. Four
        # descents, always, is the simpler and faster shape.
        best = None
        for e_lo, e_hi in ((0.0, hi[0]), (lo[0], 0.0)):
            for a_lo, a_hi in ((0.0, 180.0), (180.0, 360.0)):
                qlo, qhi = lo.copy(), hi.copy()
                qlo[0], qhi[0] = e_lo, e_hi
                qlo[1], qhi[1] = a_lo, a_hi
                here = [s for s in starts
                        if e_lo <= s[0] <= e_hi and a_lo <= s[1] <= a_hi]
                seed_v = min(here, key=lambda s: cost(_np.array(s))) \
                    if here else [(e_lo+e_hi)/2, (a_lo+a_hi)/2,
                                  0.0, s0, cx, cy, 0.0]
                got = _descend(qlo, qhi, seed_v, per)
                if best is None or got[1] < best[1]:
                    best = got
        v, val = best
    e, a, ro, s, tx, ty, d = unpack(v)
    # A PARAMETER ON ITS BOUND IS NOT CONVERGED. The three-quarter pose this
    # notebook quoted as "best" for an entire session had its perspective
    # distance railed at the sigmoid ceiling -- effectively orthographic,
    # which _project's own docstring warns against -- and nothing said so.
    # Azimuth is exempt; `_rails` says why.
    # ONLY WHAT WAS SEARCHED CAN RAIL. A pinned angle sits where the caller
    # put it, and the +/-25 window around it is never entered -- so measuring
    # its distance to a bound it was not free to reach would report the
    # ASSERTION as a failed fit. Scale, translation and distance still rail
    # and still matter: those four are what a pin leaves to be found.
    railed = _rails(v, lo, hi)
    if pinned:
        railed = [n for n in railed if n in ("scale", "tx", "ty", "distance")]
    return (e, a % 360, ro, s/sc, tx/sc, ty/sc, d), val/sc, centre, railed


def _component_residuals(airplane, mask, params, centre, work=220):
    """Each component's share of the model-to-photo chamfer. -> {name: 0..1}

    WHICH COMPONENT IS WRONG is the question a high residual actually raises,
    and it is the one `fit_geometry`'s caller has to answer to choose a `free`
    set. `_model.py` fixes dozens of constants; picking three of them by eye
    off an overlay is the step that does not happen, and the run then does not
    call the fitter at all.

    SUMMED, not averaged, which is where this differs from `fit_geometry`'s
    own `_score(per_part=True)`. That one compares a component against
    ITSELF before and after, so a per-pixel mean is the right statistic.
    Here one total is being apportioned, so a component's share has to scale
    with how much outline it owns -- averaging makes a wingtip rail with
    twenty bad pixels rank beside a fuselage with two thousand.

    MODEL-TO-PHOTO ONLY. The symmetric cost `_fit_pose` minimises also runs
    photo-to-model, which cannot be attributed: a stretch of photograph
    outline that no component reaches belongs to whichever is MISSING, and
    naming one would be a guess. `completeness` is the tool for that half.

    ON THE OUTER SILHOUETTE, which is the outline the fit actually
    minimises. This used to score each component's OWN outline against the
    mask edge, and that is a different quantity: a surface buried inside the
    body -- a pylon between fuselage and nacelle, a spar, a fin in the
    shadow of a nacelle -- has its whole outline deep in the mask interior,
    far from the edge, and so collected a large distance for doing exactly
    what an interior surface is supposed to do.

    Measured on the FT A-10 Warthog, 2026-10-10. `Nacelle Pylons` contributes
    3-7% of the model's outer outline across the three views and was charged
    14-20% of the residual -- second or third on every view, above the
    tailplane and the fins. The entry's note duly told the run to "free the
    constants those point at". Freeing them could not have moved the
    residual by construction: the chamfer never sees that outline. A
    diagnostic that points the fitter at a component it cannot act through
    is worse than no diagnostic, because the fit comes back having changed
    nothing and the run believes the shape is settled.

    So an edge pixel counts for a component only where it lies on the union
    silhouette. A component contributing no outline now scores ~0%, which is
    the true statement about what it can do to this number -- and
    `completeness` says the other true thing about it, that the photographs
    cannot see it at all.
    """
    import numpy as _np
    from scipy import ndimage as _nd
    from PIL import Image as _Image

    h, w = mask.shape
    sc = work / max(h, w)
    tw, th = max(1, int(w*sc)), max(1, int(h*sc))
    tgt = _np.asarray(_Image.fromarray(mask.astype(_np.uint8)*255)
                      .resize((tw, th), _Image.NEAREST)) > 127
    dt = _nd.distance_transform_edt(~(tgt & ~_nd.binary_erosion(tgt)))

    e, a, ro, s, tx, ty, d = params
    p = (e, a, ro, s*sc, tx*sc, ty*sc, d)
    names = [c.name for c in list(airplane.wings) + list(airplane.fuselages)]
    parts = _parts_of(airplane, resolution=_FIT_RESOLUTION)

    # THE UNION FIRST, because its edge is the only outline the cost knows.
    # `_fit_pose` rasterises every component, ORs them, and takes one edge
    # off the result; matching that here is what makes these shares add up
    # to the number they are apportioning.
    rast = [_raster(pts, faces, p, (tw, th), centre) for pts, faces in parts]
    union = _np.zeros((th, tw), bool)
    for m in rast:
        union |= m
    outer = union & ~_nd.binary_erosion(union)

    share = {}
    for name, m in zip(names, rast):
        # OWNED, not merely touched: dilate by one so a component whose
        # boundary sits a pixel inside the union edge -- rasterisation makes
        # that common where two parts meet -- still claims its own outline.
        own = outer & _nd.binary_dilation(m, _np.ones((3, 3)))
        if own.any():
            share[name] = share.get(name, 0.0) + float(dt[own].sum())
    total = sum(share.values())
    if not total:
        return {}
    return {k: v/total for k, v in sorted(share.items(),
                                          key=lambda kv: -kv[1])}


# How far the chamfer residual may run, as a fraction of sqrt(mask area),
# before the overlay is declared untrustworthy. A good fit sits near 2%;
# the seed-to-seed noise floor measured on two store photographs is 0.024%,
# so anything inside that is not a difference.
_POSE_DOUBTFUL = 0.040

#: When two independent CMA seeds count as the SAME answer, as a fraction of
#: sqrt(mask area). This is a materiality test, not a measurement-noise one:
#: reseeding a NARROWED search reproduces itself to 0.024%, but two COLD
#: searches explore a genuinely multi-modal landscape and scatter far wider.
#: Measured here -- belly 2.97% and 2.91% (the same answer twice), studio
#: 2.05% and 5.20% (not). 0.25 pp separates them and is about a tenth of a
#: typical residual, which is the scale at which a difference would change
#: what anyone did about it.
_POSE_AGREE = 0.0025

#: Last converged pose per (view, geometry). Never consulted at render: see
#: `compare_to_photo`. Backed by `_scratch/poses.json` so it OUTLIVES THE
#: KERNEL -- see `_pose_remembered`.
_POSE_CACHE = {}


def reference_views():
    """Every reference photograph that has a mask, in a stable order. -> [str]

    A VIEW IS A MASK, not a photograph: `_reference/` holds the originals too,
    and one without a cut mask is a picture nothing can be fitted against.
    `fit_geometry` has selected on `*.mask.png` since it was written and
    `show_all_views` needs the same list; two globs agreeing by hand is one
    that will disagree the first time the suffix changes.
    """
    root = _pathlib.Path(_os.environ.get("NB_ROOT", "."))
    return sorted(p.name[:-len(".mask.png")]
                  for p in (root / "_reference").glob("*.mask.png"))


def _pose_store():
    """Where remembered poses live, or None when there is nowhere. -> Path"""
    root = _os.environ.get("NB_ROOT")
    return _pathlib.Path(root) / "_scratch" / "poses.json" if root else None


def _pose_remembered(name, airplane):
    """
    The last converged pose for this view and this geometry. -> pose3 or None

    IT HAS TO SURVIVE THE KERNEL, and in memory it did not. Every
    `write_file` to `_model.py` restarts the probe kernel -- the chapter is
    re-exec'd so the model is the one on disk -- and the dict went with it.
    The build loop is WRITE, LOOK, WRITE, so the cache was empty at exactly
    the moment it was wanted, and the next overlay paid a cold 72-seed screen
    to re-find a camera the previous probe had printed in full.

    Measured on the FT A-10 Warthog, 2026-10-10: five model writes, and 703 s
    of an 819 s probe pool spent fitting cameras.

    KEYED ON THE GEOMETRY, not just the view. `_geometry_fingerprint` carries
    the component count and the bounding box, so a pose is dropped the moment
    the aircraft changes structurally -- a component added or removed, a span
    moved -- while surviving the millimetre station edits a fit makes. That
    is the property that makes reuse safe rather than merely cheap, and it is
    why the key must not be loosened to the view alone.

    A corrupt or unreadable store is a MISS, never an error: the only cost of
    not remembering is the search that used to run every time.
    """
    key = f"{name}|{_geometry_fingerprint(airplane)}"
    if key in _POSE_CACHE:
        return _POSE_CACHE[key]
    p = _pose_store()
    if p is None or not p.exists():
        return None
    try:
        import json as _json
        got = _json.loads(p.read_text()).get(key)
        return tuple(got) if got else None
    except Exception:                                        # noqa: BLE001
        return None


def _pose_remember(name, airplane, pose3):
    """Record a converged pose, in memory and on disk. Never raises."""
    key = f"{name}|{_geometry_fingerprint(airplane)}"
    _POSE_CACHE[key] = tuple(float(x) for x in pose3)
    p = _pose_store()
    if p is None:
        return
    try:
        import json as _json
        p.parent.mkdir(parents=True, exist_ok=True)
        held = {}
        if p.exists():
            held = _json.loads(p.read_text())
        held[key] = list(_POSE_CACHE[key])
        # BOUNDED. One entry per (view, geometry) and the geometry moves on
        # every fit, so an unpruned file grows for the life of the notebook.
        # Newest 64 is several views across many edits and still a small read.
        if len(held) > 64:
            held = dict(list(held.items())[-64:])
        p.write_text(_json.dumps(held, indent=1))
    except Exception:                               # noqa: BLE001, S110
        # NOTHING TO REPORT AND NOWHERE TO REPORT IT. This runs inside a
        # probe's overlay call; a warning here would land in the middle of a
        # note the model reads as measurement. The only consequence of a
        # failed write is the next probe paying the search again.
        pass


def _geometry_fingerprint(airplane):
    """A cheap key for "is this the same aircraft as last call?". -> str

    Vertex counts and the bounding box, not the mesh: a fit moves stations by
    millimetres and a warm start that survives that is the whole point, while
    anything structural -- a component added, a span changed -- moves the box
    and drops the entry. Wrong in the safe direction either way, since a miss
    only costs the cold search that used to run every time.
    """
    import numpy as _np
    try:
        comps = list(airplane.wings) + list(airplane.fuselages)
        pts = _np.vstack([_np.asarray(c.mesh_body(method="quad")[0], float)
                          for c in comps])
    except Exception:
        return "?"
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return (f"{len(comps)}:{len(pts)}:"
            + ":".join(f"{v:.3f}" for v in (*lo, *hi)))


def _reference_image(name):
    """The photograph and its mask, by reference name. -> (rgb float, bool mask)"""
    import numpy as _np
    from PIL import Image as _Image
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
    return (_np.asarray(_Image.open(img_path).convert("RGB")).astype(float),
            _np.asarray(_Image.open(mask_path).convert("L")) > 127)


#: Words in a reference `.txt` that assert which side the camera is on. The
#: description is written BEFORE anything is fitted, which is what makes it
#: independent evidence rather than a restatement of the fit.
#: PART NAMES ARE NOT CAMERA POSITIONS, and the first version of this list
#: conflated them. The F-16's description says "the dorsal spine" and "the
#: ventral fin" in one sentence while asserting the camera is ABOVE; with
#: `dorsal`/`ventral`/`belly`/`underside` in these lists it read as saying
#: both and therefore nothing. Only words about where the CAMERA is.
_SAYS_BELOW = ("below", "beneath", "underneath", "from under")
_SAYS_ABOVE = ("above", "overhead", "from over", "top-down", "plan view")


def _described_side(name):
    """
    +1, -1 or None: which side of the aircraft the `.txt` claims the camera is.

    THE ONE PIECE OF EVIDENCE THE SILHOUETTE DOES NOT CONTAIN. A foam aircraft
    is nearly planar, so the outline seen from 20 deg above and 20 deg below is
    very nearly the same shape, and the chamfer residual between the two
    mirrors differs by noise -- measured at 3.97% against 4.02% on the Little
    Piggy studio frame, which is to say not at all. No optimiser can resolve
    that, because the information is not there.

    It is in the description. `read_reference("photographs")` already tells the
    coordinator to "read the fitted camera back against your own description",
    and the F-16 shows what happens when nobody does: a frame described as
    "seen from BELOW and BEHIND" fitted at elev +36 through four entries and
    reached committed prose. So the comparison is made here, every time, and
    reported in the note rather than left as a chore.

    NOT a constraint on the fit. The `.txt` is unverified prose and can itself
    be wrong -- that is the F-16 case exactly -- so a disagreement is surfaced
    for a person to settle, never silently imposed on the search.
    """
    root = _pathlib.Path(_os.environ.get("NB_ROOT", "."))
    try:
        said = (root / "_reference" / f"{name}.txt").read_text().lower()
    except OSError:
        return None
    # COUNTED, NOT TESTED FOR PRESENCE. A description that settles the question
    # still mentions the other side in passing -- "the chin intake ... seen
    # obliquely from above, not silhouetted from below" asserts ABOVE twice and
    # denies BELOW once, and presence-testing read that as a contradiction and
    # gave up. Counting gets it right without parsing negation, which is the
    # other way to handle it and needs a grammar.
    below = sum(said.count(w) for w in _SAYS_BELOW)
    above = sum(said.count(w) for w in _SAYS_ABOVE)
    if below == above:          # silent, or genuinely balanced
        return None
    return -1 if below > above else +1


def compare_to_photo(airplane, name, pose=None, fill=0.22, refit=None):
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

    `pose=(elev, azim)` or `(elev, azim, roll)` ASSERTS the camera. It used
    to be called `hint`, which read as a free suggestion, and it is not one:
    a pose NARROWS the search to +/-25 deg around itself, so a wrong one is
    worse than none. Measured on the F-16 studio view, perturbing an already
    converged pose by 5 deg of elevation and 5 of azimuth returned 8.89%
    against a 2.05% cold baseline. Pass one when you are ASSERTING something
    the chamfer cannot see -- an aircraft is near-symmetric, so azimuth and
    azimuth+180 can both fit a silhouette and only a person can say which is
    nose-left -- or to pin the camera in an entry so the figure redraws the
    same way at render. The scale, translation and perspective distance are
    still fitted from the mask either way.

    Do NOT pass one to go looking for a better basin. In a probe the last
    converged pose for this view is reused automatically, and above a 1.2%
    residual the fit confirms itself from a second CMA seed and says whether
    what is left is camera or SHAPE. A caller that perturbs the pose by hand
    is re-implementing that loop, badly: the run this was written for wrote
    a 3x3 grid, had both probes killed on budget, and got two numbers worse
    than the one it started from.

    `refit=False` PINS the pose instead of searching around it: the angles
    are taken as given and only scale, translation and distance are found.
    Use it to REDRAW a camera an earlier probe already converged on and
    printed -- which is most of the overlays a build loop draws.

    Measured on the FT A-10 Warthog's three views, same machine, same model:

      compare_to_photo(airplane, v)                    cold    41-78 s
      compare_to_photo(airplane, v, pose=p)            fitted  10-46 s
      compare_to_photo(airplane, v, pose=p, refit=False)  pinned  3-4 s

    and the pinned residuals land within 0.01-0.32 pp of the fitted ones at
    a pose that had already converged. It is three to ten times cheaper, not
    free: the cost is dominated by rasterising the model once per trial, and
    pinning removes trials rather than rasters.

    DEFAULT: fit in a probe, PIN AT RENDER. An entry passes the pose it
    justified in a probe, and at render the job is to redraw that camera, not
    to look for it again -- so a render with a `pose` pins unless told
    otherwise. That makes the committed figure reproducible, which is what
    rule 12 is for, and takes the overlay's ~25 s surcharge off ENTRY_CEILING.
    `refit=True` forces the search anywhere, including at render.

    A PINNED RESULT IS NOT EVIDENCE THE CAMERA IS RIGHT. Four free parameters
    cannot argue with an asserted angle; they can only place it. So a pinned
    overlay is never confirmed, never cached, and never reports CONVERGED.
    """
    import numpy as _np
    from PIL import Image as _Image
    from scipy import ndimage as _nd

    photo, mask = _reference_image(name)
    H, W = mask.shape

    # FIT ON THE CHEAP MESH, DRAW ON THE FULL ONE. The search rasterises
    # thousands of times and the drawing once, so the two want different
    # meshes -- and the pose that comes back is the same one. Both use the
    # centre the fit returned, so the projection is identical either way.
    parts = _parts_of(airplane)
    cheap = _parts_of(airplane, resolution=_FIT_RESOLUTION)

    # WARM START, PROBE-SIDE ONLY. Within one probe kernel the geometry barely
    # moves between calls and the camera does not move at all, so re-running a
    # cold 36-seed screen per call is work already done. At RENDER this is off:
    # an entry pins its camera with `pose=`, and a figure that silently picked
    # up state from whatever ran before it would stop being reproducible, which
    # is the property rule 12 exists to protect.
    warm = pose
    if warm is None and _IN_PROBE:
        warm = _pose_remembered(name, airplane)

    # PIN AT RENDER, FIT IN A PROBE, unless the caller said which. The entry
    # passing `pose=` has already justified that camera in a probe; redrawing
    # it is not an occasion to search again, and a search that lands somewhere
    # else makes the committed figure depend on the optimiser rather than on
    # the file. `refit=True` overrides, and a render with no pose has nothing
    # to pin to and fits as it always did.
    pin = (not _IN_PROBE) if refit is None else (not refit)
    pin = bool(pin) and warm is not None

    params, resid, centre, railed = _fit_pose(cheap, mask, pose=warm,
                                              pinned=pin)
    scale_px = float(_np.sqrt(mask.sum()))

    # CONFIRM THE RESULT RATHER THAN ASK THE CALLER TO. Above 1.2% this used
    # to assert "another seed does better" -- untested -- and prescribe
    # `hint=(elev±5, azim±10)`. Both halves were wrong. The F-16's cold fits
    # had already converged (2.05% and 2.97%, reproduced to a tenth of a
    # degree by a reseed), so the advice sent a run to confirm a fit it
    # already had: it wrote a 3x3 grid around a function that screens 36
    # seeds and runs CMA-ES internally, had both probes killed on budget
    # (2 of 9 fits, 2 of 4), and the two studio perturbations it did get back
    # were 8.89% and 4.79% against a 2.05% baseline -- because a pose NARROWS
    # the search to +/-25 deg around a centre that was already right.
    #
    # Only this function can settle it cheaply, so it does: one more fit from
    # a different CMA seed, ~20 s, against the 75 s the caller spent failing.
    # Probe-side only -- at render the entry has pinned its pose and the
    # figure just redraws it, so ENTRY_CEILING is unmoved.
    # NOT AFTER A PIN. The confirm fit asks "would an independent search land
    # here?", and the answer is interesting only when a search ran. Pinned,
    # the angles came from the caller, so a cold reseed is not confirming the
    # result -- it is doing the 10 s of work the pin was asked to skip, and
    # then reporting a verdict about a fit that did not happen.
    confirmed = None
    if (_IN_PROBE and not pin and not railed
            and resid <= _POSE_DOUBTFUL * scale_px
            and resid > 0.012 * scale_px):
        # THE CONFIRM FIT IS COLD, ALWAYS, and that is the point of it. Run
        # from the same `pose` it would be narrowed to the same +/-25 deg
        # band, agree with itself, and report a wrong assertion as converged
        # shape -- a confident false diagnosis, which is worse than the
        # ambiguity it replaced. Cold, it TESTS the assertion instead.
        p2, r2, c2, rl2 = _fit_pose(cheap, mask, pose=None, seed=7)
        gap = 100.0*abs(r2 - resid)/scale_px
        was = 100.0*resid/scale_px
        # TAKE THE BETTER FIT ALWAYS -- it is free, it is already computed --
        # but CLASSIFY on whether the two answers differ MATERIALLY, which is
        # a separate question. Measured on this notebook: belly's seeds came
        # back 2.97% and 2.91%, a 2% relative difference that is the same
        # answer twice; studio's came back 2.05% and 5.20%, which is not.
        better = (not rl2) and r2 < resid
        # AN ASSERTED POSE IS NEVER OVERRIDDEN. `pose=` is for the thing the
        # chamfer cannot see -- an aircraft is near-symmetric, so azimuth and
        # azimuth+180 both fit a silhouette and only a person can say which
        # is nose-left. A cold fit that scores lower may simply have found
        # the mirror. So a better cold result is REPORTED against the
        # assertion and not silently swapped in.
        if better and pose is None:
            params, resid, centre, railed = p2, r2, c2, rl2
        if better and pose is not None:
            confirmed = ("disputed", gap, 100.0*r2/scale_px)
        elif gap <= _POSE_AGREE * scale_px:
            confirmed = ("converged", gap, was)
        elif better:
            confirmed = ("improved", gap, was)
        else:
            confirmed = ("stands", gap, 100.0*r2/scale_px)

    # ONLY A SEARCH IS WORTH REMEMBERING. A pinned result's angles are the
    # caller's, so storing them would let an assertion made once come back as
    # a remembered "converged" pose on a later probe that asserted nothing --
    # the caller's guess laundered into a measurement.
    if _IN_PROBE and not railed and not pin:
        _pose_remember(name, airplane, params[:3])

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

    # NORMALISE BY sqrt(MASK AREA), not by the longest extent. Views of the
    # same aircraft differ enormously in how much subject they contain: a
    # head-on silhouette here is a third the area of a three-quarter one, so
    # in raw pixels -- or against a span-like extent, which flatters a thin
    # head-on view -- damage to the smaller view is cheap. Measured: a fit
    # that freed six wing dimensions beat the untouched model on raw-pixel
    # mean AND raw-pixel worst-case, while actually being worse; normalised
    # by sqrt(area) the untouched model wins on both.
    pct = 100.0*resid/scale_px
    ok = resid <= _POSE_DOUBTFUL * scale_px

    # WHAT THE NOTE DOES NOT SAY, and why each was dropped:
    #
    #   the VIEW NAME. The caller passed it and already knows it. Saying it
    #   back lends a label nothing measured the authority of a measurement:
    #   this notebook's `belly` is a photograph taken from ABOVE, the fit
    #   returned elev +36 deg from the first call, and the disagreement went
    #   unread for four entries because the elevation was a bare number
    #   printed beside a confident name. Hence the plain words below.
    #
    #   the RESIDUAL IN PIXELS, and sqrt(mask area) beside it. Raw pixels are
    #   not comparable across views -- that is the whole reason for the
    #   normalisation ten lines up -- and printing them first got them quoted
    #   in prose: "studio 7.4 px, belly 15.1 px", two numbers a reader will
    #   divide and must not.
    #
    #   px/m. No run has used it.
    #
    # ROLL STAYS: an overlay displaced as a whole is most often rotated in
    # the image plane, and a reader cannot assert a number never shown.
    where = ("ABOVE" if params[0] >= 0 else "BELOW")
    note = (f"camera {abs(params[0]):.0f}° {where}, azim {params[1]:.0f}°, "
            f"roll {params[2]:.1f}°. ")
    # THE DESCRIPTION DISAGREES, SAY SO. Top and bottom are a genuine
    # degeneracy on a near-planar airframe -- the two mirrors scored 3.97% and
    # 4.02% on one frame here -- so the fit flips between them from one CMA
    # seed to the next and the residual cannot break the tie. The `.txt` can.
    # Reported, never imposed: the description is unverified prose and is
    # sometimes the thing that is wrong.
    said = _described_side(name)
    if said is not None and said != (1 if params[0] >= 0 else -1):
        note += (f"BUT {name}.txt SAYS THE CAMERA IS "
                 f"{'ABOVE' if said > 0 else 'BELOW'}. One of the two is "
                 f"wrong, and the silhouette cannot tell you which -- top and "
                 f"bottom mirror each other on a flat airframe. Look at the "
                 f"photograph and settle it, then assert the right one with "
                 f"pose=. ")
    if railed:
        note += ("POSE NOT CONVERGED: " + ", ".join(railed) +
                 " sat on a bound. Read nothing from this overlay. ")
    note += f"Fit: {pct:.2f}% of sqrt(mask area). "
    # SAY WHEN THE ANGLES WERE NOT SEARCHED. Every other line of this note
    # reports what a fit FOUND, and a pinned overlay's angles were found by
    # whoever typed them. Without this the reader has a residual, a camera
    # and no way to tell that two of those three were an input -- which is
    # how an assertion comes to be quoted as a measurement.
    if pin:
        note += ("POSE PINNED — the angles are the ones you passed, not "
                 "searched; only scale, translation and distance were fitted. "
                 "The residual still measures SHAPE against this camera, but "
                 "it is not evidence the camera is right. Drop refit=False to "
                 "let it look. ")
    # NO "Pose: good" AFTER A RAILED FIT. The two used to print together --
    # "Read nothing from this overlay. ... Pose: good." -- because `ok` only
    # ever tested the DOUBTFUL gate. A verdict that contradicts the warning
    # three words earlier is one a reader resolves in the direction they
    # already wanted.
    if not railed:
        note += ("Pose: good." if ok else
                 "Pose: DOUBTFUL — the outline does not track the aircraft. "
                 "Read nothing from this overlay; assert the camera with "
                 "pose=(elev, azim, roll), or ask for a better photograph.")

    # THE BRANCH. A residual above 1.2% has two causes and they want opposite
    # remedies, so the old note's single sentence was wrong half the time and
    # there was no way for the reader to tell which half. Now the confirm fit
    # above has already decided, and this reports what it found.
    # THE SHAPE VERDICT IS CHEAP AND RUNS EVERYWHERE; only the CONFIRM FIT
    # is probe-side. Splitting these was a correction: gating both on
    # `_IN_PROBE` meant a rendered note carried no component breakdown at
    # all, and the first entry to cite one -- reasonably, it is the useful
    # half -- crashed its render parsing for a line that was never emitted.
    # A second fit costs 20 s. One distance transform and N rasters costs
    # about one, so the page can have it.
    if not railed and ok and resid > 0.012 * scale_px:
        share = _component_residuals(airplane, mask, params, centre)
        worst = ", ".join(f"{k} {100*v:.0f}%"
                          for k, v in list(share.items())[:3])
        if confirmed and confirmed[0] == "converged":
            lead = (f" POSE CONVERGED — a second seed agrees to "
                    f"{confirmed[1]:.2f} pp, so the {pct:.2f}% left is SHAPE, "
                    f"not camera, and no further seed will move it.")
        elif confirmed and confirmed[0] == "stands":
            lead = (f" POSE STANDS — a second seed did worse "
                    f"({confirmed[2]:.2f}% against {pct:.2f}%), so this is the "
                    f"better of two independent searches and nothing found a "
                    f"lower basin. The {pct:.2f}% is most likely SHAPE.")
        elif pin:
            # PINNED, so there is nothing to hedge ABOUT: no search ran and
            # the line above already said the angles were given. What is
            # still worth saying is the half a pin does not weaken -- the
            # component breakdown below is measured against this camera and
            # is what `fit_geometry` acts on.
            lead = (f" The {pct:.2f}% is shape against the camera you pinned.")
        else:
            # No confirm fit ran -- a render, or a seed that disagreed. The
            # residual is still above the line, and that still means a reader
            # must not take shape off the picture.
            lead = (f" POSE HEDGED — {pct:.2f}% is above the 1.2% a converged "
                    f"fit sits at, so what is left is most likely SHAPE.")
        note += lead + ((f" Error sits on: {worst}." if worst else "")
                        + f" Free the constants those point at:"
                          f" fit_geometry(free={{...}}, poses={{{name!r}:"
                          f" ({params[0]:.1f}, {params[1]:.1f},"
                          f" {params[2]:.1f})}}).")

    if confirmed and confirmed[0] == "improved":
        note += (f" POSE IMPROVED — a second seed found a better basin and it "
                 f"is what you are looking at: {confirmed[2]:.2f}% -> "
                 f"{pct:.2f}%. The two disagreed, so this one is not confirmed "
                 f"either; if the outline still sits off as a whole, assert "
                 f"the camera with pose=(elev, azim, roll).")
    elif confirmed and confirmed[0] == "disputed":
        note += (f" POSE DISPUTED — you asserted this camera, and an "
                 f"unconstrained search found a better one: {confirmed[2]:.2f}% "
                 f"against your {pct:.2f}%. Yours is still what is drawn, "
                 f"because a lower residual can be the mirror basin on a "
                 f"near-symmetric aircraft and only you can rule that out. "
                 f"Look at the overlay: if the outline is displaced as a "
                 f"whole, drop the pose= and let it fit cold.")
    return out.astype(_np.uint8), note


def show_comparison(airplane, name, pose=None, fill=0.22, ax=None,
                    refit=None):
    """`compare_to_photo` onto matplotlib axes, for an entry. -> the note.

    PIN THE CAMERA HERE. An entry re-runs this at render, so passing the
    `pose` the probe converged on is what makes the committed figure redraw
    the same way every time. Without it the render refits cold, which costs
    the ceiling ~25 s a panel and can land somewhere else.

    A `pose` AT RENDER IS NOW PINNED by default -- the angles are taken as
    given and only scale, translation and distance are found, so a panel
    costs a few seconds instead of twenty-five and redraws identically every
    time. Pass `refit=True` to make the render search anyway, or
    `refit=False` in a probe to get the same cheap redraw there.
    """
    import matplotlib.pyplot as _plt
    rgb, note = compare_to_photo(airplane, name, pose=pose, fill=fill,
                                 refit=refit)
    if ax is None:
        _, ax = _plt.subplots(figsize=(7.0, 7.0*rgb.shape[0]/rgb.shape[1]))
    ax.imshow(rgb)
    ax.set_axis_off()
    return note


def show_all_views(airplane, poses=None, fill=0.22, refit=None, width=5.0):
    """
    Every reference view in one row of panels. -> (fig, {view: note})

    THE PANEL AN ENTRY ACTUALLY WANTS, built once here instead of in every
    probe that wants to look at the aircraft. Measured on the FT A-10
    Warthog, 2026-10-10: nine of the run's turns and about 400 s went into
    hand-assembling this figure -- `plt.subplots(1, 3)`, three
    `show_comparison` calls, `tight_layout`, `savefig` -- written out four
    times because the first lost `plt` to a kernel restart, the next two were
    killed on a budget nobody could size yet, and one more existed only to
    time a single panel. None of that is about the aeroplane.

    `poses` maps a view name to the camera it converged on. Views it does not
    name fall back to what this run already found for them, so in a probe the
    usual call is `show_all_views(airplane)` and it costs nothing to type.
    AN ENTRY SHOULD NAME THEM ALL: at render there is no probe history to
    fall back on, and a pose in the entry's source is the camera a reader can
    see and a later run can argue with.

    `refit` is `compare_to_photo`'s, with its default: pinned at render where
    a pose is known, searched in a probe. `width` is inches per panel.
    """
    import matplotlib.pyplot as _plt
    poses = dict(poses or {})
    names = reference_views()
    if not names:
        raise FileNotFoundError(
            "no reference photographs with masks in _reference/. "
            "The coordinator adds them with `nb reference`.")
    # ONE ROW. Views are compared against each other, and a reader does that
    # by scanning along them -- a grid makes two of them neighbours and the
    # rest strangers.
    fig, axes = _plt.subplots(1, len(names),
                              figsize=(width*len(names), width))
    axes = [axes] if len(names) == 1 else list(axes)
    notes = {}
    for ax, nm in zip(axes, names):
        notes[nm] = show_comparison(airplane, nm, pose=poses.get(nm),
                                    fill=fill, ax=ax, refit=refit)
    fig.tight_layout()
    return fig, notes


def with_control_surface(airplane, wing_name, name, deflection_deg):
    """
    A copy of `airplane` with a control surface on one wing. -> Airplane

    USE THIS INSTEAD OF REBUILDING `asb.Airplane`. Deflecting a surface
    tempts you to reassemble the aeroplane, and reassembling it means
    restating every component -- at which point the tailplane's chords and
    stations get retyped as literals in `_analysis.py` and quietly stop
    tracking `_model.py`. That happened here: an entry's trim analysis ran on
    a hand-copied stabiliser, so any correction to the real one would never
    have reached it.

    This never names a dimension. Every component, including any added
    later, comes along untouched, and the source airplane is not modified.
    """
    import copy as _copy
    out = _copy.deepcopy(airplane)
    cs = asb.ControlSurface(name=name, deflection=deflection_deg)
    hit = False
    for w in out.wings:
        if w.name == wing_name:
            for x in w.xsecs:
                x.control_surfaces = [cs]
            hit = True
    if not hit:
        have = ", ".join(w.name for w in out.wings)
        raise KeyError(f"no wing named {wing_name!r}; have: {have}")
    return out


def completeness(airplane, name, pose=None):
    """
    What is in the photograph that no component covers? -> (frac, note)

    NO PASS MARK, deliberately, for the same reason `compare_to_photo`
    returns no score: a threshold here is a number that gets satisfied
    rather than understood. Measured on a reasonable model at a correct
    pose -- IoU 0.77 -- 17.5% of the mask was still uncovered, most of it
    thin slivers along edges plus the propellers the model genuinely
    lacked. Any fixed gate would have rejected a sound reconstruction.

    What this gives you is WHERE. Look at the regions it names, and decide
    whether each is a component you have not built or a sliver along an
    edge you have.

    AND IT NAMES WHAT YOU BUILT THAT IS NOT THERE. The two directions are
    different faults with different remedies -- mask the model never reaches
    is a component MISSING, model outside the mask is one that should not
    exist, or is far too big -- and only the first was ever attributed. The
    second was a bare percentage, which is a number nobody can act on.

    Measured on the FT A-10 Warthog, 2026-10-10. Its model carried a
    `Nacelle Pylons` surface: a 160 x 104 mm canted plate between fuselage
    and nacelle, barely visible in any of the three photographs, and a
    LIFTING SURFACE in the VLM. The note said "8.0% of the model falls
    outside it" and named no component; the pose note put 20% of the
    residual on the pylons and that read as a shape to fit rather than a
    part to delete. It survived the entry, the assumptions prompt and two
    performance questions built on top of it.

    So a component whose own silhouette lands mostly off-mask is NAMED here.
    No threshold decides anything -- see the pass-mark note above, which
    applies with full force to this half too. The support fraction is
    printed beside the name and the reader decides.

    THE POSE DECIDES WHETHER THE NUMBER MEANS ANYTHING. An ill-posed model
    leaves most of the aircraft uncovered and every region looks missing.
    Measured on the same model and photograph:

        pose                       resid    uncovered
        correct                    3.07%       17.5%
        30 deg out in azimuth      7.21%       33.4%
        mirrored, from below       6.89%       44.0%

    So this refuses to report when the pose is DOUBTFUL. Pass `pose=` to
    reuse a pose you have already found with `compare_to_photo`, which is
    cheaper than fitting again and cannot land somewhere different.
    """
    import numpy as _np
    from scipy import ndimage as _nd
    photo, mask = _reference_image(name)
    # Fit on the cheap mesh, measure coverage on the full one -- see
    # `compare_to_photo`. The uncovered regions are what is being read here,
    # so they are rasterised at full resolution.
    parts = _parts_of(airplane)
    cheap = _parts_of(airplane, resolution=_FIT_RESOLUTION)

    # WARM START, PROBE-SIDE ONLY. Within one probe kernel the geometry barely
    # moves between calls and the camera does not move at all, so re-running a
    # cold 36-seed screen per call is work already done. At RENDER this is off:
    # an entry pins its camera with `pose=`, and a figure that silently picked
    # up state from whatever ran before it would stop being reproducible, which
    # is the property rule 12 exists to protect.
    warm = pose
    if warm is None and _IN_PROBE:
        warm = _pose_remembered(name, airplane)

    params, resid, centre, railed = _fit_pose(cheap, mask, pose=warm)
    scale_px = float(_np.sqrt(mask.sum()))
    pose_pct = 100.0*resid/scale_px

    if railed or pose_pct > 100*_POSE_DOUBTFUL:
        return None, (
            f"{name} — CANNOT JUDGE COMPLETENESS: the pose is "
            f"{pose_pct:.2f}% of sqrt(mask area)"
            + (f" and {', '.join(railed)} sat on a bound" if railed else "")
            + ". An ill-posed model leaves most of the aircraft uncovered, "
              "so every region would look missing. Fix the pose first — "
              "assert it with pose=(elev, azim, roll) — then ask again.")

    H, W = mask.shape
    cn = [c.name for c in list(airplane.wings) + list(airplane.fuselages)]
    per = []
    covered = _np.zeros((H, W), bool)
    for pts, faces in parts:
        m = _raster(pts, faces, params, (W, H), centre)
        per.append(m)
        covered |= m

    # SLACK IS THE POSE RESIDUAL, not a fixed fraction. The residual is the
    # measured scale at which model and photograph disagree for reasons that
    # are not missing components, so anything inside it is noise. Measured on
    # the P-38: a 3 px slack against a 10.4 px residual reported 20.6%
    # uncovered in 45 regions; at slack = residual it is 15.3% in 21, and the
    # output becomes readable.
    slack = max(3, int(round(resid)))
    near = _nd.binary_dilation(covered, _np.ones((slack, slack)))
    missing = mask & ~near

    # AND THE OTHER DIRECTION. Mask-not-covered finds a component you did not
    # build; model-outside-mask finds one you built that is not there, or is
    # far too big. They are different errors and only one of them was checked.
    mask_near = _nd.binary_dilation(mask, _np.ones((slack, slack)))
    excess = covered & ~mask_near

    lab, n = _nd.label(missing)
    frac = float(missing.sum())/float(mask.sum())
    xfrac = float(excess.sum())/float(mask.sum())
    # THE CHANGE IS INTERPRETABLE WHERE THE LEVEL IS NOT. A sound model at a
    # correct pose still showed 17.5% uncovered, so the absolute number says
    # little -- but "20.6% -> 14.1% after you enlarged the nacelle" is a fact
    # about the edit you just made. The build loop is a sequence; report
    # against the previous call on the same view.
    _hist = globals().setdefault("_COMPLETENESS_LAST", {})
    prev = _hist.get(name)
    delta = ""
    if prev is not None:
        d_in, d_out = 100*(frac-prev[0]), 100*(xfrac-prev[1])
        delta = (f"Since the last check: uncovered {d_in:+.1f} pts, "
                 f"outside {d_out:+.1f} pts"
                 + ("  — both better." if d_in < 0 and d_out < 0 else
                    "  — WORSE on both." if d_in > 0 and d_out > 0 else
                    "  — one improved, one did not.") + " ")
    head = (f"{name} — pose {pose_pct:.2f}% (good), slack {slack} px. "
            f"{100*frac:.1f}% of the mask uncovered; "
            f"{100*xfrac:.1f}% of the model falls outside it. " + delta)

    # WHOSE EXCESS IT IS. Unlike a gap, this needs no nearest-neighbour
    # guess: the pixels are the model's, so the component that drew them is
    # known exactly. Support is measured per component against its OWN area,
    # because share-of-total hides the case that matters -- a small part
    # entirely in the wrong place contributes little to the total and is
    # still entirely wrong.
    support, visible = {}, {}
    outer = covered & ~_nd.binary_erosion(covered)
    grown = _nd.binary_dilation(outer, _np.ones((3, 3)))
    for nm, m in zip(cn, per):
        area = float(m.sum())
        support[nm] = float((m & mask_near).sum())/area if area else 1.0
        # AND WHETHER THE PHOTOGRAPH CAN SEE IT AT ALL. A component buried
        # inside the body contributes no outline, so no overlay and no
        # residual can say anything about it -- not that it is right, and
        # not that it is wrong. That is a THIRD state beside covered and
        # uncovered, and conflating it with "supported" is how a surface
        # nobody can check comes to look checked.
        edge = m & ~_nd.binary_erosion(m)
        visible[nm] = (float((edge & grown).sum())/float(edge.sum())
                       if edge.any() else 0.0)
    # NAMED, NOT GATED. 0.5 is not a pass mark and nothing is refused on it;
    # it is the point at which "most of this component is off the
    # photograph" becomes a true sentence, which is all the note claims.
    unsupported = sorted((s, nm) for nm, s in support.items() if s < 0.5)
    # WHAT THE LAST EDIT DID TO THE VERDICT, which is the fact an ablation
    # is asking for: a component that was named and is not any more, or the
    # reverse. Levels are noisy between calls and names are not.
    was = set((prev[2] if prev is not None and len(prev) > 2 else ()) or ())
    now = {nm for _, nm in unsupported}
    _hist[name] = (frac, xfrac, tuple(sorted(now)))
    head += " "
    if prev is not None and was != now:
        came, gone = sorted(now - was), sorted(was - now)
        if came:
            head += "Newly outside the photograph: " + ", ".join(came) + ". "
        if gone:
            head += "No longer outside it: " + ", ".join(gone) + ". "
    if unsupported:
        head += ("OUTSIDE THE PHOTOGRAPH: "
                 + "; ".join(f"{nm} — {100*(1-s):.0f}% of its own silhouette "
                             f"falls off-mask here" for s, nm in unsupported)
                 + ". A component mostly outside the mask in EVERY view is "
                   "one the photographs do not show: delete it, or keep it "
                   "and declare_input why it is there. In one view only, it "
                   "is placed or sized wrong rather than imaginary — check "
                   "the others before cutting. ")
    elif xfrac > 0:
        thin = min(support.values())
        head += (f"Every component is mostly on the mask (least supported: "
                 f"{100*thin:.0f}%), so the {100*xfrac:.1f}% outside is edge "
                 f"and oversize, not a part that should not exist. ")

    # THE THIRD STATE. 0.10 is not a pass mark either: below about a tenth
    # of its own outline on the silhouette, a component is drawing almost
    # nothing a camera could photograph, and every sentence this function
    # and `compare_to_photo` emit about it is empty.
    unseen = sorted((v_, nm) for nm, v_ in visible.items() if v_ < 0.10)
    if unseen:
        head += ("THE SILHOUETTE CANNOT SEE: "
                 + "; ".join(f"{nm} ({100*v_:.0f}% of its outline is on the "
                             f"outside of the model)" for v_, nm in unseen)
                 + ". These are inside the body from this camera, so no "
                   "overlay and no residual can argue with them either way "
                   "— they are not confirmed by a good fit and not refuted "
                   "by a bad one. If a component is unseen in EVERY view, "
                   "the photographs are not what justifies it: either it "
                   "earns its place some other way and declare_input says "
                   "so, or it is carrying mass and lift for a part nobody "
                   "can check. Do not free its constants — fit_geometry "
                   "cannot move a residual through an outline that is not "
                   "there. ")

    if n == 0:
        return frac, head + "Nothing uncovered."

    sizes = _nd.sum(missing, lab, range(1, n+1))
    order = _np.argsort(sizes)[::-1][:4]
    cen = _nd.center_of_mass(missing, lab, [int(i)+1 for i in order])

    # WHICH COMPONENT IS NEAREST tells you WHAT, not just where. A gap touching
    # a component is that component being too small; a gap far from everything
    # is a component you have not built at all.
    dists = [_nd.distance_transform_edt(~m) for m in per]
    bits = []
    for i, c in zip(order, cen):
        blob = (lab == int(i)+1)
        near_names = sorted(((float(d[blob].min()), nm)
                             for d, nm in zip(dists, cn)))
        d0, nm0 = near_names[0]
        how = (f"touching {nm0}" if d0 <= slack else
               f"{d0:.0f} px from the nearest component ({nm0})")
        bits.append(f"(x={c[1]:.0f}, y={c[0]:.0f}) "
                    f"{100*sizes[i]/mask.sum():.1f}%, {how}")
    return frac, head + "Largest gaps: " + "; ".join(bits) + ". " + (
        "A gap TOUCHING a component means that component is too small or "
        "misplaced; a gap FAR from every component means one is missing "
        "entirely. A propeller belongs behind a build flag — in the "
        "silhouette, never in the aerodynamics.")


def ablate(airplane, component, poses=None):
    """
    Does the aircraft fit the photographs BETTER without this part? -> note

    THE QUESTION A NAMED COMPONENT RAISES. `completeness` says a part is
    mostly off the mask; this says what deleting it would do, across every
    view, before anyone edits `_model.py`. One probe instead of an
    edit-refit-reread cycle whose first step changes the file.

    Measured on the FT A-10 Warthog, 2026-10-10: its `Nacelle Pylons` was
    carrying 20% of the front-right residual and is barely in any
    photograph. Nothing in the kernel could answer "is it helping?", so the
    only way to find out was to delete it and see -- which is a destructive
    experiment run on the file the entry is about to be written from.

    THE POSE MUST NOT MOVE. Both arms are measured at the SAME camera, which
    is why `poses` is worth passing: refitting between arms lets the camera
    absorb some of the difference and the comparison stops being about the
    component. Pinned for the same reason, and because two cheap arms make
    it a question anyone will ask twice.

    IT REFUSES A VERDICT ON A COMPONENT THE SILHOUETTE CANNOT SEE, and that
    restriction is most of what this function knows. A buried part changes
    the residual by contributing AREA -- closing a gap in the union -- which
    looks identical to contributing correct SHAPE and means something else
    entirely. See the comment on the verdict below for the measurement that
    forced this.

    IT DOES NOT EDIT ANYTHING. The reading is what you act on; the deletion
    is yours to make, and after it BOTH the pose and any fitted constant are
    stale -- they were found with the component present and partly absorbed
    its error. Refit the poses cold, then refit the constants, then report
    the before and after. An ablation is an entry, not a patch.
    """
    import copy as _copy
    poses = dict(poses or {})
    names = [c.name for c in list(airplane.wings) + list(airplane.fuselages)]
    if component not in names:
        raise ValueError(f"no component named {component!r}. "
                         f"This aircraft has: {', '.join(names)}.")

    # A SHALLOW COPY OF THE LISTS, not of the aircraft. `_parts_of` meshes
    # whatever it is handed and never mutates it, so the components can be
    # shared; what must not be shared is the list the name is dropped from.
    without = _copy.copy(airplane)
    without.wings = [w for w in airplane.wings if w.name != component]
    without.fuselages = [f for f in airplane.fuselages if f.name != component]

    rows = []
    for v in reference_views():
        p = poses.get(v) or _pose_remembered(v, airplane)
        if p is None:
            # NO CAMERA FOR THIS VIEW YET, so find one -- once, and keep it
            # for both arms. An ablation with a different camera per arm is
            # not an ablation.
            compare_to_photo(airplane, v)
            p = _pose_remembered(v, airplane)
        a = _fit_residual_pct(airplane, v, p)
        b = _fit_residual_pct(without, v, p)
        rows.append((v, a, b, *_ablation_detail(airplane, without,
                                                component, v, p)))

    out = [(f"ablate {component!r} — residual with, then without, "
            f"at a pinned camera:")]
    for v, a, b, vis, opened in rows:
        # 0.05 pp IS THE DEAD BAND, not a tolerance to tune. Two residuals
        # computed at the same camera on the same mask differ only by the
        # rasterisation, so anything smaller is the same number twice.
        verdict = ("better without" if b < a - 0.05 else
                   "worse without" if b > a + 0.05 else "no difference")
        out.append(f"  {v:<28} {a:6.2f}%  ->  {b:6.2f}%   {verdict}"
                   f"   (draws {100*vis:.0f}% of its own outline)")
        if opened:
            out.append("       removing it opens silhouette against: "
                       + ", ".join(opened))

    worse = sum(1 for _, a, b, _, _ in rows if b > a + 0.05)
    better = sum(1 for _, a, b, _, _ in rows if b < a - 0.05)
    seen = [v for v, _, _, vis, _ in rows if vis >= 0.10]

    # THE RESIDUAL IS ONLY EVIDENCE ABOUT A COMPONENT THE CAMERA CAN SEE.
    #
    # This is the correction that matters, and the first version of this
    # function got it wrong. It reported "worse without it" as "the
    # photographs are holding this component in place; it is mis-sized
    # rather than imaginary". That inference does not follow, and on the
    # case this was written for it was false.
    #
    # MEASURED, FT A-10 Warthog, 2026-10-10. `Nacelle Pylons` draws 3-7% of
    # the model's outer outline -- the camera barely sees its edge -- and
    # removing it still made two views WORSE, 2.36% -> 3.88% on one. Both
    # facts are true because the pylon contributes AREA, not OUTLINE: it
    # spans the gap between fuselage and nacelle and keeps the union
    # silhouette connected. Delete it and a hole opens that the real
    # aircraft does not have, because the real fault is next door -- a
    # fuselage too narrow, or nacelles too far outboard. The plate was
    # PATCHING A NEIGHBOUR'S ERROR, and the chamfer cannot say so: it sees
    # the hole close and reports an improvement.
    #
    # So a part the silhouette cannot see gets no verdict here. The delta is
    # still printed, because it is a fact, and it is labelled as what it is.
    if not seen:
        out.append(
            f"NO VERDICT: {component!r} draws almost none of the model's "
            f"outer outline in ANY view, so the photographs have no opinion "
            f"about it and these deltas are not evidence either way. A part "
            f"that is invisible and still changes the residual is "
            f"contributing AREA, not shape -- it is filling a gap, and the "
            f"gap is usually a neighbour being the wrong size. Look at what "
            f"the opened silhouette runs against, above, and suspect those. "
            f"Whether this component belongs is a question for the build "
            f"documentation, not for the overlay.")
    elif better and not worse:
        out.append(
            f"Better without it in {better} view(s), worse in none, and it "
            f"draws real outline — the silhouettes do not want this "
            f"component.")
    elif worse and not better:
        out.append(
            f"Worse without it in {worse} view(s), and it draws real "
            f"outline, so the photographs are holding it in place. CHECK "
            f"WHAT THE HOLE RUNS AGAINST before concluding it is correct: a "
            f"part that only ever opens a gap against one neighbour may be "
            f"standing in for that neighbour being too small.")
    else:
        out.append(
            f"Better without it in {better} view(s), worse in {worse}. "
            f"Mixed on a component that draws real outline usually means it "
            f"is real and the wrong size. Look at the views that disagree.")

    out.append(
        "Nothing was edited. If you do remove it, BOTH the poses and every "
        "fitted constant are stale -- they were found with it present and "
        "absorbed part of its error -- so refit the poses cold, then the "
        "constants, then report before and after. That is an entry.")
    return "\n".join(out)


def _ablation_detail(airplane, without, component, name, pose):
    """
    What the component draws, and what its removal exposes. -> (vis, [names])

    `vis` is the fraction of the component's own outline that lies on the
    model's OUTER silhouette -- the same measure `completeness` reports as
    "THE SILHOUETTE CANNOT SEE", and the one that decides whether the
    residual delta means anything.

    The names are the components the newly-exposed silhouette runs against.
    THIS IS THE DIAGNOSIS, not decoration: a part whose removal opens an
    edge against the fuselage was covering for the fuselage, and the fit
    that should follow frees the fuselage's constants rather than this
    part's. `completeness` makes the same move for a gap in the mask -- "a
    gap TOUCHING a component means that component is too small" -- and this
    is that sentence for the other direction.
    """
    import numpy as _np
    from scipy import ndimage as _nd
    _, mask = _reference_image(name)
    H, W = mask.shape
    parts = _parts_of(airplane)
    names = [c.name for c in list(airplane.wings) + list(airplane.fuselages)]
    cheap = _parts_of(airplane, resolution=_FIT_RESOLUTION)
    params, _, centre, _ = _fit_pose(cheap, mask, pose=pose, pinned=True)

    per = {n: _raster(p_, f_, params, (W, H), centre)
           for n, (p_, f_) in zip(names, parts)}
    union = _np.zeros((H, W), bool)
    for m in per.values():
        union |= m
    outer = union & ~_nd.binary_erosion(union)

    mine = per.get(component)
    if mine is None or not mine.any():
        return 0.0, []
    edge = mine & ~_nd.binary_erosion(mine)
    vis = (float((edge & _nd.binary_dilation(outer, _np.ones((3, 3)))).sum())
           / float(edge.sum()) if edge.any() else 0.0)

    # The silhouette the REMOVAL creates: edge that is new, and not simply
    # the component's own former boundary showing through.
    rest = _np.zeros((H, W), bool)
    for n, m in per.items():
        if n != component:
            rest |= m
    new_edge = (rest & ~_nd.binary_erosion(rest)) & ~_nd.binary_dilation(
        outer, _np.ones((3, 3)))
    if not new_edge.any():
        return vis, []
    near = _nd.binary_dilation(new_edge, _np.ones((5, 5)))
    touched = [n for n, m in per.items()
               if n != component and (m & near).sum() > 0.02*new_edge.sum()]
    return vis, sorted(touched)


def _fit_residual_pct(airplane, name, pose):
    """One view's residual at a FIXED camera, as % of sqrt(mask area)."""
    import numpy as _np
    _, mask = _reference_image(name)
    cheap = _parts_of(airplane, resolution=_FIT_RESOLUTION)
    _, resid, _, _ = _fit_pose(cheap, mask, pose=pose, pinned=True)
    return 100.0*resid/float(_np.sqrt(mask.sum()))


class _FitResult:
    """What `fit_geometry` returns: values the agent reads, evidence it acts on."""
    def __init__(self, free, values, spread, verdict, before, after,
                 per_component, railed, seconds, seeds, model_path, start=None,
                 cut_short=0, short_by=()):
        self.free, self.values, self.spread = free, values, spread
        self.start = start or {}
        self.verdict, self.before, self.after = verdict, before, after
        self.per_component, self.railed = per_component, railed
        self.seconds, self.seeds, self._model_path = seconds, seeds, model_path
        # How many seeds ran out of probe time instead of converging. Reported
        # because a fit that was cut short is EVIDENCE OF LESS than one that
        # converged, and the spread across seeds -- which is what says whether
        # a value is pinned by the data -- is meaningless if the seeds never
        # finished. Silence here would let an under-converged number be read
        # as a settled one.
        self.cut_short, self.short_by = cut_short, tuple(short_by)

    #: How far seeds may disagree and still be written, as a fraction of span.
    #: RELAXED ON PURPOSE. Measured across three fits, the spreads form a
    #: continuous cloud from 0.15% to 8.7% of span with no natural break, so
    #: any cut is a judgement rather than a discovery. 0.5% kept 2 of 31 --
    #: strict enough to make the tool useless. 2% is 29 mm on a 1460 mm
    #: aeroplane, keeps about half, and falls at the widest gap in the
    #: distribution (1.82 -> 2.03). It is deliberately generous: the spread
    #: is printed beside every value in millimetres, so a reader who cares
    #: about a particular dimension can see exactly how well it is pinned and
    #: overrule this. The filter exists to stop the agent HAND-TYPING values,
    #: not to be the last word on which are true.
    SPREAD_LIMIT = 0.02

    #: The same generosity for angles, in degrees. 5 deg is about what a
    #: reader would shrug at on a dihedral or an incidence; a blade angle
    #: that came back +/- 73 deg is excluded by this rather than by a
    #: unit-conversion accident.
    ANGLE_LIMIT_DEG = 5.0

    @property
    def consistent(self):
        """Values pinned to within SPREAD_LIMIT of span across seeds.

        Spread is measured against the AIRCRAFT, never against the parameter:
        fin_z = 0.0042 +/- 0.0077 reads as 185% scatter but is 7.7 mm, the
        same quality of answer as hstab_x at 0.52% -- the ratio only explodes
        because the value sits near zero.
        """
        ref = getattr(self, "span_ref", None)
        if not ref:
            return dict(self.values)
        out = {}
        for k, v in self.values.items():
            lim = (self.ANGLE_LIMIT_DEG if (k.endswith("_deg") or "angle" in k)
                   else self.SPREAD_LIMIT*ref)
            if self.spread[k] <= lim:
                out[k] = v
        return out

    def __str__(self):
        w = max(len(k) for k in self.free)
        L = [f"fit_geometry — {len(self.free)} free parameter(s), "
             f"{len(self.before)} view(s), {self.seeds} seeds, "
             f"{self.seconds:.0f} s", ""]
        L.append(f"{'parameter'.ljust(w)}  {'start':>10} {'fitted':>10} "
                 f"{'per-seed range':>16}   spread")
        for k in self.free:
            rng = ""
            if getattr(self, "per_seed", None):
                vs = [d[k] for d in self.per_seed]
                rng = f"{min(vs):.4f}..{max(vs):.4f}"
            L.append(f"{k.ljust(w)}  {self.start.get(k, float('nan')):10.4f} "
                     f"{self.values[k]:10.4f} {rng:>16}   {self.verdict[k]}")
        L.append("")
        L.append(f"{'view'.ljust(w)}  {'before':>10} {'after':>10}")
        for v in self.before:
            L.append(f"{v.ljust(w)}  {self.before[v]:9.3f}% {self.after[v]:9.3f}%")
        L.append("")
        L.append("every view improved" if all(self.after[v] < self.before[v]
                                              for v in self.before)
                 else "A VIEW GOT WORSE — this is a trade, not a finding")
        # WHERE THE CAMERA STARTED, and how well it tracked the aircraft
        # there. Every number above is measured against these poses, so a
        # seed that never found the aircraft makes the whole table a
        # comparison between two wrong things that happen to differ.
        sf = getattr(self, "seed_fit", None)
        if sf:
            L.append("")
            L.append(f"{'seed pose'.ljust(w)}  {'residual':>10}   from")
            for v, (pct, bound, hinted) in sf.items():
                L.append(f"{v.ljust(w)}  {pct:9.3f}%   "
                         + ("the pose you passed" if hinted else "a cold fit")
                         + ("  — ON A BOUND" if bound else ""))
            bad = [v for v, (pct, bound, _h) in sf.items()
                   if bound or pct > 100*_POSE_DOUBTFUL]
            if bad:
                # NOT A REFUSAL. A seed residual this high is EITHER a camera
                # that missed the aircraft OR a shape wrong enough that no
                # camera can track it -- and the second case is the one a
                # geometry fit exists to repair, so refusing here would block
                # exactly the run that fixes it. The two are told apart by
                # trying a pose: if a pose you have looked at scores no better,
                # the shape is the cause.
                L.append(">>> SEED POSE DOUBTFUL: " + ", ".join(bad) +
                         ". The seed outline does not track the silhouette, "
                         "so every number above is measured against a pose "
                         "no one has seen work. Find a pose with "
                         "compare_to_photo and pass it as "
                         "poses={view: (elev, azim, roll)}; if the seed "
                         "residual stays this high with a pose that looked "
                         "right, the shape is what is wrong, not the camera.")
        # The per-component "degraded" flag was removed. It scored each
        # component by the mean distance from its OUTLINE to the nearest mask
        # EDGE -- which penalises a component that is correctly buried inside
        # the silhouette, since none of its outline is near an edge. Measured
        # on the P-38: the crew nacelle, 78% interior, scored worst of all
        # nine components while being roughly where it belongs. It also fired
        # on any increase at all, with no noise floor. Use the overlay.
        L.append("no parameter near a bound" if not self.railed
                 else ">>> HELD BY A BOUND: " + ", ".join(self.railed) +
                      "\n>>> The fit wanted to go further and could not. Widen "
                      "the bound and refit; the value is yours, not the "
                      "photograph's.")
        if self.cut_short:
            # HOW FAR SHORT, in the one unit that is actionable: seconds to
            # put in `budget_s`. "Ran out of time" alone reads the same whether
            # the fit wanted a moment more or an order of magnitude more, and
            # those call for opposite decisions.
            worst = min(self.short_by, key=lambda t: t[0]/max(1, t[1]),
                        default=None)
            L.append(f">>> {self.cut_short} of {self.seeds} seeds RAN OUT OF "
                     f"PROBE TIME rather than converging.")
            if worst:
                done, asked, secs = worst
                frac = done/max(1, asked)
                want = secs/max(frac, 1e-6)
                L.append(
                    f">>> The worst managed {done} of {asked} iterations -- "
                    f"{100*frac:.0f}% of the search -- in {secs:.0f} s.\n"
                    f">>> Finishing at that rate wants on the order of "
                    f"{want:.0f} s PER SEED. That is an upper bound, since CMA "
                    f"usually\n"
                    f">>> stops early on tolfun, but the shortfall is a "
                    f"MULTIPLE and not a margin: a\n"
                    f">>> slightly bigger budget_s will not change this "
                    f"answer.")
            L.append(
                f">>> These values are a best-so-far, and the spread above is "
                f"not evidence that\n"
                f">>> anything is pinned -- seeds that never finished cannot "
                f"agree or disagree.\n"
                f">>> Free fewer constants (cost goes as seeds x views x free) "
                f"or raise budget_s.")
        return "\n".join(L)

    def apply(self):
        """Write CONSISTENT values into `_model.py`; leave the rest alone.

        THE AGENT MUST NOT TYPE A FITTED NUMBER. Hand transcription is how a
        run came to write `width=0.185` six lines after measuring 282 mm, and
        then declare the 185. This edits the file, so the number in the model
        is the number the fit produced, by construction.

        IT PRINTS WHAT IT WROTE, old value beside new, rather than only
        returning it. Returning was enough in principle and not in practice:
        on the FT A-10 Warthog a run wrapped the call as

            try:
                fit.apply()
                print("fit applied successfully")

        which discards the report and replaces it with a sentence that knows
        nothing. Three turns then went on establishing by hand what the
        return value had already said -- grepping the model file from a
        probe (wrong cwd, FileNotFoundError), reading it with a file tool,
        and printing the constant. A result a caller can swallow is one that
        will be, so this one goes to stdout on its way past.
        """
        src = self._model_path.read_text()
        n = 0
        wrote = []
        for k, v in self.consistent.items():
            # The OLD value, read before the substitution that replaces it.
            was = re.search(rf"(?m)^{re.escape(k)}\s*=\s*([-\d.eE+]+)", src)
            new = round(float(v), 6)
            src, c = re.subn(rf"(?m)^({re.escape(k)}\s*=\s*)[-\d.eE+]+",
                              lambda m: m.group(1) + repr(new),
                              src)
            n += c
            if c:
                wrote.append((k, float(was.group(1)) if was else None, new))
        self._model_path.write_text(src)
        if wrote:
            print(f"fit.apply() -> {self._model_path.name}")
            for k, was_v, new in wrote:
                shift = ("" if was_v is None
                         else f"   ({1000*(new - was_v):+.1f} mm)")
                print(f"  {k:<28} {was_v!r:>12} -> {new!r}{shift}")
        kept = set(self.consistent)
        skipped = [k for k in self.free if k not in kept]
        ref = getattr(self, "span_ref", None)
        lim = (f"{1000*self.SPREAD_LIMIT*ref:.0f} mm" if ref
               else f"{100*self.SPREAD_LIMIT:.0f}% of span")
        return (f"wrote {n} fitted constant(s) to {self._model_path.name} "
                f"(seeds agreed to within {lim})" +
                (f"; left {len(skipped)} alone, seeds too far apart: "
                 + ", ".join(skipped) if skipped else ""))


def fit_geometry(free, reliability="normal", views=None, poses=None,
                 _chapter=None):
    """
    Fit named `_model.py` constants to every photograph at once. -> _FitResult

    `free` maps a module-level constant name to (low, high, why). The reason
    is required: a parameter freed because a finding pointed at it is
    evidence, and a parameter freed because it happened to move the number is
    not.

        fit = fit_geometry(free={
            "chord_outb": (0.12, 0.34, "entry 02: real outer TE lies aft"),
        }, poses={"threequarter": (24.0, 143.0, -2.0)})
        print(fit)
        fit.apply()

    ON A FIRST RECONSTRUCTION there is no entry to cite, and the example
    above reads as though there must be. There need not be: the overlay in
    front of you is evidence, and naming what it shows is the reason.

        fit = fit_geometry(free={
            "fuse_nose_len": (0.18, 0.34, "overlay: nose outline runs past "
                                          "the radome in both views"),
        }, poses={"studio": (19.9, 209.6, -13.4),
                  "belly":  (36.0, 118.2, 19.7)})

    WHAT IT COSTS, because a call nobody can price is a call nobody makes.
    `reliability` buys seeds -- `quick` 2, `normal` 3, `careful` 5 -- and each
    seed re-fits the geometry against EVERY view, so cost goes as seeds x
    views x free parameters. Budget a probe accordingly, and read `.seconds`
    off the result: it records what the run actually took.

    `poses` SEEDS THE CAMERA, one entry per view, `(elev, azim)` or
    `(elev, azim, roll)` -- the three numbers `compare_to_photo` prints in its
    note. Pass the pose of the overlay you actually looked at. The geometry
    here moves millimetres and the camera does not move at all, so a cold
    search per view is work already done, and it can settle in a DIFFERENT
    basin from the picture the free set was chosen off -- at which point the
    fit and the overlay are answering about two different cameras.

    A seed is not a setting. Elevation and azimuth are still searched +/-25
    deg around it, scale, translation and perspective distance are fitted
    from the mask as always, and the search then carries all seven per view
    alongside the geometry. A hint that is wrong comes back with a worse seed
    residual -- which is printed -- rather than being believed.

    WHAT IS NOT YOURS TO CHOOSE, and why:
      * every reference with a mask is used, always;
      * each view's residual is divided by sqrt(mask area) before the views
        are combined -- raw pixels make damage to a small view cheap, and
        that alone flipped a verdict from "the fitted model is better" to
        "the untouched model is better";
      * the views are combined by MEAN (minimax bought 0.1% against a 0.9%
        signal and is not smooth);
      * several seeds run, because a single run is not a result. Six separate
        findings in one session were single runs that dissolved on a second
        look.

    Published dimensions must never appear in `free`: span and length are the
    scale reference, and freeing span makes the fit degenerate against camera
    distance.
    """
    import time as _time, numpy as _np, cma as _cma
    from scipy import ndimage as _nd
    from PIL import Image as _Image
    t0 = _time.time()
    seeds = {"quick": 2, "normal": 3, "careful": 5}[reliability]

    root = _pathlib.Path(_os.environ.get("NB_ROOT", "."))
    chap = _pathlib.Path(_chapter) if _chapter else _pathlib.Path(".")
    model_path = (chap / "_model.py") if (chap / "_model.py").exists() else \
                 next(root.glob("chapters/*/_model.py"))
    src0 = model_path.read_text()

    # BOUNDS ARE OPTIONAL, and usually a mistake. Give either a bare reason
    #     {"pod_nose": "the nacelle cannot reach the nose"}
    # or, if you genuinely know a limit, (low, high, why). Invented bounds
    # silently hold the answer: measured, two parameters in one fit came to
    # rest against limits their author had guessed, and the fit reported those
    # guesses as if the photograph had chosen them. A bound you did not derive
    # from something real is a value you are asserting, not fitting.
    norm = {}
    for k, spec in free.items():
        if isinstance(spec, str):
            why, lohi = spec, None
        elif len(spec) == 3:
            lohi, why = (float(spec[0]), float(spec[1])), str(spec[2])
        else:
            raise ValueError(f"{k}: give a reason string, or (low, high, why)")
        if not why.strip():
            raise ValueError(f"{k}: the reason is required")
        if not re.search(rf"(?m)^{re.escape(k)}\s*=\s*[-\d.eE+]+", src0):
            raise KeyError(f"{k} is not a module-level constant in {model_path.name}")
        norm[k] = (lohi, why)
    free = {k: ((v[0][0], v[0][1], v[1]) if v[0] else (None, None, v[1]))
            for k, v in norm.items()}

    names = list(free)
    _start_tmp = _np.array([float(re.search(rf"(?m)^{re.escape(k)}\s*=\s*([-\d.eE+]+)",
                                            src0).group(1)) for k in names])
    # A PHYSICAL FLOOR, NOT A GUESS. Leaving a parameter truly unbounded was
    # tested and failed badly: three fits returned pod_width = -0.065 m,
    # fin_height = -0.161 m and hstab_x = 1.798 m -- an aeroplane with
    # negative-width components and a tailplane 800 mm behind its own tail --
    # and scored BETTER than the sane model (2.44% against 5.98%). The
    # assumption that absurd geometry would fail to build or project to
    # nothing is wrong: AeroSandbox builds it, and a degenerate shape covers
    # mask pixels cheaply.
    #
    # So anything that is a width, height, chord, span or diameter is forced
    # positive, and a longitudinal station is kept inside a generous envelope.
    # This is a floor the aircraft imposes, not a guess at where the answer
    # sits -- which was the other failure mode, where two parameters came to
    # rest against limits their author had invented.
    _span = _np.maximum(_np.abs(_start_tmp)*4.0, 0.25)
    _POSITIVE = ("width", "height", "chord", "semi", "diameter", "radius",
                 "thick", "span")
    def _auto_lo(i, k):
        v = _start_tmp[i]
        if any(w in k for w in _POSITIVE):
            return max(0.05*abs(v), 1e-4)        # a positive quantity stays positive
        if k.endswith("_deg") or "angle" in k:
            return v - 60.0
        return v - _span[i]

    def _auto_hi(i, k):
        v = _start_tmp[i]
        if k.endswith("_deg") or "angle" in k:
            return v + 60.0
        return v + _span[i]

    glo = _np.array([free[k][0] if free[k][0] is not None else _auto_lo(i, k)
                     for i, k in enumerate(names)], float)
    ghi = _np.array([free[k][1] if free[k][1] is not None else _auto_hi(i, k)
                     for i, k in enumerate(names)], float)
    start = _np.array([float(re.search(rf"(?m)^{re.escape(k)}\s*=\s*([-\d.eE+]+)",
                                       src0).group(1)) for k in names])
    NG = len(names)

    if views is None:
        views = reference_views()

    # GEOMETRY AND POSE ARE SOLVED TOGETHER, IN ONE SEARCH. Fitting the pose
    # inside each geometry evaluation is the obvious shape and it is
    # unaffordable: one pose fit is seconds, a geometry search is thousands of
    # evaluations, and the product is days per seed. Carrying 7 pose
    # parameters per view alongside the geometry costs one search instead.
    V = {}
    for v in views:
        photo, mask = _reference_image(v)
        H, W = mask.shape
        work = 200.0
        sc = work/max(H, W)
        tw, th = max(1, int(W*sc)), max(1, int(H*sc))
        tgt = _np.asarray(_Image.fromarray(mask.astype(_np.uint8)*255)
                          .resize((tw, th), _Image.NEAREST)) > 127
        te = tgt & ~_nd.binary_erosion(tgt)
        ys, xs = _np.nonzero(mask)
        V[v] = dict(mask=mask, nrm=float(_np.sqrt(mask.sum())), sc=sc,
                    tw=tw, th=th, te=te,
                    dt=_nd.distance_transform_edt(~te),
                    cx=xs.mean(), cy=ys.mean(),
                    ptp=max(_np.ptp(xs), _np.ptp(ys)))

    def _build(x):
        src = src0
        for k, val in zip(names, x):
            src = re.sub(rf"(?m)^({re.escape(k)}\s*=\s*)[-\d.eE+]+",
                         lambda m: m.group(1) + repr(float(val)), src)
        g = {}
        exec(compile(src, str(model_path), "exec"), g)
        return g.get("airplane_for_fit", g["airplane"])

    # SEED EACH VIEW'S POSE ONCE, cold or from `poses`. THE SEED RESIDUAL IS
    # REPORTED EITHER WAY. It was discarded here before, which meant a
    # geometry fit could spend six minutes descending from a camera that never
    # tracked the aircraft, and nothing in the output said so -- the before
    # and after columns are both measured against that same bad pose, so they
    # still improve and the fit still looks like it worked.
    hints = {}
    for v, h in dict(poses or {}).items():
        if v not in V:
            raise KeyError(f"poses: no view {v!r}; have: {', '.join(V)}")
        t = tuple(float(x) for x in h)
        if len(t) not in (2, 3):
            raise ValueError(f"poses[{v!r}]: give (elev, azim) or "
                             f"(elev, azim, roll), not {len(t)} numbers")
        hints[v] = t
    parts0 = _parts_of(_build(start), resolution=_FIT_RESOLUTION)
    seed_pose, plo, phi, seed_fit = {}, {}, {}, {}
    for v, d in V.items():
        # A SLICE EACH, so seeding four views cannot eat the whole probe.
        # These are COLD fits unless the caller passed a pose, and a cold fit
        # now scans four quadrants -- measured at ~46 s, which is most of a
        # 300 s grant once there are four photographs.
        _b = _time_left()
        pr, _r0, _c0, _rl = _fit_pose(
            parts0, d["mask"], pose=hints.get(v),
            budget=None if _b is None else 0.4*_b/max(1, len(V)))
        seed_fit[v] = (100.0*_r0/d["nrm"], bool(_rl), v in hints)
        logit = float(_np.clip(-_np.log(max(19.6/max(pr[6]-0.4, 1e-6) - 1, 1e-9)),
                               -6.5, 6.5))
        seed_pose[v] = _np.array([pr[0], pr[1], pr[2], pr[3], pr[4], pr[5], logit])
        plo[v] = _np.array([pr[0]-20, pr[1]-20, pr[2]-20, pr[3]*0.7,
                            pr[4]-200, pr[5]-200, -7.0])
        phi[v] = _np.array([pr[0]+20, pr[1]+20, pr[2]+20, pr[3]*1.3,
                            pr[4]+200, pr[5]+200,  7.0])

    LO = _np.concatenate([glo] + [plo[v] for v in V])
    HI = _np.concatenate([ghi] + [phi[v] for v in V])
    X0 = _np.clip(_np.concatenate([start] + [seed_pose[v] for v in V]),
                  LO + 1e-6*(HI-LO), HI - 1e-6*(HI-LO))

    def _real(u):
        return LO + _np.clip(_np.asarray(u), 0, 1)*(HI - LO)

    def _view_cost(parts, centre, v, p7):
        d = V[v]; sc = d["sc"]
        pp = (p7[0], p7[1], p7[2], abs(p7[3])*sc, p7[4]*sc, p7[5]*sc,
              0.4 + 19.6/(1.0 + _np.exp(-p7[6])))
        m = None
        for pts, faces in parts:
            mi = _raster(pts, faces, pp, (d["tw"], d["th"]), centre)
            m = mi if m is None else (m | mi)
        if m is None or not m.any():
            return 500.0
        me = m & ~_nd.binary_erosion(m)
        if not me.any():
            return 500.0
        return 0.5*(d["dt"][me].mean()
                    + _nd.distance_transform_edt(~me)[d["te"]].mean())/sc

    def _score(x, per_part=False):
        """-> (mean normalised %, {view: %}, {component: %})"""
        try:
            ap = _build(x[:NG])
        except Exception:
            return 1e3, {}, {}
        parts = _parts_of(ap, resolution=_FIT_RESOLUTION)
        centre = _np.vstack([p for p, _ in parts]).mean(axis=0)
        cn = [c.name for c in list(ap.wings) + list(ap.fuselages)]
        per_view, comp = {}, {}
        for i, v in enumerate(V):
            p7 = x[NG + 7*i: NG + 7*i + 7]
            r = _view_cost(parts, centre, v, p7)
            per_view[v] = 100.0*r/V[v]["nrm"]
            if per_part:
                d = V[v]; sc = d["sc"]
                pp = (p7[0], p7[1], p7[2], abs(p7[3])*sc, p7[4]*sc, p7[5]*sc,
                      0.4 + 19.6/(1.0 + _np.exp(-p7[6])))
                for j, (pts, faces) in enumerate(parts):
                    m = _raster(pts, faces, pp, (d["tw"], d["th"]), centre)
                    e = m & ~_nd.binary_erosion(m)
                    if e.any():
                        comp[cn[j]] = comp.get(cn[j], 0.0) + \
                            100.0*float(d["dt"][e].mean())/sc/d["nrm"]
        return float(_np.mean(list(per_view.values()))), per_view, comp

    def obj(u):
        return _score(_real(u))[0]

    # THE BASELINE OPTIMISES THE POSE AT THE STARTING GEOMETRY. Scoring the
    # start at a cold pose and the finish at a fitted one credits the geometry
    # with work the camera search did: measured on another aircraft, 85% of an
    # apparent "improvement" was the optimiser alone, with the model untouched.
    u0 = (X0 - LO)/(HI - LO)
    _gfix = X0[:NG].copy()
    def _obj_pose_only(up):
        x = X0.copy()
        x[NG:] = _real(_np.concatenate([u0[:NG], up]))[NG:]
        return _score(x)[0]
    # WHAT THE PROBE HAS LEFT, divided between the baseline pose polish and the
    # `seeds` geometry descents. This whole function used to run unbounded, and
    # the kill that followed took the result with it: measured, a
    # reconstruction freed 9 then 11 constants across 3 views at 3 seeds inside
    # a 300 s grant, was killed both times, and abandoned fitting altogether in
    # favour of setting the geometry by eye.
    #
    # Bounding beats refusing. An estimate up front -- seeds x views x free, as
    # this docstring prices it -- would have to be calibrated, would be wrong on
    # a new machine, and buys a refusal where a partial fit is strictly more
    # useful: CMA returns its best-so-far, and `cut_short` below says the number
    # is under-converged so nobody reads it as settled.
    _spare = _time_left()
    _slice = None if _spare is None else max(5.0, 0.15*_spare)
    _o0 = {"bounds": [0, 1], "popsize": 14, "maxiter": 200,
           "tolfun": 2e-2, "tolfunhist": 2e-3, "verbose": -9, "seed": 1}
    if _slice is not None:
        _o0["timeout"] = _slice
    _es0 = _cma.CMAEvolutionStrategy(u0[NG:], 0.15, _o0)
    _es0.optimize(_obj_pose_only)
    X0b = X0.copy()
    X0b[NG:] = _real(_np.concatenate([u0[:NG], _es0.result.xbest]))[NG:]
    base_m, base_view, base_comp = _score(X0b, per_part=True)
    results, cut_short, short_by = [], 0, []
    for sd in range(1, seeds + 1):
        _o = {"bounds": [0, 1], "popsize": 18, "maxiter": 350,
              "tolfun": 2e-2, "tolfunhist": 2e-3, "verbose": -9, "seed": sd}
        # EVERY SEED GETS AN EQUAL SHARE of what is left when it starts, so an
        # early seed that converges fast hands its unused time to the later
        # ones rather than the last seed paying for the first.
        _rest = _time_left()
        if _rest is not None:
            _o["timeout"] = max(5.0, _rest/max(1, seeds - len(results)))
        _t_seed = _time.time()
        es = _cma.CMAEvolutionStrategy(u0, 0.18, _o)
        es.optimize(obj)
        if "timeout" in (es.stop() or {}):
            cut_short += 1
            # HOW FAR SHORT, not merely that it was short. A seed that wanted
            # 10% more time and one that wanted ten times it both read as "ran
            # out", and they call for opposite responses -- wait a bit longer,
            # or stop asking this question of this many constants. Recorded as
            # iterations done against iterations asked for, which is the only
            # honest measure of how much of the search actually happened.
            short_by.append((es.countiter, int(_o["maxiter"]),
                             _time.time() - _t_seed))
        results.append(_real(es.result.xbest))
    R = _np.array(results)

    # THE VALUE IS THE BEST SEED'S COORDINATE, NOT THE MEAN ACROSS SEEDS.
    # Averaging a coupled geometry produces a configuration no seed ever
    # visited and no one checked: measured, applying the per-parameter means
    # of eleven fitted values gave a WORSE overlay (3.42%) than keeping only
    # the two reproducible ones (3.10%). The mean of three valid aeroplanes
    # is not necessarily an aeroplane. The spread is still reported — it is
    # the evidence — but the number you apply is one the optimiser actually
    # stood on.
    _scores = [_score(r)[0] for r in R]
    _best_i = int(_np.argmin(_scores))
    values = {k: float(R[_best_i, i]) for i, k in enumerate(names)}
    spread = {k: float(R[:, i].std()) for i, k in enumerate(names)}
    # NO THRESHOLD, AND NO VERDICT. Two attempts at one failed on the data:
    #
    #   * the spread is a CONTINUOUS cloud -- 0.6, 0.9, 1.5, 2.7, 4.5, 4.7,
    #     5.9, 6.5, 7.0, 7.5 % across three fits -- so any line through it
    #     separates neighbours that are not different. A 5% line called
    #     pod_height (4.7%) reproducible and fin_x (5.9%) not.
    #   * dividing by the value is wrong near zero. fin_z = 0.0042 +/- 0.0077
    #     reads as 185% scatter; it is 7.7 mm on a 1460 mm aircraft, which is
    #     tight. The ratio explodes because the value is small.
    #
    # So report the spread in the units a reader can judge -- millimetres,
    # degrees, as a fraction of the SPAN -- and let them decide. The reader
    # knows what 8 mm means on this aeroplane; the tool does not.
    _ref = None
    try:
        _ap0 = _build(start)
        _w = [w for w in _ap0.wings if "wing" in w.name.lower()]
        if _w:
            _ref = 2*max(abs(float(_np.asarray(x.xyz_le)[1])) for x in _w[0].xsecs)
    except Exception:
        pass
    # UNITS MATTER. A constant named *_deg is an angle, not a length; scaling
    # its spread by 1000 and calling it millimetres produced "+/- 73150.5 mm"
    # for a propeller blade angle, which was excluded by accident rather than
    # by any rule.
    def _is_angle(k):
        return k.endswith("_deg") or "angle" in k
    verdict = {k: (f"+/- {spread[k]:.1f} deg" if _is_angle(k) else
                   (f"+/- {1000*spread[k]:.1f} mm"
                    + (f"  ({100*spread[k]/_ref:.2f}% of span)" if _ref else "")))
               for k in names}
    # 5% OF THE RANGE, not 0.1%. A parameter resting 1.7% from its bound is
    # being held there by the bound, and a 0.1% test never fires: measured,
    # a crew nacelle nose sat 1.7% off its lower bound -- visibly too far aft
    # in the overlay -- and nothing flagged it.
    railed = [f"{k} (at its {'lower' if abs(values[k]-glo[i]) < abs(values[k]-ghi[i]) else 'upper'} bound)"
              for i, k in enumerate(names)
              if min(abs(values[k]-glo[i]), abs(values[k]-ghi[i]))
                 < 0.05*(ghi[i]-glo[i])]

    best = R[_best_i]
    fin_m, fin_view, fin_comp = _score(best, per_part=True)
    per_component = {c: fin_comp.get(c, 0.0) - base_comp.get(c, 0.0)
                     for c in base_comp}

    res = _FitResult(free, values, spread, verdict, base_view, fin_view,
                     per_component, railed, _time.time()-t0, seeds, model_path,
                     cut_short=cut_short, short_by=short_by,
                     start={k: float(v) for k, v in zip(names, start)})
    # EVERY SEED'S ANSWER, kept. Reporting only a summary makes a later
    # comparison impossible: this was discovered the hard way, after three
    # fits had already discarded theirs.
    res.span_ref = _ref
    res.per_seed = [{k: float(R[j, i]) for i, k in enumerate(names)}
                    for j in range(len(R))]
    res.per_seed_score = [float(x) for x in _scores]
    res.best_seed = _best_i
    res.seed_fit = seed_fit
    return res
