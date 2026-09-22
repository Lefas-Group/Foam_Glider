"""
`uv run --group nb python -m nb.corpus` -- the notebooks, linted,
against counts on record.

The only regression test there is, and it exists because the alternative was
measured and failed. Every lint rule in this system was calibrated by running it
across all three notebooks and reading the numbers; that was done by hand about
ten times in one session and got the wrong answer twice -- once a rule went in
whose predicate fired on four healthy chapters, once a count was predicted to
move and did not. Neither is the kind of mistake a careful reader catches,
because the evidence is three numbers that look plausible either way.

So the numbers live here instead. A rule change that moves them has to say so.

EXPECTED is not an aspiration. `aircraft-notebook` and `optimised-glider-notebook`
were built by the Claude skill this system replaced; they are FROZEN corpus and
their violations are accepted, not a backlog. What matters is that they do not
move by accident: a new rule firing 8 more times in a notebook nobody is editing
is a rule with a false-positive problem, and that signal is only visible against
a recorded baseline.

Counts, not messages, on purpose. Asserting the exact text would break on every
reworded remedy -- and the remedies get reworded often, since a message the model
cannot act on is itself a defect.
"""

import pathlib
import sys

from .config import VENDOR  # noqa: F401  -- importing it puts vendor/ on the path

# (blocking, total). Total carries the warnings, which are the half most likely
# to move silently: they do not fail a run, so nothing else would notice.
EXPECTED = {
    # glider-notebook's one warning is the transcription check: `old_sink =
    # 0.36`, taken from 01-foam-glider and rendered as an authority. It is the
    # only one, and it is real -- the design-constant false positives went when
    # the check started ignoring values the chapter's own model already holds.
    # One warning: the transcription check on `old_sink = 0.36`. The two
    # chapter-05 entries that were at 11-12 s against a 20 s ceiling now render
    # in 9.4 and 9.9 s, so rule 17 stops flagging them -- the entries got
    # faster, which is the only reason a count should ever fall.
    #
    # Back to two with chapter 06 (7a8c0c1): its entry renders in 11 s against
    # the same 20 s ceiling, so rule 17 flags it exactly as it flagged those.
    # A new chapter raising the count is the rule working, not drifting.
    # Third warning is the uncommitted biplane entry in the working tree, which
    # renders in 21 s against the 35 s ceiling it was granted. Recorded because
    # lint reads the working tree, not HEAD.
    #
    # +2 warnings, both rule 17, when `superseded_by` came out of `_notebook.py`
    # and `_CHAPTER` out of every `_model.qmd`. NOT caused by the change: rule
    # 12 watches the shim, so all six chapters had to be re-proved, and a cold
    # render of all 33 pages at once is slower per page than the incremental
    # renders that wrote the previous freezes. Two chapter-05 entries came back
    # at 14 s and 17 s against a 20 s ceiling, which is over half.
    #
    # The change itself moved nothing, and that is the number that mattered:
    # `check.py` reported `0 page(s) changed, 0 figure(s) changed` against HEAD
    # across all 33. Rule 17 is a wall-clock warning and will drift with the
    # machine; that is what this baseline is for.
    "glider-notebook": (0, 5),
    # Rules 33, 34 and 35 postdate both notebooks: the missing `order:`, the
    # missing front page, and the chapter indexes that neither list their
    # entries nor print their lineage. Both stay frozen -- the sidebar and
    # front door of a notebook nobody opens are not worth unfreezing for.
    # Rule 36 is silent on both: neither has a `_categories.yml`, and a
    # notebook that has not decided its axes is not thereby wrong.
    #
    # -1/-1 when rule 33 stopped requiring a NUMBERED TITLE. These two carry
    # unnumbered titles and were being flagged for it; glider-notebook carried
    # numbered ones and was not. Measuring the change on the notebook being
    # worked on said the check fired nowhere, which was true of one notebook
    # in three -- the exact mistake `nb.corpus` exists to catch.
    #
    # +1/+1 rule 39, which now asks an index to carry its input callouts and
    # nothing else: this one still heads its code dump "## The model".
    "aircraft-notebook": (32, 33),
    # +3 blocking from rule 31: its four chapters hold four copies of one
    # _model.py, three of them byte-identical to an earlier chapter and
    # none carrying a fork header. Correct, and frozen.
    #
    # -4/-4 with the numbered-title half of rule 33, as above: four chapters,
    # one finding each.
    #
    # +11/+11 rule 39. Four "## The model" headings and seven callouts with a
    # line of prose above their numbered items -- "Asked of the user,
    # 2026-09-03:" and the like. Correct, and frozen: both notebooks predate
    # the rule exactly as they predate 33, 34 and 35.
    "optimised-glider-notebook": (83, 109),
}


def counts(root):
    import lint
    problems = lint.check(root, lint.chapters_of(root))
    blocking = [m for _, m in problems if "(warning)" not in m]
    return len(blocking), len(problems)


def _imports():
    """
    Every module imports. Two lines, and it catches what nothing else does.

    The corpus sweep lints notebooks; it never imported the code doing the
    linting, so a syntax error in a phase module passed every check here and
    surfaced only when somebody ran that command by hand. That happened twice in
    one session -- a heredoc edit that ran off the end of a string literal in
    `new.py`, which `nb new` alone would have caught, several commits later.
    """
    import importlib
    import pkgutil

    broken = []
    for mod in pkgutil.walk_packages([str(pathlib.Path(__file__).parent)], "nb."):
        if mod.name.endswith(".corpus"):
            continue
        try:
            importlib.import_module(mod.name)
        except Exception as e:                       # noqa: BLE001 -- report all
            broken.append(f"{mod.name}: {type(e).__name__}: {e}")
    return broken


def main(argv=()):
    repo = pathlib.Path(__file__).resolve().parent.parent
    bad = []
    broken = _imports()
    for b in broken:
        print(f"  IMPORT FAILED  {b}")
    for name, expected in EXPECTED.items():
        root = repo / name
        if not root.is_dir():
            print(f"  {name:28} MISSING — not checked")
            continue
        got = counts(root)
        ok = got == expected
        print(f"  {name:28} {got[0]:3} blocking, {got[1]:3} total"
              f"{'' if ok else f'   EXPECTED {expected[0]} / {expected[1]}'}")
        if not ok:
            bad.append((name, expected, got))

    if broken:
        print(f"\n{len(broken)} module(s) do not import — fix those first.")
        return 1
    if not bad:
        print("\ncorpus unchanged.")
        return 0
    print(f"\n{len(bad)} notebook(s) moved. Either the rule change is wrong, or "
          f"the counts in\nnb/corpus.py need updating in the same commit that "
          f"justifies them:")
    for name, expected, got in bad:
        print(f"  {name}: {expected[0]}/{expected[1]} -> {got[0]}/{got[1]}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
