# Directing a run

**Status: Stages 1-3 done.** `b81da9a` render scope, `cc5f348` `consult`,
`faa1c01` `verify`, `e719253` always-detached, `82aaae7` budgets — on branch
`nb-render-scope`. Stages 4-7 unstarted; Stage 8 scoped and not recommended yet. Every number was measured on
2026-09-21 against the three notebooks, the eight run directories in
`glider-notebook/_scratch/runs/`, and the 65 rows in their metrics databases;
re-measure before starting, because two stages are calibrated against counts that
move when entries are added.

Six defects, found in one review. They share a shape: **the run decides
something that is not the agent's to decide, or records it where nothing can
read it back.** Inputs the user should have been asked for go unasked. Budgets
the user owns are prompted for every run instead of assigned. A fork's
differences — the one thing that *is* the chapter — are free text in a comment.
The entry's visual form is left to a preference the model has twice been told
and twice not followed. A render executes one page or sixteen with nothing
saying which, or why. And three mechanisms are carried for cases that do not
occur, one of them a whole extra model call per entry.

## Three things that shape every stage below

**Guidance is not a guard.** navigation.md Stage 4 landed the diagram preference
on 2026-09-18 as a field description, is marked implemented and verified, and
behaviour did not move — one figure in the four entries written since. That is
evidence about the mechanism, not about the model, and four of the seven stages
are written accordingly.

**Retrofit cost is a schedule input, not a design input.** An earlier draft let
it decide one thing outright, keeping two records of the same fact because
reconciling them would re-prove some chapters. That is the wrong trade for a
system whose whole argument is that a record nothing checks goes stale. It is
also smaller than assumed: measured from their own freezes, the four forked
chapters re-prove in **86 seconds** of render, not the "tens of minutes" the
rule-of-thumb in `guards.py` suggests.

**Most of this is not new machinery.** The assumption gate, its correction loop,
the new-chapter stop, and `check.py`'s scope reporting all exist and all run.
What they are missing is anything to show. The largest single change is a
deletion.

---

# What is actually wrong, with evidence

## 1. Asking is voluntary, so it stopped happening

Across the eight recorded runs in `glider-notebook/_scratch/runs/`:

```
ask_specified fired in      3 of 8 runs
consult fired in            0 of 8 runs
proposals with inputs: []   4 of 8
```

A proposal with an empty `inputs` list means `confirm_assumptions` hit its
`if not assumed: return []` early exit (`nb/tools/interact.py:226`) — so the
"confirm once" gate, the whole reason that function exists, **silently never ran
on half the runs**. It did not decline to fire. Nothing asked it to.

What is skipped is more than a prompt. Behind that early exit sits a correction
loop that re-enters the probe when the user changes an assumption
(`nb/phases/ask.py:174-204`), precisely so an entry is never written from
findings computed under a rejected premise. **That whole mechanism has been
inert.** The same is true of the other gate: the new-chapter stop
(`nb/phases/ask.py:221`) fires reliably, but `render_stop` shows a chapter name
and a resume command and nothing about what the chapter inherits.

The decline shows in the committed record, and tracks the move from the
Claude-era skill to nb+Gemini:

| notebook | entries | with `## Specified` | with `## Assumed` |
|---|---|---|---|
| aircraft-notebook (skill era) | 28 | 17 | 12 |
| optimised-glider-notebook | 23 | 6 | 20 |
| glider-notebook (nb era) | 26 | **4** | **5** |

Two causes, and only the second is cheap to fix.

**`propose` validates the converse case only.** `nb/tools/interact.py:367`
catches an input recorded as `owner='user'` that was never put through
`ask_specified` — a claim of an ask that did not happen. Nothing catches the
opposite and far more common failure. An empty `inputs` list passes in silence.

**The taxonomy asks for a judgement the model gets wrong.** Derivable /
Specified / Unknown (`nb/system_instruction.md:15-17`) requires the model to
classify *before* it can know whether to ask, and rule 4 exists because that
classification fails. Asking also costs turns against a pool the model can see.

## 2. Budgets are prompted every run, and the detached prompt has no number on it

**Attached, the default is shown but not explained.** `ask_budget` writes the
caret as `[120] >` and `[200] >` (`nb/tools/interact.py:134`). It does not say
what the number means or where it came from, and the two come from different
places:

```
probe pool      config.PROBE_POOL = 120.0            nb/config.py:128
render ceiling  lint._defaults(notebook.root)        nb/phases/ask.py:123-125
```

The second is deliberate and documented (`nb/config.py:140` — the notebook owns
the number it renders under, and a second copy in `config.py` disagreed once
already). The prompt presents both as bare integers.

**Detached, the default is not shown at all.** The `MAILBOX` branch at
`nb/tools/interact.py:120` passes `default=` to `mailbox.ask` and then prints
only `body`. The default never reaches the question file, so `nb board` renders a
budget question with no number on it. That is a straight bug.

**Assignment already half-works, in one mode.** `mailbox.ask` consults
pre-answers keyed by question *name* (`nb/mailbox.py:60`), so
`--answers '{"PROBE TIME POOL": 180}'` pre-empts the prompt today — but only for
detached runs. An attached run has no way to supply either number.

## 3. A fork's differences are prose, so nothing can read them

The mechanism is a comment header written by `create_chapter`
(`nb/tools/scaffold.py:247`) and finished by hand:

```python
# Forked from chapters/03-unswept-c4/_model.py at 12794f6.
#
# Differences, all deliberate, all following from 3 mm foam instead of 5 mm:
#   * wing sections naca4405 -> naca4403, tail naca0005 -> naca0003, …
#   * fuselage width 0.010 -> 0.006 m, two plies of the thinner foam.
```

Exactly one field is machine-readable — the parent — and it is parsed by a regex
written out twice, independently, both truncating at 2000 bytes:

```
glider-notebook/index.qmd:46                         _FORK, first 2000 bytes
glider-notebook/chapters/04-thinner-foam/index.qmd   the same regex again
```

Rule 31 (`_fork_provenance`, `nb/vendor/lint.py:1943`) checks only that the
header *contains* the required words in its first 1200 characters. It has no view
of whether the differences listed are the differences that exist.

So the arrows on the lineage diagram cannot be annotated: there is no structured
difference to annotate them with. The prose is also unchecked against the code —
a later edit to a forked `_model.py` leaves the header describing a fork that no
longer matches, and nothing says so. That is rule 12's failure mode one level
up, and rule 12 does not reach it.

There are **four** forks, not five: `05-fully-optimized` is at most 84% similar
to 01–04, below the 0.85 threshold, so it is a genuine rewrite and rule 31 is
right not to flag it.

## 4. The diagram preference landed, and behaviour did not move

navigation.md Stage 4 put the preference in `Proposal.figures`
(`nb/schema.py:85-96`, commit `8cb5746`, 2026-09-18):

> "PREFER A DIAGRAM, then a table, then prose: an answer that can be seen should
> be shown, and a paragraph with a number in it is the least interesting form
> the same finding can take."

Four entries have been written since. One carries a figure. The two most recent
both ask what the aircraft *looks like* and both answer with a 4×4 table of
numbers, in a notebook where `draw_three_view()` is available and has been used
in four earlier entries:

```
06-fully-optimized-5mm/2026-09-21-01-what-is-the-geometry-of-…-5-mm-glider.qmd
05-fully-optimized/2026-09-21-01-what-are-the-dimensions-of-…-3-mm-glider.qmd
```

Across all 77 entries:

```
with a figure                36
with a hand-written table     1
with a generated table        5
with neither                 25
```

In glider-notebook, 7 of 26 entries carry a figure. **What replaced figures is
not tables — it is prose with inline computed values.** Tables are what the last
two entries reached for; nothing is what the other eighteen did.

Three things push that way, and the third is a hole:

**The instruction prices visuals out.** `nb/system_instruction.md:219`: "a figure
costs roughly thirty times a small table to read." Defensible as a plot-versus-
table swap, and it reads as a general anti-visual prior.

**Rule 14 allows one visual per entry, total** — a table counts against the same
budget. A three-view schematic *plus* the plot carrying the answer is illegal.

**Rule 14 cannot see the tables the model is writing.** It counts cell labels
(`nb/vendor/lint.py:955`):

```python
labels = re.findall(r"^\s*#\|\s*label:\s*((?:fig|tbl)-[\w-]+)", text, re.M)
```

The 06 entry generates its table into a string and emits it through
`display(Markdown(md))` with no label. The 05 entry uses an inline `{#tbl-plans}`
caption, which is not a cell option either. **Both are invisible to rule 14.** So
"one visual per entry" is unenforced for the form the model currently prefers —
and adding a diagram beside one of those tables would not trip the rule today.

Rule 15 gets this right and is the precedent: it reaches into the rendered
freeze, because "a table produced by `print()` inside an `output: asis` cell is
not parseable as a table anywhere in the source."

## 5. Nothing says which render scope is happening, or why

A render can execute one page or sixteen, and the difference is not where anyone
would guess. `will_execute` records the measurement (`nb/vendor/lint.py:1153`):

```
quarto render chapters/01-foam-glider   5 kernels, 110 s, twice running
quarto render                           0 kernels, every page cached
```

**Quarto honours `freeze` on a PROJECT render only.** Name a target and every
page under it executes, whatever `_freeze/` holds. So targeting a chapter is
often *more* expensive than rendering the whole notebook.

**The model's one piece of scope guidance is wrong in the common case.** The
`render` declaration reads, in full (`nb/tools/__init__.py:71-74`): "quarto
render. Target a single entry path while iterating; the whole notebook is slow."
Against a frozen notebook the whole notebook executes nothing. The advice is
right about the entry and wrong about the alternative, and the model cannot
discover that from the tool.

**What the log says today** is the count only (`nb/tools/verifiers.py:150-152`):

```
render    deadline 60 s (2 page(s) to execute)
```

Not the scope, not who requested it, not why those pages are executing. That line
has been wrong twice, both found on 2026-09-18 and both recorded in the comment
above it: it counted `unfrozen` against a targeted render that ignores the
freeze, and it was sized from the project root while the kill was sized from the
target.

**One caller already does this properly.** `check.py` prints scope and reason
together (`nb/vendor/check.py:500-501`):

```
freeze     set aside 2 chapter(s), 1 page(s); 4 chapter(s) served from cache
           — _analysis.py changed
```

The `why` comes from `_freeze_targets`. **The pattern exists and is missing from
every other render path**: the `render` tool, `write`'s renders behind lint and
verify retries, `view`'s project render, and `create_chapter`'s silent
`rmtree(_freeze/index)`.

## 6. Three mechanisms are maintained for cases that do not occur

**`consult` has never been called.** Zero uses in eight runs, against
`ask_specified`'s three. It is a tool declaration on every ask turn, a handler, a
budget and a branch, and nothing has ever reached it.

**`verify` has never found anything, in 32 write-phase runs.** From
`nb-metrics.db`:

```
verify_findings         0     in every write run recorded
first_pass_violations   0.03  average (one run had 1; the other 31 had none)
lint_calls              2.4   average
```

`verify` is not a tool declaration. It is a whole phase — a second model call
with its own context and the rendered figures embedded, running on **every**
write (`nb/phases/write.py:749-813`). It is described in its own docstring as
"the only justified second model call", and the justification has not produced a
finding yet.

The second number is its own defect. `metrics.py` says of
`first_pass_violations`: "That number is the eval: it is a real measurement over
a real artefact, and it is what should decide a model change or a prompt change
rather than an impression formed over two runs." **It is saturated at zero.** The
metric `nb eval` is built around no longer discriminates between anything, which
is part of why Stage 1 puts render counts in the same table.

**The attached run path is the single-agent case, and single-agent is over.**
`nb ask` at a terminal blocks on stdin; `--detach` writes the question to a file
and waits for a reply. Every question site carries both
(`nb/tools/interact.py:46, 66, 120, 233`), and the two differ in behaviour, not
just plumbing:

| | attached | detached |
|---|---|---|
| unanswered Specified input | `SystemExit`, run dies, nothing on disk | question stays on disk, run resumable |
| who can answer | whoever holds that terminal | board, `nb answer`, a script, a coordinator |
| record of the answer | `say()` into the log | `answer.json`, with `replying_to` |
| survives the reader leaving | no | yes |

**The detached path is better on every row.** The attached path's one advantage
is that it needs no second terminal — and `POLL` is 1.0 s (`nb/mailbox.py:33`),
so the latency difference is imperceptible.

It is also load-bearing in a way that is easy to miss. `log.py` splits `tell()`
from `say()` and argues the split was forced: "Both streams landed on the same
terminal before, so separating them meant redirecting one away — and it cannot be
stdout, because that is where the blocking prompt is typed." **Nothing blocks on
stdin once every run is detached**, and that constraint dissolves.

---

# Stage 1 — Say what is being rendered, and why

**Done — `b81da9a`.** Two things the plan did not anticipate. `nb eval` opened
the metrics db directly and selected current columns, so a notebook whose last
run predated a column failed with `no such column`: the additive scheme
protected the INSERT and left the SELECT to find out, and `migrate()` is now
shared with readers. And the asymmetry is starker than the plan's example — in
`glider-notebook` today, rendering chapter 01 executes 5 pages against an 875 s
deadline while a whole-notebook render executes **nothing**, all 32 cached.

Diagnostic only. No behaviour changes, nothing is gated, `nb.corpus` cannot move.
First because it is the instrument every later stage is watched through — Stage 6
re-renders sixteen entries, and that is exactly when you want the log to say what
it is doing.

| change | where |
|---|---|
| report scope, page count and reason on every render | `render`, `nb/tools/verifiers.py:132-152` |
| carry a `why` from the caller, as `check.py` does | `verifiers.render(target, why=…)`, all call sites |
| flag the targeted-render asymmetry when it costs more than a project render | `_announce` |
| say which freeze trees are deleted and by whom | `create_chapter`, `nb/tools/scaffold.py:272` |
| correct the `render` tool description | `nb/tools/__init__.py:71` |
| renders and pages-executed as columns | `nb/metrics.py` |

**The line to write.** `_announce` already computes both numbers inside the lock,
immediately before the render it describes, from the same `will_execute` call
`render_quarto` deadlines on. It has everything it needs and prints half of it:

```
render  entry · 1 page · deadline 60 s · re-executing (targeted renders ignore the freeze)
render  chapter · 7 pages · deadline 200 s · targeted — a project render would execute 1
render  project · 1 page · deadline 90 s · 15 served from cache
```

The third field does not exist today and is the answer to "why is this taking two
minutes". The second line is worth calling out as it happens: the model asked for
a chapter and bought sixteen times the work it needed.

**Correct the tool description in the same commit.** "The whole notebook is slow"
is the reason a model reaches for a chapter target. Replace it with what
`will_execute` measured. Adding a warning about a choice the tool talked the
model into would be perverse.

**Put the count in metrics too.** `nb-metrics.db` already carries `solves`,
`solve_seconds` and `lint_calls` per phase-run, which is how `nb eval` answers
what a model did without new instrumentation. "This model re-renders the chapter
four times per entry" is currently an impression formed over two runs.

**Pros.** The cheapest stage here. It answers a question currently unanswerable
from the record — `nb watch` shows a run silent for 110 s and nothing says whether
that is one honest page or five needless ones. It makes the freeze asymmetry
teachable rather than lore.

**Cons.** A third field on a dense line, and `say()` is the stream nobody reads
until something breaks — an argument for the metrics columns, not against the
detail. The `why` must be threaded through every caller.

**Risk.** Near zero, with one trap: `_announce` has been wrong twice, both times
by sizing one question with another question's answer. **All three fields come
from the same `will_execute` result**, sized inside the lock.

---

# Stage 2 — Delete what the record says is unused

Three deletions, together because they are the same removal: machinery kept for
a case measurement says does not occur. Early because Stages 3, 5 and 7 all write
into `interact.py` and `write.py`, and doing them first would mean writing code
into paths about to be deleted.

| change | where |
|---|---|
| remove the `consult` declaration, handler and budget | `nb/tools/__init__.py:129`, `interact.py` |
| rename `MAX_CONSULTS` — it also bounds the correction loop | `nb/config.py:81`, `nb/phases/ask.py:174` |
| **extract the build-failure repair loop** before touching verify | `nb/phases/write.py:756-791` |
| delete `phases/verify.py`, `VerifyResult`, `MAX_VERIFY_ATTEMPTS` | `verify.py`, `schema.py:177`, `config.py:83` |
| stop writing `verify_findings`; leave the column | `nb/metrics.py:37, 82` |
| `nb ask` detaches always; `--detach` becomes a no-op alias | `nb/__main__.py`, `nb/phases/ask.py` |
| `nb ask` attaches a board scoped to the new run unless `--quiet` | `nb/phases/board.py`, `ask.py` |
| delete the stdin branch at all four question sites | `nb/tools/interact.py:46, 66, 120, 233` |
| collapse `tell`/`say` now that nothing blocks on stdout | `nb/log.py` |

## `consult`

**Done — `cc5f348`.** Zero calls in 33 recorded ask runs, not eight; the metrics
db reaches further back than the run directories. The rename was load-bearing as
predicted.

Zero calls in eight runs. Delete the declaration, the handler and
`session.consults`; open-ended guidance goes through `ask_specified`, which is
called and which records its answer.

**One trap.** `MAX_CONSULTS` does not only bound `consult` — it also bounds the
assumption-correction loop (`for _ in range(MAX_CONSULTS)` at
`nb/phases/ask.py:174`), a loop Stage 5 is about to make live. Deleting the
constant with the tool would silently uncap that loop. Rename it
`MAX_CORRECTION_ROUNDS` and leave the value at 3.

## `verify`

**Done — `faa1c01`.** The extraction held: `verifiers.build_entry` was proved
against a deliberately broken entry — a bare name in a code cell — before the
model call beside it was deleted. A healthy entry returns `None`; a broken one
returns a `BUILD_FAILED` note carrying the `NameError`, classified as retryable
rather than terminal.

Zero findings in 32 runs, at the cost of a second model call with embedded
figures on every write. Delete the phase, `VerifyResult`, `MAX_VERIFY_ATTEMPTS`,
the `verify_failed` outcome and the retry loop.

**The trap, and it is the whole of this sub-stage: verify does two jobs and only
one of them is dead.** `verify_phase.check()` renders deterministically before it
reads, because "verifying against a stale freeze is worse than not verifying at
all". So the block at `nb/phases/write.py:756-791` is also **the only path that
hands a page that does not build back to the model to fix** — the
`RENDER_FAILED` branch, bounded by `MAX_RENDER_FIXES`, which feeds the traceback
back with a note about `_model.qmd` exec'ing names into scope. Lint has already
passed by then; nothing else would notice.

Unlike verify's zero, **that path's frequency is unmeasured**: `render_fixes` is
a newer column and is absent from all three notebooks' databases, so no recorded
run can say whether it fires. It is not safe to delete something on no evidence
because it sits next to something deleted on good evidence.

So the order within the stage is fixed:

1. **extract** the render-and-repair loop into its own step in `write.py`, keeping
   `MAX_RENDER_FIXES`, the traceback hand-back and `_refresh_index_freeze`;
2. **confirm it still fires** — break an entry deliberately and watch the model
   get the traceback and fix it;
3. **then** delete verify, which by then is only the model call and its retry.

**What survives.** `read_figure` stays: it is declared to the main agent in both
phases (`nb/tools/__init__.py:106`), not only used by verify, though its
docstring's rationale ("verify exists to catch…") needs rewriting to say why an
agent reads its own figures. The deterministic render before commit stays, as
step 1 above. `verify_findings` stays as a column — additive, old rows read
NULL — and simply stops being written.

**What is lost, stated plainly.** Nothing else catches a sentence about a shape
that the figure contradicts: a caption claiming a crossover at 6 m/s when the
curve crosses at 8 is invisible to every lint rule, because rule 1 forces numbers
in prose to be computed but nothing forces a claim about a *shape* to match the
shape. That class of error is now uncaught. The counter-argument is that verify
may have been working as a deterrent rather than a filter — the model knew it
would be read — and the record cannot distinguish a deterrent from a no-op. **We
are accepting that on the evidence available**: 32 runs, zero findings, one full
model call each.

## Always detached

**Done — `e719253`.** Two things the plan did not anticipate. The board could
not be spawned as a side process: `detach_process` exits the original process at
its first fork, so the board goes THERE, in the one process that still has a
terminal, while the agent forks away. And testing caught a regression — through
the mailbox every question waited the full hour, so `--quiet` in CI would have
hung for an hour per budget where a piped run previously took its default the
instant stdin closed. Questions now take their deadline from whether they have a
default: 300 s, matching `stuck.ASK_WAIT`, against the full hour for a Specified
input that has none.

The `tell`/`say` collapse turned out to be free: `tell` already wrote to the log
as well as stdout, so detaching does it. `log.py` needed no change.

`nb ask` forks to the mailbox path in every case, and by default immediately
attaches a board scoped to the run it just started. To the single user nothing
looks different — a question appears, they answer it — but there is one mechanism
underneath instead of two, and closing the terminal no longer kills the run.

**Pros.** Deletes four branches and the entire stdin path, including `_prompt`'s
EOF handling. Every row of the table in §6 improves for the single-user case: a
question survives a closed terminal, is answerable from a second one, and leaves
`answer.json` as a record rather than a line in a log. One agent becomes the N=1
case of N agents rather than a separate mode with its own failure shapes. And it
dissolves the constraint that forced the `tell`/`say` split — with nothing typed
into stdout, the detail stream can go back to the terminal by default, which is
what a single-agent user wants.

**Cons.** It deliberately breaks a promise new.md's verification makes: "the
single-user path is untouched — the same `nb ask` at a terminal, no flags,
behaves exactly as today." That promise was right when detachment was new and
unproven; it has now run eight times. The board is `rich`-rendered and heavier
than a bare prompt, so `--quiet` has to exist for piping and for CI. A run that
dies before writing `run.json` would be invisible to a board only looking for it,
so the board must handle "the run I was started for does not exist yet" rather
than assuming.

**Risk.** Moderate, and the only stage here with real UX risk. Two specific
things: `detach_process` forks before `setup()` starts the MCP subprocess and
before the metrics connection, for a documented reason — "fork past either is how
a daemon inherits something it cannot use" — so the auto-board must be a separate
process, not something spawned inside the forked child. And `nb ask`'s exit code
currently means the ask succeeded; once it detaches always, it means the run
started. Anything scripted against it needs updating, which is the kind of change
that breaks quietly.

---

# Stage 3 — Budgets: show the default, then let it be assigned

**Done — `82aaae7`.** The detached half was worse than the plan described: the
default was not merely unprinted, it never entered `question.json` at all, so
the board had nothing to render even if it had wanted to. `--chapter` needed
enforcement in `propose` as well as the brief — a flag the model can ignore
reports the wrong chapter about as often as no flag.

Pure friction. No new mechanism, no lint rule, no corpus movement. After Stage 2,
`ask_budget` has one branch instead of two.

| change | where |
|---|---|
| put the default and its provenance in the question body | `ask_budget` |
| pass the default into the mailbox question so the board shows it | `nb/tools/interact.py:120`, `nb/mailbox.py:63` |
| `--pool N` and `--ceiling N` on `nb ask` | `nb/__main__.py`, `nb/phases/ask.py:118-125` |
| skip the prompt when either is supplied | `ask.py`'s existing `if pool is None` |
| `--chapter NN-name` to pin an existing chapter | `__main__.py`, `Session`, `propose`'s route check |
| document all three | `USAGE`, `nb/README.md` |

The body should say which number it is and where the default came from — "120 s,
from `config.PROBE_POOL`" against "200 s, declared by this notebook's
`_notebook.py`" — because those are different kinds of number shown identically.

**On pinning the chapter.** Routing to an *existing* chapter and creating a *new*
one are not the same decision, and only the second should stay a gate.
`render_stop`'s docstring makes the argument: a new chapter is a structural
commitment later entries build on. Routing a question into `04-thinner-foam` is
not that — it is a coordinator's instruction, it costs probe turns to rediscover,
and a flag removes a class of misroute. **The new-chapter stop stays as it is.**

**Pros.** Removes two prompts per run from the common case where the caller
already knows the numbers. Fixes a board showing a question with no default.
Makes a coordinator's control surface the same shape as the human's.

**Cons.** Three more flags, and `--answers` overlaps `--pool` — the flag should
win, and the precedence needs stating rather than discovering.

**Risk.** Low, with one thing to preserve: the render ceiling is written into the
entry as `ENTRY_CEILING`, `write` refuses to commit an entry that changed it, and
a run needing more escalates through `ask_specified` (`ask_render_ceiling`,
`nb/tools/interact.py:160-173`). A flag must feed that same single number, not
become a second source that can disagree with `lint._defaults` — the failure
`nb/config.py:140` already records once.

---

# Stage 4 — Make the visual rule see what the entry shows

Rule 14 first as a correctness fix, then the cap, then the wording. The rule fix
stands on its own even if the preference again fails to move behaviour.

| change | where |
|---|---|
| count generated and inline-captioned tables as visuals | rule 14, `nb/vendor/lint.py:955` |
| raise the cap to two when the second is a schematic, not a second plot | rule 14 |
| reword the "thirty times" line | `nb/system_instruction.md:219` |
| name diagrams in the form-choice list, not just "a plot" | `system_instruction.md:213-220` |
| say a geometry question is answered by a drawing | `Proposal.figures`, `nb/schema.py:85` |

**Rule 14 first**, because it is a correctness fix independent of the preference.
The rule claims to enforce one visual per entry and does not. Follow rule 15 and
read the freeze, which is where a generated table exists as literal
pipe-markdown — the same mechanism, in the same function, already written.

**Then the cap.** One visual was right against the failure it was written for:
"72 numbers printed under a plot showing the same quantities"
(`nb/vendor/lint.py:972`). It is wrong against "what does it look like", where
the schematic and the plot are different claims.

**Then the wording.** "Thirty times a small table" is a true thing about reading
cost and a false thing to put in front of a model choosing a form; the measured
result is 25 entries with no visual at all.

**Pros.** The one stage where a defect is currently *unenforced* rather than
unhelpful, and it is the failure the user sees: two entries in a row asking what
the aircraft looks like, answered with a table of millimetres.

**Cons.** "Schematic, not a second plot" is not a thing a regex knows, so the rule
counts and the guidance carries the distinction — the same shape as navigation.md
Stage 4, which did not work alone. The difference is that the count is now honest,
so the rule and the reader at least agree on what is on the page.

**Risk.** `nb.corpus` should **not** move. Measured today, no entry carries both a
labelled figure and a generated or inline table, so nothing on disk crosses one
visual once the generated ones are counted. Calibrate across all three notebooks
first; if the count moves, read the entries rather than raising the threshold.

---

# Stage 5 — Make the declaration happen

Both gates for assumptions are built and both are empty. This stage gives them
something to iterate over; Stage 7 makes what they iterate over structured. The
split matters because this half depends on nothing and that half depends on
Stage 6.

| change | where |
|---|---|
| append the chapter's declared inputs to the FIRST probe result | `probe`, `nb/tools/probe.py:125-152` |
| refuse `inputs: []` with a message the model can act on | `propose`, `nb/tools/interact.py:367` |
| an explicit escape, so "nothing was specified" is a claim not an omission | `Proposal`, `nb/schema.py` |

## Ask at the first probe, not at either end

A checkpoint *before* probing asks the model to classify inputs when it knows
least: it has not loaded the chapter, run anything, or seen what the question
touches. The terminal refusal is the mirror failure — it catches the omission
when the pool may be spent and the whole probe already ran against a placeholder.
`ask_specified` names this: "A static margin discovered at turn 3 should not be
guessed for twenty more turns."

**So neither end is right, and the first probe is.** By then the model has loaded
the vehicle and run one query against it; it has spent one probe, not the pool.

`probe` already appends bracketed notices to its own output, including one that
tells the model to go and ask (`nb/tools/probe.py:146-151`):

```
[ENTRY_CEILING: 61 s of solves already, against the 50 s granted for this
entry's render. Propose now with what you have, or ask_specified whether to
raise it -- that is the user's call, and the entry records the answer.]
```

The same shape, fired once when `session.probes == 1`:

```
[This chapter declares 1 Specified and 3 Assumed items
(chapters/04-thinner-foam/index.qmd). Which does this question CHANGE? A changed
Specified item is ask_specified, now, before the next probe. A new assumption is
yours to make and to record.]
```

**Zero extra turns**, because it rides a tool result the run already receives.
Ask-phase turn counts from `nb-metrics.db`, most recent fifteen, for scale:
`4 7 14 19 16 14 19 9 13 10 16 6 5 7 9` — median 10.

## The refusal takes the shape that already works

The claimable-stub check at `nb/tools/interact.py:383` raises a `ValueError`
describing what to do, the model reads it and acts, and the run continues. An
empty `inputs` list should hit the same path. If "this entry genuinely specified
and assumed nothing" is a real state — and it is, for an entry that only reads an
existing model — it needs to be *said*, not inferred from a missing list.

## What this alone achieves

`confirm_assumptions` starts firing, and with it the correction loop behind it
(`nb/phases/ask.py:174-204`) that re-enters the probe rather than letting an
entry be written from findings computed under a rejected premise. That loop has
never run. Nothing in Stage 7 is needed for it to work.

## Alternatives rejected

- **A blocking checkpoint before the first probe.** Rejected on timing, not
  cost: it asks the model to classify before it has loaded the chapter.
- **Asking at `create_chapter`'s return message.** A real slot — the message is
  injected as a user turn before the write model's first turn
  (`nb/phases/write.py:685-686`), and `ask_specified` IS available in write since
  `PHASE_OMITS` drops only `propose`. It loses because answers there have nowhere
  to go: `propose` does the bookkeeping that merges `session.asked` into
  `proposal.inputs`, and by write time that has already happened.

**Pros.** Closes the hole that let four of eight runs skip the assumptions gate,
by filling a gate rather than adding one. Costs no turn. Depends on nothing.

**Cons.** A required field invites filler. The first-probe notice is a third
bracketed block in a probe result that already carries two.

**Risk.** `nb.corpus` does not move. Two other things do.

- **Reactivating `confirm_assumptions` spends pool that runs previously did
  not.** Its correction path re-probes by design. Stage 3's defaults want
  re-reading once the loop fires — 120 s was calibrated on runs where it never
  did.
- **A refusal the model cannot satisfy trips the stuck detector.** `stuck.py`
  counts a productive tool that keeps failing as no progress, so the message must
  be actionable on first read.

---

# Stage 6 — Structured fork provenance, and derived arrows

Last because it touches the most surfaces: the scaffold, two index generators, a
lint rule and four existing forked chapters.

| change | where |
|---|---|
| write `_fork.yml` when forking | `create_chapter`, `nb/tools/scaffold.py:247` |
| derive the edge label from the category delta | root `index.qmd`, `nb/scaffold/` |
| read `changes` for the difference list | chapter `index.qmd`, `index.qmd.tmpl` |
| retrofit the four existing forks, and remove the comment header | `02`, `03`, `04`, `06` |
| rule 31 requires the file, not a comment | `nb/vendor/lint.py:1943` |
| rule 31b: declared changes match a real diff | new check, same function |
| rule 31c: a fork's category delta is non-empty | same |

```yaml
# chapters/04-thinner-foam/_fork.yml
parent: 03-unswept-c4
at: 12794f6
changes:
  - "wing naca4405 → naca4403, tail naca0005 → naca0003"
  - "fuselage width 10 → 6 mm"
```

## Categories and differences are not the same thing — but the arrow label is

They look redundant and are not. **Categories are absolute position on shared
axes**, drawn from a controlled vocabulary (rule 36), which is what makes
filtering work across non-adjacent chapters. **Differences are a delta from one
specific parent**, free text, at code granularity. 04's categories include
"fuselage" and "unswept quarter chord", which it *inherited* from 03 — they are
not differences.

But the **delta between two chapters' category sets** is a third thing, and it is
exactly the arrow label. Measured across every fork in the notebook:

```
01-foam-glider      -> 02-fuselage-model        added fuselage               removed wing only
02-fuselage-model   -> 03-unswept-c4            added unswept quarter chord  removed -
03-unswept-c4       -> 04-thinner-foam          added 3 mm foam              removed 5 mm foam
05-fully-optimized  -> 06-fully-optimized-5mm   added 5 mm foam              removed 3 mm foam
```

**Every fork changes exactly one axis**, and the added term is the label the
arrow wants. That is not a coincidence — `_categories.yml` says so: "each chapter
keeps what its parent modelled and adds one thing."

So an earlier draft's `summary:` field is deleted. The label is derived from data
that already exists, is already vocabulary-controlled, and is already guarded by
rule 36 — so it cannot drift from the categories, cannot invent a term, and needs
nothing written twice:

```
c03 -->|"3 mm foam"| c04
```

A rule falls out of it. **A fork whose category delta is empty varies nothing the
notebook has a word for** — either it should not be a separate chapter, or
`_categories.yml` is missing an axis. That is rule 36's own stated concern
("adding an axis is a decision about what the notebook is exploring") reached
from the other side, and it is a real check rather than a restatement.

`changes` stays, because it is at a different granularity: "naca4405 → naca4403"
is not an axis and should not become one.

## Why a file beside the model

**Not front matter in the chapter's `index.qmd`**, the strongest runner-up: that
page already carries `order:` and `categories:`, already prints the fork line,
and re-executes cheaply. It loses on a failure this codebase has already met —
rule 30 exists because "a model that rewrites index.qmd with `write_file` rather
than editing it drops the block and nothing noticed" (`nb/vendor/lint.py:1456`),
and three further rules cite the same cause. `index.qmd` is a page agents
rewrite; `_fork.yml` is a file no agent has reason to touch.

**Not a structured block inside the `_model.py` header.** It keeps the record
next to what it describes, and loses on an ONGOING cost: every future correction
to a fork header would dirty the model under rule 12 and re-prove the chapter.
The record most likely to need editing would be the most expensive to edit, which
is how a record stops being edited and starts being wrong.

**Not derived from the diff alone.** A diff gives hunks; "3 mm foam" is a reason.

**One format constraint.** `lint.py` imports nothing outside the stdlib, and says
so where it hand-parses the one YAML file it already reads
(`nb/vendor/lint.py:1790`). So the shape stays flat enough for the same idiom
that reads `_categories.yml`, or the file becomes `_fork.json`. **Flat YAML is
the better trade**: it matches an existing precedent in the same file, the parser
is about ten lines, and it stays hand-editable for the life of the notebook.

## The comment header goes — one record, not two

Two records of one fact, one checked and one not, is the drift this stage exists
to remove — and the unchecked one would be read first, since it sits at the top
of the file a human opens. The cost of reconciling them, measured from the
freezes:

```
02-fuselage-model        3 entries    12.4 s
03-unswept-c4            3 entries    18.2 s
04-thinner-foam          7 entries    19.3 s
06-fully-optimized-5mm   3 entries    36.4 s
                         16 entries   86.3 s
```

Eighty-six seconds to re-prove every forked chapter. `guards.py`'s "tens of
minutes of re-solving" is a sound general argument for making a refactor an
approved decision; it is not a measurement of this one.

## The diff check is what fixes "unreliable"

`model_kinship` (`nb/vendor/lint.py:1627`) already diffs chapter models against
each other; `at:` records the commit. Diffing the child against
`git show <at>:chapters/<parent>/_model.py` gives the hunks that actually differ
— which cannot write the prose but can say **"the model differs in three places
and `_fork.yml` lists two."** That is rule 12's argument applied to lineage, and
`freezediff.py` is the precedent for the shape.

**Pros.** The lineage diagram becomes what it was built to be — 06 hangs off 05
*and says what it changed*, which is where navigation.md stopped one step short.
Removes a duplicated parser and the 2000-byte truncation. Makes the difference
list checkable. The arrow label is derived, so it cannot disagree with the
categories.

**Cons.** A second file per chapter, and a reader opening `_model.py` no longer
sees the lineage in the first line — a real loss, covered by the chapter
`index.qmd` printing it, which is where a reader looks first anyway. The retrofit
is four chapters of hand-written prose to convert, and converting it is the kind
of transcription that goes wrong quietly: do it against the diff, not by
rereading the comment.

**Risk.** Two, neither a reason to change the design.

- **`nb.corpus` moves** by the forked chapters failing the new rule 31, which is
  all four until retrofitted. Calibrate and update the count in the same commit.
- **Four chapter freezes are invalidated** by removing the old header, so all
  sixteen entries re-render — 86 s, bounded and verifiable. Run `freezediff`
  afterwards: **any moved number is a real finding**, because deleting a comment
  must change nothing. That exercises the exact path a future refactor takes.


---

# Stage 7 — Structured inputs, and inheritance computed from them

After Stage 6, because computed inheritance reads the parent's declared set and
the parent is named by `_fork.yml`. Stage 5 made declarations happen; this makes
them structured enough to aggregate.

| change | where |
|---|---|
| `scope: new \| chapter \| notebook` on each input | `Input`, `nb/schema.py:15` |
| entries declare NEW items only; inherited ones are aggregated | `system_instruction.md:230` |
| compute the inherited set and show it at the new-chapter stop | `render_stop`, `nb/inputs.py` |
| wire up `nb inputs` | `nb/__main__.py`, `nb/inputs.py` |
| re-declare the six existing chapters' inputs | `glider-notebook/chapters/*/index.qmd` |

## Inheritance is computed, not asked

Carrying assumptions forward feels like it needs a checkpoint only because
inheritance is currently unknowable. With `scope` on `Input` and the parent named
by `_fork.yml`, the parent's declared set is on disk and the candidate list is a
**lookup**: no model judgement, no turn.

What cannot be computed is whether the fork *breaks* an inherited item. Forking
5 mm → 3 mm inherits "tail dimensions remain 100×30 mm", and that may or may not
survive. So: **compute** the candidate set, **present it at the new-chapter
stop** in `confirm_assumptions`' existing idiom (numbered, Enter accepts,
`"3: struck — 3 mm foam invalidates it"`), and let the ask phase handle only the
delta. A review of a computed list, not an open question — the same argument
`confirm_assumptions` already makes for batching.

The new-chapter stop is the right place because it already halts the run
(`nb/phases/ask.py:221`). What `render_stop` prints today is a chapter name, a
title, a sentence about re-solving and the resume command — nothing about what
the chapter inherits, which is the structural commitment being approved.

## Three levels, so a chapter with no parent is not a gap

`scope` is `new | chapter | notebook`, because the middle level is absent for an
unforked chapter:

- **a forked chapter** inherits from its parent chapter;
- **a new chapter with no fork, in an existing notebook**, inherits from the
  NOTEBOOK: span 300 mm, foam construction, minimum sink rate in trimmed glide.
  Those are stated in the root `index.qmd`, and `prefix.py` already loads every
  `index.qmd` for exactly this reason. Same gate, shorter list. A new aircraft in
  an existing notebook is where the MOST is open, so it is the strongest place
  for the gate, not the weakest;
- **the first chapter of a new notebook** inherits nothing and needs no
  mechanism: `nb new` is interactive with the human already there.

The third value also gives `nb inputs` something to group by, which is what makes
its output the design state of the aircraft rather than a flat list.

## New versus inherited is a split, not a restatement

Requiring an entry to restate the chapter's inherited items would contradict a
rule the instruction already carries (`nb/system_instruction.md:230-231`):

> "**Assumptions sit at the level they belong to.** What defines the chapter is
> stated once in `index.qmd`. Do not repeat it in entry prose."

That rule is right. The split is the correct resolution, and it is already the
practice in the one place someone wrote it by hand —
`glider-notebook/chapters/04-thinner-foam/index.qmd` lists "Asked of the user,
2026-09-15" then five items under "Inherited from earlier models". The
distinction exists in prose, in one chapter. It does not exist in the schema:
`Input` (`nb/schema.py:15-32`) carries `name`, `kind`, `value`, `owner` and
`why`, and nothing says which chapter established the item.

`nb/inputs.py` exists, works, and is wired to nothing. Its docstring says it
answers "what have we assumed about this aircraft", which nothing else does.
**The scope field is what gives it a reason to exist.**

With `scope` in place, Stage 5's refusal tightens: it checks for *new* items
specifically. An entry inheriting everything and introducing nothing is
legitimate and common; an entry that introduces nothing **and says so** is a claim
on the record; an entry silent on both is the failure.

**Pros.** Inheritance becomes derived, so it cannot drift from the parent. The
new-chapter stop gains the content it is missing. `nb inputs` becomes the design
state of the aircraft, which nothing currently answers.

**Cons.** The gate gets longer, and a stop showing fifteen items invites
Enter-mashing — the list must be the parent's DECLARED set, not everything
transitively true. The existing chapters declared theirs in prose, so the
retrofit is load-bearing rather than tidy-up — and it should be a
**re-declaration, not a scrape**, because parsing the existing callouts would
carry every ambiguity in that prose into the structured record permanently.
`scope` is one more field to get wrong, and a `scope: chapter` claim wants
checking against the chapter index, not trusting.

**Risk.** `nb.corpus` does not move — none of this is a lint rule.

## Alternatives rejected

- **A `declare_inheritance` tool.** Costs a turn for a lookup the code can do.
- **Deriving everything and asking nothing.** Fails on the judgement the
  computation cannot make: whether the fork breaks an inherited item.

---

# Stage 8 — An assert for an unquoted shape claim

**Scoped, and smaller than deleting `verify` made it sound.** Last, and honestly
optional.

Deleting `verify` left one category wholly uncaught: a claim about a curve's
*shape* that the curve contradicts. Rule 1 forces the NUMBERS in prose to be
`{python}` expressions, so a prose number is the rendered value by construction;
nothing forces a sentence about a shape to match the shape, because such a
sentence quotes nothing for rule 1 to bite on.

The convention already exists (`nb/system_instruction.md:234`): "A claim the
prose makes but does not quote gets an `assert`, so the page fails to render
rather than going quietly stale." **24 of 77 entries carry one**, and
`lint.py:998` records a problem caught "only because that entry happened to carry
an assert". It is a convention, not a rule — and Stage 2 made it bite harder,
since `build_entry` now turns a failed assert into a build failure that refuses
the commit. The gap is that writing one is optional.

## The broad form does not survive calibration

A keyword rule over comparative words — falls, rises, higher, faster, better,
converges — fires on **30 of 77 entries**. It is swamped, and the reason is
mechanical rather than a matter of taste: `lint.prose_of` strips the inline
expressions, so "structure mass falls from [] g to [] g" reads as a sentence
quoting nothing when it quotes two things. The rest are shape words used about
something that is not a curve — "liable to drop a wing", "very nearly a
drop-in", "the optimizer converges on a forward-swept wing".

## The narrow form is viable, as a warning

Restricted to vocabulary that can only describe a curve — `linear`, `monotonic`,
`crosses`, `peaks`, `plateaus`, `flattens`, `asymptotic`, `steeply`,
`scales with`, `diverges` — measured across all 77 entries:

```
match the vocabulary in prose        8 entries
  ... already carry an assert        4
  ... do not  ->  rule fires         4   (2 of them artefacts of sentence splitting)
```

So roughly **two genuine unguarded shape claims in the whole corpus history**.

| change | where |
|---|---|
| rule 39, WARNING severity: a shape word with no `assert` in the entry | `nb/vendor/lint.py` |
| split sentences with lint's own prose extraction, not a naive regex | same |
| recalibrate the corpus counts | `nb/corpus.py` |

**Warning, not blocking**, and that is the whole design. Blocking on a
2-in-77 phenomenon with a measurable false-positive rate trains an author to
route around the rule, which is worse than not having it. `lint` already splits
severity on an in-string `"(warning)"` marker, so this needs no new machinery.

**Pros.** It is the only proposal that touches the category `verify` actually
guarded, and it does so deterministically — no model call, no figure reading.
It turns an existing convention into something that is at least counted.

**Cons.** A base rate of ~3% is thin justification for lint surface. The rule
cannot tell a true claim from a false one — it only asks whether the author
bothered to assert — so it is a prompt for rigour rather than a check on truth.
And two of its four fires today are artefacts, which will need the sentence
extraction fixed before the count means anything.

**Risk.** `nb.corpus` moves by the entries that warn, which is 4 today and must
be recalibrated across all three notebooks first. **This is the one stage whose
honest recommendation is "probably not yet"** — the loss it addresses is real,
and it is two entries in a year of work.

---

# Four surfaces

Every stage lands in up to five places. Fixing `glider-notebook` fixes what
exists; the scaffold and `create_chapter` decide whether the *next* notebook and
chapter are born correct.

| stage | existing notebooks | `nb new` scaffold | `create_chapter` | agent guidance | lint guard |
|---|---|---|---|---|---|
| **1** render scope | — | — | freeze deletion | `render` tool description | — |
| **2** deletions | — | — | — | tool list shrinks | — |
| **3** budgets | — | — | — | — | — |
| **4** visuals | — | — | — | `system_instruction.md`, `schema.py` | rule 14 widened, cap raised |
| **5** declaration | — | — | — | `schema.py`, first-probe notice | — |
| **6** fork provenance | 4 × `_fork.yml`, root + 4 chapter `index.qmd` | `index.qmd.tmpl` | write `_fork.yml` | `schema.py` | rule 31 rewritten + 2 checks |
| **7** structured inputs | re-declare 6 chapters' inputs | — | — | `system_instruction.md`, `schema.py` | — |
| **8** shape asserts | — | — | — | `system_instruction.md` | rule 39, warning |

Stages 1–5 land in one or two places each and need no guard. Stage 6 lands in all
five.

# Order of work

1. **Stage 1 — render scope.** The instrument, before anything is changed.
2. **Stage 2 — deletions.** Before everything else, which would otherwise write
   code into paths about to be deleted. Internally ordered: extract the
   build-repair loop, prove it fires, *then* delete verify.
3. **Stage 3 — budgets.** One branch instead of two, after Stage 2.
4. **Stage 4 — visuals.** Rule 14 as a correctness fix, then the cap, then the
   wording.
5. **Stage 5 — make the declaration happen.** Depends on nothing. Reactivates
   the correction loop on its own.
6. **Stage 6 — fork provenance.** In two commits: the file, the readers, the
   retrofit and the header removal first; the diff check second, once there is
   something correct to check against.
7. **Stage 7 — structured inputs.** After Stage 6, which names the parent that
   inheritance is computed from.
8. **Stage 8 — shape asserts.** Optional, and calibrated at two genuine cases in
   the whole corpus. Do it if the category bites after Stage 2, not before.

Splitting inputs across 5 and 7 is what makes the dependency run forwards. An
earlier draft had one inputs stage that depended on a fork stage placed after it.

# Verification

**No corpus movement except Stage 6**, by the forked chapters failing the new
rule 31. **Stage 4 must not move it**: no entry today carries both a labelled
figure and a generated table, so widening rule 14's detection should change no
count. If it does, read the entries before touching the threshold.

**Stage 1**
- Not a single render changes. Same pages executed, same deadlines, same
  outcomes — only the log differs. Compare `will_execute` before and after.
- The announced deadline is the deadline enforced. That line has been wrong twice,
  both times by sizing one question with another question's answer.
- The corrected `render` description changes what the model targets. If the rate
  of chapter-scoped renders does not move, the description was not the lever and
  the next step is making `render` refuse a target that buys nothing.

**Stage 2**
- **The build-repair loop still fires after extraction, and before verify is
  deleted.** Break an entry deliberately — a NameError in a code cell — and
  confirm the traceback reaches the model and the model fixes it. This is the
  one thing in the stage being removed on no evidence rather than good evidence,
  and the order of work exists to protect it.
- A page that does not build is still never committed. Lint passes before this
  point, so nothing else would notice.
- `read_figure` still works after `phases/verify.py` is gone. It is declared to
  the main agent independently and must not leave with the phase.
- `verify_findings` is still a column and simply stops being written. Old rows
  keep their zeros; `nb eval` must not break on a NULL it already handles.
- `MAX_CORRECTION_ROUNDS` still caps the assumption loop at 3. Deleting
  `MAX_CONSULTS` with the tool would silently uncap a loop Stage 5 makes live.
- A single-user `nb ask` still asks and still gets answered, with no second
  terminal opened by hand.
- Closing the terminal mid-question leaves the run alive and the question on
  disk. That is the whole point of the change, and the one thing the attached
  path could never do.
- `--quiet` emits no escape sequences through a pipe, and `status.log` stays
  plain text.
- Nothing is spawned inside the forked child. `detach_process` forks before the
  MCP subprocess and the metrics connection for a documented reason.

**Stage 3**
- The flag and the notebook never disagree: `--ceiling 300`, confirm the entry
  declares 300, `write` accepts it, and `lint._defaults` is still the source when
  the flag is absent.
- A budget question on the board shows its default; let it time out and confirm
  the run proceeds on that number rather than dying.

**Stage 4**
- A read, not a test. Re-ask "what does the fully optimised 5 mm glider look
  like" and see whether it draws. If it tables again, the guidance is not the
  lever and the next move is a rule.

**Stage 5**
- The gate fires: run a question that assumes something and confirm
  `confirm_assumptions` reaches the terminal. The test is that the box appears.
- The correction loop actually re-probes, rather than writing from findings it
  already had. That loop has never run.
- No extra turn: compare ask-phase `turns` before and after. The notice rides an
  existing tool result.
- The notice fires on the FIRST probe only. A block repeated every probe is the
  third competing with two that already matter.

**Stage 6**
- Removing the comment header moves no number: delete from all four models,
  re-render, run `freezediff`. A clean diff is expected; anything moving is a
  real finding.
- The diff check fires: edit a forked `_model.py` in a way `_fork.yml` does not
  describe.
- Arrows come from the data: change a category and confirm the root index
  re-renders with the new label. `create_chapter` already deletes
  `_freeze/index/` for the node case; the label case needs the same guarantee.
- The retrofit is checked against diffs, not prose: for each of the four
  chapters, `git show <at>:chapters/<parent>/_model.py` diffed against the child
  must produce exactly the hunks `_fork.yml` lists.

**Stage 7**
- `scope` is checkable: an entry claiming a `chapter`-scoped item must match the
  chapter index.
- The new-chapter stop shows the inherited set for a forked chapter AND an
  unforked one — the second is the case most likely to be forgotten.
- Striking an item at the gate reaches the chapter. If the strike is recorded and
  ignored, the gate is theatre.

# Out of scope

- **Removing the new-chapter stop.** Stage 3 pins an existing chapter only; the
  structural commitment stays the user's.
- **A blocking checkpoint before the first probe.** Rejected on timing, not cost:
  it asks the model to classify before it has loaded the chapter.
- **Deriving fork differences automatically.** Stage 6 checks a declared list
  against a diff; it does not write the list. A hunk is not a reason.
- **Two agents in one chapter.** Unchanged by any of this, and still guarded by
  the chapter lock.
- **Deleting `nb/inputs.py`.** It was the alternative; Stage 7 wires it up
  instead.
- **Replacing verify with a cheaper check.** A lint rule cannot read a figure,
  and anything that can is another model call. The class of error verify guarded
  is uncaught after Stage 2, deliberately and on the record.
- **Fixing `first_pass_violations` as an eval metric.** It is saturated at zero
  and Stage 1 adds render counts beside it; whether the old column is retired is
  a separate question about what `nb eval` is for.
