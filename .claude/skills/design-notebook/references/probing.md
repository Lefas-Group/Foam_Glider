# Scratch probe mechanics

SKILL.md carries the rule — probe in `_scratch/` before writing an entry, reach
for `probe.py` first, overwrite per question. This is the machinery, read when a
probe misbehaves or a figure is needed.

## `probe.py` and `_probe_base.py`

Every notebook's `_scratch/` holds `_probe_base.py` (the preamble) and `probe.py`
(the question). The base resolves the notebook root, execs `_notebook.py`,
`_model.py` and `_analysis.py`, and prints `api()`. A probe is then:

```python
"""Scratch probe. Gitignored, never rendered. Edit the question, not the file."""
from _probe_base import *  # noqa: F403 -- chapter loaded, api() printed

# --- the question ----------------------------------------------------------
```

**Edit the question block; do not rewrite the file.** Successive probes then cost
the delta rather than the whole thing, which is the single largest per-entry
saving available.

`compile()` with the real path is load-bearing, exactly as in the `_model.qmd`
shim: a bare `exec()` of file text labels every function `"<string>"`, and then
`inspect.getsource()` raises `OSError`, breaking `show_source()` and `api()`
together. Probes are where a helper is about to be written, so `api()` must work
here or the discovery listing is empty.

Set `CHAPTER` in `_probe_base.py` when working on a different chapter.

## `probe.qmd`

Use it when the question produces a figure, or when rehearsing cells that are
about to become an entry — its cells paste across unchanged. For a one-off API
check needing no model, `uv run python -c` beats both.

- **The include path is relative to the probe file**, hence `../chapters/…`.
- **Cell code runs from the notebook root**, not from `_scratch/`, because the
  project sets `execute-dir: project`. Any path inside a cell is relative to the
  notebook directory.
- Run it: `uv run quarto render <notebook>/_scratch/probe.qmd`
- Output stays put — Quarto renders it standalone, not into `_site/`. Printed
  output is in `_scratch/probe.html`; figures are
  `_scratch/probe_files/figure-html/*.png`, named `cell-N-output-1.png` unless
  the cell has a `#| label:`.
- Each render costs ~8 s of fixed overhead regardless of the code, so put several
  probes in one file rather than rendering repeatedly.

Iterating on a plot re-runs every cell above it, cold, on each render. If that
starts to hurt, `exec` the model into a persistent Jupyter kernel instead and
re-plot without re-solving.

## Why `_scratch/`

The leading underscore is load-bearing: `_scratch/` sits inside the Quarto
project, and Quarto skips `_`-prefixed paths, so `quarto render <notebook>` never
sees it. Don't rename it to `scratch/`. It is gitignored, so nothing in it needs
to be tidy — but nothing in it survives either.

## Timing and benchmark hygiene

More time has been lost here than to any slow model. Each of these cost real
minutes in a single session.

**Never leave a long run unattended and silent.** `_probe_base.py` arms
`faulthandler.dump_traceback_later`, which prints where the process is stuck
without killing it, from a separate thread — so unlike a signal it reports from
inside a long C call. A solver flag that turned one solve into ten silent minutes
was indistinguishable from a hang until this existed.

**Kill your strays, and check the machine before believing a number.** Two
orphaned benchmark processes ran 35 minutes unnoticed and corrupted the timing
they were being compared against. `uptime` before and after; a wall-clock figure
from a loaded machine measures the machine. The same solve measured 533.9 s
against a 145 s baseline for this reason.

**Never run two heavy probes at once.** Both starve and neither number means
anything. Sequential is faster in practice and the results are usable.

**Shell traps that silently produce nothing:**

- `grep` in a pipeline buffers — use `--line-buffered`. Piping a live log through
  `| tail` buffers everything until exit, so a finished job looks like an empty
  one. This has twice been mistaken for "still running".
- `pgrep -f "probe.py"` matches *the shell that is waiting*, so the wait never
  ends. Use a bracket to break the self-match: `pgrep -f "probe[.]py"`.
- macOS has no `timeout`, and BSD `find` has no `-newermt` — the latter fails
  silently and returns nothing. Prefer Python when portability matters.

**Report iterations alongside time.** Wall clock alone inverts conclusions: one
comparison showed 8.4× faster while the iteration count went 192 → 481. Solve
counts can mislead too — a collocated solve was 599 s at 8 aero solves against
112 s at 3070, because the graph is built once and the solver iterates inside C
where the counter cannot see.
