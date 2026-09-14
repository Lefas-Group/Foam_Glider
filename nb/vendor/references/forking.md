# Forking a chapter, and starting a notebook

SKILL.md carries the routing table and the rule that a new notebook is never
built by reading an existing one. This is the detail: when a model change earns a
new chapter, and how to make one cheaply.

## The fork criterion is whether you want to keep both answers

Not which file the change lands in.

| | |
|---|---|
| The old answer is **superseded**: wrong physics, wrong arithmetic, or a known omission now closed | Fix in place, delete the freeze, re-render, and update the chapter index if a "left out" bullet stopped being true. The correction goes in a **later entry**. Same chapter. |
| The old answer stays **valid under its own stated assumptions**, and the comparison is the point | **New chapter.** |

An assumption of yours that the user later replaces with a measurement or a brief
is the first case, not the second: it was never the design. A genuinely different
aircraft, or a method you would want to compare against, is the second — the old
chapter then keeps rendering its own numbers *correctly*, because the model it
references has not moved.

Worked examples, from the duration-glider chapter:

- A zero-lift degeneracy in the force balance, and a lumped-CG error → mistakes.
  Fixed in place, everything recomputed.
- Foam thickness 1.6 → 5 mm and a one-ply → two-ply fuselage → unowned
  assumptions replaced by the user's measurement and brief. Never the design;
  recomputed.
- Adding interference drag → closes a gap an entry explicitly flags as missing.
  The old answer is incomplete, not a rival view. **Same chapter.**
- 2.5 mm stock → a different aircraft. The 5 mm chapter's conclusions stay true
  of 5 mm stock forever. **New chapter.**
- AeroBuildup → a vortex lattice → you would want both, to compare. **New
  chapter.**

## Copying a chapter

A forked chapter copies **both** `_model.py` and `_analysis.py`: chapters share
nothing at runtime, so one without its own `_analysis.py` cannot measure
anything.

Which file carries the intended difference depends on the fork — a design change
alters `_model.py`, a fidelity change alters `_analysis.py` — so the header of
the copy names its parent chapter, the commit it was taken at, and every
deliberate difference. `diff` between the two files is then the review, and an
empty `diff` on the file that was *not* meant to change is a positive check
rather than an absence of information.

**Copy with `cp`, edit constants with `sed`.** This is the one case where a script
edit beats `Edit`: the file is not in context, and reading a long `_model.py` in
only to write it back out costs a great deal and buys nothing. Read only the
~25-line header, to rewrite it.

## Starting a notebook

`nb new <path> "<title>"` builds it, and proves it: the command lints and
preflights before it returns, so a notebook that would fail its first `nb ask`
fails here instead, seconds in rather than minutes.

Notebooks share nothing at runtime: each has its own `_quarto.yml`, `_freeze/`,
`_scratch/` and chapters, and `execute-dir: project` scopes every path inside its
own notebook. Put a second notebook in a sibling directory of the first, so both
use one copy of `nb`, its linter and its `notebook.py`.

## The budget does not come with the fork, and cannot

A fork copies `_model.py` and `_analysis.py`. It copies no budget at all, because
budgets are not chapter-scoped: every ENTRY declares its own `SOLVE_BUDGET` and
`ENTRY_CEILING`, and the ceiling is the one the user granted at the prompt for
that entry (rules 18 and 28).

This used to need a separate `_budget.py`, kept out of `_model.py` precisely so a
fork could not inherit it. That file is gone — there is nothing left to inherit,
so the failure it guarded against cannot recur. It is on record because it did:
one chapter was forked and silently took `SOLVE_BUDGET = None` across, together
with a comment ("its pages are already frozen") that was untrue of a chapter with
no pages at all.

Size the budget from the configuration the entries will actually run. One
chapter's was taken from a 70 s solve at 30 nodes while its entries solved at 60
nodes needing 210 s, so every entry solve was truncated.
