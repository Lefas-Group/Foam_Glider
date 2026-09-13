# `nb` stage 4 — concrete changes

Companion to `agentic-notebook-spec.md`, which describes the system as built.
This is a change list in build order: every item names the file it touches and
the reason it is worth doing.

**Target:** the human at the gate becomes a coordinating agent driving several
`nb` instances — parallel chapters, or parallel entries within a chapter.

---

## Evidence this rests on

Measured 2026-09-12 on `gemini-3.1-pro-preview`, against
`optimised-glider-notebook` (4 chapters, 23 entries) or the `glider-notebook` run
of the same day.

| | |
|---|---|
| explicit cache vs implicit, 6 turns | 23.9% hit / **$0.4121** vs 67.0% hit / **$0.2082** |
| explicit cache's `cached_content_token_count` | pinned at exactly the cache size, every turn |
| implicit hit rate, steady state | 96–99% of the previous turn's prompt |
| prefix composition | tools 3,623 · system 2,590 · chapter context 6,365 · manifest 1,344 |
| `propose` tool declaration | **1,014 tokens** — larger than the next six combined |
| `_model.py` summary vs source | 1,556 vs 17,984 (**11.6×**) |
| `_analysis.py` summary vs source | 2,145 vs 44,552 (**20.8×**) |
| thought summaries | thinking billed either way (398 vs 342); ~250 tok/turn of conversation |
| rendered entry markdown | 5,624 tok full, **851 tok** with code cells stripped |
| one entry end to end | ask $0.46 + write $0.33, 0 first-pass lint violations |
| forked `_analysis.py` helpers | 12 shared across chapters, **11 byte-identical**; the one divergence is the fork's purpose |
| `_analysis.py` reuse | 11 of 42 functions called by 2+ entries; 19 called by none |

---

## The one thing that is not a code change

**The coordinator needs an explicit design brief.** Derivable is computed, Unknown
is assumed and flagged, Specified is *asked because a different answer changes
what we are building*. If the coordinator answers Specified inputs from its own
judgement, Specified collapses into Unknown with the flag removed.

Rule: **the coordinator may answer a Specified input only by quoting the brief,
and escalates anything the brief does not cover.** Stage 4e builds the routing;
the brief is out of scope here. Nothing below is worth building without it.

---

## Stage 4a — two streams

**1. `nb/log.py` (new): `say()` → stderr, `tell()` → stdout.** Telemetry, turn
lines and lint output on stderr; the Specified box, the rendered entry and the
final result on stdout.
*Why:* the coordinator reads one and ignores the other. Unredirected the terminal
is unchanged; `2>/dev/null` leaves only the conversation.

**2. Mirror stderr to `_scratch/run/status.log`.**
*Why:* `tail -f` in a second pane, and it is what you read after a run dies.

**3. Answers stay plain text on stdin — `10%`, not `{"answer":"10%"}`.**
*Why:* `_prompt` works unchanged. **EOF still raises rather than assumes**: a
silent default is how design intent leaks away.

**4. `config.py: INCLUDE_THOUGHTS`; `client.py` sets `include_thoughts`;
`loop.py` sends thought parts to `say()` and into `transcript.jsonl`.**
*Why:* "why did it do that" starts every debugging session, and the Flash-vs-Pro
diagnosis was made by inferring reasoning from tool choices. Thinking is billed
either way (398 vs 342 tokens); the cost is ~250 tok/turn of conversation, ~$0.05
today and ~$0.005 after 4f. **Do not strip thought parts to save it** — appending
the turn whole is `loop.py`'s one invariant.

**5. ~~AFC warning~~ — done.** `client.py` passes
`AutomaticFunctionCallingConfig(disable=True)`.
*Why:* every call took the SDK's function-calling path and broke immediately at
`if not function_map: break`, since the map comes from callables and we pass
declarations. It cost nothing by accident; now it does so deliberately. Its advice
(`Chat.send_message`) is wrong for us — managing `contents` ourselves is what
signatures require.

**Rejected: a JSONL event protocol on stdout.** The coordinator is a language
model and prose is its native format; JSON is *more* tokens (~30 vs ~18 per turn
line) with a schema to maintain in two places. Anything that must be exact is a
file read by path — as `proposal.json` already is.

**Deferred: one signal for "blocked, waiting for you".** Through a pipe a
90-second probe and a pending question are indistinguishable. Needs one sentinel —
a line, or `_scratch/run/.waiting`. Build it when a coordinator exists to test it.

---

## Stage 4b — remove the gate, keep two conditional stops

Asked what is left to reject once lint, render and verify have passed: very
little. *Wrong question* and *bad assumption* are real but belong to
`ask_specified` and 4e — catching them at the gate means catching them after every
probe already ran against the wrong value. The rest the notebook handles without
rejection, per the manifest's own prompt text: *"that is a correction — say so in
YOUR entry… Never edit the earlier entry."* `superseded_by()` exists because the
record is append-only. Rejection does not refund the run, and `git revert` on one
entry and its freeze is cheap.

**1. `phases/ask.py`: continue past `propose` into the write phase unless
`route == new_chapter`.** `propose` stops raising `Terminal` in the common case.
*Why:* one command runs a question through to a commit.

**2. Keep exactly two stops:** a new chapter, and editing `_model.py` in a chapter
that already has entries.
*Why:* both are **pre-flight decisions about structure and spend**, not approvals
of output. A chapter is a commitment later entries build on; a refactor costs tens
of minutes of re-solving.

**3. `tools/mcp_fs.py`: refuse `_model.py` writes when the chapter has entries;
refuse body changes to existing `_analysis.py` functions.**
*Why:* the agent cannot predict it will touch `_model.py`, and asking it to yields
the quality of `render_cost_s: 0.0`. **Refuse at the boundary instead**, so the
stop happens because it was refused rather than because something guessed. Adding
an `_analysis.py` function is safe — rule 2 leaves siblings untouched — but
changing an existing body is a refactor. `lint._defs_of()` already does the AST
pass.

**4. `tools/interact.py: request_refactor`** — raises `Terminal`, carrying the
entry count and estimated re-prove cost.
*Why:* `Terminal` already exists for `propose`; same mechanism, new trigger.

**5. `phases/write.py`: `--allow-refactor`; run `check` automatically after verify
when a refactor happened; stop on a dirty diff.**
*Why:* an empty diff means the refactor moved nothing → commit. A non-empty diff
*is* the finding → stop, naming the entries whose markdown moved.

**6. Keep `proposal.json` as an internal handoff: one command, two
conversations.** The write phase starts a fresh conversation from the proposal,
inside the same process, without stopping.
*Why:* the two surviving stops resume via `nb write`, and `proposal.json` is the
**only** thing that crosses that boundary — there is no conversation persistence
and none is planned, so without it the stops cannot resume at all.
**The cost argument is weak and was overstated in an earlier draft:** at the
measured 95% hit rate, split is ~$0.404 and merged ~$0.429 — about 6%, 2.5p an
entry. Keep it for the resume, not the money.

**7. `phases/write.py`: after commit, `tell()` the rendered prose** —
`_freeze/…/execute-results/html.json` → `result.markdown`, code cells stripped —
with the sha and path.
*Why:* rule 1 means the true numbers exist **only** in the freeze, and today no
human sees them before commit. 851 tokens stripped against 5,624 full. This is
what makes autonomous commit safe to live with.

**8. `schema.py`: drop the gate-only fields** — `rationale`, `handoff`, and the
human framing of `render_cost_s`.
*Why:* they exist to be read by a person at a gate that no longer exists.
`handoff` leaked into an entry once already.

**No LangGraph.** Every stop is a process exit and everything surviving it is
already a file. A graph buys resuming *mid-node*, which we never want — resuming
mid-probe re-runs the probe. The conditional is a Python `if`; a conditional edge
is the same `if` plus a serialisation format, a checkpointer and a node boundary.
The one thing a graph would give — conversation persistence — it does not solve
anyway, because thought signatures are opaque provider bytes with nowhere to live
in a normalised message shape; and having dropped the revise path, we no longer
want it. **Revisit if** a run needs three or more stops, stops in any order, or a
resume without a process boundary.

**Counter-argument to keep in view:** four instances at ~8 min/entry is ~30
unreviewed entries an hour. That argues for batch review, not for blocking each
instance mid-run. `metrics.Run` already has an `outcome` column — record
`rejected` for a dozen entries and the question stops being an argument.

---

## Stage 4c — make each instance safe on its own, then decide ownership

An earlier draft justified this with `index.lock`, *"a certainty, not a race"*.
That is wrong, and the real danger is worse. Both were tested.

**A commit is ~100 ms at the end of an ~8-minute run**, so lock collisions need
two instances inside the same 100 ms window — rare, loud, and retryable.

**The silent failure is the index sweep.** `_commit` does `git add -- <paths>`
then `git commit -m title` **with no pathspec**, which commits *the whole index*:

```
A: git add entryA          index: entryA
B: git add entryB          index: entryA + entryB
A: git commit -m "titleA"  ← commits BOTH, under A's title
B: git commit -m "titleB"  ← nothing to commit, fails
```

Measured — A's commit contained `a.txt` **and** `b.txt`. B's entry entered history
under A's message. Its window is the whole add→commit span, and it produces wrong
content rather than an error.

**1. `phases/write.py`: commit with a pathspec —
`git commit -m <title> -- <paths>`.**
*Why:* a pathspec-limited commit bypasses the index and takes working-tree content
for exactly those paths. Measured: two concurrent commits then contain only their
own files. **One word, and each instance is correct on its own.**

**2. `phases/write.py`: retry the commit once on `index.lock`.**
*Why:* covers the rare loud collision that remains. Loud and retryable is the easy
kind.

**3. `phases/write.py`: `--no-commit`, writing `_scratch/run/ready.json`** — exact
paths, title, chapter — with a line on stdout saying it is there. Default stays
`--commit`.
*Why:* **this is an ownership feature, not a safety one.** Items 1 and 2 make
concurrent commits correct; this lets the coordinator decide *what* is committed,
in *what order*, and *whether at all* — so it can commit one of two overlapping
entries and discard the other. Build it when the coordinator actually wants to
veto. A fuzzy path list means a wrong `git add`, so the payload is a file, like
`proposal.json`.

**4. Skip `site()` under `--no-commit`; `nb view` becomes coordinator-invoked.**
*Why:* `quarto render` is not concurrency-safe within a project — shared
`.quarto/` and `_site/`. One renderer at a time, by construction.

**Rejected:** per-instance worktrees (a worktree and a merge step to solve what a
pathspec solves for free); a commit lock inside `nb` (serialises the cheapest part
of a run to prevent a failure the pathspec already prevents).

---

## Stage 4d — allocate identifiers atomically

Three identifiers are derived by reading the filesystem, and all three race in the
gap between reading and creating. The fix is **local atomicity**, not coordination:
`mkdir` and `rename` are already atomic, so each instance can be safe on its own
without knowing another exists.

**1. `tools/scaffold.py: _number` allocates by atomic `mkdir`.** Try
`chapters/NN-slug` with `exist_ok=False`; on `FileExistsError`, increment and
retry.
*Why:* `max(existing) + 1` is read-then-create, so two instances compute the same
number. `mkdir` fails with `EEXIST` instead — whoever wins keeps the number, the
loser takes the next one. ~5 lines, no coupling, and it works when no coordinator
exists.

**2. `tools/scaffold.py`: claim the stub by atomic `rename`, then rewrite.**
*Why:* today both instances call `claimable_stub()`, both `rmtree` the same
directory, and the loser raises an unhandled `FileNotFoundError`. `os.rename` on a
directory is atomic: the winner takes it, the loser's rename raises and it falls
through to allocating a fresh number. Rename first, rewrite the templated files
after — `_model.qmd` bakes the chapter path in.

**3. `phases/write.py: _stem` allocates by atomic file creation.** Open the
candidate `.qmd` with `"x"`; on collision, increment `NN`.
*Why:* `_stem` counts same-day entries, so two parallel entries in one chapter on
one day both get `01` and the second overwrites the first. Only bites under
entry-parallel, which is out of scope below — but the fix is one flag on `open`.

**4. Optional overrides — `--chapter-number`, `--claim`, `--stem`.** They **fall
back** to atomic allocation on collision rather than rejecting.
*Why:* a coordinator may want a specific name, but it should not be able to waste
a run by guessing wrong — that is the failure stage 3 removed by letting code
renumber the model's guess. Atomic allocation as the floor means a coordinator bug
costs nothing.

**Why not have the coordinator assign?** It is the textbook answer — one allocator,
no race — but it makes numbering **state the coordinator must maintain correctly**,
adds a failure surface in the least-tested component, and turns a wrong guess into
a wasted run. Local atomicity gets the same safety with no coupling. Reserve
coordination for decisions only a coordinator can make: ordering, vetoing, naming.

**Chapter-parallel is the default; entry-parallel is opt-in.** Different chapters
share almost nothing. Entries within one share `_model.py` and `_analysis.py`, and
both rule 2 and rule 19 make writes to them likely. Two instances promoting
different helpers is a lost update — the loser's `footer()` names a function that
no longer exists, surfacing as `OSError` from `inspect.getsource`. That is a
content race, which atomic creation does **not** fix; it needs a lock held for the
whole write loop, which serialises most of the benefit. Measure before building it.

### `check.py` is the refactoring proof, and nothing reaches it

**5. `tools/__init__.py`: drop the `check` declaration; keep the module.**
*Why:* 166 tokens a turn to offer something whose own description says *"SLOW and
rarely what you want"*. A full chapter check re-solves every entry —
`04-chosen-throw` is seven at 300–500 s each — inside a 40-turn loop with a 960 s
probe ceiling. Same argument that removed `create_chapter`.

**6. `phases/write.py`: run `check` conditionally (wired in 4b item 5).** Trigger:
`_model.py` changed **and** the chapter already had entries; `_touched()` already
computes it.
*Why:* rule 19 makes `_model.py` a file that changes by design. Entries exec it
through `_model.qmd`, and Quarto's freeze tracks the page not its includes — so
committed output can silently stop matching the code that produces it, and
`_refresh_index_freeze` covers only the chapter index.

Deleting the freeze is the whole point: without it you compare a fresh render
against a cache hit, which has happened — *"a mistyped working directory meant the
freeze was never deleted and the render never ran, and everything reported
unchanged."* `git diff` cannot substitute: each `markdown` field is one JSON line,
and four things differ between identical renders. `freezediff` normalises all four
while **keeping the solve count**, because masking the runtime line once hid a real
18 → 2.

**Verify the instrument first:** on an unchanged tree the diff must be empty and
the PNGs byte-identical, or the filters need recalibrating.

---

## Stage 4e — input triage under a coordinator

Today only Specified inputs are asked; Unknowns are assumed silently and reviewed
by nobody. In the last run *"Tail geometry: 100×30 mm, sensible fixed size"* was
decided by the model, used by thirteen probes, and checked by no one.

**1. `tools/interact.py: declare_assumption`, beside `ask_specified`.** Both go to
the coordinator, which routes:

| kind | coordinator does | may answer from |
|---|---|---|
| specified | forwards to the human unless the brief covers it | the brief, quoted — **never its own judgement** |
| unknown | confirms or amends, itself | its own judgement, plus the register |
| derivable | rejects | nothing — it is computed |

*Why:* **cross-instance consistency**, a defect class currently undetectable — if
chapter 02 assumes a 100×30 tail and chapter 03 assumes 120×25, nothing finds out;
both lint clean and render. Secondary: `interact.py` already argues for asking
Specified inputs early rather than batching — *"a static margin discovered at turn
3 should not be guessed for twenty more turns"* — and that applies to assumptions
word for word.

**2. `schema.py`: `owner` becomes four-valued** — `user` (including via the brief,
because the human wrote it), `coordinator`, `agent`, `assumed`. Rendered in the
entry.
*Why:* a reader should see who is responsible for a number, not only whether it
was asked.

**3. `schema.py`: make `_discipline` reusable and run it at ask time.**
*Why:* today Specified is expensive and Unknown is free, which biases toward
Unknown. Removing the asymmetry opens the opposite failure — asking about
**Derivable** things, exactly what rule 4 exists to stop. `_discipline` currently
runs only when the proposal validates.

**4. tty mode unchanged:** Specified blocks, Unknown is assumed silently.
*Why:* otherwise single-instance use becomes far chattier for no gain.

**5. Keep Assumed reading as a weakness in the entry.**
*Why:* *"Specified is a brief; Assumed is a weakness."* Confirmation adds
information about deliberateness, not about the aircraft; `owner: coordinator`
must not read as a decision.

**6. Require a reason for an amendment, not for a confirmation.**
*Why:* the coordinator judges without the model loaded, so the risk is overriding
a well-founded assumption from less information.

**Cost:** ~1,500 incremental prompt tokens and ~50 output per round trip — half a
cent, landing mostly on the coordinator. Synchronous is fine; it is an agent, not
a person. Batch only if measurement says to.

**The register, and the part most likely to be wrong.** The coordinator
accumulates every answered input across every instance — the design state of the
aircraft, versioned, with ownership attached. **Assumptions need scoping and
nothing obvious decides it**: a tail geometry assumed in a trimmed-glide chapter
may legitimately differ from one in a structures chapter. Design the register so a
wrongly-scoped entry is visible rather than silently inherited.

---

## Stage 4f — delete the explicit cache

Measured, and the answer is the opposite of what this stage was written expecting.

| turn | A: explicit | | B: implicit only | |
|---|---|---|---|---|
| | prompt | cached | prompt | cached |
| 1 | 10,457 | **10,450** | 10,456 | 0 |
| 3 | 37,089 | **10,450** | 37,086 | 20,456 |
| 6 | 77,037 | **10,450** | 77,031 | 61,387 |
| total | 262,482 | 62,700 (23.9%) | 262,461 | **175,957 (67.0%)** |
| input cost | **$0.4121** | | **$0.2082** | |

Arm A is pinned at exactly the cache size on every turn — the same signature
production showed (`6,559 cached` on all fifteen turns). **Passing `cached_content`
does not add to implicit caching; it replaces it**, and the conversation, which is
the part that grows, is then billed at full rate forever. Arm B pays no storage
either.

**1. Delete `nb/cache.py`**, its CLI and its tests; `phases/common.py`, `ask.py`
and `write.py` pass `system_instruction` and `tools` normally.
*Why:* half the cost, and with it go the key derivation, the 4,096 floor check,
three release points, the TTL backstop, `--purge`, and the leak that had two
caches billing at $0.1256/hour.

**2. `tools/__init__.py`: give the phases different tool lists; drop `propose`
from the write phase.**
*Why:* the module says *"Both phases share the list so they share the cache."* No
cache, no constraint. `propose` is **1,014 tokens** and the docstring already
admits it "has nothing to do there" — ~7% of the prefix back on every write turn.

**3. `prefix.py`: confirm most-stable-first ordering.**
*Why:* implicit caching matches a byte prefix, so §9's ordering rule now carries
all the weight instead of relying on the explicit cache to have frozen it.

**4. Do not prune the conversation to save tokens.**
*Why:* editing anything breaks the byte-prefix match from that point on. Pruning
20k to 10k costs 10k × $1.80/1M once and saves 10k × $0.20/1M per later turn —
**break-even is nine more turns**, and runs are 14–15 total. The lever is
ingestion (`TRUNCATE = 8000`), which happens before anything enters the
conversation and carries no cache penalty.

**5. The manifest problem evaporates.** No key means a sibling's commit shortens
the matched prefix instead of dropping it to zero, so parallel instances stop
invalidating each other by construction.

**Caveats:** implicit caching is best-effort where explicit guaranteed a hit — keep
`cached_tokens` in metrics as the monitor for a silent regression. The first turn
is always cold. Re-measure when the model changes; this is a property of the
serving stack, not the API contract.

---

## Stage 4g — budgets as allocation

`MAX_TURNS = 40` is the only cap, and turn count correlates badly with cost — a
turn is 22 output tokens or 1,700. Under a coordinator these become allocation.

| budget | passed as | enforced |
|---|---|---|
| tokens | `--token-budget` | agent-visible; on exhaustion **propose from what you have** |
| probe wall clock | `--probe-budget` | a pool the agent spends from, per probe |
| solve | derived from the pool | existing `_notebook.py` watchdog |
| render | `--render-budget` | checked against a **derived** `render_cost_s` |

**1. `config.py`: budgets become defaults, not constants; `session.py` tracks
spend; `loop.py` reports it past ~50%.**
*Why:* told at turn 1 that it has a budget the agent under-explores; told at 60%
that it has 40% left, it prioritises. Never hard-exit — an instance killed at 90%
spend with no proposal burned its whole slice for nothing.

**2. `tools/interact.py`: derive `render_cost_s` from the session's last
`aero_report()` instead of taking it as a field.**
*Why:* the glider proposal declared **0.0** for an entry running a full
`opti.solve()` and nothing checked it. A budget on an unchecked number is theatre —
and this is the same failure rule 1 exists to prevent, a hand-typed number where a
computed one was available.

**3. `metrics.py`: record `render_cost_declared` vs `render_cost_actual`.**
*Why:* proves the estimate is worth budgeting against.

**4. One terse line, not four paragraphs:**
`budget 45k/120k tok · probe 380/900 s · render 0/200 s`.
*Why:* four budgets is four concepts of prompt surface on every turn.

**Do not collapse the existing layers.** `_notebook.py` records why, with
measurements: a per-solve budget is blind to 112.8 s spread over 3,070 solves, to
four multistart solves that individually pass, and to 3.5 s of problem
construction outside every solver limit. The opt-out design is load-bearing —
forgetting must land in the protected state — and the file's worst bug was a budget
that set `behavior_on_failure="return_last"`, so a timed-out solve published its
last iterate and one chapter's figures came out 11.22 s, 9.50 s, 8.92 s from
identical code. The four budgets sit *above* all of that, as allocation.

---

## Stage 4h — where helpers live

*Depends on nothing and needs no coordinator. Four lint rules; the contract goes
19 → 22, with rule 2 amended.*

`_analysis.py` exists to **force consistency** between entries and to **save
tokens**. Both were checked.

**Consistency is working.** Twelve functions exist in more than one chapter,
because forks copy `_analysis.py` wholesale. **Eleven are byte-identical across
every copy.** The one exception is `optimise` — v1 in three chapters, v2 in
`03-tabulated-section` — and that is the fork's *intended* difference, since
`forking.md` says *"a fidelity change alters `_analysis.py`"*. The failure this
prevents is on record: *"Four subtly different neutral points once existed in one
chapter because nothing advertised the first, and one of the four took its moment
reference from the wrong station."*

**Tokens are a reuse bet.** Signatures sit in the cached prefix forever — 2,145
tokens × 15 turns ≈ $0.006/run — against one avoided sibling read at 5,624 fresh
tokens ≈ $0.011, plus the output saved by calling a function instead of writing
it. It pays, **but only for functions that are actually reused**, and 31 of 42 are
called by 0–1 entries.

**1. Rule 20 — an entry-local function that reaches the vehicle belongs in
`_analysis.py`.** Parse the entry's `{python}` cells for `def`s, run the fixed
point `aero_calls_of` already uses, and check the transitive call set against
`_model.py`'s names, the `_analysis.py` names and `AERO_PRIMITIVES`.
*Why:* this is exactly the consistency criterion — the things that must not
diverge are the ones touching the model; a table formatter diverging is harmless.
It **fires on a chapter's first entry**, closing the same structural blindness
rule 19 fixed. `_defs_of` and `module_summary` supply the pieces; the new part is
extracting `def`s from `.qmd` cells, ~25 lines.
*Cost:* false positives — a genuinely one-off measurement that touches the model
gets forced into `_analysis.py`. **Ship it as a warning first** and see how often
it fires before letting it block.

**2. State the criterion in `system_instruction.md`.** *"A function that reaches
the vehicle is chapter machinery and goes in `_analysis.py`; a function that only
presents what has already been computed stays in the entry cell."*
*Why:* so the agent lands it correctly first time and rule 20 only catches misses.
Free, and one sentence.

**3. Rule 21 — an `_analysis.py` function that no entry and no sibling function
calls is dead.**
*Why:* rule 2 promotes and nothing ever demotes, so the file only grows — 44,552
tokens across four chapters against 17,984 for all four `_model.py`. Three are
dead today (`design_geometry` ×2, `optimise_launch`). And under the consistency
goal a dead function is worse than waste: it is a **divergence trap**, because
someone calls the stale one. Detection is eight lines. Rule 20 makes this
mandatory rather than optional — it promotes more, so something must demote.

**4. Rule 22 — an `_analysis.py` function called only by other `_analysis.py`
functions is private, and takes a `_` prefix.**
*Why:* nineteen functions are called by no entry, but most have internal callers
(`design_problem` +5, `optimise` +9). They are implementation, not API — yet they
are public names, so they appear in `module_summary`, the cached prefix, and
`api()`. About 17 such functions at ~51 tokens of signature each: **~870 tokens
off the prefix (~6%)**, plus a shorter `api()` listing to scan. The precedent is
already in the file — `_design_vector` and `_flight_once` are correctly private.
`_defs_of` already has the call sets.

**5. Amend rule 2 to be structural rather than textual.** Compare normalised
function bodies or statement sequences instead of three consecutive identical
lines.
*Why:* the textual heuristic misses near-duplicates that differ by a variable
name and misfires on coincidental formatting. Rule 20 takes most of its load
anyway.

**Rejected: always write helpers to `_analysis.py`.** Simpler to enforce — "no
`def` in an entry cell" is a one-line AST check that retires rule 2 — but it makes
every one-off a permanent resident of a cached prefix that only pays back on
reuse, and it puts every helper in the shared namespace, so every later edit
becomes a cross-entry refactor and 4b's refusal rule fires constantly instead of
rarely. It also makes entry-parallel worse: that is out of scope *because* entries
share `_analysis.py`, and this would make every entry write there.

**Rejected: ask the coordinator where each helper goes.** The information
asymmetry runs the wrong way. In 4e the coordinator holds the design brief —
information the instance lacks. Here it has not read the function and knows
strictly less. The one thing it does know is what siblings are in flight, and that
is better given as context up front than as several round trips per entry. And
`aero_calls_of`'s own docstring settles the general question: *"Derived rather
than configured because the alternative was measurably wrong."*

---

## Verification

**The two-instance collision test comes first.** Every claim in 4c and 4d is
reasoning from the code — the system has never had two instances against one
notebook. Run two `nb write` calls concurrently, record what breaks and in what
order, then keep it as the regression test.

- **4a** — a terminal run looks byte-identical to today; `2>/dev/null` leaves only
  the conversation; `status.log` holds the telemetry of a run that died, including
  what the model was thinking at the turn it went wrong. Confirm the prompt-token
  delta matches ~250/turn.
- **4b** — an ordinary question runs end to end on one command and commits; a
  `new_chapter` question stops before scaffolding; an attempt to edit `_model.py`
  in a chapter with siblings is refused and stops naming the entry count; after
  `--allow-refactor`, `check` runs by itself and commits on a clean diff. Seed a
  deliberate model change and confirm it stops with the moved entries named. The
  rendered prose comes back on stdout with the sha.
- **4c** — stage two entries, commit each with its own pathspec, and confirm each
  commit contains only its own files; concurrent commits produce two commits with
  the right messages. Under `--no-commit`, both produce a `ready.json` and the
  coordinator commits them serially.
- **4d** — two concurrent new-chapter runs produce `03` and `04`, not two `03`s,
  and neither clobbers the other's stub; a deliberately wrong `--chapter-number`
  falls back rather than aborting. `check` on an untouched chapter reports an empty
  diff and byte-identical PNGs.
- **4e** — a Specified input reaches the human and an Unknown does not; a Derivable
  declared as either is rejected at ask time; a tty run asks about Specified only;
  two instances assuming the same quantity differently are visible in the register.
- **4f** — re-run the A/B after deletion and confirm the live system reproduces
  ~67%; watch `cached_tokens` for a silent regression.
- **4g** — a run given a deliberately small token budget proposes rather than dying;
  declared vs actual render cost is recorded and the error is visible.
- **4h** — rules 21 and 22 fire on the three known dead functions and the ~17
  internal-only ones, and on nothing else in the two clean notebooks. Rule 20 as a
  warning: count how often it fires across a dozen entries before promoting it to
  a violation. Confirm the prefix drops by ~870 tokens after rule 22 is applied.

---

## Order

1. **Two-instance collision test** — tells you which of 4c/4d are real.
2. **4a, two streams** — small, useful today, independent of any coordinator.
3. **4b, remove the gate** — the largest simplification, depends on nothing, and
   every later stage is smaller against one command than two.
4. **4c, safe commits** — one word (the pathspec) removes a silent-corruption
   bug that exists today; `--no-commit` can wait for a coordinator that vetoes.
5. **4d, atomic allocation** — removes the remaining races without coupling.
6. **4e, input triage** — before the coordinator has habits; retrofitting the
   Specified rule means auditing everything it already decided.
7. **4f, caching** — measured; deletes code rather than adding it. Any time.
8. **4g, budgets** — needs 4a's split to report spend without drowning the
   conversation.
9. **4h, where helpers live** — independent of everything; do it whenever. Rule 22
   is free prefix; rule 20 wants a warning period first.

Steps 3, 4, 5 and 9 stand on their own merits — 4 fixes a live bug, and 5 and 9
need no coordinator at all. Steps 2, 4 and 5 are the minimum for driving parallel
chapters. Step 6 is what stops the coordinator deciding the design itself. 7 and
8 make it economical.

---

## Out of scope

- **The design brief.** The most important artefact in the vision, and not a change
  to `nb`.
- **The coordinator**, including how it compares proposals for overlap and how it
  scopes the register from 4e.
- **Entry-parallel within one chapter.** Needs a lock across the whole write loop,
  which serialises most of the benefit. Revisit with measurements.
- **Retiring `.claude/skills/design-notebook/`.** `nb/vendor/` is canonical; rule 19
  already widened the gap.
