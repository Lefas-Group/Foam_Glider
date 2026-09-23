# Removing the proposal, and three things around it

**Status: proposed.** Nothing implemented.

Three pieces, in the order they should land. Only the first is clearly right on
today's evidence; the last is a bet and is staged so it can be abandoned.

---

# What the proposal actually is

| piece | where |
|---|---|
| `Proposal`, 15 fields | `schema.py` |
| the `propose` declaration | **6,676 of 15,053 chars — 44% of the whole tool surface** |
| `Terminal`, carrying the payload out of the loop | `loop.py` |
| `proposal.json`, `persist()`, `_seal()` | `interact.py`, `write.py` |
| nine private `_` fields | `_pool_left`, `_pool_total`, `_render_ceiling`, `_corrections`, `_inherited`, `_struck`, `_replaces`, `_assumptions_confirmed`, `committed` |
| `_resolve()` — which run to resume, and refusing a live one | `write.py` |
| `render_stop()`, `nb resume` / `nb write` | `interact.py`, `__main__.py` |

## The measurement that decides it

Across the ten runs still on disk:

```
7 of 10   ask -> write in ONE process
3 of 10   crossed a process boundary
```

And every one of those three crossed it because **the system deliberately
stopped** — a new chapter, a refactor — never because anything crashed.

So: a handoff document, and the largest tool declaration in the system, exist to
cross a boundary that is crossed 30% of the time, for reasons that are all "stop
and ask the human". In the other seven runs `proposal.json` was written to disk
and read back **in the same process, milliseconds later**.

---

# Stage 1 — the stops become questions, not exits

The whole boundary is two `return 0`s. Replace both with mailbox questions and
it is never crossed.

| change | where |
|---|---|
| new-chapter approval → `MAILBOX.ask(..., default=None)` | `ask.py`, beside `confirm_inherited` |
| refused-refactor approval → the same | `write.py`'s `except Refactor` |
| accepted-refactor (`--accept-refactor`) → the same, at the gate | `write.py` |
| `render_stop()` becomes the question body, not a farewell | `interact.py` |

**`default=None` is the whole safety of this.** A defaulted question takes its
default after `DEFAULTED_WAIT` and carries on; an undefaulted one waits the full
hour and then raises `SystemExit` with the question on disk — *which is exactly
today's behaviour*. Walk away and you get today's outcome; be at the keyboard
and it costs one keystroke instead of a second command.

**The machinery is already there and already used at that exact moment.**
`confirm_inherited` puts a mailbox question to the user immediately before
`render_stop` prints. Today the new-chapter decision therefore costs *two*
interactions at *one* decision point.

**Measured cost of the current shape**, from the X-Wing run: ask ended ~14:41,
write began **14:46:36**. Five minutes of human round-trip on a run whose actual
compute was sixteen — plus four failed pastes of `continue uv run …`, which is
what prompted the output fix that went in beside this.

**Pros.** One command per question. The `propose`→`Terminal`→`return 0`→`nb
resume` path stops being the normal case and becomes what it should be: the
thing that happens when nobody answers.

**Cons.** The gate stops being unmissable. Today the process ends and you *must*
type something; as a question it can be pre-answered by `--answers` or by a
coordinator. That is the point, but it means the `default=None` property is
load-bearing and wants a test.

**Risk.** `nb resume` must keep working unchanged for the timeout path. Nothing
about stage 1 removes the document.

---

# Stage 2 — measure again

Land stage 1, run a week of entries, then count process boundaries the same way:

```bash
for f in */_scratch/runs/*/status.log; do grep -o "pid [0-9]*" $f | sort -u | wc -l; done
```

If it is 1 everywhere, stage 3 is safe. If something still resumes, that is the
real reason the document exists and it should be written down before it is
removed. **Do not skip this.** The 30% figure above is the thing the rest of the
plan rests on, and it was measured on a system that stopped by exiting.

---

# Stage 3 — `proposal.json` stops being a protocol

Keep `Proposal` and `propose`; stop persisting to disk as a handoff.

| change | where |
|---|---|
| `Terminal.payload` goes straight to `write()` in memory | `ask.py` |
| `proposal.json` is written once, as a RECORD, after the gate | `interact.py` |
| `persist()` and the nine `_` fields collapse into `Session` | everywhere |
| `_resolve()` keeps only the live-run refusal | `write.py` |

`proposal.json` survives as a **record of what was approved** — a coordinator
reads it, and it is what `nb clean` protects — but nothing reads it back. That
deletes `persist()`, `_seal()`, the private-field round trip, and the
`raw.get(...)` block at the top of `write.main`.

**`_seal`'s duplicate guard is already replaced.** The twin-slug check added
today refuses to write an entry whose question already exists in the chapter
under another date, and it fires on real data — it caught the unsealed
proposal sitting in `glider-notebook/_scratch` from the sleep incident.

---

# Stage 4 — merge the conversations. A bet, and the last thing to do

Delete `propose`, `Proposal`, `Terminal`, `render_stop`, `nb resume`. One
conversation: probe, then write, then commit.

**What it buys.** 44% of the tool surface. Two `setup()` calls become one
(5.2 s of `npx` each, measured). One metrics row per question instead of two.

**What it costs, and this is the part I would not hand-wave.** The write phase
today starts from a *curated, approved document*. Merged, it carries its own
probe transcript — including the wrong turns. On the X-Wing run that transcript
is fourteen probes of geometry iteration, several of them failures.

The number to hold it against: **`first_pass_violations` is 0.03 across 33 write
runs.** The write phase essentially never violates lint on its first attempt.
That is what a clean brief buys, and there is no evidence it survives the merge.

**So stage 4 is the one to defend with a measurement, not an argument.** Run it
behind `$NB_MERGED=1` for ten entries and compare first-pass violations and
turns. If it holds, delete the old path. If it does not, stages 1-3 already took
the latency out and stage 4 was never the point.

**Explicitly NOT a reason to do it:** the README's "~6% less than carrying the
probe history forward". Six percent of API cost is nowhere near the weight of
`Proposal` plus persistence plus resume, and defending the split on that number
invites exactly this removal. Its real reasons are the gate and the curated
brief; stage 1 removes the first, and stage 4 tests the second.

---

# The inherited gate — one defect, not the one suspected

It **already** runs only at chapter creation: `ask.py` calls it under
`if proposal.route == "new_chapter"` and nowhere else.

The real defect is at the FIRST chapter, which has no parent — so
`inputs.inherited()` falls back to the notebook's brief and the gate offers **the
brief itself for striking**. Observed on the X-Wing run:

```
INHERITED — nearest ancestor first
  from RADICAL-GLIDER  (nearest)
     1. [Specified] **Flat plate foam**, cut and slotted by hand.
     2. [Specified] **Star Wars X-Wing**, from the FliteTest plan.
```

A strike there cannot take effect, and is discarded in silence. Verified:
resolving it calls `lint.input_ids(root, "RADICAL-GLIDER")`, which looks for
`chapters/RADICAL-GLIDER/_inputs.yml`, finds nothing, and matches no id. The
user is offered a decision the system cannot act on.

It is also *wrong in principle*, and we wrote the principle down last week: the
brief is never overwritten, because a fork that departs from it is a different
aircraft and so a different notebook.

| change | where |
|---|---|
| no parent → show the brief as CONTEXT, take no strikes | `interact.py` |
| rule: an `overwrites:` naming the notebook is refused | `lint.py`, rule 31 — already true by accident, make it explicit and say why |

---

# `nb new` — it scaffolds, but it does not prove

What it produces today is structurally complete: `_inputs.yml` at both levels,
`_notebook.py`, `_probe_base.py`, `_quarto.yml`, `styles.css`, a front page, and
a claimable `01-first-chapter`. Four things are missing.

**1. The brief is a placeholder and nothing checks it.** A fresh notebook lints
**clean** with `- <id>: "**<what>**: <value>."` still in it. Rule 24 covers
chapter `_inputs.yml` and `index.qmd`; the root is watched by nothing. Same
class of hole as `claimable_stub` had, and it hides the one file a person is
supposed to write.

**2. The brief cannot be given on the command line.** `nb new <dir> [title]` is
the whole interface, so the brief is always a hand-edit afterwards — and the
prefix is built once at `nb ask`, so an unfilled brief means a run with no
notebook level at all.

**3. `chapter_title` is unreachable.** `new()` takes it; `__main__` never passes
it. Every notebook's first chapter is called "First chapter" until something
renames it.

**4. It lints and preflights, but never renders.** "It lints" is not "it
builds". The X-Wing notebook's first render was inside the first `ask`.

| change | where |
|---|---|
| `--spec "…"` / `--assume "…"`, repeatable, written into the root `_inputs.yml` with slugged ids | `__main__.py`, `new.py` |
| `--chapter-title` reaches `create_chapter` | `__main__.py` |
| rule 24 covers the root `_inputs.yml` once the notebook has ANY entry | `lint.py` |
| prove it renders, not just lints | `new.py` |

The rule needs a different trigger from the chapter one: not "this chapter has
an entry" but "this notebook has an entry". A brief that is still a placeholder
before the first entry is a notebook nobody has started; after it, it is a
notebook whose top level is a lie.

---

# Order of work

1. **Stage 1** — the stops become questions. Independent of everything else, and
   it removes the latency that prompted all of this.
2. **The inherited gate**, and **`nb new`**. Both small, both independent, both
   fix a decision-or-check that silently does nothing.
3. **Stage 2** — measure. A week of entries.
4. **Stage 3** — `proposal.json` stops being a protocol.
5. **Stage 4** — only behind a flag, only with ten entries of evidence.

# Verification

- **`nb.corpus` should not move** for stages 1 and 3. Rule 24's new half will
  move it for the two frozen notebooks if they have no root `_inputs.yml` —
  check before writing the rule, and record the number in the same commit.
- **A stop with nobody watching still ends the way it does today**: question on
  disk, proposal on disk, `nb resume` works. That is the one behaviour stage 1
  must not change, and it is one test.
- **A `--answers` file can approve a new chapter.** That is the coordinator path
  the mailbox exists for, and it has never once been exercised.
- **`nb new` with `--spec` produces a notebook that renders**, and one without
  produces a notebook that fails rule 24 as soon as it has an entry.
- **One render at the end**, not one per stage.

# Out of scope

- **Removing `nb resume`.** It is the timeout path and the crash path even after
  stage 4; only the *routine* use of it goes away.
- **The refactor gate itself.** Stage 1 changes how it asks, not what it checks.
- **Touching the frozen corpus notebooks.** They have no root `_inputs.yml` and
  are not worth migrating, exactly as with rules 33-35.
