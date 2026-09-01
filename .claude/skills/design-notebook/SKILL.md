---
name: design-notebook
description: Records aircraft design work in a chronological Quarto lab notebook. Use when the user is designing or analysing an aircraft, running AeroSandbox studies, or asks to record a finding. Scaffolds the notebook if none exists.
when_to_use: Designing or sizing an aircraft, running a trajectory or aero study, sweeping a design parameter, or saying "add this to the notebook".
allowed-tools: Bash(uv run quarto *) Bash(uv run python *) mcp__library-explorer__list_scoped_classes mcp__library-explorer__list_scoped_functions mcp__library-explorer__get_docstring mcp__library-explorer__get_methods
---

Now: !`date "+%Y-%m-%d %H:%M"`
Notebook: !`find . -maxdepth 3 -name _quarto.yml -not -path "*/_site/*" 2>/dev/null`

## Start here — route the request

Every request, before anything else.

**1. Design, or meta?**
Design is the aircraft and any model of it, including "can I trust this model?".
Meta is the notebook system itself — this skill, its templates and references,
`_lint.py`, `_notebook.py`, the MCP config, rendering. *Meta work gets done and
committed. It never becomes an entry.*

**2. Design: where does it go?** See "Where the work goes" — same model becomes
an entry, a different model or vehicle a chapter, a different aircraft a new
notebook (ask first).

**3. Does it need an input you do not have?** Classify each one:

| kind | test | action |
|---|---|---|
| **Derivable** | the model or the plans already contain it | compute it — never ask, never assume |
| **Specified** | a different answer changes *what we are building* | **ask** |
| **Unknown** | a different answer changes *how accurately we modelled it* | assume, flag, say what it costs |

Static margin is Specified — 5% and 15% are different aircraft. The `Cm`-against-
`CL` fit band is Unknown-ish but really a modelling convention; asking would be
noise.

**Never sweep a Specified input instead of asking for it.** Carrying three
values because nobody chose one turns a missing input into extra analysis, which
is worse than either asking or assuming — it triples the output and still does
not answer the question. `_lint.py` checks for this.

**4. On the reply:**

- **A value** → record it in the entry's `## Specified` callout and continue.
- **"I don't know, what do you think?"** →
  - *answerable in a sentence* → answer it, record it as Specified with yourself
    as owner and the reason, continue.
  - *needs computation to answer* → it is a question in its own right. **Return
    to step 1 with it**, answer it, then come back and finish the original.

With no user to ask — an agent running unattended — assume, and write
`owner: assumed` in the box. That keeps "did a person decide this?" visible.

## The loop

1. **Explore in the notebook's `_scratch/`** — gitignored, skipped by project
   renders, so nothing in the notebook is touched. See "Scratch probes" below.

2. **When a question has been answered, stop and propose.** Give the entry
   title (the user's question, verbatim) and its figures — nothing else. **Ask
   the Specified questions from triage step 3 in this same message**: you are
   stopping anyway, so resolving the inputs costs no extra round trip. If the
   proposal covers more than one question, split it into one entry each. Say
   what the entry will cost to render if any cell runs a solver or a sweep;
   freeze pays it once, and it survives edits to `_model.py`. **Take that cost
   from the probe, not from a guess**: `aero_report()` prints the solves the
   probe just ran, and `aerosandbox.md` gives the per-strip price to turn them
   into seconds. Guessing is how a helper spending sixty solves to converge in
   twelve went unnoticed — and freeze records no timing, so an entry's cost
   leaves no trace once written. Ask
   whether to record it and where. **Write nothing into the notebook until the
   user agrees.**

3. **On approval**, write the entry's code, render it, and read every figure and
   printed block. **Then** write the prose and the `**Answer.**` line against
   what actually rendered, and re-render. An entry must never contradict its own
   outputs — prose written from the conversation rather than from the output is
   how that happens.

Repeat per question. A discussion that answers nothing gets no entry.

**Run `uv run python <notebook>/_lint.py` before recording an entry.** Eight
rules, each earned by a failure that actually happened here: no hand-typed
numbers in prose, no code repeated across entries, the `**Answer.**` before the
evidence, no swept decision that should have been asked, no fixed trip count
around an aero solve, and the three word budgets (100 prose / 50 caption / 10
per callout item). It exits non-zero, so it can gate a commit.

## Scope

The entry answers the question asked and stops. This is the rule that gets
broken most; when in doubt, write less.

- **One question, one entry.** Two questions asked in the same breath become two
  entries, not one entry with two sections. Facets of a *single* comparison
  (cost, fidelity, applicability) are one question, not three.
- **Compute only what was asked.** "What are the polars?" means the curves — not
  max L/D, CL_max, stall angle or Cm_α. Don't print derived scalars nobody
  requested, and don't add them to the model "while you're there".
- **No unrequested studies.** A sensitivity sweep, a multistart, a comparison
  against another configuration: each is its own question, for the user to ask.
- **Don't assume a value the model can compute.** If the components are stated,
  sum them. An assumption is for a value you genuinely don't have, not one you
  didn't bother deriving. Where an assumed value and a computed one must agree,
  solve for the input that makes them agree rather than asserting both.
- **A comparison entry names what is held constant between the arms.** Two
  models differing in more than one respect measure nothing.
- **State the reference for any quantity that has one.** A `Cm` is meaningless
  without saying what it is taken about; a coefficient at chuck-glider scale is
  meaningless without the speed, since Re moves the polar materially.
- **Three word budgets, all enforced by `_lint.py`.**
  **100 words of prose per entry** — the answer, any warning, an assembly
  section, everything addressed to the reader, added up across the page.
  **50 words per figure caption.** **10 words per `## Specified` or `## Assumed`
  item.** An inline expression counts as one word, so tightening prose never
  fights computing the numbers in it. Entries drift long one clause at a time,
  and the fix is always the same: the sentence explaining *why* a number is what
  it is belongs in the figure or a code comment, not the answer.
- **No setup line.** The title is the question and the callouts carry the
  conditions; a sentence restating what was run before the reader reaches the
  answer is throat-clearing.
- **The answer goes first**, above everything: hero, `**Answer.**`, then the
  callouts, then the evidence. `code-fold` collapses the compute cell to one
  line, so the reader reaches the answer without scrolling.
- **One hero number, or none.** `::: {.hero}` carries the single value the entry
  exists to produce, with a one-line label saying what it means. Use
  `.hero-pair` when the answer *is* a comparison — measured against predicted,
  as-built against as-designed — and nothing when the answer is a figure, a
  yes/no, or a value nobody asked for. A hero that isn't the answer to the
  title is worse than no hero: it tells the reader to look at the wrong thing.
  Supporting values in the sentence get `[…]{.key}`.
- **Every number in prose is an inline expression**, `` `{python} f"{x:.2f}"` ``,
  never typed. Hand-typed numbers drift from the cells above them and the drift
  is silent until someone re-derives the result.
- **Rectangular results are a table, not a `print()` block.** A labelled
  `tbl-` cell is cross-referenceable and scannable; a wall of f-strings is
  neither. Don't print working — a fit slope, a Reynolds number already stated,
  a mass nobody asked for.
- **Captions describe, they don't conclude.** "Lift curve, drag curve and drag
  polar at 6 m/s", not "notice that everything is symmetric because…".
- **Specified and Assumed are different things.** *Assumed* is a weakness —
  nobody knows, the number may be wrong, sensitivity matters. *Specified* is a
  brief — someone decided, so it is not wrong; changing it changes the target,
  not the model's accuracy. `::: {.callout-tip}` / `## Specified` and
  `::: {.callout-note}` / `## Assumed` are each **one line of attribution
  ("Asked of the user, 2026-08-28:"), then a numbered list of inputs at ten
  words each**. Attribution goes in the preamble, not inside every item.
- **A caveat is a `::: {.callout-warning}`, not a paragraph.** "Do not trust
  that number", "what the video cannot measure", "what changed in the model" —
  yellow, titled, and still inside the 100-word prose budget.
- **Assumptions sit at the level they belong to.** What defines the chapter —
  the aero method, the section, what is left out — is stated once in
  `index.qmd`. What this entry alone had to assume goes in its `## Assumed`
  callout. Neither is repeated as commentary in the prose.
- **Interesting things you weren't asked about go in chat**, as a suggested next
  question. Never into the notebook.

The same restraint applies before the entry exists: don't probe in scratch for
tangents, only for what was asked.

## Use AeroSandbox's own functions

**Before writing any geometry or aerodynamic calculation, ask what already
exists.** Use the `library-explorer` MCP server — `list_scoped_classes`, then
`get_methods` on the class you want. It is scoped deliberately: 81 curated
classes and 353 functions, against ~183 modules in `aerosandbox`. **Do not write
your own introspection** — a `dir()` or `inspect` dump bypasses that scoping and
buries the answer in internals. (`uv run python -c` is still right for *checking*
a call you have already found; that is not discovery.)

Then three rules. The third is the one that catches things:

1. **Use the library's function.** Areas, spans, aspect ratios, chords, volumes,
   wetted areas, stability derivatives and neutral points all exist already.
   `references/aerosandbox.md` lists the ones this notebook reimplemented before
   noticing.
2. **If you reimplement anyway, say why, at the point of deviation.** Sometimes
   you must: fuselage mass in the McEagle chapter deliberately does not come
   from `Fuselage.volume()`, because a super-ellipse under-fills the rectangular
   foam slab by up to 22%. The comment saying so is the model working correctly.
3. **Where both exist, compute both and compare.** The disagreement is the
   finding. `Wing.area()` against a traced integral is what exposed a wing built
   2.75% too large; `Fuselage.volume()` against the slab is what exposed the
   mass trap. Neither was caught by reading the code. Agreement costs one line
   and becomes a regression test.

## Scratch probes

Every notebook owns `<notebook>/_scratch/`, holding `probe.py` and `probe.qmd`.
Both are scaffolded with the notebook; create them if a notebook predates this.
Overwrite them per question rather than accumulating `probe-<slug>` files; a
second file is fine when a long run is worth keeping while a new question is
explored.

**Reach for `probe.py` first.** The chapter is plain Python, so a script gets
it with a few `exec`s and gives you real tracebacks and stdout. Quarto gives you
`Cell 3/5 ... An error occurred` and then makes you scrape the output back out
of HTML. The exact preamble — which files, in which order, and why they are
`compile`d rather than `exec`d raw — is in `templates/new-notebook.md`. Copy it
from there rather than from memory; the copy that used to live here drifted out
of date and stopped working.

**Use `probe.qmd` when the question produces a figure**, or when you are
rehearsing cells that are about to become an entry — its cells paste across
unchanged. For a one-off API check that needs no model at all, `uv run python -c`
beats both.

Iterating on a plot re-runs every cell above it, cold, on each render. If that
starts to hurt, `exec` the model into a persistent Jupyter kernel instead and
re-plot without re-solving.

The leading underscore is load-bearing: `_scratch/` sits inside the Quarto
project, and Quarto skips `_`-prefixed paths, so `quarto render <notebook>`
never sees it. Don't rename it to `scratch/`.

````markdown
---
title: "Probe"
execute:
  # _freeze/ is committed and holds entry results. Probes must never land in it.
  freeze: false
---

{{< include ../chapters/NN-name/_model.qmd >}}

```{python}
<the question being explored>
```
````

- **The include path is relative to the probe file**, hence `../chapters/…`.
- **Cell code runs from the notebook root**, not from `_scratch/`, because the
  project sets `execute-dir: project`. Any path inside a cell is relative to the
  notebook directory.
- Run it: `uv run quarto render <notebook>/_scratch/probe.qmd`
- Output stays put — Quarto renders it standalone, not into `_site/`. Printed
  output is in `_scratch/probe.html`; figures are
  `_scratch/probe_files/figure-html/*.png`, named `cell-N-output-1.png` unless
  the cell has a `#| label:`. Read every figure before reporting on it.
- Each render costs ~8 s of fixed overhead regardless of the code, so put
  several probes in one file rather than rendering repeatedly.

## Where machinery lives

A notebook is `_notebook.py` (furniture, one copy) plus chapters. A chapter is
`_model.py` (the vehicle), `_analysis.py` (how the chapter measures it), and its
entries. A helper moves up a tier only when it earns it:

| tier | lives in | shown by | promoted when |
|---|---|---|---|
| entry-local | the `.qmd` cell | the folded code cell, already | one entry needs it |
| chapter-shared | `_analysis.py` | `show_source(...)` in each calling entry | a **second** entry reaches for it |
| model | `_model.py` | the chapter index | it describes the aircraft, not a measurement |
| furniture | `_notebook.py` | nothing — it is plumbing | it is about the notebook, not any aircraft |

`_notebook.py` holds `show_source()` and `api()` and is deliberately invisible in
the rendered site: the chapter index lists `_model.py` and `_analysis.py` only,
and `api()` filters to `_analysis.py`. A reader of the design does not need a
function inventory.

**`_scratch/probe.py` prints `api()` on every run**, which is the moment someone
is about to write a helper. That is where discovery belongs — not on a rendered
page the author has no reason to open. Four subtly different neutral points once
existed in one chapter because nothing advertised the first, and one of the four
took its moment reference from the wrong station.

**An entry that calls shared machinery must render it**, with `show_source()`.
Moving code out of an entry must not move the method out of sight — the
notebook exists to be reviewed.

Promoting a helper means editing an earlier entry to call it. That is allowed,
and is *not* the thing "entries are written once and left alone" forbids: that
rule protects conclusions from being quietly rewritten. A refactor is different
in kind, and the difference must be **proven, not asserted** — dump every
entry's rendered numbers before and after and diff them. Any change that is not
a deliberate deletion means the refactor altered the model.

## Where the work goes

Read each chapter's `index.qmd` — it states what defines that chapter.

| The question needs | Goes to |
|---|---|
| the same model as an existing chapter | new entry in that chapter |
| a different model, fidelity or vehicle | new chapter |
| a different aircraft project | new notebook — ask first |

New chapter or notebook: see `templates/new-notebook.md`.

## Entry files

`notebook/chapters/NN-name/YYYY-MM-DD-NN-slug.qmd` — the trailing `NN` counts
within the day so same-day entries order correctly. Title is the question as
asked. Format: `templates/entry.qmd`.

Entries are written once, debugged, then left alone. Record what actually
happened, including answers that turned out to be wrong.

When a later entry corrects an earlier one, the correction goes in the **later**
entry: state the old value, the new one, and why they differ. Never edit the
earlier entry, and don't add a pointer to it unless asked. Two entries
disagreeing, with the later one explaining the disagreement, is the intended end
state.

## Reference

- `references/quarto.md` — render and tooling traps. Read when a render fails, a
  figure misbehaves, or output needs extracting.
- `references/aerosandbox.md` — API traps and solver behaviour. Read before
  writing dynamics, optimization or mass-properties code.
- `references/aerosandbox-book/` — the AeroSandbox book, vendored. Filenames say
  what each chapter covers. The ones that come up: `11-optimal-control` for
  collocation, `12-dynamics-stack` for the `Dynamics` classes and axis systems,
  `07-atmosphere-propulsion-weights` for `MassProperties`,
  `02-robust-optimization-models` when a solve will not converge.
