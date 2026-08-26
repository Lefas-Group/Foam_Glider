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
