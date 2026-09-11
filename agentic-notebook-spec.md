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
| New notebook / chapter scaffolding | Human-run script |
| Lint rule 11 | Moves from lint gate → preflight assertion |
| Raising `SOLVE_BUDGET` / `ENTRY_CEILING` | Human decision via the gate |
| Suspected-bad lint rules | Written to the run log, never to `why.md` |

---

## 2. Architecture

```
                      ┌────────────────────────────────┐
  question ──────────▶│ router          (1 model call)  │
                      └────────────────┬───────────────┘
                                       ▼
                      ┌────────────────────────────────┐
                      │ probe_loop      (agentic loop)  │  NO interrupt inside
                      └────────────────┬───────────────┘
                                       ▼
                      ┌────────────────────────────────┐
                      │ gate            (interrupt ONLY)│  nothing before the call
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
    messages: list[dict]           # provider-native; APPENDED to, never rebuilt
    entry_path: Path | None
    violations: list[str]
    attempts: int                  # write→lint retry counter, cap 3
    cost: dict                     # accumulated token usage
    solve_seconds: float           # accumulated across probes — vs ENTRY_CEILING
```

```python
class Input(TypedDict):
    name: str
    kind: Literal["derivable", "specified", "unknown"]
    value: str | None
    owner: Literal["user", "assumed"] | None
    why: str                       # ≤ 10 words — lint rule 8 budget
```

**`messages` is append-only.** On a lint-fail retry, `write` appends a user turn
carrying the violations; it does not reconstruct the list. Rebuilding would
invalidate the cached conversation prefix on every retry.

---

## 4. Nodes

| Node | Type | Contract |
|---|---|---|
| `router` | 1 call, structured output | `{route, chapter}`. Reads chapter `index.qmd` titles only, never bodies |
| `probe_loop` | agentic loop | Explores via `probe`. Terminates on `declare_inputs`. Max 25 turns |
| `gate` | `interrupt()` only | Fires on any `kind == "specified"`, or a requested budget raise |
| `write` | agentic loop | Creates the `.qmd`, may edit `_analysis.py` / `_model.py`. Has `lint` as a tool |
| `lint` | pure code | `lint.py` + `check.py`. Unconditional edge. No model |
| `verify` | 1 call, fresh context | Prose vs rendered output. Sees the render, **not** the conversation |
| `commit` | pure code | git add + commit |

**`gate` is a bare node** — exactly one `interrupt()` call, nothing before it (§11).

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
| `list_directory` | Sibling-entry discovery |
| `search_files` | Pattern search within `chapters/` |
| `edit_file` | `edits: [{oldText, newText}]`, `dryRun` → git-style diff. **Default path for modification** |
| `write_file` | Full overwrite. **Creation only** — new entries |

Expose only these five. You are the MCP client; the remaining tools stay out of
the prefix.

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
| `declare_inputs` | `(items: list[Input]) -> str` | Terminates `probe_loop`; routes to `gate` |
| `bash` | `(command: str) -> str` | Allowlisted escape hatch, §7 |

`declare_inputs` rejects `kind == "derivable"`:
`"'{name}' is derivable — compute it, don't declare it."`

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

Used by `probe_loop` and `write`.

```python
def agent_loop(messages, system, max_turns=25):
    for _ in range(max_turns):
        resp = client.messages.create(
            model="claude-opus-5",
            max_tokens=16000,
            system=system,                    # cache_control on last block
            tools=TOOLS,
            messages=messages,
            output_config={"effort": "medium"},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError(resp.stop_details)

        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return resp, messages

        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            try:
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": HANDLERS[b.name](**b.input)})
            except Exception as e:
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": f"{type(e).__name__}: {e}",
                                "is_error": True})
        messages.append({"role": "user", "content": results})

    raise RuntimeError("max turns exceeded")
```

Invariants:

1. Append `resp.content`, **not** `.text` — carries `tool_use` and thinking
   blocks. Opus 5 thinks by default; blocks must return unmodified.
2. All `tool_result` blocks in **one** user message. Splitting degrades parallel
   tool calling silently.
3. Always return a result, `is_error: true` on failure. A missing `tool_use_id`
   is a 400.
4. `max_tokens` caps thinking **plus** text.
5. No `try/except` wrapping anything that can raise `interrupt` (§11).

---

## 9. Prompt layout and caching

Render order is `tools` → `system` → `messages`; prefix match, byte-exact.

| Segment | Contents | Cached |
|---|---|---|
| `tools` | 14 tools, frozen and sorted, identical every call | yes |
| `system` | Triage table, 17 rules as one-liners, entry format + budgets, scope section. ~150 lines | yes — `cache_control` on last block |
| `messages` | Question, date, chapter state, everything volatile | no |

**Never in `system`:** dates, notebook paths, chapter names, session IDs,
unsorted `json.dumps`. The skill's `!`date`` / `!`find`` header lines are cheap
under Claude Code and poison a frozen prefix — they move to the user turn.

Minimum cacheable prefix on Opus 5 is 512 tokens. Verify with
`usage.cache_read_input_tokens`; zero across repeated calls means a silent
invalidator.

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

1. **`interrupt()` appears only in `gate`.** On resume a node restarts from the
   top, not from the interrupt line.
2. **`probe_loop` and `write` contain no `interrupt()`.** `while` + `interrupt`
   in one node replays prior iterations exponentially on each resume.
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
visible. `gate` also fires on a requested budget raise — one gate node, two
triggers.

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
| Input/output/cache tokens per entry | `usage` per call | Cost per entry; freeze records no timing |
| Cache read ratio | `usage.cache_read_input_tokens` | Zero ⇒ silent prefix invalidator |
| Turns per probe loop | loop counter | Probe efficiency |
| Gate firings and their latency | checkpoint timestamps | How often a Specified input was genuinely missing |

First-pass violation count is a real metric over a real artifact — and the
target for any later prompt optimisation.

---

## 16. Model configuration

```python
model       = "claude-opus-5"
max_tokens  = 16000          # caps thinking + text
effort      = "medium"       # sweep low/medium/high against §15
```

Thinking is on by default on Opus 5. Do not disable it — with thinking off the
model can emit tool calls as plain text (the call silently never runs) and leak
`<thinking>` tags. Lower `effort` instead.

**Provider swap** costs one interface, written in-house:

```python
def complete(system, messages, tools, *, effort="medium") -> Response: ...
```

Both halves are provider-agnostic — MCP filesystem serves any MCP-capable
client, and no Claude-specific tool definitions are used.

**Do not use a provider-abstraction library** (LiteLLM, LangChain chat models,
or similar) for the model call. They normalise to a common request shape, and
this system's token strategy depends on three provider-native details surviving
byte-exactly: `cache_control` breakpoint placement (§9), thinking blocks
round-tripped unmodified (§8), and `output_config.effort`. Such libraries earn
their place at many providers, a team gateway, or cross-provider fallback — none
of which apply here. At two candidate providers the adapter above is ~50 lines
you own and can reason about.

---

## 17. Human-operated, outside the agent

- `make new-notebook` — scaffolds `_quarto.yml`, `_notebook.py`, `_scratch/`
- `make new-chapter`
- Editing the system prompt, `lint.py`, `check.py`, `references/`
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
