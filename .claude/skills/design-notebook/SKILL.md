---
name: design-notebook
description: Records aircraft design work in a chronological Quarto lab notebook. Use when the user is designing or analysing an aircraft, running AeroSandbox studies, or asks to record a finding. Scaffolds the notebook if none exists.
when_to_use: Designing or sizing an aircraft, running a trajectory or aero study, sweeping a design parameter, or saying "add this to the notebook".
allowed-tools: Bash(uv run quarto *) Bash(uv run python *) mcp__library-explorer__search mcp__library-explorer__list_classes mcp__library-explorer__list_functions mcp__library-explorer__get_docstring mcp__library-explorer__get_methods
---

Now: !`date "+%Y-%m-%d %H:%M"`
Notebook: !`find . -maxdepth 3 -name _quarto.yml -not -path "*/_site/*" 2>/dev/null`

## Start here — route the request

Every request, before anything else.

**1. Design, or meta?**
Design is the aircraft and any model of it, including "can I trust this model?".
Meta is the notebook system itself — this skill, its templates and references,
`lint.py`, `_notebook.py`, the MCP config, rendering. *Meta work gets done and
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
not answer the question. The linter checks for this.

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

2. **When a question has been answered, stop and propose.** Give the entry title
   (the user's question, verbatim) and its figures — nothing else — and ask
   whether to record it and where. **Ask the Specified questions from triage step
   3 in the same message**: you are stopping anyway, so the inputs cost no extra
   round trip. A proposal covering more than one question splits into one entry
   each. If any cell runs a solver or a sweep, say what it will cost to render,
   and **take that from the probe, not a guess** — `aero_report()` prints the
   solves it just ran, and `aerosandbox.md` turns them into seconds.
   **Write nothing into the notebook until the user agrees.**

3. **On approval**, write the entry's code, render it, and read every figure and
   printed block. **Then** write the prose and the `**Answer.**` line against
   what actually rendered, and re-render. An entry must never contradict its own
   outputs — prose written from the conversation rather than from the output is
   how that happens. **Draft it to the budgets under "Entry format" — 100 words
   of prose for the whole page** — rather than writing long and cutting back.

Repeat per question. A discussion that answers nothing gets no entry.

## The rules lint checks

**Know these before drafting, not after.** Finding one of them from a lint run
means the prose is already written; finding it from a *render* means paying for
the render twice. Run `uv run python <skill>/check.py <notebook> --no-render` to
check them without rendering, and the full `check.py` once the entry is right.

```
 1  no hand-typed number in prose — use `{python} …` (2+ decimals)
 2  no 3 consecutive code lines repeated across entries — promote to _analysis.py
 3  `**Answer.**` comes before the last code cell
 4  no sweeping a decision that should have been asked — record it as Specified
 5  no `for … in range(…)` around an aero solve — iterate to a tolerance
 6  prose ≤ 100 words for the whole entry, warnings included
 7  figure caption ≤ 50 words
 8  each Specified / Assumed item ≤ 10 words
 9  one prose section — no second `**Heading.**` or `##`
10  a sibling entry is linked, never named in bare prose
11  `_notebook.py` byte-matches the skill's copy
12  the freeze is not older than the model that froze it
13  every `_analysis.py` function the entry calls is passed to `footer(…)`
14  one visual per entry — a table counts as a figure
15  a table is at most 3×4 or 4×3, excluding the header
```

Why each exists, and the failure that earned it: `references/why.md`.

## Working cheaply

Context is the scarce resource; these cost nothing to follow.

- **Prefer no visual, then a table, then a plot.** Prose and the hero often carry
  the answer alone. A figure costs roughly thirty times a small table to read, so
  reach for one only when the *shape* is the argument — a curve, a crossover, a
  geometry — and a table genuinely cannot carry it. Pass an explicit `figsize`:
  `draw_three_view()` and friends ignore the notebook's rcParams and render
  several times larger than anything else.
- **`Edit`, never `sed`, on a file already in context.** A script edit makes the
  harness re-sync and echo the file back; `Edit` echoes nothing. The exception is
  a file *not* in context — copying a chapter — where `cp`/`sed` still beats
  reading it in to write it out.
- **Lint before rendering**, and **read a figure only when its bytes changed** —
  `check.py` names the ones that moved.
- **Don't re-read a file you just wrote.** `Edit` and `Write` already confirm.
- **Ask subagents for the finding, not the transcript.** Verbatim quoting is
  worth requesting when a claim must be checked against exact wording, and
  expensive as a default.

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
- **A table counts as a figure, so an entry shows one or none.** A table is a
  way of presenting evidence, not an appendix riding along beside the real one.
  Printing a grid under a plot that already shows the same quantities is the
  failure — one entry here put 72 numbers beneath a figure plotting four of its
  eight columns. Choose whichever carries the answer and delete the other.
- **A table is at most 3×4 or 4×3, excluding the header.** Past that it stops
  being something a reader takes in and becomes a grid to be searched. A wide
  two-row table is still a grid, so 2×5 is out too. If the values will not fit,
  that is the signal to plot them, or to quote the two or three that matter in
  the prose and drop the rest.
- **When you do show rectangular values, use a labelled `tbl-` cell**, not a
  wall of f-strings: it is cross-referenceable and scannable, and neither is
  true of printed output.
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

## Entry format

The shape is `templates/entry.qmd`; copy it.

### Budgets — know these before writing, not after

| | limit | counts |
|---|---|---|
| **prose, whole entry** | **100 words** | the answer, every warning, and any other running text, added up across the page |
| figure caption | 50 words | each |
| `## Specified` / `## Assumed` item | 10 words | each |

An inline expression counts as one word, so tightening prose never fights
computing the numbers in it. Only Specified/Assumed items and figure captions are
excluded from the 100 — they have their own budgets above.

Entries drift long one clause at a time, and the fix is always the same: the
sentence explaining *why* a number is what it is belongs in the figure caption or
a code comment, not the answer. The linter checks all three, but by then the
prose is written — budget it while drafting.

### The rest

- **One prose section, not several.** The answer is the entry's only run of
  prose; everything else is a callout, a figure or code. A second headed block
  (`**Assembly.**`, `**Method.**`, a `##` heading) reads as its own essay with
  its own budget, which is how an entry inside 100 words in each part ends up
  long overall. A procedure folds into the answer as a numbered list; a caveat
  becomes a `callout-warning`.
- **Don't print working.** A fit slope, a Reynolds number already stated, a mass
  nobody asked for: print results, not intermediates.
- **The answer goes first** — hero, `**Answer.**`, callouts, then the evidence.
  `code-fold` collapses the compute cell to one line, so the reader reaches the
  answer without scrolling. No setup line: the title is the question and the
  callouts carry the conditions.
- **One hero number, or none.** `::: {.hero}` carries the single value the entry
  exists to produce; `.hero-pair` when the answer *is* a comparison; nothing when
  the answer is a figure, a yes/no, or a value nobody asked for. A hero that
  isn't the answer to the title tells the reader to look at the wrong thing.
  Supporting values in the sentence get `[…]{.key}`.
- **An entry the work has moved past says so, at the top** — call
  `superseded_by("<successor stem>", "<one sentence>")` directly under the
  include. Title and link are read off disk, so they cannot go stale, and a wrong
  stem stops the render. Without it, a corrected configuration reads, to anyone
  arriving from the sidebar, as the current state of the aircraft.
- **Every entry ends with one `footer(...)` cell**, passing the shared functions
  it called. It renders the method, then what the entry cost to run — freeze
  records no timing, so this is the only trace that cost leaves.
- **Figures share one style**, set once in `_notebook.py`. Don't set fonts or
  colours per figure.

## Use AeroSandbox's own functions

**Before writing any geometry or aerodynamic calculation, ask what already
exists.** Use the `library-explorer` MCP server. It introspects the *installed*
aerosandbox — every class and function — so it cannot go stale against the
version the notebook actually imports.

`search(query)` first when you know what you want but not where it lives — it
matches full docstrings across methods too, which is the only way to find things
whose name gives no clue. `list_classes()` / `list_functions(area=…)` to browse,
`get_methods` / `get_docstring` to go deep once you have a name. Each tool's
traps are in `references/aerosandbox.md`.

**Do not write your own introspection** — a `dir()` or `inspect` dump re-derives
what these tools already return deduped and grouped. (`uv run python -c` is still
right for *checking* a call you have already found; that is not discovery.)

Then three rules. The third is the one that catches things:

1. **Use the library's function.** Areas, spans, aspect ratios, chords, volumes,
   wetted areas, stability derivatives and neutral points all exist already.
2. **If you reimplement anyway, say why, at the point of deviation.**
3. **Where both exist, compute both and compare.** The disagreement is the
   finding, agreement costs one line and becomes a regression test.

`references/aerosandbox.md` has the cases where this caught something, and the
API traps worth knowing before writing dynamics or mass-properties code.

## Scratch probes

Every notebook owns `<notebook>/_scratch/`, holding `_probe_base.py` (the
preamble — chapter loaded, `api()` printed), `probe.py` (the question) and
`probe.qmd`. All are scaffolded with the notebook.

**Reach for `probe.py` first**, and **edit its question block rather than
rewriting the file**. The chapter is plain Python, so a script gets real
tracebacks and stdout; Quarto gives you `Cell 3/5 ... An error occurred` and then
makes you scrape the output back out of HTML.

```python
"""Scratch probe. Gitignored, never rendered. Edit the question, not the file."""
from _probe_base import *  # noqa: F403 -- chapter loaded, api() printed

# --- the question ----------------------------------------------------------
```

**Use `probe.qmd` only when the question produces a figure.** For a one-off API
check that needs no model, `uv run python -c` beats both.

The leading underscore is load-bearing: `_scratch/` sits inside the Quarto
project, and Quarto skips `_`-prefixed paths, so `quarto render <notebook>` never
sees it. Don't rename it to `scratch/`.

Mechanics — paths inside cells, where output lands, the ~8 s render overhead:
`references/probing.md`.

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

**`_scratch/_probe_base.py` prints `api()` on every run**, which is the moment
someone is about to write a helper. That is where discovery belongs — not on a
rendered page the author has no reason to open.

**An entry that calls shared machinery must render it**, with `show_source()`.
Moving code out of an entry must not move the method out of sight — the
notebook exists to be reviewed.

Changing a chapter's `_model.py` or `_analysis.py` means proving what moved:

```bash
uv run python .claude/skills/design-notebook/check.py <notebook> [chapter ...]
```

It lints, deletes the freeze, renders and diffs, and names the figures whose
bytes changed. **Deleting the freeze is not optional** — freeze tracks the page,
not its includes, so without it you compare a fresh render against a cache hit
and the match is an artefact. There is no `--no-freeze` flag.

Any change that is not a deliberate deletion means the refactor altered the
model. The workflow, and why `git diff` alone cannot do this:
`references/refactoring.md`.

## Where the work goes

When the work belongs to a notebook that already exists, read that chapter's
`index.qmd` — it states what defines the chapter.

| The question needs | Goes to |
|---|---|
| the same model as an existing chapter | new entry in that chapter |
| a different model, fidelity or vehicle | new chapter |
| a different aircraft project | new notebook — ask first |

**When the model itself changes, the fork criterion is whether you want to keep
both answers** — not which file the change lands in. If the old answer is simply
superseded (wrong physics, or a known omission now closed) fix it in place and
put the correction in a later entry; if it stays valid under its own stated
assumptions and the comparison is the point, fork. An assumption of yours that
the user later replaces with a measurement or a brief is the first case: it was
never the design. Worked examples and the copying mechanics:
`references/forking.md`.

New chapter or notebook: see `templates/new-notebook.md`.

**A new notebook is built from `templates/new-notebook.md` and the skill's
`notebook.py` alone. Do not read an existing notebook to create one** — nothing
in it is needed, and it is the largest avoidable context cost. Notebooks share
nothing at runtime: each has its own `_quarto.yml`, `_freeze/`, `_scratch/` and
chapters, and `execute-dir: project` scopes every path inside its own notebook.
Put a second notebook in a sibling directory of the first, so both use the one
copy of this skill, its linter and its `notebook.py`. Start it in a fresh
session where possible — conversation history is the larger pollution.

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

- `check.py` — lint, render, and report what moved, in one call.
  `uv run python <skill>/check.py <notebook> [chapter ...] [--no-render]`.
  `lint.py` and `freezediff.py` do the first and last steps alone.
- `references/why.md` — the failure behind each lint rule. Read when a rule looks
  arbitrary, or before arguing one away.
- `references/refactoring.md` — proving a change to `_model.py`/`_analysis.py`
  moved nothing. Read before touching either.
- `references/forking.md` — when a model change earns a new chapter, and how to
  copy one cheaply.
- `references/probing.md` — scratch-probe mechanics. Read when a probe
  misbehaves or needs a figure.
- `references/quarto.md` — render and tooling traps. Read when a render fails, a
  figure misbehaves, or output needs extracting.
- `references/aerosandbox.md` — API traps and solver behaviour. Read before
  writing dynamics, optimization or mass-properties code.
- `references/aerosandbox-book/` — the AeroSandbox book, vendored. Filenames say
  what each chapter covers. The ones that come up: `11-optimal-control` for
  collocation, `12-dynamics-stack` for the `Dynamics` classes and axis systems,
  `07-atmosphere-propulsion-weights` for `MassProperties`,
  `02-robust-optimization-models` when a solve will not converge.
