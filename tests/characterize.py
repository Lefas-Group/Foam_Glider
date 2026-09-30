"""
Every finding lint makes, recorded, so a restructure can prove it changed none.

    uv run --group nb python tests/characterize.py            # write the baseline
    uv run --group nb python tests/characterize.py --check    # compare against it
    uv run --group nb python tests/characterize.py --check --strict

`nb.corpus` already pins COUNTS, and counts are the right thing for calibrating a
rule: they move when a predicate's reach changes and they do not move when a
remedy is reworded. They are the wrong thing for moving 3,300 lines of linter
into a different shape, because two findings can swap places and leave the count
alone. So this records the findings themselves.

THE TWO MODES EXIST BECAUSE THE REFACTOR HAS TWO HALVES, and they want opposite
things from the same data:

  * The restructure must not change WHAT is wrong with a notebook. It moves rules
    between modules, gives them typed inputs instead of a filesystem, and must
    come out the other side saying exactly the same sentences about exactly the
    same files. Default mode compares `(where, msg)` and ignores the rule number
    -- which is `None` for 21 of the 40 rules today, and stays `None` through
    this half.

  * Then attribution: the 10 rules implemented inline in `check()` and the 4
    bundled functions get split, so every finding can name its own rule. That
    changes the rule field and NOTHING ELSE. `--strict` compares the full triple
    and additionally refuses any finding still carrying `None`.

One baseline serves both: it always stores the triple, and the modes differ only
in what they project out of it. So `--strict` can be switched on without
regenerating anything, and the day it passes is the day the second half is done.

NOT RADICAL-GLIDER. It is the notebook being worked in, so it gains an entry
whenever a run commits one and its findings move for reasons that have nothing to
do with this refactor. The three here are stable: `glider-notebook` is finished,
and the other two are the frozen corpus `nb.corpus` documents. RADICAL-GLIDER is
covered by actually running `nb ask` against it at each phase boundary, which
tests more than lint anyway.
"""

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = pathlib.Path(__file__).resolve().parent / "baseline"

NOTEBOOKS = ("glider-notebook", "aircraft-notebook", "optimised-glider-notebook")

# How many differences to print before stopping. A restructure that breaks
# something usually breaks it in bulk -- one parser change, four hundred
# findings -- and the first few name the cause as well as the four hundredth.
SHOWN = 10


def findings(notebook):
    """
    `[[rule, where, msg]]` for one notebook, sorted, JSON-ready.

    Sorted because `check()` appends in rule order and a reordering of the calls
    is exactly the kind of harmless change this must not report.

    `where` is stored RELATIVE TO THE NOTEBOOK, not as `where.name`. The absolute
    prefix differs per machine and would make the baseline unshareable, but the
    bare filename is worse than lossy -- every chapter has an `_analysis.py`, so
    `01-x/_analysis.py` and `02-y/_analysis.py` collapse into one key. Measured
    when this was written that way: 8 collisions in optimised-glider-notebook
    hiding 17 findings, all of them rules 21 and 22 reporting the same sentence
    about a different chapter's helpers.
    """
    from nb import lint
    root = ROOT / notebook
    out = []
    for rule, where, msg in lint.check(root, lint.chapters_of(root)):
        if where is None:
            at = None
        else:
            try:
                at = str(pathlib.Path(where).resolve().relative_to(root.resolve()))
            except ValueError:
                at = str(where)          # outside the notebook; keep it whole
        # MESSAGES CARRY ABSOLUTE PATHS -- rule 11's names the canonical
        # `_notebook.py` in full -- so a baseline recorded verbatim is valid on
        # exactly one machine. Stripped to repo-relative, which is what the
        # reader wanted anyway.
        out.append([rule, at, msg.replace(str(ROOT) + "/", "")])
    return sorted(out, key=lambda r: (r[1] or "", r[2], r[0] or 0))


def _project(rows, strict):
    """
    A comparable MULTISET: the whole triple, or everything but the rule number.

    A Counter rather than a set, because dropping the rule number can make two
    findings identical and a set would then hide the loss of one of them. Same
    lesson as `where` above, one layer up.
    """
    if strict:
        return collections.Counter(tuple(r) for r in rows)
    return collections.Counter((r[1], r[2]) for r in rows)


def write():
    BASELINE.mkdir(parents=True, exist_ok=True)
    for n in NOTEBOOKS:
        rows = findings(n)
        (BASELINE / f"{n}.json").write_text(json.dumps(rows, indent=1) + "\n")
        untagged = sum(1 for r in rows if r[0] is None)
        print(f"  {n:28} {len(rows):4} finding(s), {untagged} with no rule number")
    print(f"\nbaseline written to {BASELINE.relative_to(ROOT)}/")


def check(strict):
    bad = 0
    for n in NOTEBOOKS:
        p = BASELINE / f"{n}.json"
        if not p.exists():
            print(f"  {n:28} NO BASELINE — run without --check first")
            bad += 1
            continue
        was = _project(json.loads(p.read_text()), strict)
        now = _project(findings(n), strict)
        # Counter subtraction keeps multiplicity: losing one of three identical
        # findings shows up as one lost, which a set difference would call equal.
        gone = sorted((was - now).elements())
        new = sorted((now - was).elements())
        if not gone and not new:
            print(f"  {n:28} unchanged ({sum(now.values())} finding(s))")
            continue
        bad += 1
        print(f"  {n:28} {len(gone)} lost, {len(new)} new")
        for row in gone[:SHOWN]:
            print(f"      - {row}")
        for row in new[:SHOWN]:
            print(f"      + {row}")
        if len(gone) + len(new) > SHOWN:
            print(f"      … {len(gone) + len(new) - SHOWN} more")

    # ATTRIBUTION IS A SEPARATE VERDICT and must not be reported as a behaviour
    # change. Findings carrying no rule number are the work of the refactor's
    # second half that has not been done yet; saying "the restructure changed
    # behaviour" about them would train whoever reads this to ignore the line
    # that matters.
    untagged = 0
    if strict:
        for n in NOTEBOOKS:
            u = [r for r in findings(n) if r[0] is None]
            if u:
                print(f"  {n:28} {len(u)} finding(s) carry no rule number, "
                      f"e.g. {u[0][2][:58]}")
                untagged += len(u)

    print()
    if bad:
        print(f"{bad} notebook(s) MOVED — the restructure changed behaviour.")
    else:
        print("findings unchanged.")
    if strict and untagged:
        print(f"{untagged} finding(s) not yet attributable to a rule — "
              f"the attribution half is unfinished, which is not a regression.")
    return 1 if bad or (strict and untagged) else 0


def main(argv):
    strict = "--strict" in argv
    if "--check" in argv:
        return check(strict)
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
