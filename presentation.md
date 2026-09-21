# The notebook as a thing to look at

**Status: proposed, nothing implemented.** Measured on 2026-09-21 against
`glider-notebook` as it stands after `direction.md`'s Stages 1-7. Raised from
reading the rendered site rather than the code, which is why several of these
were invisible to every check that exists.

Six findings. Five are presentation; the sixth is a hole in the lineage diagram
that only shows up once you try to read it as a tree.

**One of these reverses a decision made two days ago.** `direction.md` Stage 6
derived the diagram's edge labels from the category delta and deleted the
`summary:` field that would otherwise have carried them, on the argument that a
vocabulary-controlled source cannot drift. Removing the categories removes that
source. The argument was sound and its premise is being withdrawn; `summary:`
comes back, and is now the *only* label source rather than the redundant one.

---

# What is actually wrong

## 1. Chapter 03's index is malformed, and nothing checks it

Section order across the six chapters:

```
01-foam-glider          Specified  Assumed  Questions  The model
02-fuselage-model       Specified  Assumed  Questions  The model
03-unswept-c4           Questions  The model  Specified  Assumed     ← odd one out
04-thinner-foam         Specified  Assumed  Questions  The model
05-fully-optimized      Specified  Assumed  Questions  The model
06-fully-optimized-5mm  Specified  Assumed  Questions  The model
```

The scaffold's order is the first one. 03 also has **no defining prose at all** —
every other chapter carries a sentence saying what it is ("Added a 200 mm
fuselage made of doubled-up 5 mm foam…"), and 03 goes from the fork line
straight to "Questions asked here".

That is exactly the failure rule 30 exists for, one field over: "a model that
rewrites index.qmd with `write_file` rather than editing it drops the block and
nothing noticed". Rules 30, 33, 34, 35 and 38 each guard one scaffolded *item*.
Nothing guards the **order**, and nothing guards that the prose is there at all.

It is also why the page looks wrong. The fork line renders into an empty page:
no prose under it, no callouts near it, nothing between it and a table of
questions.

## 2. The fork line renders as loose text

What Stage 6 emits, on a page with nothing else at the top:

```html
<p>Forked from <a href="../02-fuselage-model/">02 · Fuselage model</a>. What differs:</p>
<ul>
  <li>the tip leading edge moves aft by 0.25 * c_root * (1 - taper), so the
      QUARTER CHORD is unswept instead of the leading edge</li>
</ul>
```

Three separate problems:

- **No containment.** Every other structured thing on a chapter index is in a
  callout. This is a bare paragraph and a bare list, directly under the title.
  The version it replaced was one sentence, which read as a caption; a heading's
  worth of content with no heading reads as a mistake.
- **Raw expressions in prose.** `0.25 * c_root * (1 - taper)` is not marked as
  code, so it is one asterisk away from being parsed as emphasis and reads as
  prose rather than as the expression it is.
- **One bullet is not a list.** Three of the four forks declare one or two
  changes. A single-item bullet list is heavier than the sentence it replaced.

## 3. The numbered titles cost more than they buy

`01 · Foam glider` … `06 · Fully optimized 5 mm glider`, required by rule 33.
The rule's own argument: "a sidebar can be mis-sorted by a Quarto change or a
stray file; a title reading '04 · 3 mm foam' still tells a reader where they
are."

That was written when the sidebar WAS mis-sorted — readdir order, measured at
`03, 01, 06, 04, 02, 05`. `order:` fixed it and breadcrumbs now name the chapter
on every entry page. The number is insurance against a failure that has been
fixed twice over, and it is paid for in the narrowest column on the page.

Note the halves are separable: `order:` is load-bearing and stays. Only the
title prefix goes.

## 4. The sidebar is narrower than the titles it holds

`_quarto.yml` sets no `grid:` block, so the sidebar is Quarto's default and the
longest title — `06 · Fully optimized 5 mm glider` — wraps. Confirmed present in
the installed Quarto 1.8.27 schema:

```
format.html.grid.sidebar-width   "The base width of the sidebar (left) column"
format.html.grid.body-width      also available
```

## 5. The lineage diagram is two trees, and it does not say so

Every fork's parent, from `_fork.yml`:

```
01-foam-glider          (root)
02-fuselage-model    <- 01-foam-glider
03-unswept-c4        <- 02-fuselage-model
04-thinner-foam      <- 03-unswept-c4
05-fully-optimized      (root)          ← second root
06-fully-optimized-5mm <- 05-fully-optimized
```

**05 floats.** It is a root because its `_model.py` was rewritten rather than
copied — 84% similar to 01-04, below rule 31's 0.85 threshold, so rule 31
correctly does not demand a fork header. But the DESIGN descends from 04
directly: 04 is the 3 mm redesign, 05 opens that same design to the optimiser.

So the page that exists to answer "how do the chapters relate" shows half the
notebook detached from the other half. As a top-down graph of six nodes that
reads as two lists; as the sideways evolution tree it should be, it reads as
broken.

**`_fork.yml` records CODE provenance and the diagram wants DESIGN lineage.**
They coincide for a copied model and diverge for a rewritten one. Rule 31 should
go on using similarity to demand a declaration; the file should be allowed to
declare a parent the similarity check would not have found.

## 6. The labels are one word each, and the vocabulary that feeds them is going

Rendered today:

```
01 -->|"fuselage"|               02
02 -->|"unswept quarter chord"|  03
03 -->|"3 mm foam"|              04
05 -->|"5 mm foam"|              06
```

Each is the category delta — which by construction is exactly one vocabulary
term, because `_categories.yml` says "each chapter keeps what its parent
modelled and adds one thing". Correct, derived, undriftable, and thinner than
what the chapter actually did. `_fork.yml`'s `changes:` has the substance and is
far too long for an edge:

> "the tip leading edge moves aft by 0.25 * c_root * (1 - taper), so the QUARTER
> CHORD is unswept instead of the leading edge"

And the source is being withdrawn: with the categories gone there is no delta to
derive from. Rule 31c — "a fork's categories differ from its parent's" — goes
with them, since it has nothing left to compare.

---

# Stage 1 — Guard the shape of a chapter index

Before anything cosmetic, because 03 is the reason the page looks wrong and
because every stage below edits these files.

| change | where |
|---|---|
| fix 03: restore the defining prose, put the sections in scaffold order | `03-unswept-c4/index.qmd` |
| rule 39: a chapter index's sections are in the scaffold's order | `nb/vendor/lint.py` |
| rule 39b: a chapter index carries defining prose, not just callouts | same |
| recalibrate | `nb/corpus.py` |

The scaffold order is **Specified → Assumed → Questions asked here → The
model**, and the fork line and prose sit above all of it. That is an argument
about reading: what the chapter IS, then what was given and guessed, then what
was asked of it, then the code.

**Pros.** Turns "the page looks wrong" into something a rule states. Rules 30,
33, 34, 35 and 38 each guard one scaffolded item and this is the same class of
failure — an agent rewriting the page instead of editing it.

**Cons.** Section order is a convention, and a rule that enforces it forecloses a
chapter with a genuine reason to differ. None of the six has one.

**Risk.** `nb.corpus` moves by the chapters that fail — one today, and it must be
fixed in the same commit that adds the rule. Calibrate across all three
notebooks first: `aircraft-notebook`'s two undeclared chapters have no callouts
at all and must not start failing for it.

---

# Stage 2 — Make the fork line look like the rest of the page

| change | where |
|---|---|
| wrap it in a callout, in the scaffold and all six chapters | `index.qmd.tmpl`, 6 × `index.qmd` |
| one change renders as a sentence, two or more as a list | same generated block |
| back-tick expressions in `changes:` | 4 × `_fork.yml` |

Shape: a `callout-note` titled "Forked from 02 · Fuselage model", body being the
changes. It then matches Specified and Assumed, which are the two things it sits
next to, and the page stops having one un-styled region.

**Pros.** Consistency is the whole of it. A chapter index becomes four callouts
and two listings, in one order, on every chapter.

**Cons.** Another collapsed-by-default box is another thing to open. It should be
open by default, unlike the model source below it.

**Risk.** Every chapter index re-renders. That is 6 pages of print-and-exec with
no solve — the same cost Stage 6 of `direction.md` measured at a few seconds —
and `freezediff` must report only those six index pages moving.

---

# Stage 3 — Drop the numbers, widen the sidebar

| change | where |
|---|---|
| remove the title-prefix half of rule 33, keep `order:` | `nb/vendor/lint.py:1964` |
| unnumber the six titles | 6 × `index.qmd` |
| stop `create_chapter` writing the prefix | `nb/tools/scaffold.py` |
| `grid: sidebar-width:` | `_quarto.yml`, `_quarto.yml.tmpl` |

Width wants choosing against the longest title once the numbers are gone —
"Fully optimized 5 mm glider" — rather than picked round. 300px is the usual
first try against a 250px default.

**Pros.** The sidebar is the one part of the site present on every page, and it
is currently the most cramped. Removing four characters from every entry in it
and widening the column attacks the same problem twice.

**Cons.** A reader loses the sequence at a glance in the sidebar. Breadcrumbs,
`order:` and the front page's tree all still carry it, and the tree carries it
better than a number does.

**Risk.** Low, and `nb.corpus` does not move: rule 33's title check currently
fires zero times, so removing it changes no count. Every chapter index
re-renders again, which is why this should land in one commit with Stage 2
rather than re-rendering the same six pages twice.

---

# Stage 4 — A sideways evolution tree

| change | where |
|---|---|
| `graph LR` | root `index.qmd`, `book-index.qmd.tmpl` |
| `summary:` in `_fork.yml`, 3-6 words, hand-written | 4 × `_fork.yml`, `scaffold.py` |
| label edges from `summary:`, not from categories | the generated block |
| allow a declared parent the similarity check would not find | rule 31 |
| declare 04 → 05 | `05-fully-optimized/_fork.yml` |

**`LR` is the shape the content already has.** Two chains of three, read left to
right as time. Top-down stacks them into two columns and wastes the width the
page has.

**`summary:` comes back, and this time it is the only source.** Stage 6 deleted
it because the category delta was derived and therefore could not drift — a good
argument whose premise Stage 5 below removes. What replaces it is a hand-written
3-6 words, checked by rule 31 for presence and length only. That is weaker, and
it is the trade: a label nobody can derive is a label somebody must write.

Not `changes:`, which is at code granularity and 120 characters long. The two
fields are different lengths for different readers, which is why an earlier
draft had both.

**05 gets a parent.** `_fork.yml` currently means "this file was copied from
there"; it should mean "this design came from there", with copying as the
common case. Rule 31 keeps using similarity to DEMAND a declaration — a copied
model that says nothing is still a finding — but stops treating a declared
parent below the threshold as a mistake. Without that, the tree has a floating
root and the notebook reads as two unrelated projects.

**Pros.** The diagram becomes the thing the front page promises. The 04 → 05 edge
is the single most informative line on the page and it is currently absent.

**Cons.** Hand-written labels can go stale, which is precisely what Stage 6
argued against. Mitigated only by being short and by sitting in the same file as
the `changes:` list that would contradict them.

**Risk.** Rule 31's parent check has to be loosened carefully: "declared parent
need not be the most similar" must not become "declared parent is never
checked". A parent that does not exist, or is a later chapter, is still wrong.

---

# Stage 5 — Retire the categories

Last, because Stage 4 must already have a label source that does not depend on
them.

| change | where |
|---|---|
| drop the categories column and margin filter | root `index.qmd`, `book-index.qmd.tmpl` |
| delete rule 36 and rule 31c | `nb/vendor/lint.py` |
| delete `_categories.yml` and its template | notebook, `nb/scaffold/` |
| drop `chapter_categories` | `nb/schema.py`, `write.py`, `scaffold.py` |
| stop writing `categories:` into an index | `scaffold.py`, `index.qmd.tmpl` |

**What is actually lost.** Filtering six chapters by one of three axes. The
margin filter is the only interactive element on the front page, and the thing
it filters is a six-row table that fits on one screen above it.

**What is kept.** The per-chapter question listing on every chapter index, and
Quarto's site-wide search in the sidebar — which is what actually finds an
entry, and is unaffected. (Worth knowing: there is no per-chapter search box
today. Those listings set `filter-ui: false` deliberately — "a filter over three
rows is furniture". If a per-chapter filter is wanted, that is a separate change
from this one.)

**Pros.** Deletes a vocabulary file, two lint rules, a schema field, a scaffold
substitution and a column — to lose a filter over six rows. The axes it encodes
survive in the tree, which shows them as transitions rather than tags.

**Cons.** The 2×2 that `navigation.md` §3 identified — material against method —
is genuinely not expressible in a tree, and the categories were the answer to
it. That structure will be legible only from reading the chapter titles.

**Risk.** `nb.corpus` should not move: rule 36 fires zero times across all three
notebooks today, so deleting it changes no count. Rule 31c likewise. If either
moves, something else was depending on them.

---

# Order of work

1. **Stage 1 — index shape.** Fix 03 first; it is why the page looks broken, and
   every later stage edits these files.
2. **Stages 2 and 3 together — fork callout, titles, sidebar.** One commit, so
   the six chapter indexes re-render once rather than twice.
3. **Stage 4 — the tree.** After `summary:` exists; before the categories go, so
   the diagram never has no label source.
4. **Stage 5 — retire the categories.** Last, and it should be uneventful by
   then.

# Verification

- **`nb.corpus` moves only for Stage 1**, by the chapters failing the new shape
  rules — one today. Stages 3 and 5 remove checks that currently fire zero
  times and must not move it at all.
- **`freezediff` after Stages 1-3 reports index pages only.** No entry, no
  figure. A moved entry value means something structural was changed by
  accident.
- **The tree renders with one root.** Six nodes, five edges, every edge labelled,
  and 05 reachable from 01. Two roots means the 04 → 05 declaration did not take.
- **Rule 31 still demands a declaration** from a copied model after the parent
  check is loosened. Delete a `_fork.yml` and confirm it fires.
- **Every chapter index has the same shape** after Stage 1: read all six as a
  reader, not as a diff.
- **The longest title fits the sidebar without wrapping**, at the width chosen,
  in a browser and not by arithmetic.
- **`nb new` produces all of it.** Scaffold a throwaway notebook and confirm its
  front page and first chapter are born in the new shape — every stage here
  touches a template, and a notebook born in the old shape fails the new rules.

# Out of scope

- **A per-chapter question filter.** Those listings disable it deliberately;
  adding one is a separate decision from removing the chapter-level one.
- **Restoring the 2×2 view** the categories gave. Worth its own conversation if
  it turns out to be missed.
- **Re-deriving edge labels.** Stage 4 accepts hand-written ones with the
  trade stated. If they drift, the answer is a rule that checks `summary:`
  against `changes:`, not a return to categories.
