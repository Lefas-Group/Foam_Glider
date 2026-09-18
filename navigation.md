# Navigating a notebook that fans out

**Status: plan, not implemented.**

The notebook is a DAG of design decisions presented as a numbered list. Six
chapters, twenty-two entries, and no way to see how any of it relates. This plan
fixes navigation in six stages, cheapest and most certain first.

Each stage lands in up to five places — the existing notebook, the `nb new`
scaffold, `create_chapter`, the agent's guidance, and a lint rule to stop it
decaying. **Four surfaces, not one** below is the audit; read it before
estimating any stage, because retrofitting `glider-notebook` is usually the
smallest part.

In one paragraph: **the format is right and the front door is missing.** A
Quarto website is the correct home for an append-only record — chronological,
verifiable, superseded rather than edited — but it answers only "what happened,
in order?" and never "what is the design now, and how do these chapters
relate?". Everything below adds the second view without weakening the first.

---

## What is actually wrong, with evidence

### 1. There is no book index at all

```
root-level .qmd in the notebook   NONE
nb/scaffold/index.qmd.tmpl        the CHAPTER template, used only by create_chapter
```

The website has **no front page of its own**. Quarto synthesises an
`_site/index.html` so the URL is not a 404, but nothing authored sits behind it:
`nb new` scaffolds `_quarto.yml`, `styles.css`, `_notebook.py` and a first
chapter, and no notebook of the three has a root `.qmd`. So there is nowhere
that says what the aircraft is, what is being explored, or how the chapters
relate — and no home for the one picture that would answer the question this
whole plan is about.

### 2. The sidebar order is filesystem order

`_quarto.yml` uses `- auto: "chapters"`, and no chapter `index.qmd` carries an
`order:` field. With nothing to sort on, Quarto emits sections in `readdir`
order. Measured:

```
readdir order of chapters/   03, 01, 06, 04, 02, 05
the rendered sidebar         03, 01, 06, 04, 02, 05
```

The `01-`…`06-` prefixes that encode the entire design lineage are **invisible
and ignored**.

Two consequences beyond the mess:

- **`page-navigation: true` is misleading.** Its comment says it is there "so
  entries read straight through". It does not — next/previous walks
  `03 → 01 → 06 → 04 → 02 → 05`, crossing chapters in hash order.
- **The order is unstable.** It is a hash of the directory names, so adding
  chapter 07 can reshuffle everything above it, invalidating any mental map.

### 3. Chapter order is chronological; the design relationships are not

The fork headers already in the models give the real shape:

```
01 → 02 → 03 → 04 → 05
                      ↘ 06
```

06 is **a control arm for 05, not its successor**: 04 went 5 mm → 3 mm, 05 fully
optimised the 3 mm design, and 06 applies 05's method back to 5 mm to isolate
what the material was worth. The table of contents presents it as the next step.

Underneath that, chapters vary along three independent axes:

| | model detail | material | method |
|---|---|---|---|
| 01 | wing only | 5 mm | manual sizing |
| 02 | + fuselage | 5 mm | manual |
| 03 | + unswept c₄ | 5 mm | manual |
| 04 | + unswept c₄ | **3 mm** | manual |
| 05 | + unswept c₄ | 3 mm | **full optimisation** |
| 06 | + unswept c₄ | **5 mm** | full optimisation |

A flat numbered list cannot express a 2×2. Neither can a directory tree — it has
one hierarchy and this content has three axes.

### 4. The chapter index does not orient you

`index.qmd` is title → `{{< include _model.qmd >}}` → prose → **Specified** →
**Assumed** → collapsed model source. Missing:

- the lineage (`# Forked from chapters/05-…/_model.py at e2e92dc` exists, but
  inside a collapsed code block where no reader will see it);
- a list of the chapter's own entries — you land on the index and there is
  nothing to click;
- a statement of what differs from the parent. 06's prose is 05's with
  "3 mm" → "5 mm", so the difference, which *is* the chapter, has to be found by
  diffing two paragraphs by eye.

06's **Specified** callout already gropes toward this — "Foam thickness: 5 mm"
then "*Inherited from earlier models:*". The instinct is right; it belongs at the
top of the page.

### 5. Half the chapters never show you the aircraft

The three-view is drawn in four entries across three chapters — 01, 02 and 05.
**Chapters 03, 04 and 06 have no picture at all.** Whether you can see the
aeroplane depends on whether someone happened to ask.

### 6. Cross-chapter numbers are hand-typed

Chapter 06's prose says "barely an improvement over the 0.400 m/s achieved by the
manually sized 5 mm model". That 0.400 is transcribed. It is one of the two
standing lint warnings (`old_sink = 0.36` is the other).

**Navigation and correctness are the same problem here.** Entries fan out
because they compare against each other; comparison needs citation; without
citation you get transcription; transcription is what the linter flags.

---

## Stage 1 — Ordering and orientation

Config, scaffold and one guard. No new mechanism and no solve, but it lands in
four places — see **Four surfaces** below for why that is the shape of every
stage here.

| change | where |
|---|---|
| `order: <n>` in every chapter `index.qmd` | six files |
| numbered titles — `"04 · 3 mm foam"` | same six |
| emit both for a new chapter | `create_chapter`, which already allocates the number |
| `bread-crumbs: true`, `toc: false` | `_quarto.yml` **and** `nb/scaffold/_quarto.yml.tmpl` |
| `order` placeholder | `nb/scaffold/index.qmd.tmpl` |
| a chapter index carries `order` matching its directory number | new lint rule |

`order` and `bread-crumbs` are both confirmed present in the installed Quarto
1.8.27 schema:

```
order        number   "Order for document when included in a website automatic sidebar menu"
bread-crumbs boolean  "show navigation breadcrumbs for pages more than 1 level deep"
```

Entries live at `chapters/<chapter>/<entry>.qmd` — two levels deep, so they
qualify for breadcrumbs, and every entry page would carry
`Chapters › 3 mm foam › How stable is the glider to perturbations?`.

**`toc: false`** because the "On this page" column is empty or near-empty
everywhere. Counted across the notebook:

```
## headings per page   22 pages have 0    4 have 1    2 have 2    6 have 3
```

The six 3s are the chapter indexes, and two of each three are `## Specified` and
`## Assumed` *inside callouts*, which Quarto renders as callout titles and leaves
out of the TOC — so an index shows a single entry reading "The model". This is
not a defect but a consequence of the design: one entry answers one question, so
there is nothing to navigate within a page.

Removing it also widens the content column, which matters more once Stage 4 has
entries leading with a figure. Making the margin *useful* instead — listing the
chapter's other questions there, so you can move between siblings without
returning to the sidebar — was considered and deferred: it is custom generation
for a gain that Stage 3's entry listing already covers one click away.

**Pros.** Fixes the sidebar, fixes next/previous, and answers "where am I?" —
the question hit twenty times a session. Numbered titles make the sequence
legible in the text, so a mis-sorted sidebar is still readable. The fix belongs
in `create_chapter`, which already allocates the number, so it cannot recur.

**Cons.** Sequence is the wrong shape for 06, which is a sibling of 05 rather
than its successor. Numbering makes that exception *visible* rather than hiding
it in noise, but does not express it — Stage 2 does.

**Risk.** Two, both small and neither zero — an earlier draft of this plan said
"risk: none", which was wrong on both counts.

- **Six index freezes are invalidated.** Editing `index.qmd` makes Quarto
  re-execute that page. Cheap today — exec the model, print its source, no
  solve — and cheap is a property Stage 3 is written to preserve.
- **`nb.corpus` will move** by however many chapters fail the new `order` rule
  when it lands, which is all six until they are edited. Calibrate first, and
  update the count in the same commit.

The template edit is not optional. Without it `nb new` keeps minting notebooks
with the scrambled sidebar, including the comment that asserts the ordering
works.

---

## Stage 2 — The book index

There is no front page. This creates one — in `glider-notebook` **and** in the
scaffold, since `nb new` currently writes `_quarto.yml`, `styles.css`,
`.gitignore`, the vendored files and a first chapter, and no root page at all.
A notebook that gains a front door while the next one is born without one is
half a fix.

It is also the natural home for the forking structure.

```markdown
---
title: "Optimised Glider II"
---

A 300 mm span glider cut from foam, optimised for minimum sink rate in trimmed
glide. Each chapter is one **model** — a vehicle, a fidelity, a method — and each
entry is one question asked of it.

## How the chapters relate

[generated mermaid diagram — see below]

## The chapters

[generated table: chapter · material · model detail · method]

## Where to start

Chapter 01 for the whole story from the beginning; chapter 05 for the best
design so far.
```

### The lineage diagram is generated, not drawn

Every forked model already carries its parent:

```python
# Forked from chapters/05-fully-optimized/_model.py at e2e92dc
```

`lint.model_kinship()` already parses these for rule 31 and discards the result.
A code cell on the book index can walk `chapters/*/_model.py`, read those
headers, and emit mermaid — which Quarto renders natively. The picture then
cannot disagree with the models, because it is made from them.

**Critically, this READS source rather than executing it.** No chapter model is
run, no solve happens, and there is no cross-chapter *value* dependency — so
unlike the state table, this needs nothing from Stage 5 and costs nothing to
render.

**Pros.** It is the one artifact that answers the question this plan exists for:
that 06 hangs off 05 rather than following it. It is derived, so it cannot rot.
It is cheap — text parsing, no solve. And it gives the site the front page it has
never had, which is also where a newcomer learns what the aircraft *is*.

**Cons, and one real hole.** The root index is not a chapter, so **rule 12 will
not invalidate it**: rule 12 fires on a dirty `_model.py` against that chapter's
freeze, and the root page belongs to no chapter. Add chapter 07 and the book
index would keep serving a six-node diagram from its own freeze, silently — the
exact failure rule 12 was written to prevent, one level up.

The fix is deterministic and belongs with the cause: **`create_chapter` deletes
`_freeze/index/` when it scaffolds a chapter.** A new chapter then forces the
book index to re-render, by construction. A lint rule is the alternative, but it
would be a rule enforcing something the scaffold can simply guarantee.

**What waits for later.** The chapter table's *headline numbers* are a
cross-chapter value dependency and need Stage 5. Its *axes* — material, method,
model detail — need the Stage 5 vocabulary. So build the diagram and the prose
first, and let the table grow into place.

---

## Stage 3 — The chapter index

```markdown
---
title: "06 · Fully optimized 5 mm glider"
order: 6
listing:
  id: entries
  contents: "20*.qmd"
  type: table
  fields: [title, date]
  sort: date
---

Forked from [05 · Fully optimized geometry](../05-fully-optimized/) —
the same optimisation, on 5 mm foam instead of 3 mm.

{{< include _model.qmd >}}

[three-view of this chapter's optimised design]

A 300 mm span glider cut from 5 mm foam where almost all geometry …

## Questions asked here

::: {#entries}
:::

[Specified] [Assumed] [The model, collapsed]
```

Three of the four additions are **derived, not written**: `create_chapter`
already allocates the number and receives `forked_from`, so `order`, the
numbered title and the lineage sentence come free and cannot drift. The listing
reads the directory, so it can never be stale or incomplete.

**Pros.** The lineage sentence and the entry listing are what orient a reader:
one says where the chapter came from and what changed, the other gives them
something to click. Both are derived, so neither can drift out of step with the
chapter.

**Cons.** The content is only markdown and frontmatter on a page that already
renders. The work is in the other three surfaces: `nb/scaffold/index.qmd.tmpl`
gains the listing block, `create_chapter` writes the lineage sentence from the
`forked_from` it already receives, and **the listing block needs a lint guard**.

That last one is not belt-and-braces. Rule 30 exists because a model that
rewrote `index.qmd` with `write_file` instead of editing it dropped the
scaffolded `_model.py` display block and nothing noticed. The listing is
scaffolded index content with exactly that failure mode, so it goes the same way
unless a rule watches it — and `nb.corpus` moves when that rule lands.

**No design visualisation here.** A three-view of the chapter's optimised model
was considered and dropped. It would have been the only thing on the page that
*executes* — index pages carry no `footer()`, so they have no runtime line, no
solve count, no budget and nothing rule 17 can measure, and six chapter indexes
would each have started paying an unbudgeted solve. The aircraft is shown by the
entries that ask about it, which is where the question was actually put.

**What is deliberately left out.** The headline number per entry in the listing.
A listing can only show static frontmatter, so "0.399 m/s" beside each question
would be transcription — the failure already flagged twice. That needs Stage 6.

---

## Stage 4 — Lead with the diagram

Today the stated preference for an entry's one visual is, verbatim from
`schema.py`:

> "ONE visual or none — a table counts as a figure. **Prefer none, then a table,
> then a plot.**"

Invert it: **diagram, then table, then prose.** An entry whose answer can be seen
should show it, and a page of prose with a number in it is the least
interesting form the same finding can take.

| where | change |
|---|---|
| `nb/schema.py` — the `figures` field | invert the preference and say why |
| `nb/system_instruction.md` | match, wherever it echoes the ordering |

**Nothing to retrofit.** This is the one stage that touches no notebook: existing
entries stand as written, because the record is append-only and a finding is not
improved by redrawing it later. It changes what the next entry looks like, and
only that.

**Pros.** This is **guidance, not a rule** — the preference lives only in a field
description, so nothing in `lint.py` changes and `nb.corpus` cannot move. It is
the cheapest change in this plan and the most visible: it affects every future
entry without touching a single existing one.

**Cons, and the reason the old ordering existed.** "Prefer none" was a brake on
decorative output. Rule 14's rationale in `why.md` records what it was written
against: *"Three entries printed a grid directly beneath a plot that already
showed the same quantities; one was 72 numbers under a figure plotting four of
its eight columns."* Inverting the preference must not re-open that — the
failure was **duplication**, not plotting, and rule 14 (one visual) plus rule 15
(a table fits 6×4) already hold that line.

So the inversion needs to carry its own condition: **the visual must be the
thing that answers the question**, not an illustration beside the answer. A plot
that repeats what a sentence already said is worse than the sentence, which is
what "prefer none" was clumsily protecting. Say that, rather than just flipping
the order.

**Risk.** Entries get slower to render — matplotlib, not solves, so tens of
milliseconds against a 20 s ceiling. Immaterial.

---

## Stage 5 — Grouping without moving files

`categories:` on each chapter index, plus one listing page over
`chapters/*/index.qmd` with `categories: true`, which Quarto renders as a
clickable filter.

```yaml
categories: [5 mm foam, full optimisation, unswept c₄, fuselage]
```

| where | change |
|---|---|
| six `index.qmd` | the categories themselves |
| the notebook root | a vocabulary data file |
| `nb/scaffold/` | a vocabulary template, so a new notebook starts with one |
| `nb/schema.py` | **a `Proposal` field for the categories** — `create_chapter` receives `chapter_title`, `chapter_defines` and `forked_from` today, and nothing else; without a field an agent has no way to assign any |
| `nb/vendor/lint.py` | categories ⊆ vocabulary, and the block survives a rewrite |

Click *full optimisation* → 05 and 06 sit together and it is obvious they are two
arms of one comparison. Click *5 mm foam* → 01, 02, 03, 06, and you can see 06
rejoining the line 04 left.

**Pros.** Multi-dimensional grouping that a directory tree cannot express, and
**without moving a single file** — which matters, because `chapters/<name>/` is
wired into the scaffold's numbering, several lint rules, `check`, and the freeze
paths. The lineage diagram would have shown immediately that 06 hangs off 05.

**Cons.** Free-text categories fragment: "5mm", "5 mm" and "5 mm foam" become
three tags and the grouping quietly stops working. **Categories need a
controlled vocabulary the agent picks from**, the way `Input.kind` is an enum
rather than a string. That is the difference between this working in six months
and rotting.

### How well does this take groupings nobody predicted?

Well, and one earlier decision is why.

Categories are a **flat, multi-valued tag list** — no hierarchy — so a new axis
is purely additive. Tag the chapters it applies to and the listing picks it up;
nothing existing moves, because there is no tree to restructure.

Retrofitting costs one frontmatter line per chapter. That edit invalidates the
chapter index's freeze and forces it to re-execute — which is cheap **only
because Stage 3 dropped the design visualisation.** With a three-view on each
index, every retagging would have cost six solves, and retagging would quietly
have stopped happening. Cheap indexes are what make emergent grouping viable.

**Assume retrofitting is the normal path.** Tags assigned when a chapter is
created are a guess: an agent writing chapter 07 cannot know which axis will
matter once chapter 11 exists. Groupings are recognised in hindsight and applied
backwards, so the design is optimised for that — flat tags, cheap index
re-render, and the vocabulary held as data.

**Where the vocabulary lives is the decision.** A controlled vocabulary stops
drift, but an enum inside `nb` makes every new term a change to the tool. Put it
in the NOTEBOOK — a small data file the linter checks chapter categories
against — and adding a term is one line in the notebook that owns the axes.
That keeps the drift protection without making the tool the bottleneck on a
notebook noticing something about itself.

**Open decision.** The starting axes are a claim about what this notebook is
exploring. Worth agreeing explicitly before writing them into a scaffold — but
they are a starting point, not a commitment.

---

## Stage 6 — `cite()`, and what it unlocks

A mechanism for one page to reference another page's computed value, with
invalidation.

Everything that was wanted in this discussion and deferred needs exactly this one
thing:

- a **state-of-the-design table** — one row per chapter, the headline numbers,
  each cell linked to the entry that established it;
- headline numbers in the Stage 3 chapter listings;
- any chapter **read-through** page;
- the dashboard and slide deck, both rejected below, would have needed it too.

**Pros.** It is the single unlock for every overview artifact, and it closes a
correctness hole that already exists — two standing lint warnings are
transcribed cross-chapter numbers that go stale silently when the cited chapter
re-renders.

**Cons.** It is the first **cross-chapter dependency** in a system that
deliberately has none. `forking.md` records that "`check`'s dependency graph is
intra-chapter today". Citing means `check` must know that editing chapter 04's
model invalidates a page in chapter 06 — a real extension to the verification
machinery, not a presentational change.

**Do not start here**, but do it before any further presentational work, because
three of the four things above are blocked on it.

---

## Rejected, and why

| proposal | why not |
|---|---|
| **Quarto dashboard** | Best technical fit for a state view, but creates the first cross-chapter dependency with nothing to invalidate it. Blocked on Stage 6 anyway. |
| **revealjs / PowerPoint** | Freeze is keyed per format (`execute-results/html.json`), so a second format means a second full execution of every page and a second freeze to keep honest. Slides are also *editorial* — choosing which 12 of 22 entries tell the story is judgement, not derivation. `pptx` additionally loses mermaid and produces a binary that cannot be diffed. |
| **Combining entries into one scrollable page** | Destroys the unit the system rests on: one entry = one page = one freeze = one question = one budget. `check` would lose per-entry granularity, the record would stop being append-only (every new entry *edits* a file), and rule 17's ceiling would have nothing to attach to. A *derived* read-through page is possible, but it re-executes everything it includes and needs Stage 6. |
| **Removing freeze in favour of agent-written caching** | Measured: solving is **1.7% of write-phase wall clock** (1.6 min of 95.6 min across 27 runs). Freeze is not a cache — it is `check`'s diff target, complete by construction, where a value cache is complete only where someone remembered. Invalidation is the hard part and this system has already been burned by it once. Above all, caching written by the agent is unchecked by construction: a wrong cache key produces a correct-looking page that passes everything, because the thing that would catch it is the thing the agent just wrote. Quarto's own cell `cache` is `engine: knitr` — unavailable to a Jupyter project; for this engine, **freeze is the cache**. |
| **Nesting chapter directories** | Would express one hierarchy at the cost of moving machinery wired to `chapters/<name>/`. Stage 3 gets multi-dimensional grouping for free. |
| **Two model assumption sets in one chapter** | `check` re-proves siblings when `_model.py` moves, rule 2 compares code across entries, and the refactor gate exists because "depends on this model" must be well defined. One chapter = one model is load-bearing, not stylistic. |
| **Wiki / graph tool / database with generated pages** | Each buys navigation by giving up the chronological append-only record, and would mean rebuilding the freeze/verify machinery that makes these numbers trustworthy. |

---

## Four surfaces, not one

Every stage has to land in up to five places. Retrofitting `glider-notebook`
fixes what exists; the other four decide whether the *next* notebook, chapter and
entry are born correct.

| stage | existing notebook | `nb new` scaffold | `create_chapter` | agent guidance | lint guard |
|---|---|---|---|---|---|
| **1** order, titles, breadcrumbs, toc | 6 × `index.qmd`, `_quarto.yml` | `_quarto.yml.tmpl`, `index.qmd.tmpl` | emit `order` + numbered title | — | index carries `order` matching its number |
| **2** book index | write `index.qmd` | **new template** + `new.py` writes it | delete `_freeze/index/` | — | a notebook has a root `index.qmd` |
| **3** chapter index | 6 × `index.qmd` | `index.qmd.tmpl` | lineage line from `forked_from` | — | the listing block survives a rewrite |
| **4** lead with the diagram | nothing | — | — | `schema.py`, `system_instruction.md` | — (guidance) |
| **5** grouping | 6 × `index.qmd`, vocabulary file | vocabulary template | assign categories | `Proposal` needs a field | categories ⊆ vocabulary |

### What that audit turned up

**`nb new` would keep producing the bug.** `nb/scaffold/_quarto.yml.tmpl` carries
the same `toc: true`, no `bread-crumbs`, and the same comment asserting that
"entry filenames start with their date, so alphabetical order is chronological
order" — true within a chapter, false across them, which is the Stage 1 finding.
Every new notebook is born with the scrambled sidebar. Stage 1 named
`_quarto.yml`; it meant both.

**Stage 2 had no scaffold story at all.** `nb new` writes `_quarto.yml`,
`styles.css`, `.gitignore`, the vendored files and a first chapter. There is no
root-index template, so without one added, `nb new` would go on making
notebooks with no front page while `glider-notebook` gained one.

**Stage 5 has no route to the agent.** `create_chapter` receives `chapter_title`,
`chapter_defines` and `forked_from` from the `Proposal`. Nothing carries
categories, so the schema needs a field before an agent can assign any — and its
description is where the vocabulary gets named.

**Anything scaffolded into an index needs a rule.** This is not speculative;
rule 30 exists because of it:

> "The scaffold ships that block; a model that rewrites index.qmd with
> `write_file` rather than editing it drops the block and nothing noticed,
> leaving a chapter whose aircraft appears nowhere."

`order:`, the lineage line, the listing block and the categories are all
scaffolded index content, and all decay the same way. Each wants a guard in the
same commit that introduces it — otherwise the first agent that rewrites an index
instead of editing it silently undoes the stage, and the sidebar goes back to
hash order with nothing to say so.

**This breaks the "no corpus movement" claim.** Those guards are new lint rules,
so `nb.corpus` WILL move for stages 1, 2, 3 and 5 — by however many existing
chapters fail the new rule at the moment it lands. Each has to be calibrated
across all three notebooks first, as every rule here has been, and the count
updated in the same commit.

---

## Order of work

1. **Stage 1** — config and scaffold. No decisions, no risk, fixes the daily
   irritation.
2. **Stage 2** — the book index and the lineage diagram. The site has no front
   page at all, so this is the largest gain per line, and the diagram depends on
   nothing else.
3. **Stage 3** — the chapter index: lineage sentence and entry listing.
4. **Stage 4** — lead with the diagram. Guidance only, and it changes how every
   future entry reads.
5. **Stage 5 vocabulary** — a conversation, then the categories.
6. **Stage 6** — `cite()`, then the headline numbers and the state table.

## Verification

- **`nb.corpus` moves for stages 1, 2, 3 and 5**, by the number of existing
  chapters failing each new guard. Calibrate every rule across all three
  notebooks before writing it — by hand it has got the wrong answer twice — and
  update the counts in the same commit. **Stage 4 must NOT move it**: the visual
  preference lives in a field description, not in `lint.py`.
- **Retrofit and scaffold in the same commit.** A stage applied to
  `glider-notebook` but not to `nb new` leaves the next notebook born with the
  defect, and nothing would fail to say so.
- **Stage 3 must NOT change render cost.** Nothing on the chapter index executes
  that did not already; if a render time moves, something is executing that
  should not be.
- **Stage 4 wants a read, not a test.** Take the next few entries and ask whether
  the visual carries the answer or decorates it. The old ordering was protecting
  against decoration, and the only evidence that the inversion is working is
  entries that would have been worse as prose.
- **Stage 6 needs a deliberate test**: change a cited chapter's model and prove
  the citing page is invalidated. Until that test passes, `cite()` is a
  transcription mechanism with extra steps.
- **Stage 2 needs its own invalidation test**: scaffold a seventh chapter and
  prove the book index re-renders with seven nodes. Until that passes, the
  diagram is a picture that was true once.
