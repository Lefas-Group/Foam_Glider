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
import inspect

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
