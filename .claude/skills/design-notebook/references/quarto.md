# Quarto gotchas

Render and tooling traps. Read when a render fails, a figure misbehaves, or
output needs extracting.

- `uv run quarto render` — bare `quarto` picks up the wrong Python.
- **There is no `--no-freeze` flag** (checked on Quarto 1.8.27; it falls through
  to pandoc and errors with `Unknown option`). Freeze tracks the page, not its
  includes — so editing a chapter's `_model.py` does **not** invalidate its
  entries, and they keep serving stale results silently. Delete
  `<notebook>/_freeze/chapters/NN-name/` and render normally. Cuts both ways:
  it means a change to how the model is *loaded* costs nothing to roll out, but
  a change to what it *computes* must be forced through by hand.
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
- **That recipe reads one printed block; it is the wrong tool for a whole page.**
  Most of an entry's numbers are inline expressions and table cells, which are
  prose in the HTML, not `<pre><code>`. For "did anything change?", go at
  `_freeze/**/execute-results/html.json` instead: its `result.markdown` holds
  every number already evaluated, and it is committed, so `git diff` is the
  comparison. See "Where machinery lives" in SKILL.md for the workflow.
- Scraping the HTML of a full page is a trap worth naming: a code cell closes
  with a **single** `</div>` (`<div class="sourceCode…">…</pre></div>`), so a
  `</div></div>` pattern runs past the block and silently eats the following
  prose and sometimes a whole figure. Scope to
  `<main id="quarto-document-content">` if you must do it at all.
- **Filter `CasADi` warning lines out of extracted output.** A solve that
  struggles emits dozens of `NaN detected for output g` warnings, which
  interleave with the printed results and swamp them.
- `_`-prefixed files and directories are skipped by project renders — that is
  what keeps `_model.py`/`_model.qmd` off the sidebar and `_scratch/` out of the
  site. They
  still render fine when named directly on the command line.

## Extracting printed output

```python
import re, html, pathlib
t = pathlib.Path("_site/chapters/NN-name/<entry>.html").read_text()
for m in re.findall(r"<pre><code>(.*?)</code></pre>", t, re.S):
    s = html.unescape(re.sub("<[^>]+>", "", m))
    print("\n".join(l for l in s.splitlines() if "CasADi" not in l))
```

## Prose that cannot drift from the code

**Inline expressions.** Quarto 1.4+ evaluates `` `{python} expr` `` in prose,
at render, in the page's own namespace:

```markdown
The neutral point is `{python} f"{x_np*1e3:.1f}"` mm aft of the nose.
```

Use this for **every** number in an `**Answer.**` line. Hand-typed numbers drift
from the cells above them the moment anything upstream changes, and the drift is
silent. It also removes the reason to `print()` a value purely so prose can
quote it.

The expression runs where it sits in the document, so the cell that computes the
value must appear **above** it. That is compatible with putting the answer before
the evidence: compute in one folded cell, answer, then show tables and figures.

## Tables

**Two questions come before any of this** (SKILL.md has them as rules, and
`lint.py` checks them). A table counts as a figure, so an entry shows one or the
other, never both — a grid under a plot that already shows the same quantities is
the failure. And a table is at most 3×4 or 4×3 excluding the header; if the
values will not fit, plot them, or quote the two or three that matter in the
prose. What follows is how to build the table once you have established you want
one.

Quarto treats tables as their own float type — not images. A cell whose last
expression is a DataFrame (or a `Styler`) renders as a real HTML table:

```python
#| label: tbl-ballast
#| tbl-cap: "Ballast needed at each static margin."
import pandas as pd
pd.DataFrame({...}).style.hide(axis="index")
```

- `label:` must start with `tbl-` for the caption, numbering and `@tbl-ballast`
  cross-reference to work. `fig-` for figures, likewise.
- `.style.hide(axis="index")` drops the row numbers, which are never meaningful
  here. `.style.format({...})` controls decimals per column.
- Pre-format as strings when a column holds ranges (`"1.99 – 4.59"`); use
  `.format()` when it holds numbers.
- pandas ships with AeroSandbox, so no new dependency.

Prefer a table to a block of `print()` output whenever the data is rectangular:
it can be cross-referenced, scanned by row, and read on a phone.

## Callouts

`::: {.callout-note}` … `:::` with a `## Heading` line inside. Two are in use,
and the colours carry the meaning: **`callout-note` (blue) / `## Assumed`** for
a value nobody could supply, and **`callout-tip` (green) / `## Specified`** for
a design decision the user made. Blue reads as provisional, green as settled,
which is the distinction — an assumption may be wrong, a decision cannot be.
Add `collapse="true"` to fold it — that is how the chapter index ships a full
source listing without burying the page.

## Showing a function's source in an entry

`inspect.getsource()` needs the source file, which a bare `exec()` of file text
does not provide — it labels every function `"<string>"` and `getsource` raises
`OSError`. Compile with the real path first:

```python
exec(compile(pathlib.Path(p).read_text(), p, "exec"))
```

With that in the shim, an entry can render exactly the shared functions it
called, read off the live object so it cannot drift. The same `co_filename` is
what lets a namespace be asked which functions came from which file, which is
how the chapter index lists available machinery without maintaining a list.
