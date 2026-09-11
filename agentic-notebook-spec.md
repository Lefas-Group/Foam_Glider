# Design-notebook agent — system specification

A standalone agentic system that produces Quarto lab-notebook entries for aircraft
design work. Distilled from the `design-notebook` Claude Code skill; runs without
Claude Code.

---

## 1. Scope

**In scope.** Answering a design question by probing a chapter's model, then
recording the answer as one notebook entry that passes the lint contract.

**Out of scope (META).** The system cannot modify itself: the system prompt,
`lint.py`, `check.py`, `notebook.py`, `_notebook.py`, templates, references,
`_quarto.yml`, or the introspection layer.

| Item | Disposition |
|---|---|
| `chapters/**` — entries, `_model.py`, `_analysis.py`, `index.qmd` | **Writable** — design tier |
| `_notebook.py`, `_quarto.yml` | Not exposed; drift is a preflight failure |
| `_scratch/**` | Reached only through the `probe` handler |
| New chapter | **Agent-triggered** via `create_chapter`, which runs the scaffold script; the template itself stays out of reach |
| New notebook | Human-run script — wants a fresh session |
| Lint rule 11 | Moves from lint gate → preflight assertion |
| Raising `SOLVE_BUDGET` / `ENTRY_CEILING` | Human decision via the gate |
| Suspected-bad lint rules | Written to the run log, never to `why.md` |

---

## 2. Architecture

```
                      ┌────────────────────────────────┐
  question ──────────▶│ router          (1 cheap call)  │  a HINT, not a decision
                      └────────────────┬───────────────┘
                                       ▼
              ┌──────────▶┌────────────────────────────┐
              │           │ probe_loop  (agentic loop)  │  NO interrupt inside
              │           └───────┬────────────────┬───┘  declares route + inputs
              │      consult      │                │ done
              │           ┌───────▼────────────┐   │
              └───────────┤ consult (interrupt)│   │      open-ended guidance
                          └────────────────────┘   │      max 3 per run
                                                   ▼
                      ┌────────────────────────────────┐
                      │ gate            (interrupt ONLY)│  ALWAYS fires: proposal
                      └────────────────┬───────────────┘  nothing before the call
                            fork/new   │   entry
                      ┌────────────────▼───────────────┐
                      │ create_chapter  (scaffold)      │  skipped for a plain entry
                      └────────────────┬───────────────┘
                                       ▼
                      ┌────────────────────────────────┐
                      │ write           (agentic loop)  │  lint available as a tool
                      └────────────────┬───────────────┘
                                       ▼
                      ┌────────────────────────────────┐
                      │ lint            (pure code)     │  unconditional edge
                      └───────┬────────────────┬───────┘
                         fail │                │ pass
                              └──▶ write       ▼
                                            verify (1 call, fresh context)
                                                │
                                                ▼
                                             commit
```

Orchestration: **LangGraph** (graph API) with `SqliteSaver`.
Model calls: **raw provider SDK inside nodes** — no LangChain model abstraction.
File access: **MCP filesystem server**, scoped to `chapters/`.

Rationale: byte-level control of the cached prefix; provider swap at one
interface; no hand-rolled path confinement.

---

## 3. State

```python
class S(TypedDict):
    question: str                  # verbatim; becomes the entry title
    notebook: Path
    chapter: str | None
    route: Literal["entry", "new_chapter", "new_notebook"]
    inputs: list[Input]
    contents: list[Content]        # provider-native; APPENDED to, never rebuilt
    entry_path: Path | None
    proposal: Proposal | None      # shown at the gate, before anything is written
    violations: list[str]
    attempts: int                  # write→lint retry counter, cap 3
    consults: int                  # consult-node visits, cap 3
    cost: dict                     # accumulated token usage
    solve_seconds: float           # accumulated across probes — vs ENTRY_CEILING
```

```python
class Proposal(TypedDict):
    title: str                     # the question, verbatim
    figures: list[str]             # captions only — nothing else
    render_cost_s: float           # from aero_report(), never guessed
    route: Literal["entry", "new_chapter"]
    chapter: str
```

```python
class Input(TypedDict):
    name: str
    kind: Literal["derivable", "specified", "unknown"]
    value: str | None
    owner: Literal["user", "assumed"] | None
    why: str                       # ≤ 10 words — lint rule 8 budget
```

**`contents` is append-only, and the whole `Content` object goes back.** On a
lint-fail retry, `write` appends a turn carrying the violations; it does not
reconstruct the list. Two reasons, both load-bearing:

1. Rebuilding invalidates the cached prefix on every retry (§9).
2. Model turns carry **thought signatures** — opaque blobs that must be returned
   byte-identically or the next request 400s (§8).

Appending raw `Content` objects satisfies both by construction. Any code that
extracts text and reassembles a turn breaks both at once.

---

## 4. Nodes

| Node | Type | Contract |
|---|---|---|
| `router` | 1 cheap call, structured output | Nearest existing chapter, from `index.qmd` titles only. A **hint** that seeds the probe preamble — not binding |
| `probe_loop` | agentic loop | Explores via `probe`. Terminates on `declare_route` + `declare_inputs` + `propose`. Max 25 turns |
| `consult` | `interrupt()` only | Open-ended guidance. Answer appends to `messages`; returns to `probe_loop`. Max 3 per run |
| `gate` | `interrupt()` only | **Always fires.** Carries the proposal; also any Specified input, fork decision, or budget raise |
| `create_chapter` | pure code, conditional | Runs the scaffold script. Skipped when `route == "entry"` |
| `write` | agentic loop | Creates the `.qmd`, may edit `_analysis.py` / `_model.py`. Has `lint` as a tool |
| `lint` | pure code | `lint.py` + `check.py`. Unconditional edge. No model |
| `verify` | 1 call, fresh context | Prose vs rendered output. Sees the render, **not** the conversation |
| `commit` | pure code | git add + commit |

**`gate` and `consult` are bare nodes** — exactly one `interrupt()` call each,
nothing before it (§11).

**The gate is unconditional.** Every entry stops for approval before anything is
written to the notebook, carrying the title, the figure captions, and the render
cost — *nothing else*. The cost comes from `aero_report()`, which prints the
solves the probe just ran; it is never guessed. Specified inputs are asked in the
same message: the run is stopping anyway, so they cost no extra round trip. A
proposal covering more than one question splits into one entry each.

**`consult` is for guidance, not decisions.** Open-ended questions the model
wants a human view on — "is this worth pursuing?", "does this result smell
wrong?", "should I compare against the other configuration?" — which are neither
Specified inputs nor a route decision. It exists because a single terminal gate
makes a run fail completely rather than get corrected cheaply.

A consult reply may itself turn out to be a Specified input, in which case it is
recorded with `owner: user` and the reason. If answering it needs computation, it
is a question in its own right: answer it in-loop, then return to the original.

**The route is an output of probing, not a precondition.** Whether a question

needs a new chapter depends on whether the existing model can answer it — learned
by reading `_model.py` and trying — and on whether the old answer stays valid
under its own stated assumptions. A pre-probe router has neither fact. It
therefore only nominates the nearest chapter; `probe_loop` decides.

**Fork decisions ride the gate.** The criterion is *whether you want to keep both
answers*, which changes what is being built rather than how accurately it was
modelled — Specified by the §12 test.

**Lint is both a tool and an edge, deliberately.** The tool lets `write` fix
violations inside one node without a checkpoint per cycle, and pairs with
`edit_file`'s `dryRun`. The edge is the guarantee: without it the model can
decline to call the tool and declare done. The edge re-running `lint.py
--no-render` after a clean tool pass costs nothing worth counting.

**`verify` is the only justified second agent.** Its input differs from the
worker's (rendered figures and printed blocks, not the transcript) and its
question is decidable. Every other judgment stays in `probe_loop`.

---

## 5. Tools

Frozen, sorted list — prefix position 0, never varies per request.

### From the MCP filesystem server (5 of 13 exposed)

| Tool | Notes |
|---|---|
| `read_text_file` | `head` / `tail` for slicing — use instead of whole-file reads |
| `read_media_file` | Base64 + MIME. **`verify` depends on this** (§6) |
| `list_directory` | Sibling-entry discovery |
| `search_files` | Pattern search within `chapters/` |
| `edit_file` | `edits: [{oldText, newText}]`, `dryRun` → git-style diff. **Default path for modification** |
| `write_file` | Full overwrite. **Creation only** — new entries |

Expose only these six. You are the MCP client; the remaining seven stay out of
the prefix.

Session via the official `mcp` SDK (`StdioServerParameters` → `stdio_client` →
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
| `probe` | `(question: str) -> str` | Preamble-injected, see §10. `@task` |
| `lint` | `(path: str) -> str` | `lint.py --no-render`. Same code as the edge |
| `render` | `(target: str) -> str` | `quarto render`. `@task` |
| `check` | `(chapter: str, all: bool) -> str` | `check.py`. `@task` |
| `api_search` | `(query: str) -> str` | AeroSandbox introspection |
| `api_signature` | `(path: str) -> str` | Signature + docstring |
| `read_reference` | `(name: Enum) -> str` | 7 reference docs + vendored book chapters |
| `list_chapters` | `() -> str` | Chapter names + `index.qmd` titles. Cheap; informs `declare_route` |
| `declare_route` | `(route, chapter, rationale) -> str` | Binding route decision; may override the router's hint |
| `declare_inputs` | `(items: list[Input]) -> str` | Declares every input not yet fixed |
| `propose` | `(p: Proposal) -> str` | Terminates `probe_loop`; routes to `gate` |
| `consult` | `(question: str, why: str) -> str` | Suspends `probe_loop`, routes to the `consult` node. Guidance only — not Specified inputs, not route decisions |
| `create_chapter` | `(name: str) -> str` | Wraps the scaffold script. Emits `index.qmd`, `_model.py`, `_analysis.py` from the template — the agent edits them afterwards via MCP |
| `bash` | `(command: str) -> str` | Allowlisted escape hatch, §7 |

`declare_inputs` rejects `kind == "derivable"`:
`"'{name}' is derivable — compute it, don't declare it."`

`declare_route` takes `route ∈ {entry, new_chapter}` plus a one-line rationale
naming what is held constant and what differs. `new_notebook` is not offered —
it is human-run (§17).

`consult` does **not** call `interrupt()` itself — it cannot, because
`probe_loop` is a `while` loop (§11 constraint 2). It sets a flag that ends the
current `agent_loop` turn and routes to the `consult` node, which holds the one
`interrupt()`. The reply appends to `messages` and control returns to
`probe_loop`, which resumes from the accumulated history. Capped at
`S["consults"] < 3` so it cannot ping-pong.

All native handlers truncate their own output — tracebacks keep the tail,
listings keep the head. Cap 8 kB.

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

Both read paths that reach outside a single entry stay inside `chapters/`:
rule 10 (link a sibling entry) and rule 2 (no repeated code across entries) both
read sibling `.qmd` files; "read that chapter's `index.qmd`" is chapter-level.

### Figures — the one unresolved access question

`verify` must read rendered figures as images, not just printed text. The failure
it exists to catch — prose written from the conversation rather than the output —
is mostly a *figure* failure: a caption claiming a crossover at 6 m/s when the
curve crosses at 8 is invisible to a text-only check.

`read_media_file` supplies the mechanism. The open question is **where the bytes
live**: `_freeze/chapters/<ch>/<entry>/execute-results/html.json` sits at the
notebook root, *outside* `chapters/`. If figures are embedded base64 in that
JSON, the allowlist must add read access to `_freeze/` (write access stays out —
Quarto writes it as a subprocess and never needs MCP). If they are written to a
`*_files/` directory beside the entry, the current allowlist already covers it.

`freezediff.py`'s `figures(root, repo, ref, chapters)` already locates them —
read it before finalising this. Until resolved, `verify` is text-only and rule 7
(caption ≤ 50 words) is enforced while *caption accuracy* is not.

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

Used by `probe_loop` and `write`. `google-genai`, `generate_content` (§16).

```python
def agent_loop(contents, cfg, max_turns=25):
    for _ in range(max_turns):
        resp = client.models.generate_content(
            model=MODEL, contents=contents, config=cfg,
        )
        turn = resp.candidates[0].content
        contents.append(turn)                      # WHOLE Content — signatures included

        calls = [p.function_call for p in turn.parts if p.function_call]
        if not calls:
            return resp, contents

        parts = []
        for c in calls:
            try:
                out = HANDLERS[c.name](**dict(c.args))
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {e}"}
            parts.append(types.Part.from_function_response(name=c.name, response=out))

        contents.append(types.Content(role="user", parts=parts))

    raise RuntimeError("max turns exceeded")
```

Invariants:

1. **Append `resp.candidates[0].content` whole.** Model turns carry
   **thought signatures** — encrypted blobs holding the model's reasoning state.
   The first `function_call` part of each step must carry its signature back
   *exactly as received*, or the request fails with
   `"Function call … is missing a thought_signature"`. Gemini 3 validates this
   strictly; 2.5 did not. In parallel calls only the first part carries one.
   Reconstructing a turn from extracted text drops it.
2. All function responses in **one** turn. Splitting them degrades parallel
   calling.
3. Always return a response part, including on failure — an unanswered
   `function_call` is an error on the next request.
4. No `try/except` wrapping anything that can raise `interrupt` (§11).

**Verified 2026-09-11** on `gemini-3.8-flash` and `gemini-3.1-pro-preview`, with
a negative control:

```
A  append Content whole   -> 200 OK
B  rebuild turn from name+args -> 400 INVALID_ARGUMENT
   "Function call is missing a thought_signature in functionCall parts."
```

The failure is immediate and loud, not silent — a signature bug cannot reach
production undetected. Signatures also survived on an old SDK (1.47.0), since
they ride as opaque part data.

**This is why the system is native rather than abstracted (§16).** Signature
round-tripping has been a recurring defect in framework code — dropped in
normalisation because a common message shape has nowhere to put an opaque
provider blob. Appending raw `Content` sidesteps it entirely.

`verify` constructs fresh history and therefore holds no signatures. If it is
ever given tools, its synthetic turns need the documented dummy value
`"skip_thought_signature_validator"`. As specified it makes one toolless call,
so this does not arise.

---

## 9. Prompt layout and caching

### The mechanism

`generate_content` is stateless — every request re-sends the whole conversation,
so a 20-turn probe loop transmits the system instruction and tool schemas twenty
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

**Use explicit.** This system's prefix is frozen by construction — sorted tool
list, byte-identical system instruction — which is the ideal explicit-cache case:
create one cached content at run start holding tools + system instruction, hold
the handle for the run, let the TTL expire after. That converts a best-effort
discount into a guaranteed one, and it is the reason §16 stays on
`generate_content`.

Implicit caching remains as a free fallback if the prefix falls under the
minimum or the handle expires mid-run.

### The 4,096-token floor — MEASURED, and it binds

Gemini 3.x requires **4,096 tokens** before anything caches — 8× Opus 5's 512.
Below the floor it silently does not cache; no error.

Measured against `gemini-3.8-flash`, 2026-09-11:

| | tokens |
|---|---|
| 19 tool declarations (6 MCP + 13 native) | **1,444** |
| System instruction | **14.6 tokens/line** (calibrated on `SKILL.md`: 458 lines → 6,683) |

Which puts the prefix here:

| System instruction | Prefix | |
|---|---|---|
| 100 lines | ~2,900 | short 1,193 |
| **150 lines** (the original target) | **~3,633** | **short 463** |
| **200 lines** | **~4,362** | **clears** |
| 250 lines | ~5,092 | clears |

**So the distillation target is ~200 lines, not ~150.** This inverts the usual
instinct: compressing the system instruction below ~200 lines *costs* money,
because it drops the prefix under the floor and every turn of a 25-turn probe
loop then pays full price. There is a floor on useful compression, and it is
about 2,650 tokens of system instruction.

Spend the extra ~50 lines on content that earns its place — the `why.md`
rationale behind each lint rule is the obvious candidate, since arguing with a
rule is a known failure mode and the text is already written.

### Explicit caching — validated

Confirmed working with **both** `system_instruction` and `tools` in one cached
object:

```
cache created : 8,127 tokens (SKILL.md + 19 tools, ttl=600s)
call 1        : prompt=8,136  cached=8,127  ->  9 tokens billed fresh
call 2        : prompt=8,136  cached=8,127  ->  9 tokens billed fresh
```

```python
cache = client.caches.create(model=MODEL, config=types.CreateCachedContentConfig(
    system_instruction=SYSTEM, tools=TOOLSET, ttl="3600s"))
# ... generate_content(config=types.GenerateContentConfig(cached_content=cache.name))
client.caches.delete(name=cache.name)
```

Create at run start, hold the handle, delete at the end. Set the TTL to cover a
run — note the gate may hold for days, so the cache will expire across it and
must be recreated on resume; implicit caching covers the gap.

### The layout

| Segment | Contents | Cached |
|---|---|---|
| `tools` | 17 declarations, frozen and **sorted**, identical every call | yes |
| `system_instruction` | Triage table, 17 rules **with their `why.md` rationale**, entry format + budgets, scope section. **~200 lines** — see the floor above | yes |
| `contents` | Question, date, chapter state, everything volatile | no |

**Never in `system_instruction`:** dates, notebook paths, chapter names, session
IDs, unsorted `json.dumps`, conditional sections. The skill's `SKILL.md` opens
with ``Now: !`date "+%Y-%m-%d %H:%M"` `` — harmless under Claude Code, but here it
changes the cache key every minute and re-processes tools *and* system on every
call. One line, and caching is off.

A reordered tool list has the same effect from position 0 — hence sorting after
merging MCP and native declarations (§5). Appending to `contents` (§3) extends a
cached prefix; rebuilding it discards the cache.

Verify with one number: **`usage_metadata.cached_content_token_count`**. Zero
across repeated calls means either a silent invalidator or a prefix under the
floor — check the token count first, then diff the rendered prefix.

Reference corpus stays behind `read_reference` — description in context, body on
demand. Past ~15 docs, switch to the tool-search server tool with
`defer_loading: true` so schemas append rather than swap.

---

## 10. Budget enforcement — four layers

`TimeoutPolicy` does **not** replace solver budgets. A signal cannot stop a
CasADi solve; it lands when the C call returns (measured: 1.15 s against a 0.3 s
limit). Killing a subprocess *can*, at the cost of in-process state.

| Layer | Mechanism | Scope | Stops a C call? |
|---|---|---|---|
| 1 | `SOLVE_BUDGET` in `_notebook.py`, wrapping every `opti.solve` | one solve | Yes — at the next iteration boundary |
| 2 | `budget()` | hand-written Python loops only | No |
| 3 | `subprocess.run(timeout=)` | one `probe` call | Yes, hard kill; partial stdout preserved |
| 4 | `ENTRY_CEILING` vs `S["solve_seconds"]` | whole entry | Node-level check between probes |

Layer 1 is load-bearing, and is why **`probe` takes a question, not code** — a
budget the model can skip by writing `import aerosandbox` directly is not a
budget:

```python
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

Layer 4 spans multiple tool calls, so it cannot live in a handler. `probe`,
`render` and `check` append measured cost to `S["solve_seconds"]`; `probe_loop`
checks the total against the chapter's `ENTRY_CEILING` after each turn and routes
to `gate` — raising it is a human decision, recorded in `index.qmd`.

Prefer deterministic caps to wall-clock ones. Iterations behave identically on a
loaded machine; wall time does not (the same solve measured 533.9 s against a
145 s baseline purely from load). This is also why rule 17 only warns.

---

## 11. LangGraph configuration and constraints

| Setting | Value | Why |
|---|---|---|
| Checkpointer | `SqliteSaver` | Gate may stay open for days at zero compute |
| Durability | `sync` | Gate correctness over throughput |
| `@task` | `probe`, `render`, `check` | Results restored from checkpoint on resume, not recomputed |
| `RetryPolicy` | `max_attempts=3`, explicit `retry_on` | **Default `retry_on` excludes `RuntimeError`, `OSError`, `ValueError`** — pass transient solver failures explicitly |
| `TimeoutPolicy` | Outer backstop only | §10 |
| `cache_policy` | on `probe` | Skips an identical re-probe |
| Error handler | on `lint` | Returns `Command` routing back to `write` |

**Hard constraints — violating these breaks resume:**

1. **`interrupt()` appears only in `gate` and `consult`** — bare nodes holding
   one call each and nothing else. On resume a node restarts from the top, not
   from the interrupt line.
2. **`probe_loop` and `write` contain no `interrupt()`.** `while` + `interrupt`
   in one node replays prior iterations exponentially on each resume. This is
   why `consult` is a separate node rather than a tool that blocks in place.
   Re-entering `probe_loop` afterwards is safe: `messages` is checkpointed state
   (§3), so the loop resumes from accumulated history rather than replaying, and
   `@task` memoisation covers any probe already run.
3. **One `interrupt()` per node.** Matching within a node is strictly
   index-based; conditional or loop-driven interrupts misalign resume values.
4. **Never `try/except` around `interrupt()`** — it is an exception; catching it
   swallows the gate. A broad `except Exception` in tool dispatch will eat it.
5. `interrupt()` bypasses retry policies and error handlers.
6. Anything executing before an `interrupt()` must be idempotent.

---

## 12. Input triage

Classified by `probe_loop`, enforced by code.

| Kind | Test | Action |
|---|---|---|
| **Derivable** | The model or the plans already contain it | Compute it. Never ask, never assume |
| **Specified** | A different answer changes *what we are building* | **Gate → `interrupt()`** |
| **Unknown** | A different answer changes *how accurately we modelled it* | Assume, record in `## Assumed`, state the cost |

The judgment stays with the model — it has the context. The policy is a
deterministic branch. A separate triage agent would start cold and re-read the
model to answer what the worker already knows.

Never sweep a Specified input instead of asking: it triples the output and still
answers nothing. Lint rule 4 catches the artifact.

Unattended runs set `owner: assumed`, keeping "did a person decide this?"
visible.

**The gate always fires** — it carries the proposal (§4). Specified inputs, a
`new_chapter` route, and a requested budget raise (§10) ride the same stop, which
is why asking them costs nothing extra.

`consult` is the separate channel for everything that is *not* a binding
decision. Keeping them apart matters: if guidance questions were routed through
the gate, the gate's payload would stop being "here is what I propose to write"
and start being a conversation.

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
11  → PREFLIGHT (see above)
12  the freeze is not older than the model that froze it
13  every `_analysis.py` function the entry calls is passed to `footer(…)`
14  one visual per entry — a table counts as a figure
15  a table is at most 3×4 or 4×3, excluding the header
16  a budgeted chapter does not override SOLVE_BUDGET at a call site
17  a frozen entry stays under its chapter's ENTRY_CEILING
```

Rules 2 and 13 require `_analysis.py` to be writable. Locking it makes both
unsatisfiable and the write→lint edge thrashes to `max_attempts`. It is inside
`chapters/`, so the §6 allowlist covers it — do not narrow that.

Rule 17 warns rather than fails until machine load cannot explain the overrun.

`lint.py` and `check.py` are **lifted wholesale**, not rewritten — they do real
AST work (call-graph closure, `fixed_count_solves`, freeze scoping). The prompt
is the part that shrinks; the verifier is not.

On failure the retry appends **the rule text only** — not the diff, not the
transcript.

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

| Metric | Source | Use |
|---|---|---|
| **First-pass lint violations / entry** | `lint.py` before any retry | The eval. Compare models, prompts, effort levels |
| Input/output/cached tokens per entry | `usage` per call | Cost per entry; freeze records no timing |
| Cached-token ratio | `usage.total_cached_tokens` | Zero ⇒ silent invalidator, **or** a prefix under the 4,096 floor (§9) |
| Turns per probe loop | loop counter | Probe efficiency |
| Gate latency | checkpoint timestamps | How long approval actually takes |
| Consults per run, and their text | `S["consults"]`, run log | Where the prompt or references are underspecified — a recurring consult is a missing reference doc |
| Proposals rejected at the gate | gate resume values | Wasted probe cost; the signal that routing or scope is off |

First-pass violation count is a real metric over a real artifact — and the
target for any later prompt optimisation.

---

## 16. Model configuration

**Primary model: Gemini 3.x, via the native `google-genai` SDK ≥ 2.23.**
Candidates as of 2026-09-11: `gemini-3.1-pro-preview` (deepest reasoning) and
`gemini-3.8-flash` (newest Flash). Both verified for signatures and caching.
Pin the ID explicitly — the 3.x line moves fast.

```python
cfg = types.GenerateContentConfig(
    system_instruction=SYSTEM,          # only when not using the cache handle
    tools=TOOLS,                        # sorted, frozen
    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH),
    cached_content=CACHE_HANDLE,        # explicit cache from run start (§9)
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
system stays on `generate_content` anyway:

1. **Explicit caching is unavailable on Interactions** (§9), and this system's
   frozen prefix is precisely the case explicit caching exists for.
2. **History ownership would be split.** LangGraph already checkpoints
   `contents` (§3), which is what makes the gate resumable after days. Server-side
   history adds a second source of truth whose retention this system does not
   control.

The counter-argument is real and worth revisiting: server-side history means
Google round-trips the thought signatures, removing §8's sharpest failure mode.
If signature handling proves troublesome in practice, the Interactions API is the
principled retreat — at the cost of explicit caching and single-source history.

### Provider swap

One interface:

```python
def complete(contents, cfg) -> Response: ...
```

The other half is already portable — MCP filesystem serves any MCP-capable
client, and tool schemas are plain JSON Schema from Pydantic (§5).

**Do not route this through an abstraction layer** (LiteLLM, LangChain chat
models). At one provider it buys nothing, and it carries two specific risks here:
thought-signature round-tripping, which has been a recurring defect in framework
code (§8), and explicit-cache lifecycle, which a chat-completions shape models
poorly. Adding Claude later for a §15 bake-off means a second implementation of
`complete()` — roughly 50 lines — not a rewrite.

Ignore LLM *gateways* (Bifrost, Portkey, TrueFoundry, OpenRouter) — proxy servers
for team key management, budgets and RBAC. Wrong category and wrong scale.

---

## 17. Human-operated, outside the agent

- `make new-notebook` — scaffolds `_quarto.yml`, `_notebook.py`, `_scratch/`.
  Stays human-run: a new notebook wants a fresh session, which is a process
  decision, not the agent's
- Editing the system prompt, `lint.py`, `check.py`, `references/`, and the
  chapter template that `create_chapter` instantiates
- Raising `SOLVE_BUDGET` / `ENTRY_CEILING` (recorded in `index.qmd`)
- Deciding rule changes from the friction log

---

## 18. To verify before building

1. **`edit_file` ambiguity behaviour.** It advertises whitespace normalisation
   and line-based matching — more permissive than a strict `str_replace`. Confirm
   it errors rather than guessing when a match is ambiguous, or always pair it
   with `dryRun`. A near-match landing on the wrong `{python}` cell is the
   failure mode.
2. Whether `@task` composes inside Graph API nodes, or whether the pipeline
   should use the Functional API (`@entrypoint` / `@task`) instead — four steps,
   plain control flow, expensive memoised side effects may fit it better.
3. Current LangGraph API names for `RetryPolicy`, `TimeoutPolicy`,
   `cache_policy`, `set_node_defaults`.
4. Whether `check.py`'s freeze scoping behaves correctly when invoked outside a
   Claude Code working directory.
5. How `ENTRY_CEILING` is read per chapter (`index.qmd` parse vs import) so
   layer 4 in §10 can enforce it between probes.
6. ~~Thought signatures survive the loop~~ — **DONE 2026-09-11.** Confirmed on
   both candidate models, with a negative control. See §8.
7. Whether the chapter scaffold script can be invoked headlessly by
   `create_chapter` without the Claude Code harness.
8. **Where rendered figure bytes live** (§6) — embedded base64 in
   `_freeze/**/execute-results/html.json`, or files in a `*_files/` directory.
   Determines whether the MCP allowlist needs read access to `_freeze/`. Read
   `freezediff.py`'s `figures()`. `verify` is text-only until this is settled.
9. Whether `read_media_file` output round-trips as inline image data through
   `complete()` — `verify` depends on it (§6).
10. ~~Measure the frozen prefix against the cache floor~~ — **DONE.** Prefix at
    150 lines falls 463 tokens short; target is ~200 lines. Explicit caching
    validated end to end. See §9.
11. ~~Exact model ID~~ — **DONE.** `gemini-3.1-pro-preview` /
    `gemini-3.8-flash`. Re-check periodically; the line moves.
12. ~~`role` for function-response turns~~ — **DONE.** `"user"` is correct
    (§8's loop ran green).
13. Re-measure the prefix once the system instruction is actually written — the
    200-line figure is extrapolated from 14.6 tokens/line, and prose density
    varies. The check is one `generate_content` call reading
    `prompt_token_count`; `count_tokens` **cannot** be used, as it rejects
    `tools` on the Gemini API.
14. Pick between `gemini-3.1-pro-preview` and `gemini-3.8-flash` using §15's
    first-pass violation count. Pro spent 284 thinking tokens against Flash's 46
    on the same trivial call — a real behavioural difference worth pricing.
