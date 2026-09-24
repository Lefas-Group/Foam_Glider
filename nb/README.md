# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 39-rule
lint contract, renders, and is checked against its own output before it commits.

---

## Setup

Four things have to be on the machine. Three are binaries; one is a key.

| | why | check it |
|---|---|---|
| **`uv`** | runs everything; no venv to activate | `uv --version` |
| **`quarto`** | renders the notebook | `quarto --version` |
| **`git`** | freeze scoping, diffs, and the commit each entry makes | `git --version` |
| **`npx`** (Node) | the MCP filesystem server the agent writes files through | `npx --version` |

```bash
# 1. dependencies — the notebook runtime AND the agent
uv sync --group nb

# 2. the API key, in the shell you will run from
export GEMINI_API_KEY="…"          # https://aistudio.google.com/apikey

# 3. prove it, before spending anything
uv run --group nb python -m nb.preflight glider-notebook
```

That last command is the whole of setup verification. It checks every binary,
the key, the vendored files, and that the model's copy of the rule list matches
what lint enforces. It prints `preflight ok` or the list of what is wrong.

**Run from the repo root.** There is no installed entry point and nothing to
activate — `uv run` resolves the environment each time, and every path below is
relative to the repo root.

## Running it

```bash
uv run --group nb python -m nb ask glider-notebook \
  --chapter 01-foam-glider "How heavy is the wing alone?"

# a new aircraft, named once, at creation. The title is the directory name.
uv run --group nb python -m nb new paper-dart \
  --chapter-title "Folded wing" \
  --defines "AVL at fixed alpha, flat plate, fuselage drag neglected." \
  --spec "**A4 80 gsm paper**, folded, no glue."
```

That is the whole system. It probes the aircraft model, opens an entry, writes
it, lints it, renders it, commits it, and rebuilds the site — about five
minutes, in one conversation, and it detaches immediately so closing the window
does not kill it.

**What you will be asked.** A board appears on your terminal. It asks for two
budgets up front (press Enter for the defaults), then for anything it needs a
decision on, then to confirm the assumptions it made. Ctrl-C leaves the board;
the run carries on without it.

```
uv run --group nb python -m nb board  glider-notebook   # re-attach, any terminal
uv run --group nb python -m nb watch  glider-notebook   # the detail, live
uv run --group nb python -m nb answer glider-notebook "0.12"
uv run --group nb python -m nb stop   glider-notebook
```

**Skip the questions** when you already know the answers:

```bash
uv run --group nb python -m nb ask glider-notebook "<q>" \
    --pool 180 --ceiling 300 --chapter 04-thinner-foam --quiet
```

**Read the result.** The finished entry prints to the terminal with its real
numbers, and the site is rebuilt:

```bash
open glider-notebook/_site/index.html
```

### Every command

```bash
uv run --group nb python -m nb new    <notebook> [title]     # once per aircraft
uv run --group nb python -m nb ask    <notebook> "<q>"       # the main one
uv run --group nb python -m nb ask    <notebook> "<q>" --quiet  # …no board
uv run --group nb python -m nb resume <notebook> [run]       # resume a stop
uv run --group nb python -m nb board  <notebook>             # N agents, one terminal
uv run --group nb python -m nb answer <notebook> [run] "…"   # reply to a waiting run
uv run --group nb python -m nb watch  <notebook> [run]       # follow the detail
uv run --group nb python -m nb stop   <notebook> [run]       # ask a run to stop
uv run --group nb python -m nb clean  <notebook> [run] [--keep N] [--yes]
uv run --group nb python -m nb view   <notebook> [--force]   # build the site
uv run --group nb python -m nb eval   <notebook>             # runs, by model
```

### When something goes wrong

| symptom | what it is |
|---|---|
| `preflight FAILED` | read the list; every line names its own fix |
| the run seems stuck | `nb watch <notebook>` — it stamps every line, so silence is visible |
| a question nobody answered | `nb board`, or `nb answer <notebook> "<value>"` from anywhere |
| it stopped at a **new chapter** | that stop is deliberate. `nb resume <notebook>` |
| it stopped at a **refactor** | it wants to change a chapter's `_model.py`. `nb resume <notebook> <run> --allow-refactor` |
| nothing committed | the entry is on disk; the terminal says where |
| quota exhausted | it says when to try again. Nothing was lost; `nb resume` picks up |

Every run leaves `<notebook>/_scratch/runs/<id>/` behind: the transcript, the
status log, `run.json` and any question it asked. `nb clean` drops the spent
ones and refuses to touch a run whose chapter still has uncommitted work.

---

## What `ask` actually does

`ask` is one command per entry: probe, write, lint, render, commit. ONE
question per ask — there was a `queue` that carried extra questions into
follow-on runs, and it was never used in 34 recorded asks; two questions are two
`nb ask` calls, which get two pools and run in parallel.

**`--chapter` is required.** A question is about an aircraft, and the aircraft
is the chapter — so the caller names it and the run settles it before the first
token: the name is validated, the lock is claimed, the shared modules are
snapshotted for the refactor gate, and the chapter's `_model.py` goes into the
prefix. The model used to work all that out on turn 1, which cost a turn on
every run, left `_model.py` the second-most-read file in the record, and made
the fork test a six-way classification instead of one comparison.

Two calls move the run forward, and a third only when the vehicle must change:

| call | what it settles |
|---|---|
| `declare_input` | one input, recorded the moment it is assumed |
| `open_entry` | the filename, the assumption check, and the write brief |
| `fork_chapter` | a new chapter, parent implicit. ~15% of runs |

**It used to be two processes** with `proposal.json` between them — a fifteen
-field document the model filled in at the end and a second command read back.
Seven of ten recorded runs crossed that boundary inside a single process,
milliseconds apart; the three that really crossed it did so because the system
deliberately stopped, never because anything crashed. On one run the stop cost
five minutes of human round-trip against sixteen minutes of compute. What the
document was actually for was four refusals, and all four are still enforced —
at `open_chapter` and `open_entry`, where each becomes true.

The trade is stated rather than hidden: one conversation re-sends its whole
history every turn, so prompt tokens grow with the square of the turn count
rather than the sum of two halves. Tool surface and latency down (the
declarations are 26% smaller), conversation cost up. `nb eval` is where it
shows.

It asks you for two budgets, for any **Specified** input — one where a different
answer changes what is being built — and once to confirm its assumptions.

At that last one, `1: 2.5e-4` corrects a VALUE and `1: redo — why` rejects the
APPROACH. The two are different: a corrected value needs no fresh probe,
because rule 1 makes every number in prose an expression and the entry
recomputes at render time. A rejected approach used to end the run, because the
findings had been computed under the old premise and the conversation that
produced them was gone. It does not any more: the conversation is still alive,
so the rejection comes back as a refusal the model probes past and the entry is
simply not opened. The three-round re-probe loop that was deleted for never
firing is free now, and it is free precisely because there is no boundary left
to re-probe across.

It still stops for a **new chapter** and a **refused refactor**, both being
commitments later entries depend on — but as questions the run waits on, not as
exits. Answer either at the keyboard and it costs a keystroke; walk away and it
ends exactly as it used to, with the question and the work on disk and
`nb resume` to pick it up. At the new-chapter stop it also shows what the
chapter INHERITS, grouped by ancestor with the nearest first and anything a
later chapter already superseded resolved out of the list. A chapter with no
ancestor is shown the notebook's brief as CONTEXT and asked nothing: the brief
is never overwritten, because a design that departs from it is a different
aircraft and so a different notebook.

## Budgets

| | default | where it comes from |
|---|---|---|
| probe pool, per question | 120 s | `config.PROBE_POOL` |
| `ENTRY_CEILING`, per render | the notebook's | its own `_notebook.py` |
| `SOLVE_BUDGET`, per solve | 15 s | the entry declares it |

Both are asked for at the start of a run, showing the default and where it came
from — they are different kinds of number and were being shown identically.
Supply them and the questions do not get asked:

```bash
uv run --group nb python -m nb ask glider-notebook "<q>" --pool 180 --ceiling 300
```

`--ceiling` overrides the answer, never the source of the default: the number a
notebook renders under belongs to the notebook, and a second copy of it in
`config.py` disagreed once — 20 s against 200 s, and the notebook won every time.

`--chapter NN-name` pins the run to an existing chapter. Routing to one is a
coordinator's instruction rather than a finding: it costs probe turns to
rediscover and the wrong answer is about a different aircraft. The write guard
refuses a path outside it, so it is a pin and not a hint. Creating a NEW chapter
is a different decision and still stops for approval.

They belong to the entry, never the chapter, and print in its footer:

```
Rendered in 2.3 s (limit 20 s) · 1 aero solve (budget 15 s each) · explored in 55 s (limit 120 s)
```

## Every run detaches

`nb ask` forks the agent out of your shell session and draws a board for it on
the terminal you typed into. Ctrl-C leaves the board; the run carries on, and
`nb board` or `nb answer` reach it from anywhere. Closing the window no longer
kills it.

There is no attached mode. There was one — questions on stdin — and it was not a
second transport for the same behaviour: EOF there killed the run with the
question recorded nowhere, while a question on disk is answerable from a second
terminal, a script or a coordinator, and the run resumes either way. One agent is
now the N=1 case of N agents rather than a mode with its own failure shapes.

`--quiet` skips the board and prints the run id instead — for pipes, scripts and
CI. A question with a safe default (a budget, an assumption confirmation) takes
that default after five minutes rather than holding the run for an hour;
`--answers` supplies them up front and skips the wait entirely.

`--answers` is keyed on the question's NAME, which every question logs as it is
asked (`asking 'static margin' — --answers key`) and which `question.json`
carries. `mailbox.py` lists the fixed ones; a Specified input is keyed by the
quantity itself, so several can be supplied in one file. They used to share the
single key `SPECIFIED INPUT NEEDED`, which meant exactly one could ever be
pre-answered.

## Several at once

```bash
uv run --group nb python -m nb ask glider-notebook "<question A>" --quiet
uv run --group nb python -m nb ask glider-notebook "<question B>" --quiet
uv run --group nb python -m nb board glider-notebook
```

**Do not add `&`.** `--quiet` prints the run id and the `watch` line, then
double-forks and `setsid`s: its own session, no controlling terminal, reparented
to init. The prompt returns in about a second, and closing the window leaves the
run alone. Everything a terminal can do to a process — Ctrl-Z, SIGTTIN on a
background read, a hangup — needs a controlling terminal, and the run no longer
has one. It used to detach only the *conversation*, which is how three runs got
suspended mid-question.

**One agent per chapter, and it is enforced.** `_analysis.py` is shared and
rule 2 compares code across entries, so a second run entering a chapter someone
is writing is refused before it spends a single token — the lock is claimed at
startup, not on turn 1 — and the question can be asked again when the first
finishes. Different
chapters run side by side; they meet only at the render, which is locked.

Launch both anyway when you have two questions: if they pick different chapters
you have halved the wall clock, and if they collide the second refuses in
seconds, which is still faster than waiting.

**There is no shell tool.** `bash` was an allowlisted escape hatch and became
the fourth most-used tool — 37 calls across 8 runs, of which every surviving
category had a better-instrumented equivalent: `uv run python` is `probe`
without the chapter loaded or the solve budget armed, `grep`/`ls`/`cat` are the
file tools without path confinement, and `uv run quarto render` is `render`
without the render lock or the deadline. It was never a security boundary and
never claimed to be — `probe` runs arbitrary Python by design — so removing it
changes nothing about what a run *can* do, only about what it can do
uninstrumented. `check` is refused for the same reason: re-proving a chapter is
minutes, and the run does it once, automatically, when a shared function
actually moved.

`board` shows every run, prompts you for whichever is asking, and prints each
run's ending as it happens — the answer in bold, then the rendered entry with
its real numbers, or the rules that blocked it and where the work is on disk. A
board attached to one run (which is what `nb ask` draws) leaves when that run
does. It reads `run.json` for all of it, which is the same document a
coordinator reads; nothing parses `status.log`. `nb stop` asks
a run to end: cooperative, checked before each turn and while blocked on a
question, so it exits through its own door and records `stopped` rather than
looking like a crash. It reverts nothing.

`board` is a **view, not a supervisor**: questions and answers
are files in `_scratch/runs/<id>/`, so killing the board leaves the agent
waiting, and `nb answer` works from anywhere. `--answers file.json` pre-empts
the routine questions — keyed by question name, which for a Specified input is
the quantity and for a new chapter is the directory name, so a coordinator can
approve one up front with `{"05-thinner-boom": "yes"}` or turn it down with
`{"05-thinner-boom": "no — that belongs in 04"}`.

## When a run wedges

Eight turns without writing or measuring anything and the run asks you whether
to continue — `stop`, or type advice and it goes to the model. Silence for five
minutes means continue, so a detached run is never stranded by it. Calibrated on
recorded transcripts: the run that prompted it went 26 barren turns, healthy
runs peak at 4.

A productive tool that keeps *failing* counts as no progress either, so an
`open_entry` the model cannot satisfy trips it at eight rather than sixty.

`MAX_TURNS` (60) stays as the backstop. A run that reaches it now means the
detector missed something — worth opening, not shrugging at.

## The shape of a notebook

```
glider-notebook/
  index.qmd               the front page: the aircraft's brief, and the lineage diagram
  _notebook.py            vendored runtime — footer(), cite(), chapter_inputs()
  chapters/NN-name/
    _model.py             THE VEHICLE. Guarded once the chapter has entries
    _analysis.py          how this chapter measures it. Yours to grow
    _inputs.yml           what the chapter specified and assumed, as data
    _fork.yml             parent, commit, differences, and what it supersedes
    index.qmd             renders the four above; carries `order:` and the listing
    YYYY-MM-DD-NN-slug.qmd  one entry, one question
```

A chapter's Specified and Assumed items are **data, not markdown**. `_inputs.yml`
holds them as `- <id>: <text>`; `index.qmd` renders them with
`chapter_inputs(...)`. That is what makes a superseded item movable: when a
later chapter names one in its `_fork.yml` under `supersedes:`, the item leaves
its own callout and appears under `## Superseded` on the page that declared it,
linked to the chapter that replaced it. An append-only record has no other way
to say "this is no longer true", and the version that tried to say it in an
extra line put every item on the page twice.

An ENTRY still writes its callouts as markdown. It is a one-time record; a
chapter's is a standing one.

Rules 33-35 and 37-40 keep all of it from decaying — the scaffold ships it, and
a model that rewrites an index with `write_file` would otherwise drop it
silently.

## Three checks

**lint** reads the source. **build** renders the entry and refuses to commit a
page that does not execute — lint has passed by then, and nothing else would
notice. **check** deletes invalidated freezes, re-renders, and diffs values and
figure bytes against git — what a refactor must pass.

There used to be a third, `verify`: a second model call that read the rendered
page and checked the prose against it. It produced zero findings in 32 write
runs and was deleted. The class of error it guarded — a sentence about a curve's
*shape* that the curve contradicts — is now uncaught, deliberately.

## What a render actually executes

Quarto honours `freeze` on a **whole-notebook render only**. Name a target and
every page under it executes, whatever `_freeze/` holds — so a chapter target is
routinely *more* expensive than rendering everything. Measured on
`glider-notebook`:

```
quarto render chapters/01-foam-glider   5 pages executed
quarto render                           0 pages executed, all 34 cached
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
notebook, questions at the terminal. `git show nb-single-agent:nb/README.md` has
its instructions. (This used to link a `DEPRECATED-single-agent.md` beside the
repo root; the file was never committed, so the link went nowhere.)

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
