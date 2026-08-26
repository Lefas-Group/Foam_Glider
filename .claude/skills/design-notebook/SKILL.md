---
name: design-notebook
description: Records aircraft design work in a chronological Quarto lab notebook. Use when the user is designing or analysing an aircraft, running AeroSandbox studies, or asks to record a finding. Scaffolds the notebook if none exists.
when_to_use: Designing or sizing an aircraft, running a trajectory or aero study, sweeping a design parameter, or saying "add this to the notebook".
allowed-tools: Bash(uv run quarto *) Bash(uv run python *)
---

Now: !`date "+%Y-%m-%d %H:%M"`
Notebook: !`find . -maxdepth 3 -name _quarto.yml -not -path "*/_site/*" 2>/dev/null`

## The loop

1. **Explore in the notebook's `_scratch/`** — gitignored, skipped by project
   renders, so nothing in the notebook is touched. See "Scratch probes" below.

2. **When a question has been answered, stop and propose.** Give the entry
   title (the user's question, verbatim) and its figures — nothing else. If the
   proposal covers more than one question, split it into one entry each. Say
   what the entry will cost to render if any cell runs a solver or a sweep;
   freeze pays it once, and it survives edits to `_model.py`. Ask
   whether to record it and where. **Write nothing into the notebook until the
   user agrees.**

3. **On approval**, write the entry's code, render it, and read every figure and
   printed block. **Then** write the prose and the `**Answer.**` line against
   what actually rendered, and re-render. An entry must never contradict its own
   outputs — prose written from the conversation rather than from the output is
   how that happens.

Repeat per question. A discussion that answers nothing gets no entry.

## Scope

The entry answers the question asked and stops. This is the rule that gets
broken most; when in doubt, write less.

- **One question, one entry.** Two questions asked in the same breath become two
  entries, not one entry with two sections. Facets of a *single* comparison
  (cost, fidelity, applicability) are one question, not three.
- **Compute only what was asked.** "What are the polars?" means the curves — not
  max L/D, CL_max, stall angle or Cm_α. Don't print derived scalars nobody
  requested, and don't add them to the model "while you're there".
- **No unrequested studies.** A sensitivity sweep, a multistart, a comparison
  against another configuration: each is its own question, for the user to ask.
- **Don't assume a value the model can compute.** If the components are stated,
  sum them — `MassProperties` gives CG and inertia, `run_with_stability_derivatives()`
  gives the neutral point. An assumption is for a value you genuinely don't
  have, not one you didn't bother deriving. Where an assumed value and a
  computed one must agree, solve for the input that makes them agree rather than
  asserting both.
- **A comparison entry names what is held constant between the arms.** Two
  models differing in more than one respect measure nothing.
- **State the reference for any quantity that has one.** A `Cm` is meaningless
  without saying what it is taken about; a coefficient at chuck-glider scale is
  meaningless without the speed, since Re moves the polar materially.
- **Prose is a setup line plus assumptions.** One sentence on what was run and
  at what condition, plus any assumption you had to make because a value wasn't
  given. Nothing else — no commentary on what the numbers mean, no "what this
  doesn't include", no "open threads".
- **An `**Answer.**` line only when the question can *only* be answered in
  prose** — "what are this model's limitations?" gets one; "what are the
  polars?" and "what does it look like?" are answered by their own output.
- **Captions describe, they don't conclude.** "Lift curve, drag curve and drag
  polar at 6 m/s", not "notice that everything is symmetric because…".
- **Assumptions live in the chapter's `index.qmd`**, stated once. Don't repeat
  them as commentary inside entries.
- **Interesting things you weren't asked about go in chat**, as a suggested next
  question. Never into the notebook.

The same restraint applies before the entry exists: don't probe in scratch for
tangents, only for what was asked.

## Scratch probes

Every notebook owns `<notebook>/_scratch/`, holding `probe.py` and `probe.qmd`.
Both are scaffolded with the notebook; create them if a notebook predates this.
Overwrite them per question rather than accumulating `probe-<slug>` files; a
second file is fine when a long run is worth keeping while a new question is
explored.

**Reach for `probe.py` first.** The chapter model is plain Python
(`chapters/NN-name/_model.py`), so a script gets it with one `exec` and gives
you real tracebacks and stdout. Quarto gives you `Cell 3/5 ... An error
occurred` and then makes you scrape the output back out of HTML.

```python
import pathlib
_chapter = pathlib.Path(__file__).parent.parent / "chapters" / "NN-name"
exec((_chapter / "_model.py").read_text())
```

**Use `probe.qmd` when the question produces a figure**, or when you are
rehearsing cells that are about to become an entry — its cells paste across
unchanged. For a one-off API check that needs no model at all, `uv run python -c`
beats both.

Iterating on a plot re-runs every cell above it, cold, on each render. If that
starts to hurt, `exec` the model into a persistent Jupyter kernel instead and
re-plot without re-solving.

The leading underscore is load-bearing: `_scratch/` sits inside the Quarto
project, and Quarto skips `_`-prefixed paths, so `quarto render <notebook>`
never sees it. Don't rename it to `scratch/`.

````markdown
---
title: "Probe"
execute:
  # _freeze/ is committed and holds entry results. Probes must never land in it.
  freeze: false
---

{{< include ../chapters/NN-name/_model.qmd >}}

```{python}
<the question being explored>
```
````

- **The include path is relative to the probe file**, hence `../chapters/…`.
- **Cell code runs from the notebook root**, not from `_scratch/`, because the
  project sets `execute-dir: project`. Any path inside a cell is relative to the
  notebook directory.
- Run it: `uv run quarto render <notebook>/_scratch/probe.qmd`
- Output stays put — Quarto renders it standalone, not into `_site/`. Printed
  output is in `_scratch/probe.html`; figures are
  `_scratch/probe_files/figure-html/*.png`, named `cell-N-output-1.png` unless
  the cell has a `#| label:`. Read every figure before reporting on it.
- Each render costs ~8 s of fixed overhead regardless of the code, so put
  several probes in one file rather than rendering repeatedly.

## Where the work goes

Read each chapter's `index.qmd` — it states what defines that chapter.

| The question needs | Goes to |
|---|---|
| the same model as an existing chapter | new entry in that chapter |
| a different model, fidelity or vehicle | new chapter |
| a different aircraft project | new notebook — ask first |

New chapter or notebook: see `templates/new-notebook.md`.

## Entry files

`notebook/chapters/NN-name/YYYY-MM-DD-NN-slug.qmd` — the trailing `NN` counts
within the day so same-day entries order correctly. Title is the question as
asked. Format: `templates/entry.qmd`.

Entries are written once, debugged, then left alone. Record what actually
happened, including answers that turned out to be wrong.

When a later entry corrects an earlier one, the correction goes in the **later**
entry: state the old value, the new one, and why they differ. Never edit the
earlier entry, and don't add a pointer to it unless asked. Two entries
disagreeing, with the later one explaining the disagreement, is the intended end
state.

## Reference

- `references/quarto.md` — render and tooling traps. Read when a render fails, a
  figure misbehaves, or output needs extracting.
- `references/aerosandbox.md` — API traps and solver behaviour. Read before
  writing dynamics, optimization or mass-properties code.
- `references/aerosandbox-book/` — the AeroSandbox book, vendored.
  `11-optimal-control.qmd` for collocation, `12-dynamics-stack.qmd` for the
  `Dynamics` classes and axis systems, `07-atmosphere-propulsion-weights.qmd`
  for `MassProperties`, `02-robust-optimization-models.qmd` when a solve will
  not converge.
