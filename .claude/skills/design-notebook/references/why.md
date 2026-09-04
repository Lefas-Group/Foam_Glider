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

**11 — `_notebook.py` matches the skill's copy.** It is vendored into each
notebook because it runs at render time; a shared one would make a notebook
unrenderable without the skill, and would put a render-affecting file where
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

**15 — a table fits in 3×4 or 4×3.** Past that it stops being something a reader
takes in and becomes a grid to be searched. A wide two-row table is still a grid,
so 2×5 fails too. Measured on the rendered output, because a table built by
`print()` in an `output: asis` cell is not parseable as a table anywhere in the
source — but the frozen markdown holds it as literal pipe-markdown.
