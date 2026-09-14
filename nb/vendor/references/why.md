# Why each lint rule exists

SKILL.md carries the rules as a checklist, which is what you need while drafting.
This is the failure behind each one — read it when a rule seems arbitrary, or
before arguing one away. Every rule here was earned by something that actually
happened in this project.

**1 — no hand-typed number in prose.** Three separate corrections were needed in
one session where an entry's prose disagreed with its own rendered output. Every
result in prose must be an inline expression, so the number *is* the computation
rather than a copy of it. Two decimals or more reads as a result; one decimal is
usually a condition (6 m/s, 0.5 deg) and flagging those is noise.

**2 — no code repeated across entries.** Four subtly different neutral points
were once written in one chapter, one of which took its moment reference from the
wrong station and put wrong numbers in front of the reader. Boilerplate is
excluded — axis cosmetics, imports, and `footer(`, which rule 13 *requires* in
every entry and so can never be promoted anywhere.

**3 — the answer comes before the evidence.** An entry is read to find out what
was learned; the working is there to be checked afterwards.

**4 — no sweeping a decision that should have been asked.** "Where does the
ballast go?" was once answered with three static margins because nobody asked
which was wanted — turning a missing input into extra analysis, which is worse
than either asking or assuming. The failure looks like diligence, which is why
the rule needs its reason.

**5 — no fixed trip count around an aero solve.** `trim()` was written
`for _ in range(60)` around a fixed point that settles in 9 to 13, so every call
spent about twenty seconds re-deriving an answer it already had, at a dozen call
sites. An AeroBuildup call costs the same whether asked for one angle of attack
or six hundred — the count of *calls* is the whole budget, and a loop is where
they hide. A round number someone picked also hides non-convergence, since a loop
that never converged returns exactly like one that did.

**6, 7, 8 — the word budgets.** Entries drift long one clause at a time, and the
fix is always the same: the sentence explaining *why* a number is what it is
belongs in the figure caption or a code comment, not in the answer. A
`callout-warning` counts against the prose budget — moving a paragraph into a
coloured box does not make it shorter. One entry recorded a static margin with
three lines of justification, which reads as hedging a decision that was actually
made.

**9 — one prose section.** A second headed block (`**Assembly.**`, `**Method.**`,
a `##` heading) reads as its own little essay with its own budget, which is how
an entry inside 100 words in each part ends up long overall.

**10 — a reference to another entry is a link.** "The previous entry" as bare
prose is the same defect as a hand-typed number: it points at something that can
be retitled, reordered or deleted, and nothing notices. The notebook's whole
structure is later entries revising earlier ones, so those references are the
structure, not decoration.

**11 — `_notebook.py` matches the canonical copy.** It is vendored into each
notebook because it runs at render time; a shared one would make a notebook
unrenderable without `nb` installed, and would put a render-affecting file where
Quarto's freeze cannot see edits to it — which has served stale pages here.
Vendoring costs propagation; this rule buys it back.

**12 — a freeze is not older than the model that froze it.** Freeze tracks the
page, not its includes, so editing `_model.py` leaves every entry serving values
the current model does not produce, silently. A fuselage ply count changed here,
nothing re-executed, and an entry went on rendering a duration the model no
longer gave; it surfaced only because that entry happened to carry an `assert`.

**13 — an entry renders the shared machinery it calls.** Moving code into
`_analysis.py` must not move the method out of sight; the notebook exists to be
reviewed. Checked against inline expressions as well as cells, because a value
quoted only in prose is a call that appears in no cell. Only what the entry
*names*, never the transitive closure — that would reproduce the whole file in
every entry, and make splitting a function break entries whose conclusions never
changed.

**14 — a table counts as a figure.** Three entries printed a grid directly
beneath a plot that already showed the same quantities; one was 72 numbers under
a figure plotting four of its eight columns. A table is a way of presenting
evidence, not an appendix riding along beside the real one.

**15 — a table fits in 6×4.** Past that it stops being something a reader takes
in and becomes a grid to be searched. Columns stay capped at four because a wide
table is still a grid. **Raised from 3×4-or-4×3**, which was written against a
table DECORATING a finding and also caught the case where the table IS the
finding: six optimisation variables against their bounds needs 6×4, had no legal
form, and the entry wrote fifteen numbers into one sentence instead — the same
grid, minus the alignment. Rule 25 closes that escape. Measured on the rendered output, because a table built by
`print()` in an `output: asis` cell is not parseable as a table anywhere in the
source — but the frozen markdown holds it as literal pipe-markdown.

**16 — a budgeted chapter does not override `SOLVE_BUDGET` at a call site.** The
budget exists so a runaway solve stops; a local `max_runtime=` at one of five
call sites re-opens the hole silently and nothing downstream shows it. If a solve
genuinely needs longer that is a decision for the user, recorded in `index.qmd`,
not a keyword argument nobody reads again. Static, so unlike rule 17 it cannot
behave differently on a busy machine. **Opt-out, and the first version got this
backwards**: it applied only to chapters that bound `SOLVE_BUDGET`, which made
the budget unforgettable at the call site while leaving it forgettable at the
chapter — a new chapter that never bound it ran unprotected, and forgetting is
the failure the whole mechanism exists to catch. A guard you skip by inaction is
not a guard. A chapter now exempts itself with `SOLVE_BUDGET = None`, a visible
line someone chose, which is what let this be added to a notebook whose earlier
chapters were already frozen without keeping a grandfather list.

**17 — a frozen entry stays under its chapter's `ENTRY_CEILING`.** One entry
reached 599 s and nothing anywhere said so; the cost of a notebook was invisible
until `footer()` started recording it. This blocks past a ceiling the *user* set
and only warns below it, because wall clock is not reproducible — the same solve
measured 533.9 s against a 145 s baseline purely from machine load, so a single
hard threshold would fail on a loaded laptop and pass on an idle one. Past a
user-chosen ceiling, load is no longer a plausible explanation.

**18 — the solve budget in force is declared in the chapter's index.** A chapter
was forked from another and silently inherited `SOLVE_BUDGET = None`, carried in a
file nobody re-reads, together with a comment — "its pages are already frozen" —
that was untrue of a chapter with no pages at all. A budget is a decision about
what the work may cost, so it belongs in `## Specified` with every other brief;
declared there, an inherited one is visible in the single file a fork has to
rewrite anyway. A numeric budget must appear as an inline expression so the prose
cannot drift from the value. Paired with a per-entry declaration, which a fork
cannot carry across,
so forgetting leaves a chapter on the safe defaults rather than on its parent's
exemption.

**25 — no sentence enumerates more than five computed values.** The other half of
15. Prose had no row limit, so when a table was illegal the values went into a
run-on sentence and read worse than the table would have. Five is not a guess:
across 32 written entries the most any sentence carried was five, with the
distribution falling away hard above three, and the sentence that earned this
rule carried fifteen.

**26 — the title is one question, at most 18 words.** The schema demanded the ask
VERBATIM, which is right for a question and wrong for a brief: "optimise a glider
for trimmed glide. It is constructed of foam 5mm thick density 174.4g/m^2, with a
fixed 300mm span and a sensibly sized, fixed tail" became a title, a sidebar
entry and a 70-character filename — and every constraint in it belonged to the
chapter, so the title restated what `index.qmd` already said. Measured across 35
entries: 34 are a single sentence ending in "?", the median is eight words, the
longest legitimate one is eighteen, and the one exception fails all three checks.
Rephrasing is allowed now, so the verbatim ask is recorded in the commit body
whenever it differs from the title.
