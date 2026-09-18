# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 32-rule
lint contract, renders, and is checked against its own output before it commits.
Runs on Gemini; needs `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`.

**Run from the repo root** — there is no installed entry point.

```bash
uv run --group nb python -m nb new    <notebook> [title]     # once per aircraft
uv run --group nb python -m nb ask    <notebook> "<q>"       # the main one
uv run --group nb python -m nb resume <notebook> [run]       # resume a stop
uv run --group nb python -m nb board  <notebook>             # N agents, one terminal
uv run --group nb python -m nb answer <notebook> [run] "…"   # reply to a waiting run
uv run --group nb python -m nb watch  <notebook> [run]       # follow the detail
uv run --group nb python -m nb stop   <notebook> [run]       # ask a run to stop
uv run --group nb python -m nb clean  <notebook> [--yes]     # drop spent runs
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

One agent per chapter — never two in the same one, where `_analysis.py` is
shared and rule 2 compares code across entries.

```bash
uv run --group nb python -m nb ask glider-notebook "<question>" --detach &
uv run --group nb python -m nb board glider-notebook
```

`--detach` returns a run id and then goes quiet — its conversation is the run
directory, so nothing of it prints over the board. `board` shows every run and
prompts you for whichever is asking. `nb stop` asks a run to end: cooperative, checked before each turn and while
blocked on a question, so it exits through its own door and records `stopped`
rather than looking like a crash. It reverts nothing.

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
`_categories.yml`, its lineage, and a listing of its questions. Rules 33-37 keep
all of that from decaying — the scaffold ships it, and a model that rewrites an
index with `write_file` would otherwise drop it silently.

## Three checks

**lint** reads the source. **verify** reads the *rendered* page with a fresh
model, catching prose written from what the model believed rather than what came
out. **check** deletes invalidated freezes, re-renders, and diffs values and
figure bytes against git — what a refactor must pass.

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
- **A run does not survive the lid closing.** Asleep looks exactly like wedged,
  and no timeout helps — the process is not running to observe it.
