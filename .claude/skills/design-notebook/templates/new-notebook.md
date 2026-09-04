# Scaffolding a notebook or a chapter

A **chapter** is a body of work sharing one model. Adding a chapter needs only
the last two files. Everything else is for a notebook built from scratch.

Replace `<...>` placeholders. Chapter directories are `NN-name`, numbered in
creation order.

There is **no notebook title page** — the sidebar is the index. See the note
under the chapter `index.qmd` for how the site root is handled.

---

## `notebook/_quarto.yml`

````yaml
project:
  type: website
  output-dir: _site
  # Run every cell from the notebook/ root so relative paths mean the same
  # thing regardless of which page is being rendered.
  execute-dir: project

website:
  title: "<Project> Notebook"
  description: "A chronological record of questions asked about <the aircraft>."
  # Next/Previous links in each page footer, so entries read straight through.
  page-navigation: true
  sidebar:
    style: docked
    contents:
      # Subdirectories become sections. Entry filenames start with their date,
      # so alphabetical order is chronological order.
      #
      # KEEP THIS COMMENTED OUT until the first chapter directory exists --
      # `auto` on an empty chapters/ dies with
      # "TypeError: Cannot convert undefined or null to object".
      - auto: "chapters"

format:
  html:
    toc: true
    toc-depth: 3
    # Scales matplotlib output down to the content column so pages never scroll
    # sideways.
    css: styles.css
    # Code is folded away everywhere by default -- the prose and figures are the
    # content; the code is there when you want to check it.
    code-fold: true
    code-summary: "Show code"
    code-copy: true
    code-overflow: wrap
    fig-width: 8
    fig-height: 4.5
    fig-dpi: 150

execute:
  # Entries are written once, debugged, then left alone -- so freeze genuinely
  # freezes them. Commit _freeze/ so a fresh clone renders without re-solving.
  # NOTE: freeze tracks page files, not their includes -- so editing a
  # chapter's _model.py does NOT invalidate its entries. Delete
  # _freeze/chapters/NN-name/ and render. There is no --no-freeze flag.
  freeze: auto
  warning: false
````

---

## `notebook/styles.css`

Without this, every matplotlib figure renders at its native pixel width — wider
than the content column — and the page scrolls sideways. It also carries the
hero/key styles that entries use to emphasise their answer.

````css
/* Matplotlib figures are emitted at their native pixel size, which is wider
   than the content column -- so the page scrolls sideways. Scale them to fit
   instead. */
.cell-output-display img,
figure img,
.quarto-figure img {
  max-width: 100%;
  height: auto;
}

/* Wide code output (the printed tables) scrolls in its own box rather than
   stretching the page. */
.cell-output pre {
  overflow-x: auto;
}

/* ---------------------------------------------------------------------------
   The answer, emphasised.

   Every entry produces one number it exists to produce. `.hero-value` is that
   number, set large enough to be read before the prose is; `.key` is for the
   one or two supporting values in the sentence underneath. Both use tabular
   figures so digits line up and a value cannot be misread at a glance.

   The accent is deliberately NOT the link blue -- a coloured number that looks
   clickable is worse than a plain one.
   --------------------------------------------------------------------------- */
:root {
  --key-accent: #14655c;
}

.hero,
.hero-pair {
  margin: 1.4rem 0 1.1rem;
  padding-left: 0.9rem;
  border-left: 3px solid var(--key-accent);
}

/* Two values at equal size, for the entries whose answer IS a comparison:
   measured against predicted, as-built against as-designed. The reference half
   is muted rather than smaller -- they are peers, but only one of them is the
   finding. */
.hero-pair {
  display: flex;
  gap: 2.4rem;
  flex-wrap: wrap;
}

.hero-ref {
  color: #5c6670;
}

.hero-value {
  display: block;
  font-size: 2.6rem;
  font-weight: 600;
  line-height: 1.05;
  letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums;
  color: var(--key-accent);
}

.hero-label {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.9rem;
  color: #5c6670;
}

.key {
  font-size: 1.15em;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--key-accent);
  white-space: nowrap;
}

@media (max-width: 480px) {
  .hero-value { font-size: 2rem; }
}

/* What the entry cost to run. Printed by footer() in _notebook.py, from a timer
   the shim starts -- freeze records no timing of its own, so without this an
   entry's cost leaves no trace once it is written. Recessive on purpose: it is
   provenance, not a result. */
.runtime {
  display: block;
  margin-top: 2rem;
  padding-top: 0.6rem;
  border-top: 1px solid rgba(128, 128, 128, 0.25);
  font-size: 0.8rem;
  color: #6b747d;
  font-variant-numeric: tabular-nums;
}
````

---

## `notebook/chapters/NN-name/index.qmd`

Keep it to one sentence and a handful of one-line bullets. This page states what
the model is and what it assumes; it does not explain how the notebook is
organised.

The `aliases` entry matters: with no title page, Quarto redirects the site root
to whichever page it happened to render first. The **first** chapter's index
should claim that redirect. Later chapters omit it.

The listing cell reads `_model.py` off disk rather than copying it, so it
cannot drift from what the entries run. Update the path to match the chapter.

`````markdown
---
title: "<Chapter name>"
# There is no notebook title page, so Quarto redirects the site root to whatever
# it rendered first. Claim that redirect for the chapter instead. FIRST CHAPTER
# ONLY.
aliases:
  - /index.html
---

<One sentence: the vehicle and the method.>

- **<Method>**, <the analysis class used>.
- **<Aero model>**, <the section or force model>.
- **<Key assumption>.**
- **<What is left out>.**
- **<Operating condition held fixed>.**

## The model

Read straight from `_model.py` rather than copied, so this listing cannot drift
from what the entries actually run.

````{python}
#| echo: false
#| output: asis
import pathlib

code = pathlib.Path("chapters/NN-name/_model.py").read_text()

print('::: {.callout-note collapse="true"}')
print("## `_model.py`\n")
print("```python")
print(code.strip())
print("```")
print(":::")
````
`````

---

## `notebook/_scratch/probe.qmd`

Every notebook gets its own scratch dir, created with it. The leading underscore
keeps it out of project renders — Quarto skips `_`-prefixed paths — while still
rendering when named directly. One rolling file, overwritten per question.

````markdown
---
title: "Probe"
execute:
  # _freeze/ is committed and holds entry results. Probes must never land in it.
  freeze: false
---

<!-- Include path is relative to this file. -->
{{< include ../chapters/NN-name/_model.qmd >}}

```{python}
<the question being explored>
```
````

Run with `uv run quarto render notebook/_scratch/probe.qmd`. Output stays in
`_scratch/` rather than going to `_site/`.

---

## `notebook/_scratch/_probe_base.py`

The preamble every probe repeats, so no probe has to. Written once per notebook;
set `CHAPTER` when working on a different one.

````python
"""
The preamble every scratch probe repeats. Import it; don't retype it.

    from _probe_base import *      # chapter loaded, api() printed

compile() with the real path is load-bearing, as in the _model.qmd shim: a bare
exec() of file text labels every function "<string>", and then
inspect.getsource() raises OSError, breaking show_source() and api() together.
Probes are where a helper is about to be written, so api() must work here or the
discovery listing is empty.
"""
import pathlib

CHAPTER = "NN-name"

_root = pathlib.Path(__file__).resolve().parent.parent
_chapter = _root / "chapters" / CHAPTER
for _p in [_root / "_notebook.py", _chapter / "_model.py", _chapter / "_analysis.py"]:
    exec(compile(_p.read_text(), str(_p), "exec"))

print(f"[{CHAPTER}] already available -- check here before writing a helper:")
for _sig, _doc in api():
    print(f"  {_sig:52s} {_doc[:44]}")
print()
````

---

## `notebook/_scratch/probe.py`

For questions that need a real traceback and stdout instead of Quarto's
render-then-scrape-HTML loop. Run with `uv run python notebook/_scratch/probe.py`.

**Edit the question block; do not rewrite the file.** Successive probes then cost
the delta rather than the whole thing.

````python
"""Scratch probe. Gitignored, never rendered. Edit the question, not the file."""
from _probe_base import *  # noqa: F403 -- chapter loaded, api() printed

# --- the question ----------------------------------------------------------
````

---

## `notebook/_notebook.py`

**Copy `.claude/skills/design-notebook/notebook.py` verbatim** to
`<notebook>/_notebook.py`. That file is the canonical copy; nothing in it is
project-specific, and the linter checks the two match (rule 11), so an
improvement to `footer()` or the plot style surfaces in every notebook that has
not taken it yet.

It is vendored rather than run from the skill, unlike `lint.py`, because it is
`exec`'d into every page at render time and its output is baked into the
published HTML. Sharing it would make the notebook unrenderable without the
skill installed, and would put a render-affecting file outside the Quarto
project — where **freeze cannot see edits to it**, which is how stale pages get
served.

Deliberately invisible in the rendered site: the chapter index lists `_model.py`
and `_analysis.py` only, and `api()` filters to `_analysis.py`, so none of this
file's functions appear in the notebook a reader sees.

---

## Linting — no file to create

**A notebook carries no lint configuration.** The linter lives in the skill and
is run against a notebook by path:

```bash
uv run python .claude/skills/design-notebook/lint.py <notebook>
```

Nothing needs configuring, because nothing is declared that could be derived:
the helpers that cost an aero solve are worked out from each chapter's own call
graph, and a reference to a sibling entry is matched generically. A notebook
scaffolded a minute ago lints correctly with nothing added to it.

One shared copy is safe here and not for `_notebook.py` because this is a
*checker*: it runs at authoring time, reads the notebook and writes nothing, so
nothing it does reaches the rendered site and a notebook does not need it
present in order to render.

**To exempt a chapter**, put a `_lint-skip` file in the chapter directory whose
contents say why:

```
Predates the entry format; its freeze holds solver runs that would be
expensive to reproduce.
```

Opt-out, not opt-in — a chapter added tomorrow is checked the moment it exists.
The marker sits in the chapter it describes, so deleting the chapter deletes its
exemption; a central list of names outlives the chapter and then silently
exempts whatever is created with that name next.

---

## `notebook/chapters/NN-name/_analysis.py`

The chapter's shared machinery — the calculations more than one entry performs.
Created empty with the chapter; helpers arrive by promotion from entries, never
by anticipation. Nothing about rendering or discovery goes here: that is
`_notebook.py`.

---

## `notebook/chapters/NN-name/_model.qmd`

A shim, not the model. It execs both chapter files, model first.

**`compile()` with the real path is load-bearing.** A bare `exec()` of file text
labels every function `"<string>"`, and then `inspect.getsource()` raises
`OSError` — which breaks `show_source()` and `api()` together.

Do **not** write an include shortcode literally inside these comments — the
chapter index prints the model through `output: asis`, and a literal shortcode
there risks being expanded.

````markdown
```{python}
#| include: false
# The chapter lives in two files next to this one -- _model.py (the vehicle)
# and _analysis.py (how the chapter measures it). exec rather than import,
# because every chapter names its model `_model` and real imports would collide
# in sys.modules. Paths are relative to the notebook root -- _quarto.yml sets
# `execute-dir: project`, so that is always the cwd.
import pathlib

for _p in ["_notebook.py",
           "chapters/NN-name/_model.py",
           "chapters/NN-name/_analysis.py"]:
    exec(compile(pathlib.Path(_p).read_text(), _p, "exec"))

# The chapter this page belongs to, taken from the paths above rather than
# retyped -- superseded_by() resolves its forward link inside this directory.
# Then start the entry's clock and zero the solve counter, both read by footer().
_CHAPTER = str(pathlib.Path(_p).parent)
_T0 = time.perf_counter()
aero_cost.update(calls=0, seconds=0.0)
```
````

---

## `notebook/chapters/NN-name/_model.py`

Skeleton only. Fill it with the chapter's actual model. Plain Python, so it can
be read by a scratch script, a Jupyter kernel and the chapter index alike.

````python
# =============================================================================
# <Chapter name> model.
#
# This file defines the chapter. A different model gets its own directory and
# its own _model.py, sharing nothing with this one.
#
# Loaded two ways, both by exec into the caller's namespace: entries via the
# _model.qmd shim, scratch scripts via _scratch/probe.py.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete the chapter's _freeze/ directory before re-rendering.
# =============================================================================

##### Imports
# <analysis library, numpy, matplotlib>

##### Vehicle
# <geometry, mass, aero coefficients>

##### Operating conditions
# <what is held fixed: speed, altitude, launch energy, mission>

##### Derived quantities
# <helpers computed from the above>

##### The analysis
# <the function every entry in this chapter calls. Its arguments should decide
#  what is fixed and what is free, so the same code serves as both simulator
#  and optimizer. Return a dict of the solved result plus its scalars -- but
#  only quantities the entries actually use.>
````

---

## `.gitignore`

````gitignore
# Quarto render output. Each notebook's _freeze/ is deliberately NOT ignored: it
# holds the frozen results of each entry, so a fresh clone renders without
# re-running any computation.
notebook/_site/
notebook/.quarto/

# Draft/probe work, never committed. Each notebook has its own; the leading
# underscore is what keeps Quarto from rendering it as part of the project.
_scratch/
````

---

## `pyproject.toml`

Quarto needs `jupyter` and `pyyaml` to execute Python cells at all.

````toml
dependencies = [
    "aerosandbox>=4.2.10",
    "matplotlib>=3.9",
    # Quarto needs both of these to execute Python cells in .qmd files.
    "jupyter>=1.1",
    "pyyaml>=6.0",
]
````

Then `uv sync`.
