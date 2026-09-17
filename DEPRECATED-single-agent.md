# The single-agent `nb`, preserved

`main` runs several agents at once, on different chapters of one notebook,
answered from a single terminal via `nb board`. Before that it ran **one agent,
one notebook, questions answered where you typed** — a smaller system, and a
clearer one to read if you want to understand the idea rather than the
concurrency.

That version is kept as the tag **`nb-single-agent`**, and it works: preflight
passes, `nb.corpus` passes, and a checkout runs with no manual steps.

**If `git worktree add` says the tag is unknown**, the tag is not on the remote:
tags are not pushed by `git push`, they need `git push origin nb-single-agent`.
Ask whoever owns the repo to push it, or recreate it locally from the history.

## Getting it running

```bash
git worktree add ../nb-single-agent nb-single-agent
cd ../nb-single-agent
export GEMINI_API_KEY=...

uv run --group nb python -m nb.corpus                       # prove it is intact
uv run --group nb python -m nb ask glider-notebook "<question>"
```

`uv` fetches the dependencies on first run. The worktree is a full, independent
checkout — run it while `main` is doing something else; the two share nothing
but the object store. When finished:

```bash
git worktree remove ../nb-single-agent
```

## Why a tag and not a copied directory

A copy of `nb/` alone **would not run**. Rule 11 compares each notebook's
`_notebook.py` byte-for-byte against the vendored copy, and preflight refuses
to start on drift — so a frozen `nb/` beside a live `glider-notebook` declines
to do anything. The two have to move together, and a tag is the only way to
keep a whole consistent tree without duplicating ~150 files that no test covers
and that would rot in silence.

## What it does not have

- `--detach`, `nb board`, `nb answer` — questions are asked at the terminal
- run-scoped `_scratch/runs/<id>/`; there is one `_scratch/run/`
- the render lock, so two concurrent renders will fail on `_freeze/site_libs/`
- `ipopt.max_wall_time` confined to probes, so a busy machine can kill a solve
  mid-render and present it to the model as a bug to fix
- the stuck detector, so a run that wedges burns every turn it has left

Everything else — the 32 rules, the two stops, budgets in the footer,
`verify`, `check`, the manifest — is the same.

## Two commits on top of the boundary

The tag is not the raw pre-parallelism commit. Two fixes were needed to make it
a tree that actually runs:

- **`_probe_base.py` is committed.** `_scratch/` was ignored wholesale, so the
  file rule 11 requires was never in git and a fresh checkout could not start.
  This was a live bug on `main` too, fixed there as `421c4a6` — found precisely
  by checking this tag out and watching it fail.
- **The corpus baseline matches the tree.** The recorded counts predated two
  chapter-05 entries.
