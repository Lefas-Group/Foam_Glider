# Design-notebook agent — system specification

A standalone CLI that produces Quarto lab-notebook entries for aircraft design
work. Distilled from the `design-notebook` Claude Code skill; runs without Claude
Code, on Gemini.

---

## 1. Scope

**In scope.** Answering a design question by probing a chapter's model, then
recording the answer as one notebook entry that passes the lint contract.

**Out of scope (META).** The system cannot modify itself: the system instruction,
`lint.py`, `check.py`, `notebook.py`, `_notebook.py`, templates, references,
`_quarto.yml`, or the introspection layer.

| Item | Disposition |
|---|---|
| `chapters/**` — entries, `_model.py`, `_analysis.py`, `index.qmd` | **Writable** — design tier |
| `_notebook.py`, `_quarto.yml` | Not exposed; drift is a preflight failure |
| `_scratch/**` | Reached only through the `probe` handler |
| New chapter | Agent-triggered via `create_chapter`; the template stays out of reach |
| New notebook | Human-run script |
| Lint rule 11 | Moves from lint gate → preflight assertion |
| Raising `SOLVE_BUDGET` / `ENTRY_CEILING` | Human decision at the gate |
| Suspected-bad lint rules | Written to the run log, never to `why.md` |

---

## 2. Architecture — two commands

```
$ nb ask "would more pitch damping fix the disagreement?"
    ├── preflight            §13
    ├── build/reuse cache    §9
    ├── probe loop           agentic, max 25 turns
    │     ├── ask_specified  blocks on stdin — as often as needed
    │     └── consult        blocks on stdin — guidance, max 3
    ├── propose              writes proposal.json + working code
    └── EXIT ────────────────────────────────────── the gate

        ... human reads proposal.json, edits or approves, minutes or days ...

$ nb write
    ├── create_chapter       only if route == new_chapter
    ├── write loop           agentic; lint available as a tool
    ├── lint                 always, after the loop returns
    │     └── fail → back into the loop, cap 3
    ├── render + check
    ├── verify               fresh context, reads the rendered figures
    ├── commit               rebuilds the manifest
    └── next queued question, if any
```

**The gate is a process boundary, not a checkpoint.** Every run stops at exactly
one place, always, and the process exits there. That is what removes the need for
an orchestration framework (§11).

| Layer | Choice |
|---|---|
| Orchestration | None — two commands, state on disk |
| Model calls | Native `google-genai`, `generate_content` |
| File access | MCP filesystem server, scoped to `chapters/` |

Rationale: byte-level control of the cached prefix; provider swap behind one
function; no hand-rolled path confinement; no framework constraints to obey.

---

## 3. State — on disk, not in memory

Nothing persists in process. Two artefacts, both in `_scratch/run/`:

```python
# proposal.json — written by `nb ask`, read by `nb write`
class Proposal(TypedDict):
    title: str                  # the question, verbatim; becomes the entry title
    question: str
    queue: list[str]            # remaining questions from a multi-question ask
    chapter: str
    route: Literal["entry", "new_chapter"]
    rationale: str              # what is held constant, what differs
    figures: list[str]          # captions only — nothing else
    render_cost_s: float        # measured (§10), never guessed
    inputs: list[Input]
    findings: str               # the answer, and what the probe established
    working_code: str           # the code that produced it
    handoff: str                # anything `nb write` needs that isn't above
```

```python
class Input(TypedDict):
    name: str
    kind: Literal["derivable", "specified", "unknown"]
    value: str | None
    owner: Literal["user", "agent", "assumed"]
    why: str                    # ≤ 10 words — lint rule 8 budget
```

`transcript.jsonl` — one line per turn, appended as the loop runs. Purely for
crash recovery and debugging; nothing reads it in the happy path.

**The two phases share no conversation state, by design.** `nb write` needs the
finding and the code that produced it — both in `proposal.json` — and not the
probe transcript, because the entry's code cells re-run the computation at render
time anyway. This is what makes the process boundary clean rather than a
truncation.

---

## 4. The two phases

### `nb ask` — probe and propose

| Step | Contract |
|---|---|
| preflight | §13. Fails in ~5 ms before any tokens |
| cache | Build or reuse the explicit cache (§9), keyed on `hash(system + tools + manifest)` |
| probe loop | Agentic, max 25 turns. Asks for Specified inputs inline (§12). Terminates on `propose` |
| propose | Validates and writes `proposal.json`. Prints the proposal. Exits |

The loop decides everything the old design gave a router: which chapter, whether
a new chapter is needed, and whether the ask is really several questions. It
makes those calls on turn one or later with *more* information than a separate
routing call would have — it can read `_model.py` and try.

**A multi-question ask splits rather than being rejected.** The skill's rule is
*a proposal covering more than one question splits into one entry each*. The
first question becomes this proposal; the rest go in `queue`, and after committing
`nb write` calls `ask` again with the next one, leaving a fresh `proposal.json` at
the gate. The gate still fires between every entry — auto-advance removes
retyping, not review.

The carried remainder is merged into the saved proposal **by `propose`**, not by
asking the model to copy it forward: the queue is bookkeeping, and a model asked
to copy a list forward will sometimes improve it instead.

Verified both ways. *"How does zoom height vary with launch speed, and what speed
doubles it?"* was correctly judged **one** question — facets of a single
comparison (cost, fidelity, applicability) are one question, not three. *"What is
the wing area? And separately, what fraction of mass is the fuselage?"* split into
one proposal plus one queued question, which then ran on its own after the commit.

**The cache rebuilds after a commit, by design.** The manifest is part of the
prefix, and a new entry changes it — so the key changes and the next phase creates
a new cache object (13,848 → 13,887 tokens, observed). That is the manifest doing
its job, not a cost to engineer away.

**The route is an output of probing, not a precondition.** Whether a question
needs a new chapter depends on whether the existing model can answer it, and on
whether the old answer stays valid under its own stated assumptions. The fork
criterion is *whether you want to keep both answers* — Specified by the §12 test,
so it goes through `ask_specified` at the moment the loop realises a fork is on
the table, not deferred to the proposal.

### `nb write` — write, verify, commit

| Step | Contract |
|---|---|
| `create_chapter` | Only when `route == "new_chapter"`. Runs the scaffold script |
| write loop | Agentic. Creates the `.qmd`; may edit `_analysis.py` / `_model.py` |
| lint | **Always runs after the loop returns.** Fail → back into the loop, cap 3 |
| render + check | `check.py`: lint, delete freeze, render, diff |
| verify | Renders, then one toolless call on the rendered page + figures — not the transcript. Findings re-enter the loop, capped |
| commit | git add of named paths + commit; then the next queued question |

**Lint is both a tool and a mandatory step.** The tool lets the write loop fix
violations in place. The step after the loop is the guarantee — without it the
model can decline to call the tool and declare done. Re-running
`lint.py --no-render` on a clean pass costs nothing worth counting.

**`verify` is the only justified second model call with its own context.** Its
input differs from the writer's — rendered figures and printed blocks, not the
conversation — and its question is decidable. Every other judgment stays in the
probe loop, which has the context to make it.

**Built, and it catches what it was built for.** Renders deterministically first
(the write loop is not required to have rendered, and verifying against a stale
freeze is worse than not verifying), reads `result.markdown` from the freeze with
every inline expression already evaluated, attaches each figure as an inline
image part, and makes one toolless call returning `VerifyResult{ok, findings}`.
Toolless means no thought signatures are in play, so the
`skip_thought_signature_validator` case never arises.

Tested against a real entry with a figure, by doctoring the rendered markdown:

| case | result |
|---|---|
| untouched | **ok** — no false positive |
| hero number changed 3.0 s → 9.7 s | caught: *"the figure plots … approximately 3.0 s"* |
| prose inverted the curve's direction | caught: *"the figure shows time aloft increasing"* |
| caption swapped for another plot's | caught: *"the figure actually plots time aloft"* |

That third case is the one no lint rule can reach: rule 1 forces the *numbers* in
prose to be computed, but nothing forces a sentence about a **shape** to match
the shape. Findings feed back into the write loop exactly as lint failures do,
capped at `MAX_VERIFY_ATTEMPTS`.

**Commit adds specific paths, never `-A`.** The working tree routinely carries
untracked Quarto output — `chapters/**/*.html`, `*_files/`, `site_libs/` — from
any render or preview that happens to be running. This is not hypothetical: a
blanket `git add` in this repo swept 17 `.html` files into history, and they then
had to be deleted again. `_commit` names the entry, its freeze directory, and any
of `_analysis.py` / `_model.py` / `_budget.py` that `git status --porcelain`
reports as actually changed.

---

## 5. Tools

One frozen, sorted list, shared by both phases. Prefix position 0; never varies
per request.

### From the MCP filesystem server (6 of 14 exposed)

| Tool | Notes |
|---|---|
| `read_text_file` | `head` / `tail` for slicing — use instead of whole-file reads |
| `read_media_file` | Base64 + MIME. **`verify` depends on this** (§6) |
| `list_directory` | Sibling-entry discovery |
| `search_files` | Pattern search within `chapters/` |
| `edit_file` | `edits: [{oldText, newText}]`, `dryRun` → git-style diff. **Default path for modification** |
| `write_file` | Full overwrite. **Creation only** — new entries |

You are the MCP client; the remaining eight stay out of the prefix.
**Verified:** a `../../pyproject.toml` escape is refused with `Access denied -
path outside allowed directories`. The boundary holds in a *different process*,
which is the whole reason to prefer it to hand-rolled path confinement — a bug in
this code cannot widen it.

The handler resolves notebook-relative paths to absolute before calling, so the
model writes `04-chosen-throw/entry.qmd` rather than an absolute prefix it could
not have got wrong anyway.

**This is the only remaining use of MCP.** The AeroSandbox introspection server
went over stdio because Claude Code had no other way in; vendored, its
`@mcp.tool()` decorators, `FastMCP` construction and stdio `main()` are stripped
and the five functions are imported directly. It builds its index from the
INSTALLED package on first call, so there is no stored index to go stale — which
is why preflight does **not** assert an `INDEX_BUILT_AGAINST` version, as §13
originally specified.

Session via
the official `mcp` SDK (`StdioServerParameters` → `stdio_client` →
`ClientSession`), then convert each tool's JSON Schema to a
`types.FunctionDeclaration`. The server enforces the directory boundary (§6) in
its own process, which is why that boundary is trustworthy.

**Merge and sort once:**

```python
TOOLS = sorted(mcp_decls + native_decls, key=lambda d: d.name)
```

MCP servers do not guarantee stable tool ordering across restarts, and tools sit
at prefix position 0 — an unsorted merge silently invalidates the cache on every
server restart (§9).

### Native handlers

| Tool | Signature | Notes |
|---|---|---|
| `probe` | `(question: str) -> str` | Preamble-injected, §10 |
| `lint` | `(path: str) -> str` | `lint.py --no-render`. Same code as the mandatory step |
| `render` | `(target: str) -> str` | `quarto render` |
| `check` | `(chapter: str, all: bool) -> str` | `check.py` |
| `api_search` | `(query: str) -> str` | AeroSandbox introspection |
| `api_signature` | `(path: str) -> str` | Signature + docstring |
| `read_reference` | `(name: Enum) -> str` | 7 reference docs + vendored book chapters |
| `propose` | `(p: Proposal) -> str` | Terminates the probe loop. Validates, writes `proposal.json`, exits |
| `ask_specified` | `(name, why, options?) -> str` | Blocks on stdin. Records into `inputs[]`. **As often as needed** |
| `consult` | `(question: str, why: str) -> str` | Blocks on stdin. Free-form guidance, max 3 |
| `create_chapter` | `(name: str) -> str` | Wraps the scaffold script; the agent then edits the result via MCP |
| `bash` | `(command: str) -> str` | Allowlisted escape hatch, §7 |

Schemas are generated from Pydantic models — `model_json_schema()` for the
declaration, `model_validate()` on the way back in, so a malformed `propose`
returns a clean error the model can fix rather than a `KeyError` in the handler.

**`propose` is the single terminal tool.** Route, inputs and proposal arrive
together. It rejects `kind == "derivable"` with `"'{name}' is derivable — compute
it, don't declare it."`, and rejects any `specified` input whose `owner` is
`assumed` — those must have been asked (§12).

**`ask_specified` and `consult` need no special machinery.** The process is alive
and you are at the terminal, so each reads stdin and returns. This is the whole
benefit of dropping the framework: under LangGraph every one of these needed its
own node, because a `while` loop containing an `interrupt()` replays prior
iterations exponentially on resume — which also capped how often you could
sensibly ask. Here the cap is only good manners.

All native handlers truncate their own output — tracebacks keep the tail,
listings keep the head. Cap 8 kB.

---

## 5a. What the model knows about the notebook's history

**There is no memory across runs.** Under Claude Code the skill gets this free —
three entries written in one session and the model still remembers the first when
writing the third. Every run here starts cold. Without a substitute the agent
re-derives what it learned last run and will essentially never notice it is
contradicting an earlier entry.

The substitute is a **generated chapter manifest**, built from entry frontmatter
and hero values:

```
04-chosen-throw  (AVL + 6-DOF rollout, tail fixed)
  2026-09-09-01  can-we-optimise-against-a-real-flight-path      → 8.4 s
  2026-09-10-01  would-more-pitch-damping-fix-the-disagreement   → no
  2026-09-11-01  what-if-we-sweep-launch-speed-instead...        → 11.2 m/s
```

Generated, never hand-maintained — `commit` rebuilds it. It serves rule 10
(linking a sibling by stem), route decisions, and correction-spotting (§13a).

### Reading policy

| Tier | Contents | Cost |
|---|---|---|
| **Always — inside the explicit cache** | System instruction, tools, manifest, **every** chapter's `index.qmd`, **every** `_model.py` name, **every** `_analysis.py` signature | ~10,100 tokens with system |
| **On demand — `read_text_file`** | Full entry bodies, when linking a sibling or checking a suspected contradiction | ~625 tokens each |

**Cache every chapter, not just the target.** Measured: all four `index.qmd` ≈
1,900 tokens, all four signature lists ≈ 1,200. Cheap — and it means the prefix
is **identical for every run in the notebook**, so one cache object serves them
all until the manifest changes. Targeting a single chapter would require knowing
the chapter before the cache is built, which is the only real argument there ever
was for a separate routing call.

`index.qmd` is mandatory context, not optional: it states what defines each
chapter and the assumptions that live at chapter level, which entry prose must
**not** repeat.

### `_model.py`'s names are load-bearing, and were missed

The first end-to-end run failed because of this. `index.qmd` describes a chapter
in prose; it does not say that `ZOOM_EFF` and `launch_height()` live in *this*
chapter and not that one. Without those names the model cannot route a question,
and the observed behaviour was twenty turns of `search_files`, `git log`, and
probes used to walk the filesystem — never landing on the right chapter at all.

So the prefix carries each `_model.py`'s **functions with signatures AND its
module-level constants**. The constants matter as much as the functions: a
question about the zoom climb is routed by seeing `ZOOM_EFF = 0.55` in three
chapters and choosing among them, which is a judgement, rather than by guessing,
which is not. Adding them moved the first tool call from a blind directory
listing to a correctly-targeted probe.

Two smaller corrections from the same run:

- **`probe` must refuse an unknown chapter.** `_probe_base` falls back to the
  first chapter alphabetically when `NB_CHAPTER` is unset and says so only on
  stderr — swallowed into tool output, that is how a probe comes to answer
  confidently about the wrong aircraft. It happened on turn 21 of the first run.
- **`git log` / `git show` come off the bash allowlist.** Eight consecutive turns
  went on git archaeology. `check.py` shells to git itself for the one workflow
  that needs history, so the agent never has to.

Measured against the real notebook (25 entries, 4 chapters): all `index.qmd` ≈
1,900 tokens; one chapter's entries ≈ 5,600; every entry ≈ 16,000. Against a 1M
window these are not quantities to agonise over — the skill's context warnings
were written for a Claude Code session that accumulates, and do not transfer at
this scale.

---

## 6. File access model

```
MCP allowed directories:  <notebook>/chapters/
```

The allowlist matches the writable set exactly, with nothing to exclude inside
it. Everything else falls outside by construction:

| Path | Why it's out |
|---|---|
| `_quarto.yml`, `_notebook.py` | Notebook root, outside `chapters/` |
| `_freeze/` | Notebook root; written by Quarto as a subprocess |
| `_scratch/` | Reached only via the `probe` handler |
| Skill, `lint.py`, references | Outside the notebook entirely |

**Principle: content the agent may read but not write is a tool, not a file.**
The agent does not need filesystem access to `_notebook.py` — it needs to know
what `footer()`, `show_source()` and `md_table()` do, which `api_search` and
`read_reference` provide. This is why no read-only filesystem tier is required,
and why no custom path-confinement code exists in this system.

### Figures — RESOLVED by reading `freezediff.py`

`verify` must read rendered figures as images, not just printed text. The failure
it exists to catch — prose written from the conversation rather than the output —
is mostly a *figure* failure: a caption claiming a crossover at 6 m/s when the
curve crosses at 8 is invisible to a text-only check.

They are **real PNG files on disk**, not base64 inside the JSON:

```
_freeze/chapters/<chapter>/<entry-stem>/figure-html/<name>.png
```

`freezediff.figures()` globs exactly that and compares each against
`git show <ref>:<path>` by SHA-256. The `execute-results/html.json` beside it
holds the rendered *markdown*, which references the PNG by relative path.

That sits outside `chapters/`, so it is served by a **native `read_figure()`**
rather than by widening the MCP allowlist. The filesystem server has no
read-only tier, and adding `_freeze/` would grant write access to the one
directory whose integrity `freezediff` depends on. Content the agent may read
but not write is a tool, not a file.

---

## 7. Bash allowlist

```python
ALLOWED  = [("uv","run","quarto"), ("uv","run","python"),
            ("git","show"), ("git","status"), ("git","diff")]
FORBIDDEN = set("&|;`$><\n")

def run_bash(command: str) -> str:
    if FORBIDDEN & set(command):
        return "rejected: shell operators not permitted"
    argv = shlex.split(command)
    if not any(tuple(argv[:len(p)]) == p for p in ALLOWED):
        return f"rejected: '{argv[0] if argv else ''}' not in allowlist"
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    return out[-8000:] if len(out) > 8000 else out
```

`subprocess.run(argv, ...)` with a **list** — never `shell=True`.

Not a security boundary: `uv run python -c "import os; os.system(...)"` walks
through it, and `probe` runs arbitrary Python by design. It prevents accidents
and gives an audit log. Threat model is a local single-user notebook.

---

## 8. The agent loop

Used by both phases. `google-genai`, `generate_content` (§16).

```python
def agent_loop(contents, cfg, max_turns=25):
    for _ in range(max_turns):
        resp = client.models.generate_content(
            model=MODEL, contents=contents, config=cfg,
        )
        turn = resp.candidates[0].content
        contents.append(turn)                    # WHOLE Content — signatures included
        log(turn)                                # transcript.jsonl, for crash recovery

        calls = [p.function_call for p in turn.parts if p.function_call]
        if not calls:
            return resp, contents

        parts = []
        for c in calls:
            try:
                out = HANDLERS[c.name](**dict(c.args))
            except Terminal:                     # propose() — writes and exits
                raise
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {e}"}
            parts.append(types.Part.from_function_response(name=c.name, response=out))

        contents.append(types.Content(role="user", parts=parts))

    raise RuntimeError("max turns exceeded")
```

Invariants:

1. **Append `resp.candidates[0].content` whole.** Model turns carry **thought
   signatures** — encrypted blobs holding the model's reasoning state. The first
   `function_call` part of each step must carry its signature back *exactly as
   received*, or the request fails with `"Function call … is missing a
   thought_signature"`. Gemini 3 validates this strictly; 2.5 did not. In parallel
   calls only the first part carries one. Reconstructing a turn from extracted
   text drops it.
2. All function responses in **one** turn. Splitting them degrades parallel
   calling.
3. Always return a response part, including on failure — an unanswered
   `function_call` is an error on the next request.
4. The broad `except` must not swallow the terminal signal from `propose`.

**Verified 2026-09-11** on `gemini-3.8-flash` and `gemini-3.1-pro-preview`, with
a negative control:

```
A  append Content whole          -> 200 OK
B  rebuild turn from name + args -> 400 INVALID_ARGUMENT
   "Function call is missing a thought_signature in functionCall parts."
```

The failure is immediate and loud, not silent — a signature bug cannot reach
production undetected. Signatures also survived on an old SDK (1.47.0), since
they ride as opaque part data.

**This is why the system is native rather than abstracted (§16).** Signature
round-tripping has been a recurring defect in framework code — dropped in
normalisation, because a common message shape has nowhere to put an opaque
provider blob. Appending raw `Content` sidesteps it entirely.

`verify` constructs fresh history and therefore holds no signatures. If it is
ever given tools, its synthetic turns need the documented dummy value
`"skip_thought_signature_validator"`. As specified it makes one toolless call, so
this does not arise.

---

## 9. Prompt layout and caching

### The mechanism

`generate_content` is stateless — every request re-sends the whole conversation,
so a 25-turn probe loop transmits the system instruction and tool schemas 25
times. Caching lets the model skip re-processing the front of that payload.
Three facts define it:

1. **The request renders in a fixed order:** `tools` → `system_instruction` →
   `contents`.
2. **The cache key is the leading span of that payload.**
3. **It is a prefix match.** A single changed byte at position *N* invalidates
   *N* → end; 0 → *N*−1 still hits.

The design rule follows mechanically: **stable content must physically precede
volatile content**, because anything volatile poisons everything downstream.

### Two mechanisms, and which to use

| | Implicit | Explicit |
|---|---|---|
| Setup | None — on by default, 2.5 and newer | `client.caches.create(...)`, reference the handle |
| Saving | 75% off matched prefix, **best effort** | Guaranteed, with a storage charge for the TTL |
| Available on | Both APIs | `generate_content` only — **not** the Interactions API |

**Use explicit.** The prefix is frozen by construction — sorted tool list,
byte-identical system instruction, whole-notebook context (§5a) — which is the
ideal explicit-cache case, and the reason §16 stays on `generate_content`.

Key the cache on `hash(system + tools + manifest)` and reuse it across commands
and across runs; rebuild only when the manifest changes, i.e. after a commit.
Implicit caching is the free fallback in the gap.

### The 4,096-token floor — MEASURED, and it binds

Gemini 3.x requires **4,096 tokens** before anything caches — 8× Opus 5's 512.
Below the floor it silently does not cache; no error.

Measured against `gemini-3.8-flash`, 2026-09-11:

| | tokens |
|---|---|
| 19 tool declarations, as a proxy for the final ~17 | **1,444** |
| System instruction | **14.6 tokens/line** (calibrated on `SKILL.md`: 458 lines → 6,683) |

Tools plus a 150-line system instruction alone is ~3,633 — **463 short**. The
§5a whole-notebook context clears it with room to spare:

**Built and measured, not estimated:**

| | tokens |
|---|---|
| 19 tool declarations, as built | **3,505** |
| System instruction + manifest + all chapter context | **10,133** |
| **Prefix** | **13,640** — clears the floor by 9,544 |

Both halves came in well above the estimate: the declarations because real tool
descriptions are prose rather than a line each, and the context because
`_model.py`'s names had to be added (§5a). The floor stopped being a constraint
the moment whole-notebook context went in, and caching is worth roughly twice
what the estimate implied — 40 turns against a 13.6k prefix is ~545k tokens
uncached.

Confirmed live: **12,165 of 12,408 prompt tokens served from cache on turn 1,
and the same 12,165 on every turn after it.**

The useful principle survives: **compressing the prefix below ~4,100 tokens
costs money**, because every turn then pays full price. If it ever lands short,
add the `why.md` rationale behind each lint rule rather than padding — arguing
with a rule is a known failure mode and the text already exists.

### Explicit caching — validated

Confirmed working with **both** `system_instruction` and `tools` in one object:

```
cache created : 8,127 tokens (SKILL.md + 19 tools, ttl=600s)
call 1        : prompt=8,136  cached=8,127  ->  9 tokens billed fresh
call 2        : prompt=8,136  cached=8,127  ->  9 tokens billed fresh
```

```python
cache = client.caches.create(model=MODEL, config=types.CreateCachedContentConfig(
    system_instruction=SYSTEM, tools=TOOLSET, ttl="3600s"))
# ... generate_content(config=types.GenerateContentConfig(cached_content=cache.name))
```

### The layout

| Segment | Contents | Cached |
|---|---|---|
| `tools` | 19 declarations (6 MCP + 13 native), frozen and **sorted** | yes |
| `system_instruction` | Triage table, 17 rules as one-liners, entry format + budgets, scope section. ~150 lines | yes |
| *(same cached object)* | Manifest, all `index.qmd`, all `_analysis.py` signatures (§5a) | yes |
| `contents` | Question, date, everything else volatile | no |

**Never in `system_instruction`:** dates, notebook paths, chapter names, session
IDs, unsorted `json.dumps`, conditional sections. The skill's `SKILL.md` opens
with ``Now: !`date "+%Y-%m-%d %H:%M"` `` — harmless under Claude Code, but here it
changes the cache key every minute and re-processes tools *and* system on every
call. One line, and caching is off.

A reordered tool list has the same effect from position 0 — hence sorting after
the merge (§5). Append to `contents`, never rebuild it: appending extends a
cached prefix, rebuilding discards it (and drops signatures, §8).

Verify with one number: **`usage_metadata.cached_content_token_count`**. Zero
across repeated calls means either a silent invalidator or a prefix under the
floor — check the token count first, then diff the rendered prefix.

Reference corpus stays behind `read_reference` — description in context, body on
demand. Past ~15 docs, switch to a tool-search approach so schemas append rather
than swap.

---

## 10. Budget enforcement — five layers

A signal cannot stop a CasADi solve; it lands when the C call returns (measured:
1.15 s against a 0.3 s limit). Killing a subprocess *can*, at the cost of
in-process state.

| Layer | Mechanism | Scope | Stops a C call? |
|---|---|---|---|
| 1 | `SOLVE_BUDGET` in `_notebook.py`, wrapping every `opti.solve` | one solve | Yes — at the next iteration boundary |
| 2 | `budget()` | hand-written Python loops only | No |
| 3 | `subprocess.run(timeout=)` | one `probe` call | Yes, hard kill; partial stdout preserved |
| 4 | `ENTRY_CEILING` vs accumulated probe time | whole entry | Checked between probes |
| 5 | `PROBE_BUDGET` watchdog in `_notebook.py` | one probe | Yes — `os._exit(9)` at 300 s, or `PROBE_BUDGET_CHAPTER` |

Layer 1 is load-bearing, and is why **`probe` takes a question, not code** — a
budget the model can skip by writing `import aerosandbox` directly is not a
budget:

```python
# NB_CHAPTER is how `_probe_base` picks the chapter; unset, it falls back to the
# first alphabetically and says so only on stderr. The handler refuses an unknown
# chapter rather than let that fallback answer about the wrong aircraft. Note the
# comment claims nothing about api(): `_probe_base` prints NOTHING on import, and
# the claim that it does is stale in the skill's own probe.py and entry.qmd.
PREAMBLE = "from _probe_base import *  # noqa: F403 — chapter loaded, budgets armed\n"

def run_probe(question: str) -> str:
    (SCRATCH / "probe.py").write_text(PREAMBLE + textwrap.dedent(question))
    try:
        r = subprocess.run(["uv", "run", "python", "probe.py"], cwd=SCRATCH,
                           capture_output=True, text=True, timeout=PROBE_WALL_CLOCK)
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired as e:          # partial output survives
        out = (e.stdout or b"").decode() + f"\n[killed at {PROBE_WALL_CLOCK}s]"
    return out[-8000:]
```

**`ENTRY_CEILING` lives in `chapters/<N>/_budget.py`**, a bare module-level
float, alongside `SOLVE_BUDGET` and `PROBE_BUDGET_CHAPTER`. It is a separate file
so that forking a chapter — which copies `_model.py` and `_analysis.py` — cannot
carry the parent's budget across. Only one of four chapters declares one, and
`_notebook.py`'s `DEFAULT_ENTRY_CEILING` is documented but read by no code, so
absence means unbounded and rule 17 stays the real check.

**Layer 5 was missed entirely.** `_notebook.py` runs its own watchdog thread that
`os._exit(9)`s a probe. Our subprocess timeout is therefore set *above* it, so
the watchdog fires first: it knows why it killed the probe and says so, where a
subprocess timeout knows only that time ran out.

Layer 4 accumulates across tool calls in the runner, not in a handler. The total
becomes the proposal's `render_cost_s` — already measured, so the gate can quote
what an entry will cost to render without parsing `aero_report()` out of stdout,
and you can decline an expensive render before paying for it. Exceeding
`ENTRY_CEILING` mid-probe ends the loop and says so in the proposal; raising the
ceiling is a human decision, recorded in `index.qmd`.

Prefer deterministic caps to wall-clock ones. Iterations behave identically on a
loaded machine; wall time does not (the same solve measured 533.9 s against a
145 s baseline purely from load). This is also why rule 17 only warns.

---

## 11. Why no orchestration framework

The rule:

> **An orchestration framework earns its place when the process must survive a
> pause it did not choose.**

This system has no such pause. `nb ask` exits deliberately at a fixed point;
`nb write` runs start to finish; `consult` blocks on stdin with the process
alive. So LangGraph's checkpointer, `interrupt()`, and `@task` memoisation have
nothing to do — you never resume *into* a loop, so there is nothing to restore.

| Framework feature | Replacement |
|---|---|
| Checkpointer + `interrupt()` | Process exit + `proposal.json` |
| `@task` memoisation | Nothing to restore |
| `RetryPolicy` | A `for` loop with backoff |
| `TimeoutPolicy` | `subprocess(timeout=)` — already budget layer 3 |
| Multi-question queue | A list in `proposal.json`, driven by the CLI |
| Time travel | git, plus `transcript.jsonl` |

**What is deleted along with it** is the real win — a set of constraints that
existed only because the framework did, and that were the subtlest thing in the
design: `interrupt()` only in bare nodes; no `interrupt()` inside a `while` loop
(exponential replay on resume); one `interrupt()` per node (index-based
matching); never `try/except` around an `interrupt()`; idempotence before every
interrupt. All accidental complexity, all gone.

**Adopt a framework when** any of these becomes true, and the migration is
mechanical because the phases are already separable functions:

- The gate becomes conditional again, so pauses are unpredictable.
- You want a daemon or server rather than a CLI.
- Hand-written transcript-replay-and-resume grows past ~50 lines.
- You want to re-run a bad run from the middle to debug it, and git plus the
  transcript is not enough.

---

## 12. Input triage, and the two modes

| Kind | Test | Action |
|---|---|---|
| **Derivable** | The model or the plans already contain it | Compute it. Never ask, never assume |
| **Specified** | A different answer changes *what we are building* | **`ask_specified`, immediately.** Never assumed, never deferred |
| **Unknown** | A different answer changes *how accurately we modelled it* | Assume, record in `## Assumed`, state the cost |

The judgment stays with the model — it has the context. The policy is a
deterministic branch. A separate triage agent would start cold and re-read the
model to answer what the probe loop already knows.

Never sweep a Specified input instead of asking: it triples the output and still
answers nothing. Lint rule 4 catches the artefact.

### Asking is always allowed, and always required

**There is no unattended mode.** A Specified input is asked, every time. The
system is an interactive CLI; if nobody is at the terminal, the run waits.

This departs from the skill in two ways, both deliberate:

**Ask immediately, not at the proposal.** The skill batches Specified questions
into the proposal message because *you are stopping anyway, so the inputs cost no
extra round trip* — an optimisation for a chat interface where each round trip is
expensive. Here the process is alive and you are at the terminal, so asking costs
nothing, and asking *early* is strictly better: the rest of the probe runs
against the real value instead of a placeholder. A static margin discovered at
turn 3 should not be guessed for twenty more turns.

**Ask as often as needed.** `ask_specified` has no cap. `consult` keeps one
(max 3) because open-ended guidance can loop; a Specified input cannot — there
are only so many decisions a question contains.

The gate therefore carries only the proposal: *this is what I intend to write*.
It is cheap — you are already there, you read three lines — and it still catches
the four expensive failures: the entry answers the wrong question; the entry
should not exist at all; wrong chapter; the render costs more than it is worth.

### When the answer is "I don't know, what do you think?"

From the skill, and it still applies:

- **Answerable in a sentence** → answer it, record it as Specified with
  `owner: "agent"` and the reason, continue.
- **Needs computation** → it is a question in its own right. Probe it, answer it,
  record it, then return to the original.

`owner` is therefore three-valued: `user` (you answered), `agent` (the model
answered a Specified question you delegated), `assumed` (an Unknown, nobody
knows). Keeping them distinct is the whole point of the field — it preserves
"did a person decide this?" on the page.

`propose` rejects any `specified` input carrying `owner: "assumed"`. That
combination means the discipline was skipped.

---

## 13. Verifier

### Preflight — before any tokens

```python
assert sha256(nb/"_notebook.py") == sha256(SKILL/"notebook.py")   # was rule 11
assert aerosandbox.__version__ == INDEX_BUILT_AGAINST
assert (nb/"_quarto.yml").exists()
```

Meta-invariants the agent can never fix. A mid-run dead end becomes a 5 ms
failure.

### Lint contract

```
 1  no hand-typed number in prose — use `{python} …` (2+ decimals)
 2  no 3 consecutive code lines repeated across entries — promote to _analysis.py
 3  `**Answer.**` comes before the last code cell
 4  no sweeping a decision that should have been asked — record it as Specified
 5  no `for … in range(…)` around an aero solve — iterate to a tolerance
 6  prose ≤ 100 words for the whole entry, warnings included
 7  figure caption ≤ 50 words
 8  each Specified / Assumed item ≤ 10 words
 9  one prose section — no second `**Heading.**` or `##`
10  a sibling entry is linked, never named in bare prose
11  → PREFLIGHT — `_notebook.py` AND `_scratch/_probe_base.py` byte-match
12  the freeze is not older than the model that froze it
13  every `_analysis.py` function the entry calls is passed to `footer(…)`
14  one visual per entry — a table counts as a figure
15  a table is at most 3×4 or 4×3, excluding the header
16  a budgeted chapter does not override SOLVE_BUDGET at a call site
17  a frozen entry stays under its chapter's ENTRY_CEILING
18  the solve budget in force is declared in the chapter's index
```

**There are 18, not 17.** Rule 18 was missed in the original reading, and rule 11
covers `_probe_base.py` as well as `_notebook.py` — added after an improvement to
it sat in one notebook while the scaffold that creates the next still held the
old text, drift invisible precisely because nothing compared them.

**There are no rule numbers in lint's output.** `lint.check()` returns
`(Path | None, str)` tuples carrying prose only, and `"(warning)"` is a marker
inside the string rather than a field. So "append the rule text only" means the
message verbatim, and severity is split with `"(warning)" not in msg` — exactly
as `check.py` does it. Measured on a deliberately bad entry: six violations, each
message naming its own fix, no numbering needed.

**Rule 2 is a one-entry fix.** `lint.py` hashes every 3-line window across
entries and reports blocks appearing in ≥2 files. The agent satisfies it by
changing only its own entry: promote the logic to `_analysis.py` and call it, and
the block no longer appears twice — the earlier entry is untouched. No
cross-entry refactor; the write→lint loop handles it.

Do **not** pre-emptively write every helper to `_analysis.py` to dodge the rule.
The tier table promotes on the *second* use deliberately, and eager promotion
turns `_analysis.py` into a junk drawer the agent then has to read. `why.md`
records the real failure — four subtly different neutral points in one chapter,
one taking its moment reference from the wrong station — and that is divergence,
which lazy promotion plus the lint loop catches.

**Port the `BOILERPLATE` regex verbatim.** `footer(` is on the exclusion list
because rule 13 *requires* one in every entry: a line the rules demand everywhere
can never be promoted, so flagging it puts two rules in direct contradiction.
That happened. Axis cosmetics are excluded for the same reason.

Rules 2 and 13 require `_analysis.py` to be writable. It is inside `chapters/`,
so the §6 allowlist covers it — do not narrow that, or both become unsatisfiable
and the write→lint loop thrashes to its cap.

Rule 17 warns rather than fails until machine load cannot explain the overrun.

`lint.py` and `check.py` are **lifted wholesale**, not rewritten — they do real
AST work (call-graph closure, `fixed_count_solves`, freeze scoping). The prompt
is the part that shrinks; the verifier is not.

On failure the retry appends **the rule text only** — not the diff, not the
transcript.

---

## 13a. Refactoring and corrections

### Proving a `_model.py` / `_analysis.py` change moved nothing

`check.py` lints, deletes the freeze, renders and diffs, naming the figures whose
bytes changed. Deleting the freeze is not optional — freeze tracks the page, not
its includes, so without it a fresh render is compared against a cache hit and
the match is an artefact.

**`check` renders the whole notebook.** Only freeze *deletion* is scoped by
chapter; `check.py` then runs `quarto render <root>` regardless. On a notebook
with a 600 s entry ceiling that is minutes, so its tool description says so and
points at `render` on a single entry for iteration. Reach for `check` when
proving a model change moved nothing, not while drafting.

**This stays agent-facing and automated.** The agent made the refactor, so it
knows whether a moved figure is the deliberate deletion it intended or a bug it
introduced — and with `read_media_file` it can look at the figures `check.py`
names. That is a tight correction loop, not a judgment call. The gate sits
upstream at proposal time and `verify` downstream, so a bad self-certification
still gets caught before commit.

### Corrections across entries

When a later entry corrects an earlier one, the correction goes in the **later**
entry: state the old value, the new one, and why they differ. Never edit the
earlier entry. Two entries disagreeing, with the later one explaining the
disagreement, is the intended end state.

The manifest (§5a) carries each entry's hero value, which makes *noticing* a
contradiction tractable — the agent can see that an earlier entry reported 8.4 s
for something it just computed as 6.1 s, and read that entry to check. Without
the manifest this required a full chapter read and would not reliably happen.

---

## 14. Entry format

`chapters/NN-name/YYYY-MM-DD-NN-slug.qmd` — trailing `NN` orders same-day
entries. Title is the question verbatim.

| Budget | Limit |
|---|---|
| Prose, whole entry | 100 words, warnings included |
| Figure caption | 50 words each |
| `## Specified` / `## Assumed` item | 10 words each |

An inline `{python}` expression counts as one word. Order: hero → `**Answer.**`
→ callouts → evidence → `footer(...)`. One visual or none. One prose section.

---

## 15. Observability

**Built:** `nb/metrics.py`, a SQLite table at `<notebook>/_scratch/nb-metrics.db`
— gitignored, per notebook, surviving runs as `_scratch/run/` deliberately does
not. One row per *phase*-run, not per entry, so an ask that never proposed is
still recorded with `outcome='max_turns'`. `python -m nb.metrics <notebook>`
prints the recent rows plus the aggregate that matters:

```
  first-pass lint violations, by model:
    gemini-3.1-pro-preview   1 entries   0.00 violations   3.0 turns
```

No platform needed at this scale; emit OpenTelemetry GenAI semantic conventions
instead if you later want a trace UI.

| Metric | Source | Use |
|---|---|---|
| **First-pass lint violations / entry** | `lint.py` before any retry | The eval. Compare models, thinking levels, prompts |
| Input/output/cached tokens per run | `usage_metadata` per call | Cost per entry; freeze records no timing |
| Cached-token ratio | `cached_content_token_count` | Zero ⇒ silent invalidator, or a prefix under the floor (§9) |
| Turns per probe loop | loop counter | Probe efficiency |
| Consults per run, and their text | run log | A recurring consult is a missing reference doc |
| Proposals rejected at the gate | `nb write` not run, or edited first | Wasted probe cost; the signal that routing or scope is off |
| **Verify findings per entry** | `verify_findings` column | Prose contradicting the render. Distinct from lint: rule 1 forces numbers in prose to be *computed*, but nothing forces a sentence about a SHAPE to match the shape |
| Outcome | `proposed` / `committed` / `max_turns` / `lint_failed` / `verify_failed` / `commit_failed` | Where runs die |

First-pass violation count is a real metric over a real artefact — and the target
for any later prompt optimisation.

---

## 16. Model configuration

**Primary model: `gemini-3.1-pro-preview`**, via the native `google-genai` SDK
≥ 2.23. Pin the ID explicitly — the 3.x line moves fast.

**Chosen by measurement, and the margin was not close.** Same question, same
prefix, same tools:

| | turns to a proposal |
|---|---|
| `gemini-3.8-flash` | **never**, in 25+ turns, across three runs |
| `gemini-3.1-pro-preview` | **2** — one probe, then propose |

Flash picked the right chapter and then wandered: reading sibling entries,
grepping, running `git log`, and using `probe` to walk the filesystem. Three
prompt interventions (whole-notebook context, an explicit turn budget, direct
prohibitions) improved its *first* call and did not fix the wandering. That is a
planning failure rather than a knowledge one, and it is not a thing more prompt
fixes.

The cheap model was a false economy: it spent twenty times the turns and produced
nothing. Start on Pro. Re-run the comparison on first-pass lint violations once
entries are being written — that is the metric that decides it long-term, and one
question is not an eval.

```python
cfg = types.GenerateContentConfig(
    tools=TOOLS,                        # sorted, frozen
    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH),
    cached_content=CACHE_HANDLE,        # carries system_instruction + tools (§9)
)
```

**SDK version matters.** `thinking_level` needs ≥ 2.x — on 1.47 `ThinkingConfig`
exposes only `include_thoughts` and `thinking_budget`, and the attribute is
simply absent. Pin the version; don't let a stale system install shadow it.

**Measured thinking levels** (both models): `LOW`, `MEDIUM`, `HIGH` accepted;
**`MINIMAL` returns a 400** despite being in the enum. Sweep LOW/MEDIUM/HIGH
against §15's first-pass violation count — it is the effort-sweep equivalent and
the main cost lever. `thinking_level` and the legacy `thinking_budget` are
mutually exclusive; sending both returns a 400.

### Why `generate_content` and not the Interactions API

The Interactions API is GA and is where new Gemini capabilities land; it manages
conversation history server-side via `previous_interaction_id`. Two reasons this
system stays on `generate_content`:

1. **Explicit caching is unavailable on Interactions** (§9), and this system's
   frozen prefix is precisely the case explicit caching exists for.
2. **The probe phase owns its history** and discards it at the gate. Server-side
   history adds a second source of truth with retention this system does not
   control, for a conversation it deliberately does not keep.

The counter-argument is real and worth revisiting: server-side history means
Google round-trips the thought signatures, removing §8's sharpest failure mode.
If signature handling proves troublesome in practice, the Interactions API is the
principled retreat — at the cost of explicit caching.

### Provider swap

One interface: `def complete(contents, cfg) -> Response`.

The other half is already portable — MCP filesystem serves any MCP-capable
client, and tool schemas are plain JSON Schema from Pydantic (§5).

**Do not route this through an abstraction layer** (LiteLLM, LangChain chat
models). At one provider it buys nothing, and it carries two specific risks here:
thought-signature round-tripping, a recurring defect in framework code (§8), and
explicit-cache lifecycle, which a chat-completions shape models poorly. Adding
Claude later for a §15 bake-off means a second implementation of `complete()` —
roughly 50 lines — not a rewrite.

Ignore LLM *gateways* (Bifrost, Portkey, TrueFoundry, OpenRouter) — proxy servers
for team key management, budgets and RBAC. Wrong category and wrong scale.

---

## 17. Human-operated, outside the agent

- `make new-notebook` — scaffolds `_quarto.yml`, `_notebook.py`, `_scratch/`
- Editing the system instruction, `lint.py`, `check.py`, `references/`, and the
  chapter template that `create_chapter` instantiates
- Raising `SOLVE_BUDGET` / `ENTRY_CEILING` (recorded in `index.qmd`)
- Deciding rule changes from the friction log

### Deliberate non-goals

Skill features intentionally not ported. Each is here so it reads as a decision
rather than an oversight:

| Not ported | Why |
|---|---|
| **`superseded_by()`** | Requires knowing a *later* entry obsoletes an earlier one. A run that knows only its own question cannot make that call — inherently retrospective. Human annotation |
| **META branch** | §1. Rules can no longer be earned from failures; the friction log replaces `why.md` growth, and acting on it is manual |
| **New notebooks** | A new notebook wants a fresh session — a process decision, not the agent's |
| **Discussion with no artefact** | The skill can think with you and produce nothing. This system is question-in → entry-out; `consult` is the narrow substitute |

---

## 18. To verify before building

1. **`edit_file` ambiguity behaviour.** It advertises whitespace normalisation
   and line-based matching — more permissive than a strict `str_replace`. Confirm
   it errors rather than guessing when a match is ambiguous, or always pair it
   with `dryRun`. A near-match landing on the wrong `{python}` cell is the
   failure mode.
2. ~~Where rendered figure bytes live~~ — **DONE.** Real PNGs at
   `_freeze/chapters/<c>/<stem>/figure-html/*.png`, served by a native
   `read_figure()`. See §6.
3. ~~Whether figures round-trip as inline image data~~ — **DONE.** A
   `function_response` part and an inline image part are accepted in ONE user
   turn. Measured on a real 68 KB PNG: **1,298 prompt tokens, and the model reads
   the axis labels off it.** The same figure as base64 inside a function response
   was ~23k tokens of string the model could not see — so `read_figure` returns
   bytes and `loop.py` emits the image part.
4. Whether `check.py`'s freeze scoping behaves correctly when invoked outside a
   Claude Code working directory.
5. Whether the chapter scaffold script can be invoked headlessly by
   `create_chapter`.
6. How `ENTRY_CEILING` is read per chapter (`index.qmd` parse vs import) so
   layer 4 in §10 can enforce it between probes.
7. Re-measure the prefix once the system instruction is actually written — the
   figures are extrapolated from 14.6 tokens/line and prose density varies. The
   check is one `generate_content` call reading `prompt_token_count`;
   `count_tokens` **cannot** be used, as it rejects `tools` on the Gemini API.
8. ~~Pick between the two models~~ — **DONE, provisionally.** Pro proposes in 2
   turns where Flash never proposes at all (§16). Still worth re-running on
   first-pass violation count across several questions: one question is a signal,
   not an eval.

### Found by building stage 2

- **An entry that will not render must not be committed.** The first cut of the
  verify step treated "could not verify" as a skip and committed anyway — so a
  page that failed to build would have entered history, which is precisely the
  class of failure verify exists to prevent. Any note from `verify.check()` is now
  a hard stop. Tested with a deliberate `NameError` in a cell.
- **Figures must arrive as inline image parts.** Base64 inside a
  `function_response` is a string the model cannot see, at ~18× the tokens.
- **A cache object belongs to the model that created it**, so the cache key
  carries the model ID — otherwise switching model 400s a long way from its cause.
- **Record the entry's own question, not the ask's.** On a split ask the model
  keeps the whole original in `question` and this entry's question in `title`, so
  metrics keyed on `question` label every entry of a multi-part ask identically.

### Found by building stage 1

- **`_model.py`'s names must be in the prefix** (§5a). Without them the model
  cannot route a question, and no amount of prompt fixes that.
- **A cached content object belongs to the model that created it.** The cache key
  must include the model ID, or switching models reuses the other one's cache and
  fails with a 400 a long way from its cause.
- **`probe` must refuse an unknown chapter**, rather than let `_probe_base`'s
  alphabetical fallback answer about the wrong aircraft.
- **Line-buffer stdout.** A run is minutes long and prints one line per turn;
  block-buffered to a pipe, that is a silent hang, indistinguishable from a stuck
  probe at exactly the moment you want to tell them apart.
- **`git log` / `git show` do not belong on the bash allowlist.** Eight
  consecutive turns went on git archaeology.

**Settled by measurement, 2026-09-11:** thought signatures round-trip when the
whole `Content` is appended (§8, with negative control); the 4,096-token cache
floor and how the prefix clears it (§9); explicit caching works with both
`system_instruction` and `tools` (§9); `role="user"` is correct for
function-response turns; `MINIMAL` thinking level 400s; current model IDs.
