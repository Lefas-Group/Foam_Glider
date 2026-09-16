# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 32-rule
lint contract, renders, and is checked against its own output before it commits.
Runs on Gemini; needs `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`.

**Run from the repo root** — there is no installed entry point.

```bash
uv run --group nb python -m nb new    <notebook> [title]     # once per aircraft
uv run --group nb python -m nb ask    <notebook> "<q>"       # the main one
uv run --group nb python -m nb write  <notebook>             # resume a stop
uv run --group nb python -m nb board  <notebook>             # N agents, one terminal
uv run --group nb python -m nb answer <notebook> [run] "…"   # reply to a waiting run
uv run --group nb python -m nb watch  <notebook> [run]       # follow the detail
uv run --group nb python -m nb view   <notebook> [--force]   # build the site
uv run --group nb python -m nb eval   <notebook>             # runs, by model
```

`ask` is one command per entry: probe, write, lint, render, verify, commit.

It asks you for two budgets, for any **Specified** input — one where a different
answer changes what is being built — and once to confirm its assumptions. It
stops and writes `proposal.json` for a **new chapter** or a **refused
refactor**, both being commitments later entries depend on; `nb write` resumes
either.

## Budgets

| | default |
|---|---|
| probe pool, per question | 120 s |
| `ENTRY_CEILING`, per render | 20 s |
| `SOLVE_BUDGET`, per solve | 15 s |

They belong to the entry, never the chapter, and print in its footer:

```
Rendered in 2.3 s (limit 20 s) · 1 aero solve (budget 15 s each) · explored in 55 s (limit 120 s)
```

## Several at once

One agent per chapter — never two in the same one, where `_analysis.py` is
shared and rule 2 compares code across entries.

```bash
uv run --group nb python -m nb ask glider-notebook "<question>" --detach &
uv run --group nb python -m nb board glider-notebook
```

`--detach` returns a run id at once. `board` shows every run and prompts you for
whichever is asking. It is a **view, not a supervisor**: questions and answers
are files in `_scratch/runs/<id>/`, so killing the board leaves the agent
waiting, and `nb answer` works from anywhere. `--answers file.json` pre-empts
the routine questions.

## Three checks

**lint** reads the source. **verify** reads the *rendered* page with a fresh
model, catching prose written from what the model believed rather than what came
out. **check** deletes invalidated freezes, re-renders, and diffs values and
figure bytes against git — what a refactor must pass.

## Testing a change

`python -m nb.corpus` lints all three notebooks against recorded counts. Every
rule here was calibrated with that sweep; by hand it got the wrong answer twice.
A change that moves the counts updates them in the same commit.

## Four things that will bite

- **Freeze tracks the page, not its includes.** Editing `_model.py` leaves its
  entries serving stale values; that is what `check` and rule 12 are for.
- **Chapters are exec'd, never imported.** `from _analysis import …` raises
  `ModuleNotFoundError` at render (rule 29) — the names are already in scope.
- **A cited number is transcribed, not computed.** No `cite()`; lint warns, and
  nothing detects drift once the cited chapter re-renders.
- **A run does not survive the lid closing.** Asleep looks exactly like wedged,
  and no timeout helps — the process is not running to observe it.
