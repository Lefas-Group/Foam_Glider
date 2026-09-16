# Cross-chapter parallelism, and a coordinator instead of a person

**Status: plan, not implemented.**

The target is **N agents on different chapters of one notebook, launched and
answered from a single terminal**, with a coordinator agent eventually taking
over the answering while the user still watches.

In one paragraph: give every run its own scratch directory, put a lock and a
retry around **rendering only**, and move the three blocking prompts onto files so that
`nb board` — one terminal — can show every run and answer any of them. Parallel
runs become **correct** after the second of those and **usable** after the
board. Files rather than pipes throughout, because a coordinator that restarts
has to be able to pick the conversation back up, and scrollback is not state.

One thing was measured rather than assumed: **two concurrent `quarto render`
calls on one project fail, four times out of four**, on `_freeze/site_libs/` —
without corrupting any value, and with the freeze surviving. That is why the fix
is a lock plus a retry rather than either alone.

One finding is not about parallelism at all: the heaviest entries render in
**11–13 s against a 15 s solve budget**, so a background compile is already
enough to kill a solve mid-render — which then asks the model to fix a
non-existent bug in a correct entry. Worth fixing whether or not any of the rest
is built.

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

**Three things stand in the way** — shared files, the question interface, and
machine load — and they are independent enough to land separately. Two further
sections follow them: where the coordinator's context comes from, and why
chapters in a chain turn out to parallelise after all.

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

### Run-scoped scratch

```
_scratch/runs/<run-id>/   proposal.json · transcript.jsonl · status.log · probe.py
_scratch/nb-metrics.db    shared, with WAL
```

`run-id` is short and sortable — `20260916-a3f2`. `Notebook` already centralises
every path (`proposal_path`, `transcript_path`, `run`), so this is a constructor
argument threaded through, not a search-and-replace.

Useful even single-user: each run's artefacts stay inspectable afterwards
instead of being overwritten by the next one.

The one wrinkle is that `nb write <notebook>` with no run id becomes ambiguous.
Resolve it by defaulting to the most recent run and printing the id chosen, so
the resume path stays a single command.

### sqlite

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

**`--detach` implies the mailbox**, because a detached process has no terminal
to read: one flag, not two. Agents in this mode never touch stdin. They write questions to files and
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

### Rendering: adopt `rich`

An earlier draft argued for plain stdio on the grounds that `watch.py` already
dims by hand. That reasoning was weak, and the evidence is that the hand-rolled
dimming **does not render**.

Diagnosed: the code is correct — `_styled()` does emit `\x1b[2m` around gutter
lines, verified against real log lines — but **SGR 2 (faint) is the least
supported ANSI attribute there is**, ignored outright by macOS Terminal.app
among others. The immediate fix is one character class: `\x1b[90m` (bright
black) or `\x1b[38;5;244m` (256-colour grey), both near-universal. That fix is
worth making regardless of what follows, and it is independent of any
dependency.

But hand-rolled escapes are the wrong substrate for a board carrying eight
concurrent runs, and the faint bug is a fair sample of why: every attribute is a
guess about the terminal, tested only by looking.

**`rich`, not `textual`.**

| | |
|---|---|
| **`rich`** | a *printing* library. `Live` + `Table` gives a refreshing run table above a scrolling log, which is exactly the board's shape. Detects `isatty()` itself and strips styling when piped, so "output must survive a pipe" is handled by the library rather than by a flag we maintain. Synchronous — no restructuring. |
| **`textual`** | a full TUI *application* framework: async event loop, widgets, mouse, focus. Justified for scrolling panes per agent and keyboard navigation; for a table plus a question prompt it is a large amount of machinery and an async rewrite of a synchronous program. |

Recommended: **`rich` in the `nb` dependency group**, used in three places:

- **`nb board`** — a `Live` table of runs (chapter, phase, turn, last line,
  waiting-on) above the tagged stream, with the pending question rendered as a
  panel rather than as prose competing with the log.
- **`nb watch`** — replace the hand-rolled `DIM`/`RESET` and the manual
  `isatty()` branch. This is where the bug is.
- **the run's own conversation output** — the boxes drawn today with `─ * 72`
  and the answer block assembled by `_readable()` are both doing by hand what
  `rich` does properly, including the wrapping that currently assumes 80
  columns because a file cannot be re-flowed.

**What NOT to let it touch:** `status.log`. The log is plain text on purpose —
read by `tail`, by `grep`, and eventually by a coordinator agent — and the
writer/reader split (*"the run emits facts; `nb watch` decides when they have
stopped arriving"*) depends on it staying that way. `rich` belongs on the
reading side only. That constraint is the same one that made the dimming live
in `watch.py` rather than in `log.py`, and it survives this change intact.

### Alternatives, and why not

| | why not |
|---|---|
| **named pipes (FIFO)** | no trace once read, so the user cannot observe or audit; open() blocks until both ends attach; nothing survives a restart |
| **unix socket / local HTTP** | same observability objection, plus a server to supervise. Robust and standard, and still the wrong shape for a system whose state is files |
| **one supervisor process owning stdin** | good UX, but it becomes a thing to keep alive, and a crashed supervisor takes every agent's question with it |
| **`rich`** | **use** — for the board, `nb watch`, and the conversation output. Not for `status.log`, which stays plain. The one dependency this plan adds, and it is on the READING side only: nothing an agent writes depends on it |
| **`textual`** | rejected — an async TUI framework where a live table suffices |
| **Celery / RQ / Huey** | a broker for N≈4 local subprocesses |
| **MCP server for answers** | the project already runs one for the filesystem; a second protocol where two JSON files suffice |

### Either way: pre-answers

`nb ask --answers answers.json`, consulted before anything is asked. Trivial,
independently useful for scripted sweeps, and it reduces how often the mailbox
is needed at all. It does not replace it — anticipating every Specified input is
exactly the judgement `ask_specified` exists because models get wrong.

**Do not break the single-user path.** Interactive stdin stays the default; the
mailbox arrives with `--detach`, so a person at a terminal sees exactly what
they see today.

## Problem 3 — load, and the deadline I removed

Two measurements already on record, both in the repo:

- *"the same solve measured 533.9 s against a 145 s baseline purely from machine
  load, 3.7x"* (`lint.py`)
- *"Never run two heavy probes at once. Both starve and neither number means
  anything."* (`probing.md`)

The render deadline used to carry 4× slack for exactly this. **That slack was
removed**, so `ENTRY_CEILING` is now execution time with no headroom. Under
N-way concurrency, honest renders will be killed.

**How much is actually serialised — measured, not assumed.** Across 16 runs with
a real solve measurement, the **median CPU fraction of a phase is 2.3%**: solves
of 1–17 s inside phases of 100–1400 s. The rest is API latency. Adding the
render floor (~11 s of kernel and pandoc, ~3 renders an entry) gives roughly
**48 s of serialisable work in a 458 s entry — about 10%**.

| agents | utilisation of the serialised resource |
|---|---|
| 2 | 21% |
| 4 | 42% |
| 8 | 84% — queueing begins to bite |

So serialising costs almost nothing up to four agents and starts to matter near
eight, where the render lock becomes the ceiling. The machine has 8 cores
and IPOPT is single-threaded, so four concurrent solves would not starve each
other even unlocked. The lock is bought for *correctness* of the render, and it
implies no probe serialisation at all.

Options, in increasing order of honesty:

- **Inflate every grant by the fan-out.** Puts the slack back, invisibly, in a
  number the coordinator has to compute. Worst of both.
- **A concurrency-aware deadline**: `floor + ceiling × active_agents`, with the
  active count read from the run directories. Honest and automatic, but the
  ceiling stops meaning "seconds of solving" and starts meaning something
  conditional.
- **Lock the RENDER only.** Not probes — see below. Agents overlap on thinking,
  which is ~98% of the wall clock, and queue on the one operation that provably
  breaks. **Recommended.**

### Budgets under load: keep wall clock, fix only the kill

Serialising probes was proposed for **budget accuracy**. It is not worth it, and
neither is changing the clock the pool is charged in.

Five things are measured in wall clock, and all of them over-charge under load:
the probe pool, the probe watchdog, `ipopt.max_wall_time`, `aero_cost` (and so
`render_cost_s`), and rule 17 judging the footer.

**Measured inflation**, identical work against N competitors:

| concurrent | CPU | wall |
|---|---|---|
| 1 | 0.92 s | 0.97 s |
| 2 | 1.71 s | 1.89 s |
| 4 | 1.87 s | 2.19 s |
| 8 | 2.10 s | 3.29 s |

CPU is **not** work-invariant either — 2.0× against wall's 2.3× at N=4 — because
this machine has 4 performance and 4 efficiency cores, and displaced work lands
on a slower one. There is no cheap clock that measures work.

**So accept the inflation.** The decisive fact is what happens when the pool
runs out, and it is *graceful*: the agent is told to *"propose now with what you
have, and say in `rationale` what you did not get to."* The consequence of a
shrinking effective budget is **less exploration, recorded in the entry** — not
a failed run, not lost work. A sanity bound that degrades by writing down what
it skipped is behaving correctly.

Wall clock also keeps the prompt honest: *"seconds of exploring"* means elapsed
seconds, which is what the person granting it experiences. Charging CPU would
make the granted number mean something the user cannot observe.

**One number to revisit.** The worst run on record spent 55 s of its 120 s pool
unloaded; at N=4 that becomes ~124 s, just over. So heavy runs will start
hitting the cap at four agents. Either widen the pool when fanning out, or
accept the graceful degradation — both are defensible, and the prompt already
takes a value per run, so a coordinator can simply grant more when it knows how
many agents are running.

**Killing a starved solve is fine in a PROBE and bad in a RENDER**, and the two
go through the same `_budgeted_solve`.

In a probe it is the budget working. The agent asked for 15 s, took longer, and
gets told so; it raises `budget_s` and re-probes. Cheap, visible,
self-correcting — there is no case for protecting it.

In a render it is destructive for a reason that has nothing to do with budgets:
a failed render **hands its traceback to the model and asks it to fix the
cause** (`MAX_RENDER_FIXES`). A solve killed by a neighbour therefore presents
as a code error in an entry that is correct, and the model may edit it to fix a
race — after which the retry renders cleanly and the spurious edit ships.

**And the headroom is already thin, today, without any parallelism.** The
heaviest entries on record render in 11–13 s against a 15 s `SOLVE_BUDGET`:
1.25×. A background compile is enough. Parallelism does not create this; it
makes it routine.

So: **apply the wall limit only outside a Jupyter kernel.** `_notebook.py`
already computes `_IN_KERNEL`, which is exactly the probe/render distinction,
and `_budgeted_solve` reads its globals at call time. Two lines:

- **probe** — `max_cpu_time` *and* `ipopt.max_wall_time`, plus the watchdog. The
  wall contract is enforced strictly, as granted.
- **render** — `max_cpu_time` only. Still bounded twice: by CPU, and by the
  render deadline, which has its own floor.

Accounting stays in the clock the user granted. The kill switch is strict where
being killed is cheap, and lenient where being killed corrupts an entry.

### The lock is for rendering. Probes need run-scoping, not a lock

Worth separating, because an earlier draft said "probe subprocesses and renders"
and only the second was measured.

**A render writes to project-level state.** `_freeze/site_libs/` and `.quarto/`
belong to the Quarto *project*, and every render touches them even when
rendering one page. That is the measured failure, and it cannot be made
finer-grained than one lock per notebook, because the contended directory is
per-notebook.

**A probe writes to nothing shared, once run-scoped.** It reads `_notebook.py`,
`_model.py` and `_analysis.py` — reads only — and writes exactly two things,
both of which are collisions that run-scoping fixes rather than a lock:

- `_scratch/_nb_probe.py`, the script, which is problem 1's dangerous case
- `_scratch/_probe_fig.png`, the figure filename `probing.md` documents

Move both under `_scratch/runs/<id>/` and set the probe's `cwd` there, and two
probes share nothing. The `sys.path` insert in `probe_base` is already absolute,
so it survives the cwd change.

**That leaves only CPU contention, which is not currently a problem**: 8 cores,
single-threaded IPOPT, and a median 2.3% CPU fraction per phase. Locking probes
would serialise the cheapest part of the run for no measured benefit.

**When that would change:** a probe doing a multistart or a sweep is a different
animal, and the 3.7× inflation on record came from exactly that. The design
should leave room for an optional probe lock — same `flock` helper, different
lock file — without taking one now.

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

## Where the coordinator's context comes from

Mostly from things that already exist, and — importantly — **the same things the
agents read**. There is no bespoke coordinator format to invent or keep in step.

### Results: the manifest, already built

`manifest.build()` is the ledger of what the notebook knows: one line per entry,
stem plus title plus the hero answer, read from the **committed freeze** rather
than the source, so it carries `0.36 m/s` and not
`{python} f"{res['sink']:.2f}"`. 17 entries, 2.5 kB, regenerated on every commit
and never hand-maintained — it picked up a chapter created minutes ago without
anyone touching it.

It is already in every agent's prefix, with the instruction that a computed
value contradicting one of these is a *correction* to be stated, never a silent
overwrite. The coordinator reading the same block means coordinator and agents
cannot disagree about what is known.

### History: `nb-metrics.db`, already built

One row per phase: model, chapter, entry stem, turns, lint calls, first-pass
violations, solve seconds, outcome, duration. `nb eval` already aggregates it.
This is how the coordinator answers "is this working?" — which chapters cost
most, where runs die, whether a model change helped.

**Its gap: the row is written only on `close()`.** A running agent has no row at
all, so the db is history and cannot be a live view.

### Live: the one piece missing

Today the only marker of a live run is the pid in the `status.log` header, which
`nb watch` parses to tell a wedged run from a dead one. That is enough for one
run and not enough for eight.

Add `_scratch/runs/<id>/run.json`, written at start and updated at each phase
transition:

```json
{"run": "20260916-a3f2", "pid": 81234, "chapter": "04-thinner-foam",
 "question": "how stable is it?", "phase": "ask", "turn": 7,
 "started": "...", "waiting_on": null}
```

`nb board` needs exactly this to draw its table, so the board and the
coordinator consume one file rather than two mechanisms. `waiting_on` names the
pending question, which is how "who is blocked" is answered without opening
every run directory.

### Conversation: this is what the mailbox is really for

The strongest argument for files over a supervisor's pipes is not ergonomics —
it is that **a coordinator's context does not survive its own scrollback**. An
agent coordinator will be compacted, restarted, or handed over mid-flight. If
the questions and answers lived in a terminal, that history is simply gone, and
the coordinator re-asks things the user already settled.

With `question.json` / `answer.json` per run, the conversation is durable and
greppable: a restarted coordinator reconstructs what was asked, what was
answered, by whom, and when — by reading files, which is the one thing it can
always do.

**Answers already reach the permanent record** by a separate path: `propose`
merges them into `inputs`, the entry writes them into its `## Specified`
callout, and chapter-level commitments land in `index.qmd` — which the prefix
carries for every chapter. So "what has the user already told us about this
chapter" is answered today. What the mailbox adds is the *cross-run, in-flight*
view: what is being asked right now, and what was answered in the last hour but
is not yet committed anywhere.

### What this means for the design

The coordinator needs no new context pipeline. It needs:

- the manifest — **exists**
- the metrics db — **exists**
- a live run registry — `run.json`, small, and needed by `nb board` anyway
- a durable conversation — the mailbox files, which is the reason to prefer
  them over any transport that leaves no trace

Three of the four are already built or already required for other reasons. That
is the argument for the file-based design, restated: not that files are
convenient, but that they are the only form of state a restarted agent can pick
back up.

## What else already helps

- **The chapter dependency graph is derivable.** Rule 31 fork headers name each
  chapter's parent: `01 ← 02 ← 03 ← 04` parses straight out of `_model.py`.
  Useful for ordering, **but not an exclusion** — see below.
- **`lint.model_kinship()`** already reports which chapters share a vehicle.
- **Prose logs, not an event stream.** `log.py` decided this deliberately:
  *"A coordinating agent reads prose natively, and JSON costs more."* Keep it.
  `rich` goes on the reading side only — the log stays plain text, which is what
  lets `tail`, `grep`, `nb board` and a coordinator all read the same file.

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
| `fcntl.flock` (stdlib) | **use** — POSIX advisory locks, ~30 lines, no dependency |
| `filelock` / `portalocker` | better tested and cross-platform; not worth a dependency for a macOS/Linux tool |
| SQLite WAL + `busy_timeout` | **use** — two pragmas, solves the metrics db outright |
| `git worktree` | rejected — `_freeze/` is committed, so every merge conflicts over generated JSON, and it hides collisions rather than preventing them: two agents editing one `_analysis.py` merge cleanly into an entry neither validated. Right for cross-*notebook* work, which needs no isolation anyway |
| Celery / RQ / Huey | rejected — needs a broker for N≈4 local subprocesses |
| An MCP server for answers | rejected — the project already runs one for the filesystem, and this would be a second protocol where two JSON files suffice |
| `concurrent.futures` in-process | rejected — agents are subprocesses today, which gives isolation and a real exit code for free |

---

## Files

| path | change |
|---|---|
| `nb/config.py` | `Notebook(root, run_id=None)`; `run`, `proposal_path`, `transcript_path` and the probe script move under `_scratch/runs/<id>/`. 19 call sites reference these |
| `nb/metrics.py` | WAL + `busy_timeout`; write a `run.json` row at START as well as the db row at close |
| `nb/tools/probe.py` | probe script and figure into the run directory, and `cwd` with them. No lock: a probe writes nothing shared once scoped |
| `nb/tools/verifiers.py` | render under a notebook lock, with one retry |
| `nb/vendor/notebook.py` | `_budgeted_solve` sets `ipopt.max_wall_time` only when `not _IN_KERNEL` — strict in probes, CPU-only in renders |
| `nb/locks.py` *(new)* | a `flock` context manager; ~30 lines. Used by the render; left available for an optional probe lock if probes ever get heavy |
| `nb/tools/interact.py` | mailbox path for the three blocking prompts, behind `--detach`; stdin path unchanged |
| `nb/phases/board.py` *(new)* | the single terminal: run table, tagged stream, question panel, answering |
| `nb/phases/answer.py` *(new)* | `nb answer <run> "…"` — one file write, for scripts and second terminals |
| `nb/phases/ask.py`, `write.py` | `--detach`, `--answers`, and a run id through to `Notebook` |
| `nb/phases/watch.py` | `rich` in place of the hand-rolled dimming; follow all runs |
| `nb/tools/scaffold.py` | fork from `git show <ref>:<path>` rather than the working tree |
| `nb/vendor/references/forking.md` | "Copy with `cp`" becomes "copy from the commit" |
| `nb/vendor/references/probing.md` | the documented figure path `_scratch/_probe_fig.png` becomes run-relative |
| `pyproject.toml` | `rich` in the `nb` group |
| `nb/README.md` | the new commands and the parallel model |

Everything in `vendor/` except `forking.md` is untouched: no lint rule changes,
so `nb.corpus` should not move at any point.

## Open questions

Worth deciding during the work rather than pretending they are settled:

- **The render lock cannot cover a human.** `quarto preview` in another terminal
  is outside `nb` and no advisory lock inside it will help. Worse than a plain
  failure: a failed render now **hands its traceback to the model** and asks it
  to fix the cause (`MAX_RENDER_FIXES`), so a race presents as a code error in
  an entry that is fine, and the model may make a spurious edit that then
  renders cleanly on the retry and ships. Detecting a live preview and warning
  is cheap; letting the model try to fix `utime` on `site_libs` is not.
- **Does `rich`'s `Live` cooperate with a blocking prompt?** The board must
  stop refreshing while the user types, or the input line is repainted away.
  `Live.stop()`/`start()` around the prompt is the expected answer, and it needs
  trying before the board's shape is fixed.
- **What is the mailbox timeout?** Too short and a user who steps away loses a
  run; too long and a wedged coordinator holds an agent all night. It probably
  wants to be generous (an hour) and paired with `run.json` making the wait
  visible, rather than short and safe.
- **How much does `_readable()` move to `rich`?** It currently wraps at a fixed
  76 columns because the same text goes to a file. If the terminal and the log
  diverge in formatting, that is two renderings to keep in step — the same trap
  `log.py` avoided once already.
- **How far does the render lock scale?** With billing expanded, quota stops
  being the ceiling and the render lock becomes it. One entry needs ~33 s of
  render behind a per-notebook lock; at N=8 that is ~84% utilisation and runs
  start queueing noticeably. The lock cannot be made finer — the contended
  directory is the Quarto project — so genuinely large fan-out would mean
  several notebook *copies*, which is cross-notebook parallelism wearing a
  different hat. Worth knowing before promising N=8 on one notebook.

## Order of work

**Correct at step 3, usable at step 6.** Steps 2–4 are
mechanical and loud when they fail; 5–6 are the interface.

1. ~~Measure concurrent quarto.~~ **Done** — fails reproducibly on
   `_freeze/site_libs/`, corrupting no value. See problem 3.
2. **Run-scoped scratch** + sqlite WAL, plus `run.json` per run — the live
   registry `nb board` and a coordinator both read. Worth doing single-user
   anyway: run artefacts stop being clobbered by the next run.
3. **Render lock + one retry.** Renders only — probes need nothing beyond
   step 2. Parallel runs are now correct.
4. **`ipopt.max_wall_time` only outside a kernel** — strict in probes, where a
   kill is cheap and self-correcting; CPU-only in renders, where a kill
   presents as a code error and invites a spurious fix. Worth doing regardless
   of parallelism: the heaviest entries are at 1.25× of the solve budget today.
5. **`--detach`.** Agents stop reading stdin: they
   write `question.json`, poll, and on timeout exit with the question on disk.
   `nb answer` covers the scripted case and any second terminal.
6. **`nb board`** — the single terminal: tagged live stream, pending questions,
   inline answering. This is the deliverable the whole thing is for.
7. **Fork from a commit** (`git show` rather than `cp`), making the rule 31
   header true by construction and removing the only real chain hazard. Worth
   doing single-threaded too.
8. **`--answers` pre-answers**, to cut how often the board is interrupted at all.
9. **Coordinator agent**: writes `answer.json` instead of the user typing.
   Nothing else changes, and `nb board` keeps showing the conversation.

## Verification

- **Two agents, two chapters, one notebook, to commit.** Both entries land, both
  freezes correct, `nb.corpus` unchanged, and neither run's `proposal.json`,
  probe script or metrics row is attributable to the other.
- **The probe-script race, deliberately.** Two agents probing within a second;
  each result must match its own question. This is the failure that is silent
  and plausible, so it needs a test rather than an observation.
- **A question under `--detach`** is answered through the mailbox without
  the agent losing its probe history — measured by the pool spend before and
  after, which must not reset.
- **Timeout falls back cleanly**: no answer written, agent exits, question is on
  disk, `nb write` resumes.
- **The single-user path is untouched**: the same `nb ask` at a terminal, no
  flags, behaves exactly as today.
- **Load**: N agents' rendered values must equal the values they produce alone.
  A render killed by a neighbour is the regression to watch for.
- **A probe still respects its wall budget.** Give a probe a solve budget it
  cannot meet and confirm it is still killed and still says why. Leniency here
  would be a regression, not a fix.
- **A render is not killed by a neighbour.** Render the heaviest entry (13 s
  against a 15 s budget) while three probes run. Before the change it should
  die and the write phase should ask the model to fix a non-bug; after it, it
  should render late and unchanged. That second half — that the model is not
  invited to edit a correct entry — is the point of the change.
- **Pool exhaustion stays graceful under load.** A run that hits its pool
  because of its neighbours must still commit an entry, with `rationale`
  recording what it did not get to. If it fails instead, the accepted trade-off
  has not held.
- **The render race is actually fixed**: repeat the measured experiment through
  `nb` rather than raw quarto — four concurrent renders, zero failures. Without
  the lock it failed 4 times out of 4.
- **A chain forks cleanly under load**: one agent adding entries to a chapter
  while another forks it; the fork's content must equal `git show <ref>:<path>`
  for the ref in its own header, and must not contain the first agent's
  uncommitted work.
- **A restarted reader loses nothing.** Kill `nb board` and any coordinator
  mid-flight, then reconstruct from files alone: which runs are live
  (`run.json`), what each has answered so far (`question.json`/`answer.json`),
  and what the notebook knows (`manifest`). If that reconstruction needs
  scrollback, the design has failed its main purpose.
- **The conversation is observable**: after a run that asked something, the
  question and its answer are both on disk and both appear in `nb board`,
  whether a person or a coordinator answered.
- **The board is a view, not a supervisor**: kill `nb board` mid-question and
  the agent must still be waiting; restart it and the question must reappear.
  Answering from a second terminal with `nb answer` must release the agent
  while the first board is not even running.
- **It scales to the number actually wanted**: launch eight detached asks across
  eight chapters and drive them from one board, and confirm the run table stays
  readable at that count.
- **Styling actually renders.** The bug being fixed is invisible in code review
  — `_styled()` emits the right escape and the terminal ignores it. Check the
  rendered output by eye, in the terminal that is actually used, not by
  asserting on the bytes.
- **Piping still works.** `nb board` and `nb watch` through a pipe must emit no
  escape sequences at all, and `status.log` must stay plain text whatever the
  reader does.

## Out of scope

- **Two agents in the same chapter.** `_analysis.py` is shared writable
  state, and rule 2 compares code *across* entries — two agents can each pass
  lint alone and violate it jointly, with the gate firing on whoever commits
  second.
- **Cross-notebook parallelism**, which needs none of this.
- **`cite()`** and the cross-chapter baseline, unchanged.
