# Navigating a notebook that fans out

**Status: plan, not implemented.**

The notebook is a DAG of design decisions presented as a numbered list. Six
chapters, twenty-two entries, and no way to see how any of it relates. This plan
fixes navigation in four stages, cheapest and most certain first.

In one paragraph: **the format is right and the front door is missing.** A
Quarto website is the correct home for an append-only record — chronological,
verifiable, superseded rather than edited — but it answers only "what happened,
in order?" and never "what is the design now, and how do these chapters
relate?". Everything below adds the second view without weakening the first.

---

## What is actually wrong, with evidence

### 1. The sidebar order is filesystem order

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

### 2. Chapter order is chronological; the design relationships are not

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

### 3. The chapter index does not orient you

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

### 4. Half the chapters never show you the aircraft

The three-view is drawn in four entries across three chapters — 01, 02 and 05.
**Chapters 03, 04 and 06 have no picture at all.** Whether you can see the
aeroplane depends on whether someone happened to ask.

### 5. Cross-chapter numbers are hand-typed

Chapter 06's prose says "barely an improvement over the 0.400 m/s achieved by the
manually sized 5 mm model". That 0.400 is transcribed. It is one of the two
standing lint warnings (`old_sink = 0.36` is the other).

**Navigation and correctness are the same problem here.** Entries fan out
because they compare against each other; comparison needs citation; without
citation you get transcription; transcription is what the linter flags.

---

## Stage 1 — Ordering and orientation

Config and scaffold only. No new mechanism, no render cost, nothing to decide.

| change | where |
|---|---|
| `order: <n>` in every chapter `index.qmd` | six files + `create_chapter` |
| numbered titles — `"04 · 3 mm foam"` | same |
| `bread-crumbs: true` | `_quarto.yml` |

`order` and `bread-crumbs` are both confirmed present in the installed Quarto
1.8.27 schema:

```
order        number   "Order for document when included in a website automatic sidebar menu"
bread-crumbs boolean  "show navigation breadcrumbs for pages more than 1 level deep"
```

Entries live at `chapters/<chapter>/<entry>.qmd` — two levels deep, so they
qualify for breadcrumbs, and every entry page would carry
`Chapters › 3 mm foam › How stable is the glider to perturbations?`.

**Pros.** Fixes the sidebar, fixes next/previous, and answers "where am I?" —
the question hit twenty times a session. Numbered titles make the sequence
legible in the text, so a mis-sorted sidebar is still readable. The fix belongs
in `create_chapter`, which already allocates the number, so it cannot recur.

**Cons.** Sequence is the wrong shape for 06, which is a sibling of 05 rather
than its successor. Numbering makes that exception *visible* rather than hiding
it in noise, but does not express it — Stage 3 does.

**Risk: none.** No execution changes, so no freeze is touched.

---

## Stage 2 — The chapter index as a front door

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

### The visualisation

Show **the chapter's own model, optimised** — not "the latest entry's design".

> **Entries are not iterations.** Most are checks or excursions. "What is the
> penalty for constraining the wings to sweep backwards?" is a what-if, not a
> new baseline. "The latest design in this chapter" is undefined, and picking
> the most recent entry would sometimes present a deliberately hobbled variant
> as the design. What *is* well defined is the chapter's model, optimised —
> which is exactly what a chapter is.

**Pros.** Needs no new mechanism: the index already execs `_model.py` and
`_analysis.py` via `_model.qmd`, so `optimize_full_glider()` and
`make_full_glider(...)` are in scope. Purely intra-chapter, so no `cite()`
problem, and rule 12 already covers staleness. It makes the notebook consistent
— every chapter shows its aircraft — and future chapters no longer spend an
entry on "what does it look like". Side effect: the index and the establishing
entry run the same code, so a disagreement means one of the two freezes is
stale. A passive staleness detector, free.

**Cons, and this is the real cost.** **Index pages carry no `footer()`** — all
six checked. No runtime line, no solve count, therefore no budget and nothing
rule 17 can measure. Today they are nearly free; after this each costs a solve,
unbudgeted. The index would want its own `ENTRY_CEILING` and a `footer()`, or it
becomes the one page in the system that can get slow without anyone noticing.

**Defect to fix first.** **Chapter 05's index has no freeze** — the only one of
six missing. It therefore re-executes on every render today, and after this
change it would pay a solve every single time. Worth understanding before adding
cost to it: likely a render that was interrupted, or a `check` that deleted the
freeze and never re-rendered.

**What is deliberately left out.** The headline number per entry in the listing.
A listing can only show static frontmatter, so "0.399 m/s" beside each question
would be transcription — the failure already flagged twice. That needs Stage 4.

---

## Stage 3 — Grouping without moving files

`categories:` on each chapter index, plus one listing page over
`chapters/*/index.qmd` with `categories: true`, which Quarto renders as a
clickable filter.

```yaml
categories: [5 mm foam, full optimisation, unswept c₄, fuselage]
```

Click *full optimisation* → 05 and 06 sit together and it is obvious they are two
arms of one comparison. Click *5 mm foam* → 01, 02, 03, 06, and you can see 06
rejoining the line 04 left.

Plus a **lineage diagram** on the book index. Quarto renders mermaid natively and
the data already exists — `lint.model_kinship()` parses the fork headers for rule
31 and throws the result away.

**Pros.** Multi-dimensional grouping that a directory tree cannot express, and
**without moving a single file** — which matters, because `chapters/<name>/` is
wired into the scaffold's numbering, several lint rules, `check`, and the freeze
paths. The lineage diagram would have shown immediately that 06 hangs off 05.

**Cons.** Free-text categories fragment: "5mm", "5 mm" and "5 mm foam" become
three tags and the grouping quietly stops working. **Categories need a
controlled vocabulary the agent picks from**, the way `Input.kind` is an enum
rather than a string. That is the difference between this working in six months
and rotting.

**Open decision.** The axes are a claim about what this notebook is exploring.
Worth agreeing explicitly before writing them into a scaffold.

---

## Stage 4 — `cite()`, and what it unlocks

A mechanism for one page to reference another page's computed value, with
invalidation.

Everything that was wanted in this discussion and deferred needs exactly this one
thing:

- a **state-of-the-design table** — one row per chapter, the headline numbers,
  each cell linked to the entry that established it;
- headline numbers in the Stage 2 chapter listings;
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
| **Quarto dashboard** | Best technical fit for a state view, but creates the first cross-chapter dependency with nothing to invalidate it. Blocked on Stage 4 anyway. |
| **revealjs / PowerPoint** | Freeze is keyed per format (`execute-results/html.json`), so a second format means a second full execution of every page and a second freeze to keep honest. Slides are also *editorial* — choosing which 12 of 22 entries tell the story is judgement, not derivation. `pptx` additionally loses mermaid and produces a binary that cannot be diffed. |
| **Combining entries into one scrollable page** | Destroys the unit the system rests on: one entry = one page = one freeze = one question = one budget. `check` would lose per-entry granularity, the record would stop being append-only (every new entry *edits* a file), and rule 17's ceiling would have nothing to attach to. A *derived* read-through page is possible, but it re-executes everything it includes and needs Stage 4. |
| **Removing freeze in favour of agent-written caching** | Measured: solving is **1.7% of write-phase wall clock** (1.6 min of 95.6 min across 27 runs). Freeze is not a cache — it is `check`'s diff target, complete by construction, where a value cache is complete only where someone remembered. Invalidation is the hard part and this system has already been burned by it once. Above all, caching written by the agent is unchecked by construction: a wrong cache key produces a correct-looking page that passes everything, because the thing that would catch it is the thing the agent just wrote. Quarto's own cell `cache` is `engine: knitr` — unavailable to a Jupyter project; for this engine, **freeze is the cache**. |
| **Nesting chapter directories** | Would express one hierarchy at the cost of moving machinery wired to `chapters/<name>/`. Stage 3 gets multi-dimensional grouping for free. |
| **Two model assumption sets in one chapter** | `check` re-proves siblings when `_model.py` moves, rule 2 compares code across entries, and the refactor gate exists because "depends on this model" must be well defined. One chapter = one model is load-bearing, not stylistic. |
| **Wiki / graph tool / database with generated pages** | Each buys navigation by giving up the chronological append-only record, and would mean rebuilding the freeze/verify machinery that makes these numbers trustworthy. |

---

## Order of work

1. **Stage 1** — config and scaffold. No decisions, no risk, fixes the daily
   irritation.
2. **Investigate chapter 05's missing index freeze** — small, and Stage 2 adds
   cost to exactly that page.
3. **Stage 2** — chapter index, with `footer()` and a ceiling for index pages.
4. **Stage 3 vocabulary** — a conversation, then the categories and the lineage
   diagram.
5. **Stage 4** — `cite()`, then revisit the state table.

## Verification

- **Stages 1–3 must not move `nb.corpus`.** None of them touch a lint rule; a
  changed count means something unintended.
- **Stage 2 will change render cost.** Record the before and after per chapter
  index, and give the page a ceiling rather than discovering the cost later.
- **`check` must stay clean across Stage 2.** The index and the establishing
  entry solve the same model; if their numbers disagree, a freeze is stale and
  that is a finding, not noise.
- **Stage 4 needs a deliberate test**: change a cited chapter's model and prove
  the citing page is invalidated. Until that test passes, `cite()` is a
  transcription mechanism with extra steps.
