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
than the content column — and the page scrolls sideways.

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

## `notebook/_scratch/probe.py`

For questions that need a real traceback and stdout instead of Quarto's
render-then-scrape-HTML loop. Run with `uv run python notebook/_scratch/probe.py`.

````python
"""Scratch probe. Gitignored, never rendered."""
import pathlib

_root = pathlib.Path(__file__).parent.parent
_chapter = _root / "chapters" / "NN-name"
for _p in [_root / "_notebook.py", _chapter / "_model.py", _chapter / "_analysis.py"]:
    # compile() with the real path so api() and inspect.getsource() work here
    # exactly as they do in a rendered entry.
    exec(compile(_p.read_text(), str(_p), "exec"))

print("already available -- check here before writing a helper:")
for _sig, _doc in api():
    print(f"  {_sig:52s} {_doc}")

# <the question being explored>
````

---

## `notebook/_notebook.py`

Notebook furniture, one copy for every chapter. Copy verbatim; nothing in it is
project-specific. Deliberately invisible in the rendered site — the chapter index
lists `_model.py` and `_analysis.py` only, and `api()` filters to `_analysis.py`,
so neither function appears in the notebook a reader sees.

````python
import inspect


def show_source(*objs):
    """Render the source of the shared functions an entry called."""
    print('::: {.callout-note collapse="true"}')
    print("## The method, as called\n")
    print("```python")
    for o in objs:
        print(inspect.getsource(o).rstrip())
        print()
    print("```")
    print(":::")


def api(filename="_analysis.py"):
    """Every function defined in `filename`, with signature and summary line."""
    for name, obj in sorted(globals().items()):
        if inspect.isfunction(obj) and obj.__code__.co_filename.endswith(filename):
            yield (name + str(inspect.signature(obj)),
                   (inspect.getdoc(obj) or "").strip().split("\n")[0])
````

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
