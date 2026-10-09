# Replacing the coordinator with Gemini 3 Pro

## Context

`nb` runs an aircraft-design programme as two roles. The **run** is a Gemini agent
in a sandboxed tool loop — it probes, writes an entry, lints, renders and commits.
The **coordinator** is the other half: it holds the direction, picks the next
question and its chapter, answers what the runs ask, escalates what the direction
does not settle, and sets a new aircraft up. Today that is Claude Code driving the
`nb` CLI from a prose skill at `.claude/skills/coordinate-design/SKILL.md`.

The goal is Gemini 3 Pro in that role, in its own tool loop, **without retiring the
skill** — Claude Code should still be able to coordinate, and the two must not drift.

This is less a port than it looks. `nb/process/coordinator.py:1` already models the
coordinator as a participant in the run mailbox at a reserved id, holding no lock,
state entirely on disk; `nb/process/mailbox.py:21` says the file-based protocol
exists so the answerer can be *"now themselves, later a coordinator agent"*;
`nb/cli/board.py:9` calls that independence *"the whole design — it is what lets a
coordinator agent replace the person here without the agents changing."*

Four findings from exploration shape the work:

- **`nb/agent/loop.py:226` already returns images.** A handler returning
  `{"_image": bytes, "mime_type": …}` gets an inline image part beside its function
  response, verified against the API. `nb/tools/figures.py:82` priced one PNG at
  1,298 tokens against 23k for the base64 mistake. Vision needs no loop change.
- **A blocking tool call costs zero turns.** `loop.py:197` dispatches handlers
  synchronously, so a `wait()` that blocks twenty minutes spends no turn and no
  tokens. Every "RUN THIS IN THE BACKGROUND" instruction in the skill is a
  workaround for Claude Code's ten-minute shell cap (`nb/cli/listen.py:22`) and
  deletes rather than ports.
- **Mask cutting is now one parameterless command** (`e9598e0`). `nb mask` cuts with
  a pinned BiRefNet session; `nb/tools/masks.py:28` says *"NO ESCAPE HATCH,
  deliberately. There is no predicate, no bound, no crop."* The coordinator no
  longer writes code to cut a mask, which removes the only reason it needed
  arbitrary code execution.
- **Tool lists cannot change mid-session.** `nb/tools/__init__.py:8` removed
  per-phase filtering because tools render at prefix position 0, so a list that
  changes at a transition invalidates the implicit cache from that point.

## Decisions taken

| | |
|---|---|
| Coordinator model | `gemini-3.1-pro-preview`. Runs stay on `gemini-3.8-flash` — quota is 250/day **per model** (`nb/config.py:68`), so coordinator turns never eat a run's budget. |
| Scope | Both halves: new-aircraft setup **with vision**, and the steady-state programme loop. |
| Human channel | `nb escalate` and the coordinator mailbox only. No second conversation surface. |
| Packaging | **One** entry point, `nb coordinate <notebook>`, one fixed tool list. |

### Why one command, not two

An earlier draft split `nb setup` from `nb coordinate` so that unsandboxed
capability lived in a visibly separate command — the point being not to quietly
reverse `nb/tools/__init__.py:44`'s case for deleting `bash` from the run agent.

The masking simplification dissolves that. With `cut(bg=…, keep=…, bound=…)` gone,
setup's tool surface is entirely typed — `new`, `search`, `fetch`, `add_photo`,
`read_image`, `read_plan_page`, `source`, `mask`, `overlay`, `reference`. There is
no code-execution tool to quarantine, so there is nothing for a second command to
hold.

Phase-gating the tools inside one session is also ruled out by the caching doctrine
above. Ten extra declarations carried for the whole programme is a small constant
prefix cost; a list that changes at the setup/steady-state boundary invalidates the
cache from that point, which is the mistake `PHASE_OMITS` already was.

## The tool surface

All thin wrappers over code that exists. No shell, no arbitrary Python.

| tool | wraps | note |
|---|---|---|
| `direction` | `cli/direction.py` | |
| `ask` | **subprocess** `python -m nb ask --quiet` | see below |
| `wait` | `cli/listen.py` + `process/coordinator.wait` | **new**: one wait, both sources |
| `answer` | `cli/answer.py` | `by="coordinator"` default |
| `read_run` | `run.json` | the whole record — `answer`, `prose`, `outcome`, `findings`. Never `status.log` |
| `board` | `cli/board.py` | **structured**, not the human table |
| `manifest` | `domain/manifest.build` | the same picture the run gets |
| `history` | `git log -- <nb>/chapters/` | |
| `note` · `escalate` | `cli/note.py` · `cli/escalate.py` | |
| `stop` · `resume` · `clean` | `cli/*.py` | recovery |
| `new` | `cli/new.py` | `--spec`/`--assume`/`--target` as lists |
| `reconstruct` | **subprocess** `python -m nb reconstruct --quiet` | the first run; carries a standing `--why` |
| `search` | Gemini `google_search` grounding, or a typed wrapper | see **Research** below |
| `fetch` | `urllib` → session scratch | candidates, before the notebook exists |
| `add_photo` | writes `<name>.png` **and** `<name>.txt` into `_reference/` | atomic: a photo cannot land undescribed |
| `read_image` · `read_plan_page` | `_image` · `pdftoppm` | judge a candidate; read a plan's spec table |
| `source` | appends to `_reference/SOURCES.txt` | what was found, with its URL — and what was **not** |
| `mask` · `reference` · `overlay` | `cli/mask.py` · `cli/reference.py` · `tools/masks.overlay` | `overlay` returns `_image` |
| `finish` | `coordinator.note` + a clean exit | **terminal**; refuses while a run is live |

Four things to get right:

- **`ask` must spawn a subprocess, not call `cli.run.ask`.** `_start`
  (`nb/cli/run.py:288`) double-forks via `process/detach.py`; calling it in-process
  would fork the coordinator. A fixed argv through `Popen` is not a `bash` tool and
  does not reopen that argument.
- **`wait` must watch both sources.** `listen` wakes on runs, `coordinator.wait` on
  the human. Blocked in one, the coordinator is deaf to the other. `listen.py`
  already polls at 2 s with a predicate over the run dirs; add the coordinator
  mailbox to it.
- **`wait` must not spin.** `listen.py:44` deliberately re-reports a standing
  question every call, so a model that waits without answering gets an instant
  return and burns a turn in a tight loop. `wait` should refuse to block on a
  question it already reported, and say why. `stuck.Detector` is the backstop.
- **Ending is a tool, not the absence of one.** `loop.run` returns as soon as a
  turn carries no tool calls (`loop.py:195`), which would let the coordinator walk
  away from a run still in flight. A detached run outlives it — `process/detach.py`
  gives it its own session precisely so nothing in the shell can reach it — so it
  would hit its assumptions prompt with nobody listening and take a default. That
  is the recorded chapter-06 failure, reproduced structurally. `finish(summary)`
  therefore **refuses while any run is live**, names them, and tells the model to
  `wait` instead; it writes the closing line to the board and lets the loop end.

## Standing up a new aircraft, end to end

The order is forced by two constraints: `nb new` refuses a directory that exists
and is non-empty (`cli/new.py:110`), and it is what creates `_reference/` — so
nothing can be fetched into the notebook before it exists, and the brief rows have
to be researched before it is created.

```
search / fetch / read_plan_page   research the aircraft           → scratch
source                            SOURCES.txt copy, incl. absences
new                               --spec --assume --target --chapter-title --defines
read_image                        judge candidate frames for angular spread
add_photo  × N                    chosen frames + their .txt into _reference/
mask                              one pinned model, no parameters, ~1 min/photo
overlay    × N                    LOOK — the only check for a wrong object
reference                         green: labelled, sized, worst-pair IoU < 0.80
reconstruct --chapter 01-…        the first run: build the vehicle, prove the targets
wait → read_run                   …and the programme loop begins
```

Two details that bite:

- **`add_photo` is one tool, not `fetch` plus a write.** A photograph whose sibling
  `.txt` is missing is not `kind: photo` (`figures.reference_kind`), so it is
  silently skipped — it does not fail, it just never reaches the run. Bundling the
  image and its description into one call makes an undescribed photograph
  unrepresentable. The `.txt` must open with the word `photo` and state the
  viewpoint in words, because that is what the run reads as fact and what the
  fitted camera is later checked against.
- **`reconstruct` is the initialisation step, and it is a run.** It takes no
  question — the question is always "can we reconstruct this within tolerance?" —
  and it carries its own standing `--why`. So it is launched like `ask` (detached
  subprocess, run id back) and answered through the same `wait`/`answer` loop.

## Turn economics

One entry, steady state:

```
ask(chapter="06-…", question=…, why=…)   → run id                [instant]
wait()                                    → blocks 90 s · "run … asks: assumptions"
answer(run, "2: 0.85") + note(…)
wait()                                    → blocks 14 min · "run … ended: committed"
read_run(run) … and the next ask          → headline, findings, declared inputs
```

≈4 turns and ~15 min per entry; a ten-entry programme ≈40 turns against
`MAX_TURNS = 80`.

**Neither turns nor context is tight.** `read_run` returns the whole `run.json`
record and should: `prose` is the *rendered entry* — the published page, real
numbers, code stripped — not the model's reasoning. `run.py:72` draws that line
deliberately: *"A reader of `run.json` should not have to sift the model's
reasoning to find out what happened — `answer`, `prose` and `findings` are there so
it never has to."* The reasoning is in `status.log` and `transcript.jsonl`, and the
coordinator reads neither; `PROSE_CAP` is 4,000 characters against a **measured 616
on a real entry** (`run.py:65`), so ten entries is ~1.5k tokens. There is nothing
here to ration, and the coordinator gets the finding in full — which is what
"follow the finding, not the plan" requires.

**Every turn figure in this plan is an estimate, not a measurement** — ~4 per entry,
~10 for setup, ~15 for research, and the SKILL.md line split. They come from reading
the code, not from a run. `nb eval` is what will replace them.

Setup is now cheap too. The old cut → look → adjust-the-discriminant → re-cut loop
is gone; it is `mask` once, then one overlay per photograph, then swap any frame the
model got wrong. Call it ~10 turns and ~5 images (≈6.5k tokens), which is why it
fits inside the programme session rather than needing its own.

### Concurrency is preserved, and is why this is an agent and not a script

`nb ask --quiet` detaches and returns a run id; `nb/README.md:147` describes parallel
asks with two pools; `claim_chapter` refuses a second writer per chapter;
`process/locks.py` serialises only the genuinely contended render. One `wait()`
returns on *any* run asking, ending or dying, so **turn cost scales with events, not
with runs in flight** — three concurrent runs cost the same per event as one.

A scripted driver over one run is a clean `while` loop. Over N it is a scheduler:
which chapters are free, whether run A's finding invalidates the question queued for
chapter 04, whether to stop run B now that A has settled what B was probing. That
interleaving is the judgement the model is for. The coordinator needs `board()` to
know which chapters have live runs before it routes a question.

## Research

The coordinator must be able to search the web — to find an aircraft's published
specifications, to find photographs in the first place, and to answer what a run
asks. This is not a loosening of the system's rules; it is the half they already
assume. SKILL.md states the asymmetry outright — *"The agent cannot research. No
network, sandboxed to `chapters/`… You can research; it cannot. A row that states
the number is worth five that state its absence."*

**The run stays offline, and nothing here is registered in `nb/tools/__init__.py`.**
The coordinator and the run now live in one package, so this has to be stated rather
than assumed: `search`, `fetch` and `read_image` go on the coordinator's tool list
only. `nb/tools/masks.py:34` already sets the precedent for a coordinator-only module.

### Reuse the reading, build the writing

Checked before proposing new code, since `nb/tools/mcp_fs.py` shows this codebase
already consumes an MCP server where one earns its place.

**Reuse, zero code.** `google_search` grounding and `url_context` are both
server-side Gemini tools — one `types.Tool` entry each, no handler, no key, no
dependency. Between them they cover "find the aircraft" and "read its spec page",
which is most of the research job.

**Do not reuse, for a measured reason.** A generic MCP fetch server returns content
*into the conversation*. For a photograph that is precisely the mistake
`nb/tools/figures.py:82` already records and fixed — a PNG through a function
response cost ~23k tokens against 1,298 for an inline part, and vision never
engaged. Reference images must go **disk to disk and never touch the context**, and
no off-the-shelf server does "download this URL to `_reference/<name>.png` and write
its `.txt`". There is also a standing tax: declarations sit at prefix position 0 and
are billed on every request, which is why `mcp_fs.py:24` exposes five of the
filesystem server's fourteen tools. An eight-tool fetch server to get one capability
is a permanent cost for a one-off job.

**So build `fetch` and `add_photo` — about 40 lines of `urllib` and pathlib.**
`add_photo` has to be local regardless, because it encodes the `_reference/`
convention and the `.txt` rule.

**Design out the path hazard rather than confining it.** `mcp_fs.py:7` exists
because a bug in path handling cannot be allowed to widen a boundary, and it names
the earlier failure — *"a glob allowlist ran against the model's raw string and
`../../` walked straight through it"*. A `fetch(url, dest)` taking a model-supplied
path reopens exactly that. So the model never supplies a path: `add_photo` takes a
bare `name` slug and computes the destination, and `fetch` writes only into a
session scratch directory under a generated name. No traversal surface to defend,
and no second process needed to defend it.

### Two mechanisms, and `fetch` is needed either way

- **Native `google_search` grounding — SETTLED, 2026-10-08, and it works.** Measured
  against `gemini-3.1-pro-preview` on the installed SDK:

  | config | result |
  |---|---|
  | function declarations only | OK — calls the declared tool |
  | `google_search` only | OK — searches |
  | both, as two `Tool` entries | **400** `INVALID_ARGUMENT` |
  | both, as one `Tool` entry | **400** `INVALID_ARGUMENT` |

  The 400 names its own fix: *"Please enable
  `tool_config.include_server_side_tool_invocations` to use Built-in tools with
  Function calling."* With `tool_config=types.ToolConfig(
  include_server_side_tool_invocations=True)` **both shapes return 200**, and a
  second probe confirms the model still routes correctly with both declared — a
  question only search can answer produced two web queries and three sources and no
  function call; a question only the notebook can answer produced the function call
  and no search.

  So: two `Tool` entries, plus that one `tool_config` field. **`client.config()`
  does not currently set `tool_config` at all**, so it needs a parameter — the
  single code change this unlocks. No handler, no API key beyond the existing one,
  citations arrive as `grounding_metadata` (`web_search_queries`,
  `grounding_chunks`).

- **A typed `search(query)`** over an external API — no longer needed, kept here only
  as the fallback if grounding quality disappoints.

**One warning from the probe, and it supports a rule already in this plan.** Asked
for the Little Piggy's published wingspan, grounding found the right pages but
answered that Flite Test *"have not prominently indexed its exact wingspan"* — while
`little-piggy/_reference/SOURCES.txt` records `Wingspan 29 in (736.6 mm)` straight
off the store page. Grounding is good at *finding the page* and unreliable at
*extracting the figure*. That is exactly why `SOURCES.txt` lines must come from a
page `fetch` actually returned rather than from a search summary.

`fetch` is required under both. Grounding returns *text*; photographs and plan PDFs
have to become files on disk, which only a fetch tool does — writing to session
scratch under a generated name, with `add_photo` the only thing that puts anything
into `_reference/`.

### Research must land on disk, not in the conversation

`little-piggy/_reference/SOURCES.txt` is the existing artefact and the model for
what good output looks like: a URL, what it published, and — explicitly — what it
did not. *"WING AREA and WING LOADING are NOT published. Neither is thrust."*

Three rules, all of which reuse doctrine that already exists:

1. **Record the absence.** An unknown the coordinator names is one the run declares;
   one left silent is one it invents and attributes. A search that fails is a result
   and belongs in `SOURCES.txt`.
2. **A fetched URL, not a recalled one — ENFORCED, not advised.** Every
   `SOURCES.txt` line must come from a page `fetch` actually returned in this
   session. This is the one failure mode research adds that the system has no
   existing defence against, and the stage-0 probe showed it is not hypothetical:
   grounding found the right Flite Test pages and still reported the wingspan as
   unpublished, when the store page prints `29 in (736.6 mm)`.

   So it is a precondition in code, not a line of doctrine. `fetch` records
   `(normalised url, sha256, bytes, fetched_at)` in a per-session ledger on the
   coordinator's own run directory; `source(url=…, text=…)` requires `url` and
   **refuses with the ledger's contents** when that URL is not in it:

   ```
   refused: nothing was fetched from store.flitetest.com/ft-little-piggy/.
   SOURCES.txt records what a page said, so fetch it first.
   Fetched this session: <3 urls>
   ```

   Two deliberate consequences. A figure the model recalls rather than reads cannot
   be recorded at all — it has to go and get the page, which is the behaviour
   wanted. And an **absence** is still recordable, because recording "X is not
   published" means having fetched the page that fails to publish it; `source` with
   no URL is refused for the same reason, so "I searched and found nothing" must
   name the page that came up short.

   The ledger is per session and deliberately not persisted: a URL fetched in a
   previous run of `nb coordinate` proves nothing about what this one read.
3. **More research makes the target trap worse, not better.** A published dimension
   is an input, not a target — span, length, prop size go in `--spec`, or in
   `--target` marked `(given)`. An agent that can find twenty published figures is
   under twenty times the temptation to type them as targets, and the F-16's "0.39%,
   all airframe targets inside tolerance" was the model being compared with itself.
   `the-brief.md` carries this and belongs in the prefix for exactly this reason.

### Searching does not make a Specified input answerable

This is the governance point, and it needs saying in the doctrine because the
capability invites the error. A Specified input is *"the one you may not invent"* —
answerable only when the user's direction settles it, otherwise escalated. **A
number found on the web is not the user's direction.**

The resolving distinction already exists in the assumptions-prompt section, and
research maps onto it cleanly:

- a **property of the real aircraft** (published thrust, span, dry weight) — research
  is the right answer. Find it, `source` it, answer, and say where it came from.
- a **design decision** (what static margin do we want, which mission) — research
  cannot settle it. Escalate. A plausible figure from a forum post is the most
  dangerous possible answer here, because it looks sourced.

### Cost

Judging candidate photographs means looking at them: ~1,298 tokens each
(`figures.py:82`), so a dozen candidates is ~16k. Budget the search phase at ~15
turns and cap candidates rather than fetching everything a query returns.

## Vision is still required — and for a different reason than before

The simplification narrows the visual step without removing it, and it changes which
failure the eye is catching.

The old per-pixel rules failed by **under-segmentation**: shaded panels fell outside
the mask, a ragged boundary followed, and `noise` partly caught it — the bad Little
Piggy cuts scored 14.4 / 2.6 / 1.7% against good re-cuts at 3.8 / 0.9 / 0.4%, which
overlap, so the number was only ever corroboration.

The model fails differently. `masks.py:28` records that on the Mustang *every* model
tested kept the hand holding the aircraft. A hand-plus-aeroplane silhouette has a
perfectly clean boundary, so **`noise` cannot catch it at all** — the model's own
noise is 1.5% against the hand cuts' 3.0%. The numbers got better and less decisive
at the same time. `SKILL.md` states it plainly: *"LOOK AT THE OVERLAYS. This is the
part no tool does for you. The model reports nothing when it is wrong."*

So the exit condition for setup is a green `nb reference` **plus** an overlay the
agent has looked at per frame, and the remedy when one is wrong is now `fetch` a
different photograph — not a parameter, because there deliberately is none.

Two guards the agent inherits for free: `nb mask` refuses to overwrite a mask in a
notebook with committed entries, and launch refuses on any mask whose size differs
from its photograph (`nb/cli/run.py:215`).

## Handing back to the user

A bounded direction — "ask five questions about the wing, then come back" — needs
nothing special. The model runs the loop five times and calls `finish`; `nb
coordinate` prints the summary and exits. Five questions is ~20 turns against
`MAX_TURNS = 80`.

The user gives more direction by running `nb coordinate <notebook>` again. That is
the cold-start path below, which is the **normal** entry rather than a recovery
mode: the prefix rebuilds from `manifest.build` and `coordinator.notes`, and the new
direction is recorded with `nb direction`, which is what pins the pivot on the board.

Mid-programme the coordinator can also stop *without* ending: `escalate` puts the
question where the user is sitting and `wait` holds for the reply, costing no turns
while it blocks. Use that when the programme should continue after an answer, and
`finish` when the session's work is done.

## Cold start

`nb coordinate` lives for hours and will sometimes die mid-programme. The *state*
survives — mailbox files, `coordinator/log.jsonl`, git, the `ends` watermark in the
coordinator's own `run.json` (`listen.py:33`) — but the conversation does not, and
should not be resumed from a transcript. The prefix rebuilds context from
`domain/manifest.build` and `coordinator.notes`. `nb/domain/manifest.py:4` notes that
under Claude Code the skill got continuity free from a long session while every run
starts cold; the coordinator now joins them, and the manifest is what makes that safe.

So `nb coordinate` on a notebook with work already in it is the **normal** entry
path, not a recovery mode. A notebook that does not exist yet is the other branch,
and it opens with setup.

## Keeping the skill intact

Both coordinators reach `nb` through the same CLI and the same on-disk mailbox, so
nothing here takes anything from Claude Code. The hazard is **drift**: two copies of
hard-won doctrine. It is already demonstrable — `nb/__main__.py`'s `USAGE` documents
`nb new … [--spec] [--assume]` but omits `--target`, which `__main__.py:141` parses
and `nb/cli/new.py` renders, and which SKILL.md's dimension-vs-target section depends
on existing.

So the skill survives by ceasing to be the source. Durable doctrine moves to
`nb/references/coordinator/*.md` — the pattern `nb/agent/prefix.py` already uses,
with `PREFIX_DOCS` (prefix.py:44) always in the cached head and `nb/tools/refs.py:28`
holding the governing rule that a page in the prefix is *removed* from the lookup
enum, because offering both buys a wasted turn.

Classifying the current 524 lines:

| bucket | ≈lines | content |
|---|---|---|
| **Durable doctrine** | ~300 | what you hold · read before asking · `--why` is your sentence · Specified inputs · escalation · record the direction · narrate · choose the next question · the plan sheet first · `--assume` is not a directive · angular spread and overlay inspection · dimension-vs-target · the assumptions prompt |
| **Claude-Code harness** | ~80 | `nb open` and the one tab · `--quiet` is not optional · watcher windows · "do not poll, background it" · "background the `await`" · the shell-cwd trap |
| **Redundant under typed tools** | ~140 | always pass the run id · the exit code only reports the launch · the question is ONE quoted argument · `--chapter` is required · the `kind`→how-to-answer table (already in `question.json`'s `how`) · the `run.json` field table · recovery mechanics |

Pages, under `nb/references/coordinator/`, with a `doctrine.py` registry mirroring
`tools/refs.py`:

| page | holds | in prefix |
|---|---|---|
| `programme.md` | the boundary, the direction, notes, choosing the next question, escalation | always |
| `the-brief.md` | `--spec`/`--assume`/`--target` discipline, the F-16 directive rows, dimension-vs-target | always |
| `sources.md` | find the plan before you build the aircraft; what `SOURCES.txt` is for; record the absence; a fetched URL not a recalled one; research settles facts, never decisions | always |
| `reference-photographs.md` | angular spread, overlay inspection, change-the-photograph-not-the-code | always |
| `judging-a-run.md` | the question kinds, Specified inputs, the assumptions prompt as a defect report | always |

All five in prefix, against the `prefix.py:34` test — *"a page that prevents a wrong
conclusion is not a page to leave behind an optional lookup"* — and because a single
command has one tool list and one prefix. Total is well under the ~7,700 tokens the
run agent already carries. `reference-photographs.md` is roughly half what it was:
the saturation table, the three-class sampling rule and the worked `cut` script all
died with the hand-cutting API. The run-side `nb/references/photographs.md` stays as
it is and is cross-referenced, not duplicated.

SKILL.md keeps buckets 2 and 3 plus a pointer. Claude Code has no include directive,
so expose the pages through one command rather than five paths — `nb doctrine` with
the same grouping `doctrine.py` hands the prefix, so a regrouping changes what Claude
reads automatically. `allowed-tools` already permits `Bash(uv run … -m nb *)`.
Net: ~524 → ~250 lines.

## Drift checks

In `nb/preflight.py`, beside `_rule_list_problems` (preflight.py:22) — which exists
because a hand-copied rule list went eight rules stale:

1. **Registry completeness** — every file in `references/coordinator/` is in
   `doctrine.PAGES` and vice versa; no page is both in the prefix and in the lookup
   enum (the `refs.py:28` invariant, currently enforced only by a comment).
2. **No second copy** — normalised ≥8-word shingles shared between SKILL.md and any
   `coordinator/*.md`. This enforces the actual goal: not "is the copy fresh" but
   "there is no copy".
3. **`USAGE` against the parsers** — the `--target` omission above, caught the same
   way the rule list is.

The `nb/tools/api.py` generation trick applies only to signatures, and there are
barely any left to generate now that the mask API is one parameterless command. Not
worth a generator; a test that `ast.parse`es the fenced examples and binds them
against real signatures covers it.

## Sequencing, and when to abandon

This plan is four separable pieces and should not be built as one. The order below
puts the load-bearing uncertainty first and the polish last, so that a failure costs
a day rather than a fortnight.

**0 — Settle the unknown. ✅ DONE, 2026-10-08.** `google_search` and function
declarations coexist on `gemini-3.1-pro-preview` provided
`tool_config.include_server_side_tool_invocations=True` is set; without it both
shapes 400. Routing between the two was verified in both directions. See
**Research → Two mechanisms** for the table. The only consequence for the build is
that `client.config()` gains a `tool_config` parameter.

**BUILT, 2026-10-08 — all four stages.** `nb/coord/` (`session.py`, `tools.py`,
`research.py`, `prefix.py`, `doctrine.py`), `nb/references/coordinator/*.md`,
`nb/cli/coordinate.py`, `nb/cli/doctrine.py`, `tests/coordinator.py`, and four
drift checks in `nb/preflight.py`. 24 typed tools plus server-side
`google_search`. SKILL.md is 524 → 169 lines.

**Run live, end to end, on a fresh `little-piggy`.** It researched the
aircraft, wrote a brief with span/length/wheel in `spec` and mass/CG in
`target`, recorded the absences in `SOURCES.txt`, found one photograph,
escalated for more rather than settling, survived a process death and a cold
restart, collected the answer, reached four viewpoints at worst-pair IoU 0.49
against the 0.46 reached by hand, masked and inspected every overlay, launched
a reconstruction, answered its budget question, and committed.

**And the entry it committed is worthless**, which is the finding that matters.
See *What the live run exposed* below.

What the first live session found, all fixed — and all of it plumbing rather
than judgement, which is worth noting because the model's research half worked
from the first turn:

| | |
|---|---|
| `new` took a `directory` argument | so the model named the notebook. Launched as `nb coordinate little-piggy`, it created `ft-little-piggy`. The name comes from the command line now; the parameter is gone. |
| a failed `new` left the directory behind | `nb new` creates, *then* lints and renders, so a failure blocks the retry with "exists and is not empty" — and the model escaped to `ft-little-piggy-2`. With the name pinned there is no escape, so `_new` removes what that call created. |
| `direction` was refused before `new` | turn 1 was `direction`, correctly, and the log lives inside a notebook that did not exist. It never came back to it. Now buffered, like `source`. |
| the setup transcript went to `None` | an aircraft-setup session left no record — the sessions most worth reading back. Temp file, filed under the notebook afterwards. |

## What the live run exposed

Two failures, and they are at different layers.

**The coordinator accepted a guessed constant it could have looked up.** The
run declared `foam areal density: 0.40 kg/m^2 — yields reasonable ballast`.
The published figure is 0.293 (and 0.297 from a second supplier). The
coordinator called the assumption "sound". With the density 37% high the foam
mass was wrong, so the run closed the gap to the published dry mass with 130 g
of invented ballast and hit the CG by typing a battery station — then reported
`0.01% — maximum error across all targets`, which is the model agreeing with
itself. Root cause: the brief carried a mass target and no material density,
because nothing told the coordinator to research what a target is MADE of.
Both halves are now in `sources.md` and `judging-a-run.md`, with the measured
case written in.

**The run abandoned the photograph check and nothing noticed.** It called
`compare_to_photo` 37 times and `fit_geometry` 17, fitted geometry on poses
its own log recorded as `POSE NOT CONVERGED` and `Pose: DOUBTFUL`, timed
`fit_geometry` out at 300 s, and then switched to setting the fuselage width
and root chord "by eye" — the exact thing silhouette fitting replaces.
`show_comparison` appears **zero** times in the committed entry, which carries
a three-view and an error chart, both model-against-model, under prose
claiming "the shape matches the supplied photographs".

**The coordinator could not have caught the second one, and that is an
architectural gap rather than a prompt problem.** `read_run` returns `answer`,
`prose`, `outcome` and `findings`; all four looked healthy. That the poses
were doubtful and the overlay was dropped exists only in `status.log`, which
the coordinator is explicitly told never to read. Nothing proposed here fixes
it. The candidates, none yet chosen:

- a rule that refuses an entry whose prose claims a photographic match with no
  `show_comparison` rendered — the same shape as rule 44, which was written to
  catch a derived target typed as a constant and has now missed twice;
- `run.json` carrying the last pose verdict per view, so the coordinator sees
  `DOUBTFUL` without reading the log;
- a bigger probe grant for `fit_geometry`, since 300 s against four views is
  not enough and the run spent 17 partial attempts discovering that.

`tests/coordinator.py` holds the separation the two agents depend on: the run
can reach no networked tool, the coordinator can reach no authoring tool,
declarations and handlers are in parity, and every notebook-dependent tool
refuses in words rather than raising before `new`.

**1 — Steady state only, on `little-piggy`.** `nb coordinate` with the programme
tools and no research, no vision, no setup: `direction` `ask` `wait` `answer`
`read_run` `board` `manifest` `note` `escalate` `finish`. Doctrine as one
hand-written prefix page, not yet a refactor of SKILL.md. This is maybe a fifth of
the work and it proves every claim the rest rests on — blocking waits cost nothing,
the mailbox round-trips, the board reads right, Pro can pick a next question worth
asking. **Stop here and evaluate before building anything else.**

**2 — Setup and research.** `new`, `search`, `fetch`, `add_photo`, `read_image`,
`source`, `mask`, `overlay`, `reference`, `reconstruct`. A fresh aircraft end to end.

**3 — The doctrine restructure.** Split the prefix page into the five
`references/coordinator/*.md`, shrink SKILL.md to point at them, add `nb doctrine`.
Deferred because it is the piece that pays off *later* — it prevents drift between
two coordinators that both have to exist first — and because the prose written for
stage 1's prefix is most of it anyway.

**4 — The drift checks.** The three preflight additions. Cheapest and last; they
guard a structure that must already be in place.

### The kill criterion, stated now

`nb/config.py:55` records a model swap decided off an encouraging smoke test and
reversed the same morning: flash burned forty turns and never proposed an answer.
`nb/cli/eval.py` exists *because* nobody queried the numbers that were already
there. So fix the test before running it, not after.

After stage 1, over at least five questions on a live notebook, Pro coordinating
should show: every run reaching `committed` or a recorded, sensible non-commit; no
question defaulting unanswered; `--why` lines a reader would accept a month later;
and a next-question choice that follows the previous finding rather than a backlog.

**Abandon if**: questions time out while the coordinator is alive and well — that
is the chapter-06 failure and it is the one the whole design is meant to prevent;
or the `--why` lines are method descriptions rather than reasons, which is the
failure more prompt does not fix. Reverting costs nothing: the skill still works,
and nothing in `nb` has been taken away.

## Files

**First step**: write this document to `coordinator_plan.md` at the repo root, as
asked. Plan mode confines edits to the plan file, so that copy happens on approval.

**New**
- `nb/coord/{__init__,prefix,tools,session}.py` — the coordinator agent. Reuses
  `agent/client.py`, `agent/loop.py`, `agent/stuck.py`, `agent/setup.py` unchanged.
- `nb/cli/coordinate.py` — the entry point.
- `nb/references/coordinator/*.md` + `nb/coord/doctrine.py` + `nb/cli/doctrine.py`.

**Modified**
- `nb/__main__.py` — `coordinate` and `doctrine` in `USAGE` and the dispatch chain;
  add the missing `--target` line.
- `nb/cli/listen.py` — wait on both sources; suppress the standing-question spin.
- `nb/config.py` — `COORD_MODEL`, separate from `MODEL`.
- `nb/agent/client.py` — `config()` gains a `tool_config` parameter, so the
  coordinator can set `include_server_side_tool_invocations`. The run agent passes
  nothing and is unaffected.
- `nb/preflight.py` — the three checks above.
- `.claude/skills/coordinate-design/SKILL.md` — shrink to the harness half + pointer.

**Unchanged on purpose**: `nb/agent/loop.py`, `nb/tools/__init__.py`,
`nb/process/mailbox.py`, `nb/process/coordinator.py`, `nb/tools/masks.py`.

## Verification

1. **Steady state.** `nb coordinate little-piggy` with a one-line direction. `nb board`
   should read as it does under Claude Code — pinned direction, notes, questions,
   answers, with `--by coordinator` on the agent's own decisions.
2. **Blocking is free.** Confirm from the transcript that a `wait()` spanning a
   14-minute run shows one turn, not a poll.
3. **Concurrency.** Three asks in three chapters: one `wait()` serialises the events,
   a same-chapter collision is refused at turn 0, the coordinator routes around a
   locked chapter.
4. **Spin guard.** Answer nothing; `wait()` must refuse rather than return instantly
   in a loop.
5. **Setup with vision.** A fresh aircraft end-to-end. The transcript must show
   overlay images arriving as inline parts, and the agent must reject a mask that
   `nb reference` passes — the hand case is the test that matters, since `noise`
   cannot see it.
6. **Research.** Settle the `google_search`-beside-function-declarations question
   first, with a ten-line script, before any of the rest is built. Then: a fresh
   aircraft where the coordinator finds the specs itself, and `SOURCES.txt` is
   checked line by line against pages it actually fetched — including at least one
   recorded absence. Confirm a published dimension went into `--spec`, not `--target`.
7. **`nb eval <notebook>`** — the coordinator's runs appear with model, turns and
   outcome, so pro-vs-flash stays answerable from the table rather than a comment.
   This is the whole reason `nb/cli/eval.py` exists.
8. **No drift.** `nb preflight` fails on a sentence duplicated between SKILL.md and a
   doctrine page, and on a `USAGE` flag the parser does not document.
9. **Claude Code still works.** Run the existing skill on another notebook and reach
   the same decisions from the same pages.
10. **The run is still offline.** Assert no `search`/`fetch`/`read_image`
    declaration reaches `nb/tools/build()` — a test, not a convention, now that both
    agents share a package.
