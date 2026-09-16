# Cross-chapter parallelism, and a coordinator instead of a person

**Status: plan, not implemented.** Written after auditing the shared state a
second `nb` process would touch.

---

## What changes

Today one `nb ask` runs against one notebook, and a person answers its questions
at a terminal. The target is **N agents working different chapters of the same
notebook at once, with one coordinator holding the conversation** — the
coordinator being an agent, with the person above it.

Cross-chapter is the axis worth building: the *physics* is already isolated
(`_model.qmd` execs only its own chapter's files), the prefix is already
whole-notebook and identical for every run so one cache object serves them all,
and it is the only axis that makes a single design go faster. Cross-notebook
parallelism works today, unmodified, but a notebook is an aircraft — it buys
breadth, never depth.

Three things stand in the way. They are independent and can land separately.

---

## Problem 1 — six files assume one writer

| path | what breaks |
|---|---|
| `_scratch/run/proposal.json` | second run overwrites the first's only resume point |
| `_scratch/_nb_probe.py` | **written then executed** — one agent can run another's probe |
| `_scratch/run/transcript.jsonl` | interleaved |
| `_scratch/run/status.log` | interleaved |
| `_scratch/nb-metrics.db` | plain `sqlite3.connect`, no busy timeout → `database is locked` |
| `_freeze/site_libs/` | **measured**: concurrent renders race here and one fails every time (problem 3) |

`_nb_probe.py` is the dangerous one: it fails *silently and plausibly*, attributing
one agent's result to another's question.

### Option 1a — run-scoped scratch (recommended)

```
_scratch/runs/<run-id>/   proposal.json · transcript.jsonl · status.log · probe.py
_scratch/nb-metrics.db    shared, with WAL
```

`run-id` is short and sortable — `20260916-a3f2`. `Notebook` already centralises
every path (`proposal_path`, `transcript_path`, `run`), so this is a constructor
argument threaded through, not a search-and-replace.

- **For**: small, local, and each agent's artefacts stay inspectable afterwards
  rather than being overwritten by the next run — which is useful even with one
  agent.
- **Against**: `nb write <notebook>` with no run id becomes ambiguous. Resolve by
  defaulting to the most recent run, and printing the id it chose.

### Option 1b — git worktree per agent

Each agent gets `git worktree add` on its own branch; the coordinator merges.

- **For**: total isolation — scratch, freeze, `.quarto`, git index. No locks
  anywhere, and a failed agent is discarded by deleting a branch.
- **Against**: `_freeze/` is **committed**, so every merge is a conflict over
  generated JSON, and the 63 MB `.git` is copied per worktree. Worse, it hides
  the collision rather than resolving it: two agents editing one chapter's
  `_analysis.py` merge cleanly and produce an entry neither validated.
- **Verdict**: rejected for chapters. It is the right answer for cross-*notebook*
  work, which needs no isolation anyway.

### sqlite, either way

`PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` in `metrics._db`. Two
lines, stdlib, and the standard answer for multi-process readers with occasional
writers.

---

## Problem 2 — one stdin, N agents, and a conversation to watch

Three blocking `sys.stdin.readline()` calls: `_prompt` (Specified inputs and
consults), `ask_budget`, `confirm_assumptions`. N agents cannot share stdin.

Two requirements, not one:

1. **Someone must answer** — the user now, a coordinator agent later.
2. **The user must be able to OBSERVE the conversation either way**, including
   after a coordinator takes over the answering.

Requirement 2 decides more than it looks. A question answered over a pipe or a
socket leaves no trace: the user can watch it happen live or not at all. A
question answered through a **file** is on disk, timestamped, greppable, and
still there tomorrow. That is the same argument `log.py` already makes —
*"Anything that must be exact is a FILE read by path"* — and it rules out the
transport-based options on grounds that have nothing to do with convenience.

### One terminal, many agents

The target is **N agents launched and watched from a single terminal**, scaling
past the handful a person can hold in separate tabs. That rules out the tabs
interim an earlier draft proposed, and puts the question interface back on the
critical path — for a different reason than a coordinator agent would: it is
needed for the USER first, and a coordinator inherits it unchanged.

**Agents never read stdin in this mode.** They write questions to files and
poll; nothing owns their terminal, so nothing has to multiplex it.

```
_scratch/runs/<id>/question.json   {kind, name, why, options, asked_at}
_scratch/runs/<id>/answer.json     {value, answered_at, by}
```

Two commands over that:

```bash
nb ask <notebook> "<question>" --detach   # prints a run id, returns at once
nb board <notebook>                       # the single terminal
```

`nb board` is the whole interface: a tagged live stream of every run, the
pending questions, and a prompt to answer them.

```
[03·ask ] turn 7   probe  what is the neutral point at 3 mm foam?
[05·write] lint     clean (attempt 1)
[04·ask ] turn 3   ask_specified

  ── 04-thinner-foam asks ─────────────────────────────
     Foam thickness and area density
     A different thickness is a different aircraft.
     options: 3 mm | 5 mm | 6 mm
  [1/2 waiting] > _
```

Output from other runs buffers while a question is on screen, so an answer is
never typed into a scrolling wall — the agents keep working, only their display
pauses.

**Why files and not a supervisor owning the agents' pipes.** A supervisor is the
obvious design and it is worse here:

- If it dies, every agent is orphaned mid-question with nothing to read.
- The Q&A exists only in its scrollback — failing the observability requirement
  from the previous section.
- It cannot be replaced by a coordinator agent without the agents changing too.

With files, `nb board` is a *view*. Kill it, restart it, run two of them, answer
from a different terminal with `nb answer`, or let a coordinator agent write the
same file — the agents neither know nor care. That is the property that makes
this scale in both directions: more agents, and eventually a different answerer.

**How it looks when the coordinator agent arrives:** it writes `answer.json`
instead of the user typing. `nb board` keeps working, now showing questions
being answered by something else — which is exactly the "observe the
conversation" requirement, satisfied by construction rather than by a second
mechanism.

### Rendering the board: plain stdio, not a TUI

`rich` and `textual` would both give a nicer board — a live table, a fixed
question pane. Neither is installed, and a full-screen TUI fights two things the
project already relies on: scrollback *is* the record, and output must survive
being piped. `watch.py` already does ANSI dimming by hand behind
`sys.stdout.isatty()`, which is the pattern to follow.

Start line-oriented with a short `[chapter·phase]` tag. If N agents prove
genuinely unreadable that way, `rich` is a contained upgrade to one file — but
it should be earned by an unreadable board, not assumed.

### Alternatives, and why not

| | why not |
|---|---|
| **named pipes (FIFO)** | no trace once read, so the user cannot observe or audit; open() blocks until both ends attach; nothing survives a restart |
| **unix socket / local HTTP** | same observability objection, plus a server to supervise. Robust and standard, and still the wrong shape for a system whose state is files |
| **one supervisor process owning stdin** | good UX, but it becomes a thing to keep alive, and a crashed supervisor takes every agent's question with it |
| **Celery / RQ / Huey** | a broker for N≈4 local subprocesses |
| **MCP server for answers** | the project already runs one for the filesystem; a second protocol where two JSON files suffice |

### Either way: pre-answers

`nb ask --answers answers.json`, consulted before anything is asked. Trivial,
independently useful for scripted sweeps, and it reduces how often the mailbox
is needed at all. It does not replace it — anticipating every Specified input is
exactly the judgement `ask_specified` exists because models get wrong.

**Do not break the single-user path.** Interactive stdin stays the default; the
mailbox is enabled by `--coordinator`, so a person at a terminal sees exactly
what they see today.

## Problem 3 — load, and the deadline I removed

Two measurements already on record, both in the repo:

- *"the same solve measured 533.9 s against a 145 s baseline purely from machine
  load, 3.7x"* (`lint.py`)
- *"Never run two heavy probes at once. Both starve and neither number means
  anything."* (`probing.md`)

The render deadline used to carry 4× slack for exactly this. **It was removed
this week at the user's request**, so `ENTRY_CEILING` is now the execution time
with no headroom. Under N-way concurrency, honest renders will be killed.

Options, in increasing order of honesty:

- **Inflate every grant by the fan-out.** Puts the slack back, invisibly, in a
  number the coordinator has to compute. Worst of both.
- **A concurrency-aware deadline**: `floor + ceiling × active_agents`, with the
  active count read from the run directories. Honest and automatic, but the
  ceiling stops meaning "seconds of solving" and starts meaning something
  conditional.
- **Serialise the expensive phases** behind one lock per notebook — probe
  subprocesses and renders — so agents overlap on thinking (API latency, which
  is most of the wall clock) and queue on CPU. **Recommended.** A run is
  ~13 s/turn of API time against ~2–10 s of solving, so the overlap is where the
  gain is; solving was never the bottleneck.

### Measured: concurrent renders fail, reproducibly

Run on a disposable copy of `glider-notebook`, two entries in *different*
chapters, freezes cleared so both had to execute.

| | result |
|---|---|
| serial | 35 s, both exit 0 |
| concurrent, 4 trials | **one render fails every time** — exits `0 1`, `1 0`, `1 0`, `0 1` |

It is a genuine race: which of the two fails varies between trials. The failure
is not `.quarto/idx`, which is what I guessed:

```
ERROR: NotFound: No such file or directory (os error 2):
  utime '…/_freeze/site_libs/quarto-nav/headroom.min.js'
  at copyToProjectFreezer → freezeLibDir → renderProject
```

`_freeze/site_libs/` is a **project-level** directory that every render copies
into, even when rendering a single page. One render replaces a file while the
other is mid-copy.

**Three findings that shape the fix:**

1. **No values were corrupted.** All 17 pages compared identical before and
   after four concurrent trials. This damages the *build*, not the record.
2. **The failed render still wrote its freeze.** The expensive half — execute,
   solve, freeze — completes; only the cheap site-assembly step dies. So the
   work is not lost, but `verifiers.render()` checks the exit code and would
   report `render FAILED`, aborting the write phase and refusing to commit a
   perfectly good entry.
3. **A retry succeeds, in 14 s**, because the freeze is already there and the
   re-render is a cache hit.

**So the lock is for correctness, not timing** — but it is not the only option,
and it may not be the best one:

- **Serialise renders behind one lock per notebook.** Proven to work; costs
  little, since two renders are 35 s against a run's 100–300 s of API latency.
- **Retry on failure.** The freeze survives and a retry is a 14 s cache hit.
  Cheaper under low contention, and it degrades rather than blocks — but it is
  a race, so N agents make retries themselves collide.
- **Both**: a lock around the render, and a retry for the case the lock does not
  cover (a human running `quarto preview` in another terminal, which no lock
  inside `nb` can see).

Recommended: **lock plus one retry.** The lock handles agents, the retry handles
everything outside `nb` — and the retry is nearly free given the freeze
survives.

---

## What the coordinator needs, that already exists

- **The chapter dependency graph is derivable.** Rule 31 fork headers name each
  chapter's parent: `01 ← 02 ← 03 ← 04` parses straight out of `_model.py`.
  Useful for ordering, **but not an exclusion** — see below.
- **`lint.model_kinship()`** already reports which chapters share a vehicle.
- **`nb eval`** already aggregates runs by model, and would aggregate by agent
  with one more column.
- **Prose logs, not an event stream.** `log.py` decided this deliberately:
  *"A coordinating agent reads prose natively, and JSON costs more."* Keep it.
  The coordinator tails `status.log` per run and reads `proposal.json` when it
  needs something exact.

## Chains can parallelise — the earlier claim was too strong

An earlier draft said chapters in a chain must not be worked at once, because an
agent forking 05 from 04 while another edits 04 forks a moving target. Having
enumerated what actually couples a chapter to its parent, that is wrong in the
general case and right in one narrow one.

What couples a fork to its parent:

| coupling | parallel-safe? |
|---|---|
| the copied `_model.py` / `_analysis.py` | **only if copied from a commit** — see below |
| numbers cited from the parent's entries | already unsolved (`cite()` does not exist); timing, not structure |
| `check` re-proving siblings | scoped to one chapter — no cross-chapter effect |
| the chapter index freeze | per chapter |
| chapter number allocation | already atomic (`mkdir` reservation) |

**The one real hazard is the copy, and it is already half-solved.** Rule 31
requires the fork header to name *the commit it was taken at* — so the fork is
conceptually pinned already. But `forking.md` says *"Copy with `cp`"*, i.e. from
the **working tree**, which means a fork taken while the parent is dirty copies
another agent's unfinished work *and* writes a commit hash that does not
describe what was copied. The header becomes a lie.

**Mitigation: fork from the commit, not the tree.** `git show <ref>:<path>`
instead of `cp`, with `<ref>` defaulting to HEAD and recorded in the header. Two
lines, and it makes the header true by construction rather than by discipline.
It is worth doing even single-threaded: today nothing stops a fork being taken
from a half-finished edit.

Once forks come from commits, a chain is no more coupled than a fan. A fork is a
snapshot by design — 03 does not track 02's later changes, and that is the whole
point of `forking.md`'s criterion ("the old answer stays valid under its own
stated assumptions").

**What remains a genuine exclusion: two agents in the same chapter.** That is
about shared writable `_analysis.py` and rule 2 comparing code across entries,
and it is unchanged.

**What remains a scheduling concern, not an exclusion:** an entry that wants to
cite its parent's answer needs that answer committed first. The coordinator
should sequence on *answers it needs*, not on the chapter graph — which is a
looser and more accurate constraint.

## Tools considered

| | verdict |
|---|---|
| `fcntl.flock` (stdlib) | **use** — POSIX advisory locks, no dependency, matches the project's no-framework stance |
| `filelock` / `portalocker` | better tested and cross-platform; not worth a dependency for a macOS/Linux tool |
| SQLite WAL + `busy_timeout` | **use** — two pragmas, solves the metrics db outright |
| `git worktree` | rejected for chapters (see 1b); right for cross-notebook |
| Celery / RQ / Huey | rejected — needs a broker for N≈4 local subprocesses |
| An MCP server for answers | rejected — the project already runs one for the filesystem, and this would be a second protocol where two JSON files suffice |
| `concurrent.futures` in-process | rejected — agents are subprocesses today, which gives isolation and a real exit code for free |

---

## Order of work

**Two agents become correct at step 3; usable at step 5.** Steps 2–3 are
mechanical and loud when they fail; 4–5 are the interface.

1. ~~Measure concurrent quarto.~~ **Done** — fails reproducibly on
   `_freeze/site_libs/`, corrupting no value. See problem 3.
2. **Run-scoped scratch** (1a) + sqlite WAL. Worth doing single-user anyway:
   run artefacts stop being clobbered by the next run.
3. **Render lock + one retry.** Parallel runs are now correct.
4. **`--mailbox` questions and `--detach`.** Agents stop reading stdin: they
   write `question.json`, poll, and on timeout exit with the question on disk.
   `nb answer` covers the scripted case and any second terminal.
5. **`nb board`** — the single terminal: tagged live stream, pending questions,
   inline answering. This is the deliverable the whole thing is for.
6. **Fork from a commit** (`git show` rather than `cp`), making the rule 31
   header true by construction and removing the only real chain hazard. Worth
   doing single-threaded too.
7. **`--answers` pre-answers**, to cut how often the board is interrupted at all.
8. **Coordinator agent**: writes `answer.json` instead of the user typing.
   Nothing else changes, and `nb board` keeps showing the conversation.

## Verification

- **Two agents, two chapters, one notebook, to commit.** Both entries land, both
  freezes correct, `nb.corpus` unchanged, and neither run's `proposal.json`,
  probe script or metrics row is attributable to the other.
- **The probe-script race, deliberately.** Two agents probing within a second;
  each result must match its own question. This is the failure that is silent
  and plausible, so it needs a test rather than an observation.
- **A question under `--coordinator`** is answered through the mailbox without
  the agent losing its probe history — measured by the pool spend before and
  after, which must not reset.
- **Timeout falls back cleanly**: no answer written, agent exits, question is on
  disk, `nb write` resumes.
- **The single-user path is untouched**: the same `nb ask` at a terminal, no
  flags, behaves exactly as today.
- **Load**: N agents' rendered values must equal the values they produce alone.
  A render killed by a neighbour is the regression to watch for.
- **The render race is actually fixed**: repeat the measured experiment through
  `nb` rather than raw quarto — four concurrent renders, zero failures. Without
  the lock it failed 4 times out of 4.
- **A chain forks cleanly under load**: one agent adding entries to a chapter
  while another forks it; the fork's content must equal `git show <ref>:<path>`
  for the ref in its own header, and must not contain the first agent's
  uncommitted work.
- **The conversation is observable**: after a run that asked something, the
  question and its answer are both on disk and both appear in `nb board`,
  whether a person or a coordinator answered.
- **The board is a view, not a supervisor**: kill `nb board` mid-question and
  the agent must still be waiting; restart it and the question must reappear.
  Answering from a second terminal with `nb answer` must release the agent
  while the first board is not even running.
- **It scales to the number actually wanted**: launch eight detached asks across
  eight chapters and drive them from one board. What to watch for is not
  correctness but legibility — whether a tagged line stream is still readable at
  that count, which is what decides whether `rich` is earned.

## Out of scope

- **Two agents in the same chapter.** `_analysis.py` is shared writable
  state, and rule 2 compares code *across* entries — two agents can each pass
  lint alone and violate it jointly, with the gate firing on whoever commits
  second.
- **Cross-notebook parallelism**, which needs none of this.
- **`cite()`** and the cross-chapter baseline, unchanged.
