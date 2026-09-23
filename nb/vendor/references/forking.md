# Forking a chapter, and starting a notebook

SKILL.md carries the routing table and the rule that a new notebook is never
built by reading an existing one. This is the detail: when a model change earns a
new chapter, and how to make one cheaply.

## The fork criterion is a change to the MODEL

A chapter is a vehicle. It forks when the vehicle changes — not when the way you
interrogate the vehicle changes.

| the change | where it lands | |
|---|---|---|
| **Material** — 5 mm stock becomes 3 mm | `_model.py` | **New chapter** |
| **Design** — a fuselage is added, the quarter chord is unswept | `_model.py` | **New chapter** |
| **Free variables** — a fixed tail is opened to the optimiser | `_model.py` | **New chapter** |
| **Optimisation** — a different objective, bounds, multistart, solver settings | `_analysis.py` | Same chapter |
| **Fidelity of the analysis** — more strips, a tighter tolerance, a finer sweep | `_analysis.py` | Same chapter |
| **A new measurement** of the same vehicle | `_analysis.py` | Same chapter |

The test is mechanical and you can run it: **would `_model.py` differ?** If the
answer is no, it is an entry in the chapter you are already in, however large the
study.

This is what the machinery already measures. Rule 31 compares `_model.py`
similarity and demands a `_fork.yml` above 85%; `model_kinship` and the lineage
diagram read the same number. Nothing has ever looked at `_analysis.py` to decide
whether something was a fork, so a criterion resting on analysis or fidelity was
asking for a judgement no check could support — and got one: chapter 05 forked
for optimisation scope, and at 35% similarity to its parent it appears in no
kinship pair at all. Its `_fork.yml` exists because a person wrote it.

### The second question: is it a correction instead?

Once you know the model changes, ask whether the OLD answer survives.

| | |
|---|---|
| The old answer is **superseded**: wrong physics, wrong arithmetic, or a known omission now closed | Fix in place, delete the freeze, re-render, update the chapter index if a "left out" bullet stopped being true. The correction goes in a **later entry**. Same chapter. |
| The old answer stays **valid under its own stated assumptions**, and the comparison is the point | **New chapter.** |

An assumption of yours that the user later replaces with a measurement or a brief
is the first case, not the second: it was never the design.

Worked examples, from the duration-glider chapter:

- A zero-lift degeneracy in the force balance, and a lumped-CG error → mistakes.
  Fixed in place, everything recomputed. **Same chapter.**
- Foam thickness 1.6 → 5 mm and a one-ply → two-ply fuselage → unowned
  assumptions replaced by the user's measurement and brief. Never the design;
  recomputed. **Same chapter.**
- Adding interference drag → closes a gap an entry explicitly flags as missing,
  and lands in `_analysis.py`. **Same chapter.**
- 2.5 mm stock → a different aircraft, and `_model.py` differs. The 5 mm
  chapter's conclusions stay true of 5 mm stock forever. **New chapter.**
- AeroBuildup → a vortex lattice → the vehicle is identical and only the method
  moved. **Same chapter**, as a second entry that compares the two. This used to
  say new chapter; it was the one example that contradicted the criterion above,
  and it would have produced a chapter the lineage diagram draws as an
  unconnected root, because a VLM `_analysis.py` shares nothing with a buildup
  one and `_model.py` never changed.

### Recording what a fork replaces

A fork usually makes one of its ancestors' declarations false — 3 mm foam
replaces 5 mm, a fuselage replaces "fuselage neglected". The record is
append-only, so that ancestor's index goes on declaring the dead version unless
something says otherwise, and a fork taken below you inherits it.

`_fork.yml` carries the link:

```yaml
supersedes:
  - 01-foam-glider: foam-stock
  - 01-foam-glider: airfoil-sections
```

The id is the handle in that chapter's `_inputs.yml`, where its Specified and
Assumed items live — they are data, not markdown, precisely so that a
superseded one can MOVE. Rule 31 refuses an id that does not exist.

The item then leaves its own callout on that page and appears under
`## Superseded`, linked to your chapter. Nothing is stated twice, and a chapter
whose every item has been replaced renders no "new" callouts at all. `nb`'s
inheritance review also stops offering the version you replaced: on this
notebook that took chapter 06's candidate list from thirteen items — which
included both "Foam thickness: 3 mm" and "Foam 5 mm sheet throughout" — down to
nine.

You will usually not write this by hand. What you strike at the new-chapter
gate is written here for you, because striking an inherited item IS declaring
that your chapter supersedes it.

## Citing an earlier chapter's answer

Use `cite()`. Never retype the number.

```python
sink_manual = cite("02-fuselage-model",
                   "2026-09-14-01-how-does-modeling-the-fuselage-change-the-optimized-glider")
```

It reads that entry's hero value out of the COMMITTED freeze, so the citing page
cannot drift from what the cited page actually published. An entry with two hero
blocks needs `label=` to say which. Rule 37 checks that the target exists and
publishes a hero value, and `check` re-renders every page citing a chapter it
rebuilds — the one cross-chapter edge in the dependency graph.

This section used to say the opposite: *"There is no mechanism for this,
deliberately … a number from another chapter is transcribed … The known upgrade
is a `cite(chapter, entry, key)` reading the committed freeze. It is not built."*
It was built. Transcribing is now the failure mode rather than the procedure —
a hand-typed number stays correct only until the cited chapter is re-rendered,
and nothing tells you when it stops. Lint warns when a typed number matches one
another chapter publishes, but it is about a third accurate: it misses anything
reformatted on the way across, kg to g or 0.0965 to 0.096, which no string match
can see.

The prose still names and links the cited entry, so rule 10 records the
dependency for a reader as well as for `check`.

## Copying a chapter

A forked chapter copies **both** `_model.py` and `_analysis.py`: chapters share
nothing at runtime, so one without its own `_analysis.py` cannot measure
anything.

A fork is a `_model.py` change by definition, so that is the file to diff. The
`_analysis.py` that came across with it is a starting point, free to grow; the
`_fork.yml` beside them names the parent chapter, the commit it was taken at,
every deliberate difference, and anything it supersedes. `diff` between the two files is then the review, and an
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
