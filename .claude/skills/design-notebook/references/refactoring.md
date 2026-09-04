# Changing shared code without changing the answers

SKILL.md carries the rules — the tier table, "an entry that calls shared
machinery must render it", and "deleting the freeze is not optional". This is the
workflow and the reasoning behind it. Read it before touching a chapter's
`_model.py` or `_analysis.py`.

## Promotion is allowed; silent rewriting is not

Promoting a helper means editing an earlier entry to call it. That is allowed,
and is *not* what "entries are written once and left alone" forbids: that rule
protects **conclusions** from being quietly rewritten. A refactor is different in
kind — and the difference must be **proven, not asserted**.

## Git is the baseline

`_freeze/**/execute-results/html.json` stores each page's rendered markdown with
its inline expressions **already evaluated**, and the figure PNGs sit alongside
it — all committed, because a notebook commits its freeze so a fresh clone
renders without re-solving. So the baseline exists before you start, with nothing
to capture and nothing to remember to capture.

`git diff` cannot read it usefully, though: each `markdown` field is one JSON
line, so a single changed digit reports the whole page as modified. And four
things differ between two renders of identical code — the runtime seconds, fenced
code blocks, Quarto's per-render random cell ids, and figure UUIDs. `freezediff`
normalises all four while **keeping the solve count**, which matters: masking the
whole runtime line once hid a real 18 → 2.

```bash
uv run python <skill>/check.py <notebook> [chapter ...]
```

`check.py` lints, deletes the freeze, renders and diffs in one call, and names
the figures whose bytes moved so only those need reading. `freezediff.py` alone
does the last step if the render is already done.

**Verify the instrument before believing it.** On an unchanged tree the diff must
come back empty and the PNGs byte-identical. If it reports noise, the filters
need recalibrating before any result from it means anything.

## The failure this exists to prevent

A comparison run without deleting the freeze is a fresh render against a cache
hit, and the match is an artefact. That has happened here: a mistyped working
directory meant the freeze was never deleted and the render never ran, and
everything reported unchanged. `freezediff` now refuses to compare when a page's
frozen code no longer matches its `.qmd`, but the discipline comes first.

## Why `api()` matters, and why it is invisible to readers

`_notebook.py` holds `show_source()` and `api()` and is deliberately absent from
the rendered site: the chapter index lists `_model.py` and `_analysis.py` only,
and `api()` filters to `_analysis.py`. A reader of the design does not need a
function inventory.

`_scratch/_probe_base.py` prints `api()` on every run, which is the moment
someone is about to write a helper — that is where discovery belongs, not on a
page the author has no reason to open. Four subtly different neutral points once
existed in one chapter because nothing advertised the first, and one of the four
took its moment reference from the wrong station. The same failure recurred when
`_analysis.py` was empty and `api()` printed nothing: a near-duplicate of the
design solve got written in a probe.
