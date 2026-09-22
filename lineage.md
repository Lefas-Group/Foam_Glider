# The lineage diagram, with entries in it

**Status: proposed.** The design is settled — drafted outside the notebook over
a dozen renders and picked from a comparison page. What is not settled is the
plumbing, which is what this is about: the diagram is about to depend on
something that changes every time an entry is committed, and nothing currently
notices.

The picture: each chapter is a box carrying the change that produced it, with a
tick per entry running down from it. A fork puts the child on the **same rank**
as the tick it was taken from, so the arrow is horizontal and every chapter's
line starts level with the entry it came from. That makes y an axis — how far
down two lines reach is directly comparable, and the lowest tick on the page is
the most recent work.

---

# What it needs, and where each part comes from

| what the diagram needs | where it comes from | self-managing? |
|---|---|---|
| the chapters | `chapters/*/` | yes |
| each chapter's label | `_fork.yml`'s `summary:` | yes, written at fork |
| the parent | `_fork.yml`'s `parent:` | yes, written at fork |
| **entries per chapter** | count `20*.qmd` in the chapter | **yes, derived** |
| **the fork point** | nothing records it | **no — this is the gap** |

Two of these are new, and they behave very differently.

## Entries per chapter: derived, and therefore free

`len(notebook.entries(chapter))` already exists and already counts exactly the
files a chapter's listing shows. Nothing to record, nothing to keep in step: add
an entry and the chapter grows a tick.

## The fork point: has to be recorded, at the moment it is known

"How many entries had the parent written when this chapter was taken" cannot be
reconstructed afterwards. The drafts guessed it from filename dates against the
fork commit's date, which is day-granular — that is why the draft claims 04 was
forked after **one** entry of 03, drawn as a single tick, and it is the number
I trust least on the whole picture.

`create_chapter` knows it exactly, because it runs at the moment of the fork and
already has the notebook in hand:

```yaml
parent: 03-unswept-c4
at: 12794f6
at_entry: 3          # len(notebook.entries(fork_from)), written here
summary: "Changed to 3 mm foam."
```

One line, right by construction, and rule 31 requires it the way it already
requires `parent`, `at` and `summary`. **The archaeology only gets harder**, so
this is worth doing whether or not the diagram ships.

---

# The trap: the diagram will go stale and nothing will say so

The root `index.qmd` belongs to no chapter, so **rule 12 cannot protect it** —
that is already written in the generated block's own comment, and it is why
`create_chapter` deletes `_freeze/index/` when it scaffolds a chapter.

Today the diagram depends only on `_fork.yml`, which changes when a chapter is
created. That is exactly the case already covered. **Entry counts are a new
dependency, and they change on every entry commit** — which nothing invalidates:

```
write.py:244   deletes  _freeze/<chapter>/index   when _model.py moved
scaffold.py:282 deletes _freeze/index             when a chapter is scaffolded
                        _freeze/index             on an entry commit — NOTHING
```

So: commit an entry, and the front page goes on serving a diagram with the old
tick count, from its own freeze, silently. That is the failure rule 12 exists to
prevent, one level up, for the second time.

There is a second half to it. `write.py` commits the entry's freeze and the
chapter index's freeze, and **never the root index's** — so even once it is
rebuilt, the picture in git does not match the entries in git. That gap exists
today and is invisible only because nothing on the front page depends on entry
counts yet.

| change | where |
|---|---|
| delete `_freeze/index/` when an entry is committed | `write.py`, beside `_refresh_index_freeze` |
| add the root index freeze to the commit | `write.py`'s `_commit_paths` |
| rule 40: the root index freeze is not older than the entries it counts | `nb/vendor/lint.py` |

The rule is the part that makes it self-managing rather than remembered. It is
rule 12's argument — "the freeze is not older than the model that froze it" —
applied to the one page rule 12 cannot see, and it is cheap: compare the mtime
of `_freeze/index/` against the newest entry file.

---

# Stage 1 — Record the fork point

| change | where |
|---|---|
| write `at_entry:` when forking | `create_chapter`, `nb/tools/scaffold.py` |
| require it | rule 31, `nb/vendor/lint.py` |
| backfill the five existing forks, marked as reconstructed | 5 × `_fork.yml` |
| template | `nb/scaffold/` |

The backfill is a guess and should say so in the file, because a number that
was measured and a number that was inferred are different things and only one
of them is worth trusting:

```yaml
at_entry: 3          # reconstructed from dates; forks after this are exact
```

**Risk.** `nb.corpus` moves by the forks failing the new rule 31 — all five
until backfilled, so backfill and rule land in the same commit.

---

# Stage 2 — The generator

| change | where |
|---|---|
| emit the new `dot` block | root `index.qmd`, `book-index.qmd.tmpl` |
| entry counts from `notebook.entries`-equivalent | the same block, reading `chapters/*/20*.qmd` |

Settled parameters, from the drafts:

```
splines=spline · nodesep=0.22 · ranksep="0.05 equally"
node  height=0.22 margin="0.2,0.03" penwidth=1.4
ink   border #495057 · text #212529 · line #495057
tick  shape=point width=0.06
fork  {rank=same; tick; child} + constraint=false
side  alternates by generation, via declaration order
```

Three of those are not preferences and should not be tuned casually:

- **`ranksep="... equally"`** is what makes a chapter's ticks evenly spaced. A
  rank is as tall as the tallest thing in it, so without `equally` a rank
  holding some other chapter's box stretched one chapter's entry spacing
  through no fault of its own.
- **Box height IS the entry spacing**, as a consequence: `equally` makes every
  rank as tall as the tallest thing in ANY rank, and that is a box. Shrinking
  the gap means shrinking the boxes.
- **Declaration order is the only lever on which side a fork lands.**
  `dir=back` does nothing (`constraint=false` removes the edge from ordering),
  `ordering=out` only sorts a node's own out-edges, and dropping `group` and
  `weight` changes nothing. Reversing declaration order mirrors the whole tree,
  so the side is chosen here, not by dot.

**`group` and `weight` are dropped.** Measured: the chains come out vertical
without them, because a straight line is already the minimum-length layout for
a chain — they were enforcing something that was going to happen anyway.

**Risk.** The diagram gets wider as chapters are added, and the width is boxes
sharing a rank — a direct consequence of putting each child level with its fork
tick, which is what makes y an axis. Measured on a lineage with two branches:
1310px full labels, 1013px with labels cut to 14 characters. **The levers are
shorter labels and `nodesep`, not spacing.** Going back to children a rank below
their fork point would narrow it and lose the axis.

---

# Stage 3 — Keep it honest

| change | where |
|---|---|
| delete `_freeze/index/` on an entry commit | `nb/phases/write.py` |
| commit the root index freeze | `_commit_paths` |
| rule 40: root index freeze newer than the entries it counts | `nb/vendor/lint.py` |

**Pros.** Without this the front page is wrong after the first entry and says
nothing about it. With it, the diagram manages itself: an entry is committed,
the freeze goes, the next render redraws, and a rule catches it if either step
is skipped.

**Cons.** Every entry commit now re-executes the root index. It is cheap — the
page reads source and executes no chapter model, which is the property the
generated block was written to preserve — but it is no longer free.

**Risk.** The ordering inside `write.py` matters. `site()` runs AFTER the
commit, so a freeze deleted before the commit is rebuilt after it and left
dirty unless `_commit_paths` picks it up. That is the state a new-chapter run
leaves today, unnoticed because nothing checks it.

---

# Order of work

1. **Stage 1 — record the fork point.** Independent, and the value decays: every
   fork taken before it lands is another one reconstructed from dates.
2. **Stage 3 — the freeze plumbing.** Before the generator, so the first render
   of the new diagram is already being kept current. Landing it after would mean
   a window where the front page is silently stale.
3. **Stage 2 — the generator.** Last, and it is the only one with a visible
   result.

# Verification

- **`nb.corpus` moves once**, for rule 31's new `at_entry` requirement, by the
  five existing forks. Rule 40 must not move it: the root index freeze is
  current today.
- **Add an entry and the diagram grows a tick**, without anyone touching the
  front page. This is the whole claim of "self-managing" and is one run to test.
- **Commit an entry, then check `git status`.** The root index freeze must be in
  the commit, not left dirty in the tree.
- **Rule 40 fires** on a root index freeze older than the newest entry — break
  it deliberately by touching an entry file.
- **`create_chapter` writes a correct `at_entry`.** Scaffold a chapter in a
  throwaway notebook that has entries, and confirm the number matches what the
  parent actually holds.
- **`nb new` produces the new front page**, diagram and all, and lints clean on
  arrival — every stage here touches a template.
- **One render at the end**, not one per stage.

# Out of scope

- **A diagonal entry chain.** Probed and abandoned: dot has no lever for a
  controlled diagonal, and forcing one with invisible padding distorts the
  layout without buying width back.
- **Reconstructing exact fork points for the five existing chapters.** The
  filename dates are day-granular and several chapters have multiple entries per
  day. Backfill the best guess, mark it as one, and let the recorded numbers
  accumulate from here.
- **Entry labels on the ticks.** A tick is a click target away from being a link
  to its entry, which is tempting and is a different diagram.
