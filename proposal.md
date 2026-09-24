# Removing the proposal

**Status: IMPLEMENTED, 2026-09-23.** Done in one, as planned. What landed
differed from this document in four places, each noted inline below:

1. **The `overwrites:` check already existed.** `lint._departure_targets` is
   "rule 31, second half" and already refused a row that names no real item.
   What was missing was the MESSAGE for the one case that matters — a row
   naming the notebook — so that is what changed, rather than a second check
   beside the first.
2. **The inherited gate was broken more widely than described.** It runs before
   `create_chapter`, so `chapters/<new>/_fork.yml` does not exist yet and
   `ancestry()` returned empty for EVERY new chapter, fork or not — the
   notebook-brief fallback was doing the work of the lookup, silently and
   always. `inputs.ancestry(notebook, chapter, parent)` now seeds the walk from
   the declared parent, and a strike resolves to a real `(chapter, id)`, which
   it never did before.
3. **The turn budget became one pool.** `MAX_TURNS` each side of a boundary
   that no longer exists would have silently doubled it, so `loop_once` counts
   model turns and draws them down across probing and writing alike.
4. **`session.phase` went with the split**, and nothing read it any more, so
   `build(session, fs)` and `setup(session)` lost their `phase` parameter too.

Supersedes the staged version and `merged.md`, both of which hedged toward doing
this in four steps with a flag.

`propose` is not mainly a document. It is the single point where a run commits
to a chapter, a title and a set of inputs, and it enforces four refusals there.
Removing it means re-homing those, not deleting them — which is most of what
follows.

---

# What goes

| piece | where |
|---|---|
| `Proposal`, 15 fields | `schema.py` |
| the `propose` declaration | **6,676 of 15,053 chars — 44% of the whole tool surface** |
| `Terminal`, carrying the payload out of the loop | `loop.py` |
| `proposal.json`, `persist()`, `_seal()` | `interact.py`, `write.py` |
| nine private `_` fields | `_pool_left`, `_pool_total`, `_render_ceiling`, `_corrections`, `_inherited`, `_struck`, `_replaces`, `_assumptions_confirmed`, `committed` |
| `render_stop()`, and the `return 0` that ends `ask` | `interact.py`, `ask.py` |
| `PHASE_OMITS` — there are no phases | `tools/__init__.py` |
| the ask/write split itself | `phases/` |

## The evidence

Across the ten runs still on disk:

```
7 of 10   ask -> write in ONE process
3 of 10   crossed a process boundary
```

Every one of those three crossed it because **the system deliberately stopped** —
a new chapter, a refactor — never because anything crashed. In the other seven
`proposal.json` was written to disk and read back **in the same process,
milliseconds later**.

**What the stop costs**, from the X-Wing run: ask ended ~14:41, write began
**14:46:36**. Five minutes of human round-trip on a run whose compute was
sixteen — plus four failed pastes of `continue uv run …`, which is what prompted
the output fix that went in beside this.

---

# The replacement: three tools

```
open_chapter(chapter, title?, defines?, forked_from?)
declare_input(name, value, source, why)
open_entry(title)
```

## `open_chapter` — routing, settled when the model decides it

| it does | which today is |
|---|---|
| refuses a chapter other than `--chapter` | `propose`'s pin check |
| refuses filling a claimable stub without `title`+`defines` | `propose`'s stub check |
| creates or claims the chapter from `title`/`defines`/`forked_from` | `write.main`'s `create_chapter` |
| asks the new-chapter approval, **`default=None`** | the `return 0` stop |
| runs the inheritance review | `confirm_inherited` |
| claims the chapter lock | `write.main`'s `claim_chapter` |
| returns the scaffolder's message | `chapter_msg`, injected as a user turn |

For an existing chapter it only pins and locks.

**`create_chapter` stays out of the model's hands.** `open_chapter` is a
declaration of intent that the system acts on — the distinction
`tools/__init__.py` already draws, and the reason `create_chapter` was never a
tool: "a tool that could only ever return `rejected: already exists`, and
ownership ambiguous on the one path that is structurally irreversible."

**`default=None` is the whole safety of the approval.** A defaulted question
takes its default after `DEFAULTED_WAIT` and carries on; an undefaulted one
waits the full hour and then raises `SystemExit` with the question on disk —
*which is exactly today's behaviour*. Walk away, get today's outcome. Be at the
keyboard, pay one keystroke instead of a second command.

## `declare_input` — recorded when assumed, not collected at the end

Mirrors `ask_specified`: called the moment the model assumes or decides
something, rather than filled into a field afterwards.

This targets something measured: **four of eight recorded runs proposed no
inputs at all**, which is what a list you complete last looks like. The same
argument already justifies `ask_specified` firing immediately — "a static margin
discovered at turn 3 should not be guessed for twenty more turns".

It **records**; it does not ask. The batched confirmation survives at
`open_entry`, because the reason for batching was about asking: per-assumption
*asking* "makes the model judge which of its assumptions are load-bearing".

## `open_entry` — the transition, and the only hard gate

The one call that says *probing is over, this is the question*.

| it does | which today is |
|---|---|
| holds the title to rule 26 before it becomes a filename | lint, after the fact |
| refuses no inputs with nothing said about it | `propose`'s empty-inputs refusal |
| refuses `source: asked` never put through `ask_specified` | `propose`'s `unasked` check |
| runs `confirm_assumptions`, corrections and all | the gate, after `propose` |
| freezes `render_cost_s` from measured solve seconds | `propose`, L72 |
| allocates the stem and **returns the path to write** | `_stem` |
| injects the write brief as a user turn | `write.main`'s `BRIEF` |

Returning the path is what keeps the `YYYY-MM-DD-NN-slug` convention without a
filename protocol: the model does not choose it, it is told it.

## The loop already ends correctly

`loop.run` returns as soon as a turn calls no tool (`loop.py:161`). A run that
stops before `open_entry` is `no_entry` — the same outcome shape as today's
`no_proposal`, and with the same message.

---

# A path allowlist on the write tools

An earlier draft gated tool AVAILABILITY on run state — `write_file` absent
until an entry was open. That was wrong twice, and the reasoning is worth
keeping so it is not re-proposed.

**It would not have caught the failure it was written for.** The
`test.py`/`test2.py`/`test3.py` mess happened *after* the entry was open, so a
state gate would have let every one of those writes through. The gate is about
WHEN you may write; the failure was about WHAT.

**And it breaks caching.** Tools render at prefix position 0 —
`tools/__init__.py` sorts them because "an unsorted merge silently breaks the
byte-prefix match that caching depends on". Changing the list at a transition
changes the prefix, so implicit caching resets at every one: in a 25-turn
conversation at a measured 67% hit rate, that is re-paying full rate for the
whole accumulated history, twice, to save a few hundred tokens.

The right shape already exists. `guards.wrap_writes` refuses `_model.py` in an
established chapter by leaving the tool DECLARED and refusing in the HANDLER —
cache-safe by construction, and the model reads the refusal and adapts. Its own
docstring makes the argument: "do not predict -- refuse at the boundary."

| change | where |
|---|---|
| refuse a write outside the chapter's own files | `guards.py`, beside the `_model.py` guard |
| refuse any write before `open_chapter` | the same guard |
| the refusal names `probe` as the place to run code | the same message |

Allowed: the entry being written, `_model.py`, `_analysis.py`, `_inputs.yml`,
`index.qmd`, `_fork.yml`. Nothing else.

**The premise behind the state machine was weak anyway.** `write_file` is
available in the ask phase today and the ask half has NEVER written a file —
zero calls across every retained transcript, with only the brief saying "Write
nothing into the notebook in this phase."

---

# What carries the state

`run.json`, which already exists, is already written atomically with
`os.replace`, already survives the process, and is already read by `nb board`,
`nb answer` and `nb clean`. It gains three fields:

```json
{"chapter": "04-thinner-foam", "stem": "2026-09-23-01-…",
 "pool_left": 51.0, "ceiling": 80.0}
```

That is the whole of crash recovery. `nb resume` re-enters with the entry on
disk and `is_clean` short-circuits the loop exactly as it does for
`--accept-refactor` today — "a resumed run often has nothing for the model to
do… and the loop ran anyway, costing 16 turns" — and every gate downstream still
runs.

**What is lost: a resumed run has no conversation.** Today it rebuilds a brief
from the proposal; after, it gets the write brief plus "the entry is at `<path>`,
lint says X, fix it", and reads its own entry for the rest. For the common case —
entry written, lint clean — the two are identical, because the loop is skipped
either way.

`_seal`'s duplicate guard is already replaced: the twin-slug check refuses an
entry whose question exists in the chapter under another date, and it fires on
real data.

---

# What gets better, beyond the obvious

**The assumption gate stops being terminal.** Today a rejected approach ends the
run, because `findings` and `working_code` were computed under the old premise
and the probe conversation is gone. Merged, **the conversation is still alive**:
a rejection becomes a user turn — "the user rejected the point-mass assumption,
probe again with trim" — and the run continues. The three-round re-probe loop
that was deleted for never firing becomes free, and it is free precisely because
there is no longer a boundary to re-probe across.

**A corrected value stops needing a private field.** `_corrections` exists to
carry it over the boundary. Merged, it is a sentence in the conversation.

**The write brief arrives when writing starts**, rather than as the opening
statement of a fresh conversation — read in context instead of in the abstract.

---

# What gets worse, stated plainly

**Prompt tokens almost certainly go UP.** Measured per question today:

```
ask     10.3 turns   180,264 prompt
write   14.5 turns   265,146 prompt
SPLIT                445,410
```

A conversation re-sends its whole history every turn, so cost grows with the
square of the turn count, not the sum of two halves. One 25-turn conversation is
plausibly more expensive than a 10-turn and a 15-turn one — which is exactly what
the README's "$0.404 split against $0.429 merged" measured.

**So: tool surface and latency down, conversation cost up.** That is the trade,
it is being made deliberately, and `nb eval` is where it will show. If prompt
tokens per question rise by more than the ~25% that split-vs-merged implies,
something else is wrong and the number is worth chasing.

**What I previously claimed and now doubt.** I argued the split's value was the
curated brief, citing `first_pass_violations = 0.03` across 33 write runs. That
is far more likely to come from the 200-line write brief and the rule list,
**both of which survive unchanged**. The only untested part is whether the probe
transcript sitting above the brief degrades the writing. Watch the number; do
not build around it.

---

# Do not repeat the mistake that made `PHASE_OMITS` necessary

Weighed, the `propose` declaration was mostly not a schema:

```
figures        239 tok  19.0%    "Match the form to the question: a DRAWING when…"
route          186 tok  14.8%    the whole fork criterion, restated
forked_from    157 tok  12.5%    how forking works, restated
title          134 tok  10.7%    rule 26, restated, with a worked example
────────────────────────────
               716 tok    57%   of all field descriptions
```

All four are **already in `system_instruction.md`**, which is shared and cached
once. `PHASE_OMITS` existed to stop paying for them twice — a mechanism whose
only job was to work around a bloated declaration.

**The three new tools must not inherit it.** Their descriptions say what the
parameter IS and point at where the doctrine lives:

    route: "entry | new_chapter. The test is whether `_model.py` would
            differ -- see the Scope section of your instructions."

There is a second reason beyond tokens: **duplicated doctrine drifts and nothing
catches it.** `route`'s description still described the OLD fork criterion — "a
different model, fidelity or vehicle" — until it was rewritten by hand last
week, long after `forking.md` had changed. A pointer cannot go stale.

---

# Two fixes that come with it

## The inherited gate offers a decision it cannot act on

It already runs only at chapter creation. The defect is at the FIRST chapter,
which has no parent — so `inputs.inherited()` falls back to the notebook's brief
and the gate offers **the brief itself for striking**. Observed on the X-Wing
run:

```
INHERITED — nearest ancestor first
  from RADICAL-GLIDER  (nearest)
     1. [Specified] **Flat plate foam**, cut and slotted by hand.
     2. [Specified] **Star Wars X-Wing**, from the FliteTest plan.
```

A strike there is silently discarded. Verified: resolving it calls
`lint.input_ids(root, "RADICAL-GLIDER")`, which looks for
`chapters/RADICAL-GLIDER/_inputs.yml`, finds nothing, and matches no id.

It is also wrong in principle: the brief is never overwritten, because a fork
that departs from it is a different aircraft and so a different notebook.

| change | where |
|---|---|
| no parent → show the brief as CONTEXT, take no strikes | `interact.py` |
| an `overwrites:` naming the notebook is refused, explicitly | `lint.py`, rule 31 |

## `nb new` scaffolds but does not prove

Structurally complete — `_inputs.yml` at both levels, `_notebook.py`,
`_probe_base.py`, `_quarto.yml`, `styles.css`, a front page, a claimable
`01-first-chapter`. Four things missing:

1. **The brief is a placeholder and nothing checks it.** A fresh notebook lints
   **clean** with `- <id>: "**<what>**: <value>."` still in it. Rule 24 covers
   chapter `_inputs.yml` and `index.qmd`; the root is watched by nothing.
2. **The brief cannot be given on the command line**, so it is always a
   hand-edit afterwards — and the prefix is built once at `nb ask`, so
   forgetting means a run with no notebook level at all.
3. **`chapter_title` is unreachable.** `new()` takes it; `__main__` never passes
   it, so every first chapter is called "First chapter".
4. **It lints and preflights, but never renders.** "It lints" is not "it
   builds". The X-Wing notebook's first render was inside its first `ask`.

| change | where |
|---|---|
| `--spec "…"` / `--assume "…"`, repeatable, written into the root `_inputs.yml` with slugged ids | `__main__.py`, `new.py` |
| `--chapter-title` reaches `create_chapter` | `__main__.py` |
| rule 24 covers the root `_inputs.yml` once the notebook has ANY entry | `lint.py` |
| prove it renders, not just lints | `new.py` |

The rule needs a different trigger from the chapter one: not "this chapter has
an entry" but "this notebook has an entry". A placeholder brief before the first
entry is a notebook nobody has started; after it, it is a top level that lies.

---

# Order of work

1. **The path allowlist**, and **`nb new`**, and **the inherited gate.** All
   three are independent of the merge, all three fix something that silently
   does nothing today, and none of them can be broken by what follows.
2. **`declare_input`**, alongside the existing `propose`. Both write the same
   register. This is the one piece worth landing before the rest, because it
   tests whether per-assumption declaring fixes the four-of-eight empty-inputs
   problem while there is still a fallback.
3. **`open_chapter`**, taking `propose`'s routing half and `write.main`'s
   chapter block. `propose` keeps the rest, briefly.
4. **`open_entry`**, and `propose`, `Proposal`, `Terminal`, `render_stop`,
   `proposal.json` and `PHASE_OMITS` are deleted with it. `ask.py` and
   `write.py` become one phase.
5. **Slim the new declarations** to pointers, once they exist and their real
   weight is measurable.

# Verification

- **`nb.corpus` must not move.** Nothing here touches a lint rule except by
  deleting callers — except rule 24's new half, which will move the two frozen
  notebooks if they have no root `_inputs.yml`. Check before writing it and
  record the number in the same commit.
- **Each of the four refusals has a test that fires it in its new home.** They
  are why the mechanism exists and they must not quietly become three.
- **A stop with nobody watching ends the way it does today**: question on disk,
  entry on disk, `nb resume` works.
- **A `--answers` file can approve a new chapter.** The coordinator path the
  mailbox exists for, and it has never once been exercised.
- **A run that dies after `open_entry` resumes from `run.json`** and commits the
  entry already on disk. That is the one thing `proposal.json` did that nothing
  else does.
- **The path allowlist is asserted**: a write to `test.py` is refused and the
  refusal names `probe`; a write to `_analysis.py` is not.
- **Prompt tokens per question, before and after.** Recorded in `nb eval`, and
  expected to rise. Anything much beyond ~25% is a bug, not the trade.
- **One render at the end**, not one per step.

# Out of scope

- **`ask_specified`, `probe`, `lint`, `render`, `check`** — untouched.
- **The refactor gate.** It moves from `write.main`'s exception stack into the
  same post-loop sequence, unchanged in what it checks; its approval becomes a
  mailbox question like the new-chapter one.
- **Removing `nb resume`.** It is the timeout path and the crash path still;
  only its routine use disappears.
- **Touching the frozen corpus notebooks.** They have no root `_inputs.yml` and
  are not worth migrating, exactly as with rules 33-35.
