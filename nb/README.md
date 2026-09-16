# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 32-rule
lint contract, renders, and is checked against its own output before it commits.

Distilled from the `design-notebook` Claude Code skill, and runs without it, on
Gemini. Requires `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`.

**Run everything from the repo root.** There is no installed entry point:
`python -m nb` finds the package because Python puts the current directory on
`sys.path`. From anywhere else it is `ModuleNotFoundError`, and from outside the
project `uv run` finds no `pyproject.toml` and falls back to an interpreter
without the dependencies.

---

## Commands

```bash
uv run --group nb python -m nb new   <notebook> [title]      # once per aircraft
uv run --group nb python -m nb ask   <notebook> "<question>" # the main one
uv run --group nb python -m nb write <notebook>              # resume a stop
uv run --group nb python -m nb watch <notebook>              # follow the detail
uv run --group nb python -m nb view  <notebook> [--force]    # build the site
uv run --group nb python -m nb eval  <notebook>              # runs, by model
```

`ask` is one command per entry. It probes the chapter's model, writes the entry,
fixes it against lint, renders it, verifies the prose against what actually
rendered, commits, prints the entry with its real numbers, rebuilds the site,
and picks up the next queued question if the ask contained more than one.

## What it asks you

**Two budgets, at the start.** Seconds of exploring for the whole question
(default 120), and seconds of solving one render of the entry may take
(default 20). Enter accepts either. These are the only prompts with defaults,
because a spend cap has a defensible one.

**Specified inputs, whenever one comes up.** An input where a different answer
changes *what is being built*. Answer it, or type `you decide` to delegate —
delegation is recorded as the agent's decision, not yours.

**Assumptions, once, before anything is built on them.** Everything the probe
assumed, listed together. Enter accepts; `1: 12 mm` corrects one. **A correction
re-enters the probe** rather than continuing — the findings were computed under
the old value, and a changed *method* cannot be fixed by re-rendering.

## The two stops

A run halts, writes `proposal.json` and exits for exactly two things, both
decisions about **structure or spend** made before the work they authorise is
paid for:

- **a new chapter** — later entries build on its `_model.py`, so changing it
  afterwards means re-solving all of them;
- **a refused refactor** — an edit to a `_model.py` that existing entries
  already depend on.

`nb write <notebook>` resumes from the proposal in either case. There is **no**
gate on a finished entry: by then lint, render and verify have all passed, the
record is append-only, and an entry that turns out wrong is corrected by the
next one.

## Budgets

| | default | enforced by |
|---|---|---|
| probe pool, per question | 120 s | the agent divides it; a probe asking for more than remains gets what remains |
| `ENTRY_CEILING`, per render | 20 s | granted at the prompt, written into the entry, commit refused if changed |
| `SOLVE_BUDGET`, per solve | 15 s | the agent's to choose, and must fit inside the ceiling |

Budgets belong to the **entry**, never the chapter — nothing is inherited by a
fork. The render deadline is `35 s floor + 5 s/page + the ceilings of the pages
that will execute`, with **no slack**: a slow machine needs a bigger number at
the prompt. All four figures print in the entry's footer:

```
Rendered in 2.3 s (limit 20 s) · 1 aero solve (budget 15 s each) · explored in 55 s (limit 120 s)
```

## Two tabs

The terminal carries the **conversation** — questions, failures, decisions, the
finished entry. Everything else (turn lines, the model's reasoning, per-probe
budgets, lint output) goes to `<notebook>/_scratch/run/status.log`.

```bash
uv run --group nb python -m nb watch <notebook>     # in a second tab
```

`watch` dims the reasoning and warns when a run has stopped advancing, using the
pid and deadline the run writes into the log. The writer emits facts; the reader
decides they have stopped arriving — a heartbeat thread inside the run would
keep printing cheerfully while the main thread was stuck.

## Structure

```
__main__.py      the six commands
config.py        model, budgets, limits; importing it puts vendor/ on sys.path
client.py        the one provider seam — swap this to change model vendor
loop.py          the turn loop, thought-signature handling, turn deadline
session.py       per-run state: pool, answers, consults, refactor notes
schema.py        Proposal and Input, with the rules the schema can enforce
prefix.py        the cached system prefix: rules, chapter map, API surface
metrics.py       one row per phase into _scratch/nb-metrics.db
corpus.py        the regression test — lint counts for all three notebooks
preflight.py     what must be true before a run starts

phases/   ask · write · verify · new · view · watch · eval · common
tools/    probe · verifiers · interact · guards · scaffold · api · figures
          refs · shell · mcp_fs (filesystem, in its own process)
vendor/   lint.py · check.py · freezediff.py · notebook.py · probe_base.py
          library_explorer.py · references/
```

`vendor/` is shared with the notebooks: `notebook.py` and `probe_base.py` are
copied into each one and compared byte-for-byte by rule 11, because a notebook
has to render without `nb` installed.

## Three checks, in order of what they can see

- **lint** reads the source. Cheap, runs first, and every message names its own
  fix. 3 attempts.
- **verify** reads the *rendered* page and its figures, with a fresh model and
  no memory of writing it — it catches prose that describes what the model
  believed rather than what came out. 2 attempts. A render that fails outright
  gets 1 fix of its own, since the page must build before verify has anything
  to read.
- **check** deletes the freezes an edit can have invalidated, re-renders, and
  diffs the values and figure bytes against git. This is what a refactor has to
  pass before it can move a shared function.

## Testing a change

```bash
uv run --group nb python -m nb.corpus
```

Lints all three notebooks and asserts the counts on record. Every rule here was
calibrated by running that sweep; doing it by hand got the wrong answer twice in
one session, once by a rule that silently stopped applying — which looks exactly
like a notebook that improved. A rule change that moves the counts must update
them in the same commit that justifies it.

`nb eval <notebook>` groups the recorded runs by model: turns, lint calls,
first-pass violations, and how many reached a proposal. That table, not a
comment, is what decides a model swap. `NB_MODEL=gemini-3.8-flash` overrides the
model for one run without touching a tracked file.

## Four things that will bite

**Quarto freeze tracks the page, not its includes.** Editing a chapter's
`_model.py` does not invalidate its entries — they go on serving values the
model no longer produces. That is why `check` exists and why rule 12 reports a
dirty shared module against a clean freeze.

**Every chapter is exec'd, never imported.** `_model.qmd` execs `_model.py` and
`_analysis.py` into the page namespace, so their names are already in scope and
`from _analysis import …` raises `ModuleNotFoundError` at render (rule 29).

**A number from another chapter is transcribed, not computed.** There is no
`cite()`. The entry links its source and lint warns when a hand-typed number
matches one another chapter publishes — about a third of them are caught, and
nothing detects drift after the cited chapter re-renders.

**An `nb` run does not survive the lid closing.** A run that spans a laptop
sleep looks identical to a wedged one: pid alive, nothing advancing. No timeout
helps, because the process is not running to observe it.
