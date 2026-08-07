---
name: design-notebook
description: Records aircraft design work in a chronological Quarto lab notebook. Use when the user is designing or analysing an aircraft, running AeroSandbox studies, or asks to record a finding. Scaffolds the notebook if none exists.
when_to_use: Designing or sizing an aircraft, running a trajectory or aero study, sweeping a design parameter, or saying "add this to the notebook".
allowed-tools: Bash(uv run quarto *) Bash(uv run python *)
---

Now: !`date "+%Y-%m-%d %H:%M"`
Notebook: !`find . -maxdepth 3 -name _quarto.yml -not -path "*/_site/*" 2>/dev/null`

## The loop

1. **Explore in the notebook's `_scratch/probe.qmd`** — gitignored, skipped by
   project renders, so nothing in the notebook is touched. See "Scratch probes"
   below for the file and how to run it.

2. **When a question has been answered, stop and propose.** Give the entry
   title (the user's question, verbatim) and its figures — nothing else. If the
   proposal covers more than one question, split it into one entry each. Ask
   whether to record it and where. **Write nothing into the notebook until the
   user agrees.**

3. **On approval**, write the entry, render it, look at every figure, report the
   numbers.

Repeat per question. A discussion that answers nothing gets no entry.

## Scope

The entry answers the question asked and stops. This is the rule that gets
broken most; when in doubt, write less.

- **One question, one entry.** Two questions asked in the same breath become two
  entries, not one entry with two sections.
- **Compute only what was asked.** "What are the polars?" means the curves — not
  max L/D, CL_max, stall angle or Cm_α. Don't print derived scalars nobody
  requested, and don't add them to the model "while you're there".
- **No unrequested studies.** A sensitivity sweep, a multistart, a comparison
  against another configuration: each is its own question, for the user to ask.
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

Every notebook owns `<notebook>/_scratch/probe.qmd`. It is scaffolded with the
notebook; create it if a notebook predates this. **One rolling file per
notebook** — overwrite it for each new question rather than accumulating
`probe-<slug>.qmd` files.

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
- Each render costs ~8s of fixed overhead regardless of the code, so put several
  probes in one file rather than rendering repeatedly.

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

## Quarto gotchas

- `uv run quarto render` — bare `quarto` picks up the wrong Python.
- **There is no `--no-freeze` flag** (checked on Quarto 1.8.27; it falls through
  to pandoc and errors with `Unknown option`). Freeze tracks the page, not its
  includes — so after editing a chapter's `_model.qmd`, delete
  `<notebook>/_freeze/chapters/NN-name/` and render normally.
- `- auto: "chapters"` crashes on an empty `chapters/` with
  `TypeError: Cannot convert undefined or null to object`. Keep the line
  commented out until the first chapter directory exists.
- **A cell whose last expression returns an object renders that object's repr as
  a second output**, which demotes the figure to a subfigure captioned "(a)" and
  dumps something like `array([[<Axes3D: …>]])` beneath it. Bind the result:
  `_ = bfg.draw_three_view(show=True)`.
- **Matplotlib figures overflow the content column** and make the page scroll
  sideways — they carry their native pixel width. The notebook's `styles.css`
  fixes this globally; keep it wired in via `css:` in `_quarto.yml`.
- Reading results back: printed output is in `_site/**/*.html` — extract
  `<pre><code>` blocks with Python rather than grepping, since syntax
  highlighting splits code across spans. Figures land in
  `_freeze/chapters/NN-name/<entry>/figure-html/*.png`; Read every one before
  reporting.
- `_`-prefixed files and directories are skipped by project renders — that is
  what keeps `_model.qmd` off the sidebar and `_scratch/` out of the site. They
  still render fine when named directly on the command line.

## AeroSandbox gotchas

- `op_point.reynolds(c)` returns a **scalar** when `velocity` is scalar, even if
  `alpha` is a vector — indexing it raises `IndexError`.
- `AeroBuildup` gets its section data from NeuralFoil. For flat foam, name a
  symmetric section of the right thickness (`asb.Airfoil("naca0007")` for 5 mm
  on a 70 mm chord) rather than inventing coordinates — and say in the chapter
  index that it stands in for a flat plate, which stalls earlier and softer.
- Dihedral is a `z` offset on the tip `WingXSec`, with `symmetric=True` on the
  `Wing`.
- `Airplane(xyz_ref=…)` sets the moment reference. State what it is whenever a
  `Cm` is quoted; it is not the CG unless you made it so.
- `draw_three_view` builds its own figure, so `fig-width`/`fig-height` cell
  options do nothing — it emits ~1896 px square regardless. Only CSS constrains
  it.
- At chuck-glider scale, chord Reynolds number is 1–4 × 10⁴ and the polar moves
  materially with airspeed. Record the speed alongside any coefficient.
