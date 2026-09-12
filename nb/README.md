# `nb` — the design-notebook agent

Turns a design question into a Quarto lab-notebook entry that passes an 18-rule
lint contract, renders, and is checked against its own output before it commits.

Distilled from the `design-notebook` Claude Code skill, and runs without it, on
Gemini. Design and rationale: `../agentic-notebook-spec.md`.

Requires `GEMINI_API_KEY`, and `quarto`, `git`, `npx` on `PATH`.

---

## Use

```bash
uv run --group nb python -m nb ask <notebook> "why is the tail so big?"
```

Probes the chapter's model. Stops and asks you about anything **Specified** — an
input where a different answer changes *what is being built*. Writes
`<notebook>/_scratch/run/proposal.json` and **exits**.

Read the proposal. Edit it if you like. Then:

```bash
uv run --group nb python -m nb write <notebook>
```

Writes the entry, fixes it against lint, renders it, verifies the prose against
what actually rendered, commits, and picks up the next queued question if the ask
contained more than one.

Nothing reaches the notebook before you have seen the proposal.

### Other commands

```bash
uv run --group nb python -m nb.metrics   <notebook>            # cost + the eval
uv run --group nb python -m nb.cache     <notebook> [--purge]  # held caches
uv run --group nb python -m nb.prefix    <notebook> --measure  # cached prefix size
uv run --group nb python -m nb.manifest  <notebook>            # what the model sees
uv run --group nb python -m nb.preflight <notebook>            # before any tokens
uv run --group nb python nb/vendor/lint.py <notebook>          # the 18 rules
```

---

## Making a new notebook

There is no one-shot command; a notebook is a deliberate act. Seven steps, and
only two of them are fussy.

```bash
NB=my-new-notebook            # a sibling directory of the existing notebooks
mkdir -p $NB/chapters $NB/_scratch

# The two files rule 11 checks. They must be BYTE-IDENTICAL to these copies --
# they are vendored into every notebook because Quarto execs them at render time,
# so a notebook must render without nb installed.
cp nb/vendor/notebook.py   $NB/_notebook.py
cp nb/vendor/probe_base.py $NB/_scratch/_probe_base.py

printf '/.quarto/\n**/*.quarto_ipynb\n' > $NB/.gitignore
```

Then take `_quarto.yml`, `styles.css`, `_scratch/probe.qmd` and
`_scratch/probe.py` from **`vendor/templates/new-notebook.md`**, which holds each
file's contents with the reasoning beside it. The one setting that matters is
`execute-dir: project` — every cell runs with the notebook root as cwd, which is
why chapter paths are written `chapters/NN-name/_model.py` everywhere.

Finally, the first chapter:

```bash
uv run --group nb python -c "
from nb.config import Notebook
from nb.tools.scaffold import create_chapter
print(create_chapter(Notebook('$NB'), '01-first-chapter', 'First chapter',
                     'The aero method, the section, what is left out.'))"

uv run --group nb python nb/vendor/lint.py $NB      # expect: 0 problems
uv run --group nb python -m nb.preflight   $NB      # expect: preflight ok
```

Fill the scaffolded `_model.py` with the vehicle and say in `index.qmd` what
defines the chapter. Then `nb ask` it.

**Adding a chapter to an existing notebook is not a manual step** — propose
`route: "new_chapter"` and `nb write` scaffolds it from `chapter_title` and
`chapter_defines`. A chapter is a structural commitment later entries build on,
so it goes through the gate; `create_chapter` is deliberately not a tool the
model can call.

---

## Structure

    __main__.py    the CLI: ask | write
    config.py      model, paths, caps. Importing it puts vendor/ on sys.path
    schema.py      Proposal and Input. Pydantic generates the tool schemas AND
                   validates on the way back in, so a malformed propose is an
                   error the model can read
    client.py      complete(contents, cfg) — the ONE provider seam
    loop.py        the agent loop
    cache.py       the explicit cache: create, reuse, release
    prefix.py      assembles what gets cached
    manifest.py    one line per entry: stem, title, hero value
    preflight.py   invariants the agent cannot fix, checked before any tokens
    budgets.py     reads _budget.py; parses aero_report()
    metrics.py     one SQLite row per phase-run
    session.py     what one run accumulates
    text.py        output truncation

    phases/ask.py     preflight -> cache -> probe loop -> propose -> exit
    phases/write.py   scaffold? -> write loop -> lint -> render -> verify -> commit
    phases/verify.py  one toolless call on the rendered page + its figures

    tools/         one handler per tool. mcp_fs.py is the only MCP left
    scaffold/      chapter templates
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
| **lint** | the source | all 18 rules — budgets, hand-typed numbers, structure |
| **render** | — | code that does not run |
| **verify** | the *rendered* page and its figures, **not** the conversation | prose that contradicts the output |

`verify` exists for what lint cannot reach: rule 1 forces the numbers in prose to
be computed, but nothing forces a sentence about a **shape** to match the shape.
A caption claiming a crossover at 6 m/s when the curve crosses at 8 passes every
rule. Verify reads the PNG and catches it.

### Where state lives

    <notebook>/_scratch/run/proposal.json    the handoff; the only thing that
                                             crosses the process boundary
    <notebook>/_scratch/run/transcript.jsonl one line per turn, for debugging
    <notebook>/_scratch/run/cache.json       the held cache handle
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

**An explicit cache bills for as long as it is *held*** — $4.50/1M/hour on Pro
against $0.0251 saved per turn, so it pays for itself at ~2.5 turns/hour. A
commit supersedes the cache (the manifest is in the key), so `build()` releases
the old one before creating the next, and `write` releases after a run that ends.
Use `python -m nb.cache <nb>` to see what is held.

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
