# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes a 26-rule
lint contract, renders, and is checked against its own output before it commits.

Distilled from the `design-notebook` Claude Code skill, and runs without it, on
Gemini. Design and rationale: `../agentic-notebook-spec.md`.

Requires `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`.

**Run everything from the repo root.** `python -m nb` finds the package because
Python puts the current directory on `sys.path` — there is no installed entry
point, so from anywhere else it is `ModuleNotFoundError: No module named 'nb'`.
From outside the project it fails twice: `uv run` finds no `pyproject.toml`
walking up, and falls back to a system interpreter without the dependencies. The
notebook argument is a path, so `optimised-glider-notebook` resolves relative to
that same root.

---

## Use

```bash
uv run --group nb python -m nb new <notebook> [title]   # once per aircraft
uv run --group nb python -m nb ask <notebook> "why is the tail so big?"
```

**One command per entry.** It probes the chapter's model, writes the entry, fixes
it against lint, renders it, verifies the prose against what actually rendered,
commits, prints the entry with its real numbers, rebuilds the site, and picks up
the next queued question if the ask contained more than one.

It stops to ask you about anything **Specified** — an input where a different
answer changes *what is being built* — and otherwise runs through.

**Each phase gets a pool of probe wall clock**, 900 s by default, and the agent
divides it: every `probe` call states a `budget_s`, drawn from the pool, and the
result says how much is left. Asking for more than remains grants what remains.
When the pool is gone, the next probe is refused and it proposes with what it has.

That is the first bound on a run's compute that actually exists — each probe was
capped at 300 s, but nothing capped how *many* probes a run could take. It also
makes the agent forecast: a probe that asks for 400 s and finishes in 20 tells
you it does not understand what it is doing. Enforcement is coarse to about 15 s,
the watchdog's poll interval, so budgets under ~20 s buy nothing.

### The two stops

A run halts, writes `proposal.json` and exits for exactly two things. Both are
decisions about **structure or spend**, made before the work they authorise is
paid for — not approvals of finished output:

| | why it stops |
|---|---|
| **a new chapter** | later entries build on it, and it is far harder to undo than an entry |
| **an edit to `_model.py` in a chapter that has entries** | every sibling would have to be re-solved to prove its answers did not move |

Resume either with:

```bash
uv run --group nb python -m nb write <notebook> [--allow-refactor]
```

### Why there is no gate on the finished entry

By then lint, render and verify have all passed, and what is left to reject is
either something `ask_specified` should have caught during probing, or something
the notebook already has an answer for: *"that is a correction — say so in YOUR
entry… Never edit the earlier entry."* `superseded_by()` exists because the
record is append-only. Rejecting also refunds nothing — the run is already paid
for — and `git revert` on one entry and its freeze is cheap.

`write` builds the site only when every entry already has a freeze. Otherwise it
names the ones that do not and stops, because a project render does not fail on a
missing freeze -- it silently re-executes it, and that is hundreds of seconds of
aero solves. `nb view <notebook> --force` rebuilds them deliberately.

Nothing reaches the notebook before you have seen the proposal.

### Other commands

```bash
uv run --group nb python -m nb view      <notebook> [--force]  # build the site
uv run --group nb python -m nb.inputs    <notebook>            # specified + assumed
uv run --group nb python -m nb.metrics   <notebook>            # cost + the eval
uv run --group nb python -m nb.cache     <notebook> [--purge]  # held caches
uv run --group nb python -m nb.prefix    <notebook> --measure  # cached prefix size
uv run --group nb python -m nb.manifest  <notebook>            # what the model sees
uv run --group nb python -m nb.preflight <notebook>            # before any tokens
uv run --group nb python nb/vendor/lint.py <notebook>          # the 26 rules
```

---

## Making a new notebook

```bash
uv run --group nb python -m nb new my-new-notebook "My New Glider"
```

Creates the directory as a sibling of the existing notebooks, scaffolds
`_quarto.yml`, `styles.css`, `.gitignore`, `_scratch/`, the two vendored files
and a first chapter — then **lints and preflights before it returns**, so a
broken notebook fails here rather than several minutes into your first `ask`.

```
  created   /…/my-new-notebook
  vendored  _notebook.py, _scratch/_probe_base.py  (rule 11)
  chapter   chapters/01-first-chapter/
  lint      clean
  preflight ok
```

Then fill `chapters/01-first-chapter/_model.py` with the vehicle, say in its
`index.qmd` what defines the chapter, and `nb ask` it.

You can also just `nb ask` straight away. The first chapter is a **claimable
stub**: an `ask` that routes `new_chapter` takes the empty scaffold over and
renames it, rather than leaving a dead `01` beside a real `02`. The scaffold has
to exist at all because `_quarto.yml`'s `auto: "chapters"` crashes on an empty
`chapters/`.

Options: a second positional argument is the site title (defaults to the
directory name); `chapter=` and `chapter_title=` override the first chapter.
It refuses a non-empty directory and a chapter name that is not `NN-kebab-case`.

**Why this is a command and not a documented procedure.** `_notebook.py` and
`_scratch/_probe_base.py` are *vendored* into every notebook — Quarto execs them
at render time, so a notebook has to render without `nb` installed — and lint
rule 11 requires them byte-identical to `vendor/`. Copied by hand, a stray edit
or a truncated paste is silent until the first lint run.

**Adding a chapter is not this.** Propose `route: "new_chapter"` and `nb write`
scaffolds it from `chapter_title` and `chapter_defines`. A chapter is a
structural commitment later entries build on, so it goes through the gate;
`create_chapter` is deliberately not a tool the model can call. The model
supplies the slug; the code supplies the number, so a wrong guess renumbers
rather than aborting a run the ask has already been paid for. A new *notebook*
is a second aircraft, which is why it is a command you run rather than a route
the agent can take.

---

## Structure

    __main__.py    the CLI: new | ask | write | view
    config.py      model, paths, caps. Importing it puts vendor/ on sys.path
    schema.py      Proposal and Input. Pydantic generates the tool schemas AND
                   validates on the way back in, so a malformed propose is an
                   error the model can read
    client.py      complete(contents, cfg) — the ONE provider seam
    loop.py        the agent loop
    log.py         say() -> stderr (telemetry), tell() -> stdout (conversation)
    prefix.py      assembles what gets cached
    manifest.py    one line per entry: stem, title, hero value
    preflight.py   invariants the agent cannot fix, checked before any tokens
    inputs.py      every Specified and Assumed item, across the notebook
    budgets.py     reads _budget.py; parses aero_report()
    metrics.py     one SQLite row per phase-run
    session.py     what one run accumulates
    text.py        output truncation

    phases/new.py     scaffold a notebook, then lint and preflight it
    phases/view.py    project render, guarded against re-solving a lost freeze
    phases/ask.py     preflight -> probe loop -> propose -> write (or stop)
    phases/write.py   scaffold? -> write loop -> lint -> render -> verify -> commit
    phases/verify.py  one toolless call on the rendered page + its figures

    tools/         one handler per tool. mcp_fs.py is the only MCP left
                   guards.py refuses _model.py writes in a chapter with entries
    scaffold/      templates: _quarto.yml, styles.css, probe.{py,qmd},
                   and the chapter files
    vendor/        copied from the skill; canonical from here on

### Why two commands

The gate between them is a **process boundary, not a checkpoint**. Every run
stops at exactly one place and the process exits there, so nothing ever has to
survive a pause it did not choose — which is why there is no orchestration
framework and no checkpointer. `proposal.json` is the whole handoff; the phases
share no conversation state, because the entry's code cells recompute the answer
at render time anyway.

### Three checks, in order of what they can see

| | sees | catches |
|---|---|---|
| **lint** | the source | all 26 rules — budgets, hand-typed numbers, structure |
| **render** | — | code that does not run |
| **verify** | the *rendered* page and its figures, **not** the conversation | prose that contradicts the output |

`verify` exists for what lint cannot reach: rule 1 forces the numbers in prose to
be computed, but nothing forces a sentence about a **shape** to match the shape.
A caption claiming a crossover at 6 m/s when the curve crosses at 8 passes every
rule. Verify reads the PNG and catches it.

### Two tabs, and what is in each

**The terminal is the conversation.** Questions it stops to ask, the milestones
(`chapter`, `lint`, `verify`, `commit`), the finished entry with its real
numbers, and anything that ends a run without committing. About ten lines for a
successful entry.

**Everything else is detail** — one line per turn with tokens and tool, the
model's own reasoning, per-probe budgets, lint output — and goes to
`<notebook>/_scratch/run/status.log`. Follow it from another tab:

```bash
uv run --group nb python -m nb watch <notebook>          # live, from now on
uv run --group nb python -m nb watch <notebook> --all    # from the top
```

The log appends across runs and each opens with a dated separator, so you can
read back through earlier ones. `nb watch` may be started before the run it
watches.

**There is no flag for this.** Both streams used to land on the same terminal, so
separating them meant redirecting one away — and it cannot be stdout, because
that is where you type answers. An option everyone sets the same way is a default
in disguise, so `say()` simply stopped reaching the terminal. The consequence is
a rule: anything a run's outcome depends on must be `tell()`, or a failed run
ends in silence.

**The model's reasoning is always on**, and never re-enters the conversation.
`loop.py` shows each thought part and then drops it before appending the turn —
safe because Google's documentation attaches the enforced signature *"only to the
first functionCall part"*, so filtering the part list preserves it. Verified with
a negative control: a turn rebuilt from `name`+`args` still 400s.

### Where state lives

    <notebook>/_scratch/run/proposal.json    the handoff; the only thing that
                                             crosses the process boundary
    <notebook>/_scratch/run/transcript.jsonl one line per turn, with thoughts
    <notebook>/_scratch/run/status.log       the telemetry stream, mirrored
    <notebook>/_scratch/nb-metrics.db        one row per phase-run

All under `_scratch/`, which is gitignored. Nothing a run leaves behind is ever
committed except the entry and its freeze.

---

## Four things that will bite

**Append `resp.candidates[0].content` whole.** Model turns carry thought
signatures; the first `function_call` part of each step must carry its signature
back byte-identically or the next request 400s. Rebuilding a turn from name and
args drops it — verified, with a negative control.

**The prefix is a byte-exact match.** A date, a path, an unsorted dict in the
system instruction silently invalidates the lot. Check
`usage_metadata.cached_content_token_count` — zero across repeated calls means
something is varying. The cache key includes the model ID, because a cache object
belongs to the model that created it.

**Do not add an explicit cache back.** There was one; it cost about twice what it
saved. Passing `cached_content` does not add to implicit caching, it *replaces*
it — measured over six turns, 23.9% hit at $0.4121 with an explicit cache against
67.0% at $0.2082 without, and the cached count pinned at exactly the cache size
on every turn while the conversation grew. Implicit caching stores nothing and
bills no storage. Watch `cached_tokens` in metrics: it is best-effort, so a
silent drop in the ratio is the only symptom you would get.

**Do not prune the conversation either.** Editing anything breaks the byte-prefix
match from that point on, so a prune costs one cold turn to save a 90% discount
on every later one — break-even is nine more turns, and runs are 14–15 total.
The lever is `TRUNCATE`, which caps what enters in the first place.

**Images must be inline parts, not base64 in a function response.** The same PNG
costs 1,298 tokens as an image part the model can read, or ~23k tokens as a
base64 string it cannot.

---

## Diverging from the skill

`vendor/` is the canonical copy now. The skill is its ancestor and the two are
expected to drift apart; there is deliberately **no drift check between them**,
because that would reintroduce the coupling this removes. Rule 11 still pins each
notebook's `_notebook.py` and `_scratch/_probe_base.py` to `vendor/`, which is
the coupling that has to stay.
