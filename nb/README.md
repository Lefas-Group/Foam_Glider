# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 38-rule
lint contract, renders, and is checked against its own output before it commits.
Runs on Gemini; needs `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`.

**Run from the repo root** — there is no installed entry point.

```bash
uv run --group nb python -m nb new    <notebook> [title]     # once per aircraft
uv run --group nb python -m nb ask    <notebook> "<q>"       # the main one
uv run --group nb python -m nb ask    <notebook> "<q>" --detach  # …and walk away
uv run --group nb python -m nb resume <notebook> [run]       # resume a stop
uv run --group nb python -m nb board  <notebook>             # N agents, one terminal
uv run --group nb python -m nb answer <notebook> [run] "…"   # reply to a waiting run
uv run --group nb python -m nb watch  <notebook> [run]       # follow the detail
uv run --group nb python -m nb stop   <notebook> [run]       # ask a run to stop
uv run --group nb python -m nb clean  <notebook> [run] [--keep N] [--yes]
uv run --group nb python -m nb view   <notebook> [--force]   # build the site
uv run --group nb python -m nb eval   <notebook>             # runs, by model
```

`ask` is one command per entry: probe, write, lint, render, verify, commit.

It asks you for two budgets, for any **Specified** input — one where a different
answer changes what is being built — and once to confirm its assumptions. It
stops and writes `proposal.json` for a **new chapter** or a **refused
refactor**, both being commitments later entries depend on; `nb resume` resumes
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

```bash
uv run --group nb python -m nb ask glider-notebook "<question A>" --detach
uv run --group nb python -m nb ask glider-notebook "<question B>" --detach
uv run --group nb python -m nb board glider-notebook
```

**Do not add `&`.** `--detach` prints the run id and the `watch` line, then
double-forks and `setsid`s: its own session, no controlling terminal, reparented
to init. The prompt returns in about a second, and closing the window leaves the
run alone. Everything a terminal can do to a process — Ctrl-Z, SIGTTIN on a
background read, a hangup — needs a controlling terminal, and the run no longer
has one. It used to detach only the *conversation*, which is how three runs got
suspended mid-question.

**One agent per chapter, and it is enforced.** `_analysis.py` is shared and
rule 2 compares code across entries, so a second run entering a chapter someone
is writing is refused before it spends a turn — its proposal is already on disk,
and `nb resume <notebook> <run>` picks it up when the first finishes. Different
chapters run side by side; they meet only at the render, which is locked.

Launch both anyway when you have two questions: if they pick different chapters
you have halved the wall clock, and if they collide the second refuses in
seconds, which is still faster than waiting.

`board` shows every run and prompts you for whichever is asking. `nb stop` asks
a run to end: cooperative, checked before each turn and while blocked on a
question, so it exits through its own door and records `stopped` rather than
looking like a crash. It reverts nothing.

`board` is a **view, not a supervisor**: questions and answers
are files in `_scratch/runs/<id>/`, so killing the board leaves the agent
waiting, and `nb answer` works from anywhere. `--answers file.json` pre-empts
the routine questions.

## When a run wedges

Eight turns without writing or measuring anything and the run asks you whether
to continue — `stop`, or type advice and it goes to the model. Silence for five
minutes means continue, so a detached run is never stranded by it. Calibrated on
recorded transcripts: the run that prompted it went 26 barren turns, healthy
runs peak at 4.

A productive tool that keeps *failing* counts as no progress either, so a
`propose` the model cannot satisfy trips it at eight rather than sixty.

`MAX_TURNS` (60) stays as the backstop. A run that reaches it now means the
detector missed something — worth opening, not shrugging at.

## The shape of a notebook

A front page draws the chapter graph from each `_model.py`'s fork header, so it
cannot disagree with the models. Each chapter index carries `order:` (the sidebar
does not sort without it), `categories:` from the notebook's own
`_categories.yml`, its lineage, and a listing of its questions. Rules 33-38 keep
all of that from decaying — the scaffold ships it, and a model that rewrites an
index with `write_file` would otherwise drop it silently.

## Three checks

**lint** reads the source. **verify** reads the *rendered* page with a fresh
model, catching prose written from what the model believed rather than what came
out. **check** deletes invalidated freezes, re-renders, and diffs values and
figure bytes against git — what a refactor must pass.

## What a render actually executes

Quarto honours `freeze` on a **whole-notebook render only**. Name a target and
every page under it executes, whatever `_freeze/` holds — so a chapter target is
routinely *more* expensive than rendering everything. Measured on
`glider-notebook`:

```
quarto render chapters/01-foam-glider   5 pages executed
quarto render                           0 pages executed, all 32 cached
```

Every render says which it is doing, and why:

```
render    entry · 1 page · deadline 60 s · targeted, so the freeze is ignored · the agent asked
render    project · 0 pages · deadline 195 s · 32 served from cache · rebuilding the site
```

`nb watch` follows those lines; `nb eval`'s `rndrs` and `pages` columns carry the
same counts per run, because the cost of a render is the pages it executes and
not the call.

## Testing a change

`python -m nb.corpus` lints all three notebooks against recorded counts. Every
rule here was calibrated with that sweep; by hand it got the wrong answer twice.
A change that moves the counts updates them in the same commit.

## The version before this one

`nb-single-agent` tags the system as it was before parallelism: one agent, one
notebook, questions at the terminal. It still runs —
[`../DEPRECATED-single-agent.md`](../DEPRECATED-single-agent.md) has the one
command.

## Four things that will bite

- **Freeze tracks the page, not its includes.** Editing `_model.py` leaves its
  entries serving stale values; that is what `check` and rule 12 are for.
- **Chapters are exec'd, never imported.** `from _analysis import …` raises
  `ModuleNotFoundError` at render (rule 29) — the names are already in scope.
- **Quote another chapter with `cite()`, never by retyping.** It returns that
  entry's hero value from its freeze, and `check` re-renders every page citing a
  chapter it rebuilds — the one cross-chapter edge in the graph. An entry with
  two hero blocks needs `label=` to say which.
- **A detached run survives the terminal, but not the lid.** Closing the window
  is safe now. Sleep is not: every budget here is wall clock, and wall clock
  runs while the process does not — so a probe interrupted by sleep wakes to a
  watchdog that believes it overran by hours and kills it. One suspended run
  recorded `15 s granted · 5596 s used`.
