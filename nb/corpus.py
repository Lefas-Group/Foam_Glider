"""
`python -m nb.corpus` -- the notebooks, linted, against counts on record.

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
    "glider-notebook": (0, 1),
    "aircraft-notebook": (27, 28),
    # +3 blocking from rule 31: its four chapters hold four copies of one
    # _model.py, three of them byte-identical to an earlier chapter and
    # none carrying a fork header. Correct, and frozen.
    "optimised-glider-notebook": (59, 85),
}


def counts(root):
    import lint
    problems = lint.check(root, lint.chapters_of(root))
    blocking = [m for _, m in problems if "(warning)" not in m]
    return len(blocking), len(problems)


def main(argv=()):
    repo = pathlib.Path(__file__).resolve().parent.parent
    bad = []
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
