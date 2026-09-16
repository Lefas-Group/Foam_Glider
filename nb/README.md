# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 32-rule
lint contract, renders, and is checked against its own output before it commits.
Distilled from the `design-notebook` Claude Code skill; runs without it, on
Gemini.

Needs `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`. **Run from the
repo root** — there is no installed entry point, so anywhere else is
`ModuleNotFoundError`.

```bash
uv run --group nb python -m nb new   <notebook> [title]      # once per aircraft
uv run --group nb python -m nb ask   <notebook> "<question>" # the main one
uv run --group nb python -m nb write <notebook>              # resume a stop
uv run --group nb python -m nb watch <notebook>              # follow the detail
uv run --group nb python -m nb view  <notebook> [--force]    # build the site
uv run --group nb python -m nb eval  <notebook>              # runs, by model
```

`ask` is one command per entry: probe, write, lint, render, verify, commit,
print the entry with its real numbers, rebuild the site, and take the next
queued question.

## What it asks

- **Two budgets**, at the start: seconds of exploring for the question (120),
  and seconds of solving one render may take (20). Enter accepts both.
- **Specified inputs**, as they arise — where a different answer changes *what
  is being built*. `you decide` delegates, and is recorded as the agent's call.
- **Assumptions**, once, before anything is built on them. Enter accepts;
  `1: 12 mm` corrects one, which **re-enters the probe** rather than continuing,
  since the findings were computed under the old value.

## The two stops

It halts and writes `proposal.json` for a **new chapter** (later entries build
on its `_model.py`) and for a **refused refactor** (a `_model.py` edit existing
entries depend on). `nb write` resumes either. There is no gate on a finished
entry: lint, render and verify have all passed, and the record is append-only.

## Budgets

| | default | |
|---|---|---|
| probe pool, per question | 120 s | the agent divides it |
| `ENTRY_CEILING`, per render | 20 s | granted at the prompt; commit refused if changed |
| `SOLVE_BUDGET`, per solve | 15 s | the agent's, and must fit the ceiling |

They belong to the entry, never the chapter, so a fork inherits nothing. The
render deadline is `35 s + 5 s/page + the ceilings of pages that will execute`,
with **no slack**. All of it prints in the entry's footer:

```
Rendered in 2.3 s (limit 20 s) · 1 aero solve (budget 15 s each) · explored in 55 s (limit 120 s)
```

## Two tabs

The terminal carries the conversation — questions, failures, decisions, the
finished entry. Everything else goes to `_scratch/run/status.log`; follow it
with `nb watch`, which dims the reasoning and warns when a run stops advancing.

## Structure

```
__main__.py  the six commands          phases/  ask · write · verify · new
config.py    model, budgets, limits             view · watch · eval · common
client.py    the one provider seam     tools/   probe · verifiers · interact
loop.py      turns, signatures                  guards · scaffold · api · refs
session.py   per-run state                      figures · shell · mcp_fs
schema.py    Proposal and Input        vendor/  lint · check · freezediff
prefix.py    the cached system prefix           notebook · probe_base
metrics.py   one row per phase                  library_explorer · references/
corpus.py    the regression test
```

`vendor/notebook.py` and `probe_base.py` are copied into each notebook and
compared byte-for-byte by rule 11 — a notebook must render without `nb`.

## Three checks

**lint** reads the source (3 attempts). **verify** reads the *rendered* page and
its figures with a fresh model, catching prose written from what the model
believed rather than what came out (2 attempts; a failed render gets 1 fix of
its own). **check** deletes invalidated freezes, re-renders, and diffs values
and figure bytes against git — what a refactor must pass.

## Testing a change

`uv run --group nb python -m nb.corpus` lints all three notebooks against recorded counts. Every
rule here was calibrated with that sweep; by hand it got the wrong answer twice,
once because a rule silently stopped applying, which looks exactly like a
notebook that improved. A change that moves the counts updates them in the same
commit.

`nb eval` groups recorded runs by model — turns, lint calls, first-pass
violations, how many reached a proposal. `NB_MODEL=…` overrides for one run.

## Four things that will bite

- **Freeze tracks the page, not its includes.** Editing `_model.py` leaves its
  entries serving stale values; that is what `check` and rule 12 are for.
- **Chapters are exec'd, never imported.** `from _analysis import …` raises
  `ModuleNotFoundError` at render (rule 29) — the names are already in scope.
- **A cited number is transcribed, not computed.** No `cite()`; lint warns, and
  nothing detects drift once the cited chapter re-renders.
- **A run does not survive the lid closing.** Asleep looks exactly like wedged,
  and no timeout helps — the process is not running to observe it.
