# Aim

To use Claude Code to design a foam chuck glider using [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox). This can then be verified in real life.

The first task was to give Claude a 'skill' helping it create a 'notebook' for
the aircraft design, listing answers to the user's design questions in a robust,
repeatable manner. The notebook forms end-to-end documentation of the design's
development, which can be human reviewed for trust.

The second task, now the main one, is **`nb`** — the same idea distilled out of
the Claude Code skill into a standalone agent that runs on Gemini. One command
turns a design question into a notebook entry that passes a 32-rule lint
contract, renders, is checked against its own output, and commits. See
[`nb/README.md`](nb/README.md).

The goal either way is to replace the user with a higher-level agent that
interrogates the design assumptions and outputs and drives further decisions.
`nb` is the shape that makes it possible: it already runs unattended apart from
the questions it must ask, and several instances could be driven in parallel.

There are three notebooks. `glider-notebook` is the live one, written by `nb`.
`aircraft-notebook` and `optimised-glider-notebook` were written by the skill
and are kept frozen — they are the regression corpus `nb` calibrates its lint
rules against, so their contents are deliberately not updated.

## Structure

```
nb/                            The agent: one command per notebook entry
glider-notebook/               Live design, written by nb — 300 mm-span foam glider
optimised-glider-notebook/     Frozen: 30 cm-span duration glider (skill-written)
aircraft-notebook/             Frozen: the McEagle-derived chuck glider (skill-written)
.claude/skills/design-notebook/
  SKILL.md                     how entries get written, for Claude Code
  check.py                     lint, re-render and report which figures moved
  lint.py, freezediff.py       the two halves of check.py, runnable alone
  notebook.py                  shared page furniture, vendored into each notebook
  references/                  Quarto + AeroSandbox gotchas, vendored AeroSandbox book
  mcp_servers/library_explorer/  introspects installed AeroSandbox (see .mcp.json)
```

`nb` carries its own copies of `lint.py`, `check.py`, `freezediff.py` and
`notebook.py` under `nb/vendor/`, so the two systems do not share code and the
skill can be removed without breaking `nb`.

`check.py` is what to run after changing a chapter's `_model.py` or
`_analysis.py`: it lints, deletes the freeze, re-renders and names the figures
whose bytes changed, so a refactor has to prove it moved nothing. The
`library-explorer` MCP server is wired up by `.mcp.json` and needs approving once
when you first launch Claude in this repo. `SKILL.md` covers the rest.

## What's in the notebooks

- **`glider-notebook`** — the current design and the only one still being
  written to. Sixteen entries across four chapters, each chapter a variation on
  a 300 mm-span foam glider: *Foam glider* (the baseline planform in 5 mm
  stock), *Fuselage model* (its mass and drag included), *Unswept quarter chord*
  (the zero-sweep line moved off the leading edge), and *3 mm foam*.
- **`optimised-glider-notebook`** — a flat-plate foam-tray glider optimised for
  time aloft. Chapter 01, *Duration glider*: AeroBuildup inside an `asb.Opti`
  that trims and balances the glide together. Chapter 02, *Flight path*: the
  same aircraft flown rather than trimmed.
- **`aircraft-notebook`** — the earlier McEagle-derived design, including the
  as-built reconciliation and the first-flight comparison.

## Render and view a notebook

Install the following:

- [uv](https://docs.astral.sh/uv/)
- [Quarto CLI](https://quarto.org/docs/download/) (tested on 1.8.27)

Then, from the repository root:

```bash
uv run quarto preview glider-notebook --port 4321
```

This renders the site, opens it in a browser at `http://localhost:4321/`, and
live-reloads on edits. The `--port` is worth passing: without it Quarto picks a
random port between 3000 and 8000 and prints it. It is not a suggestion — if
something else already holds the port, Quarto exits rather than moving. For
static output instead:

```bash
uv run quarto render glider-notebook
open glider-notebook/_site/index.html
```

Each notebook's `_freeze/` is committed, so a fresh clone renders without
re-running any solve. Swap the directory name for any of the three.

## Writing an entry with `nb`

Requires `GEMINI_API_KEY`. From the repository root:

```bash
uv run --group nb python -m nb ask glider-notebook "why is the tail so big?"
```

It asks for two budgets, stops for anything Specified, confirms its assumptions,
then writes, renders, verifies and commits one entry. Follow the detail in a
second tab with `python -m nb watch glider-notebook`.
[`nb/README.md`](nb/README.md) covers the rest.

## Using the skill with Claude

Requires [Claude Code](https://claude.com/claude-code). The skill is
project-scoped, so there is no installation step — clone the repo, run `claude`
in its root, and `design-notebook` is available. Invoke it with
`/design-notebook`, or just describe the analysis you want and it triggers on its
own. On the first launch Claude will ask whether to trust the project's
`.mcp.json`; approve it to give the skill its AeroSandbox lookup server.

It works in a loop: explore in `_scratch/`, then propose an entry title and its
figures, and write nothing into the notebook until you agree.
