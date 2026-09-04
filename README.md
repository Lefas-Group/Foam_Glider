# Aim

To use Claude Code to design a foam chuck glider using [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox). This can then be verified in real life.

The first task has been to provide claude with a 'skill' helping it to create a 'notebook' for the aircraft design, which lists answers to the users design questions in a robust, repeatable manner. Once this system is efficient, the user can be replaced with a higher level agent, which interrogates the design assumptions and outputs, and drives further decisions. The notebook forms an end to end documentation of the development of the design, which can be human reviewed for trust. There are now two notebooks: `aircraft-notebook`, written while the skill was taking shape, and `optimised-glider-notebook`, the current design, written by the matured skill.

## Structure

```
optimised-glider-notebook/     Current design: 30 cm-span duration glider
aircraft-notebook/             Earlier example: the McEagle-derived chuck glider
.claude/skills/design-notebook/
  SKILL.md                     how entries get written
  check.py                     lint, re-render and report which figures moved
  lint.py, freezediff.py       the two halves of check.py, runnable alone
  notebook.py                  shared page furniture, vendored into each notebook
  references/                  Quarto + AeroSandbox gotchas, vendored AeroSandbox book
  templates/                   entry and new-notebook scaffolds
  mcp_servers/library_explorer/  introspects installed AeroSandbox (see .mcp.json)
```

`check.py` is what to run after changing a chapter's `_model.py` or
`_analysis.py`: it lints, deletes the freeze, re-renders and names the figures
whose bytes changed, so a refactor has to prove it moved nothing. The
`library-explorer` MCP server is wired up by `.mcp.json` and needs approving once
when you first launch Claude in this repo. `SKILL.md` covers the rest.

## What's in the notebooks

- **`optimised-glider-notebook`** — a flat-plate foam-tray glider optimised for
  time aloft. Chapter 01, *Duration glider*: AeroBuildup inside an `asb.Opti`
  that trims and balances the glide together. Chapter 02, *Flight path*: the same
  aircraft flown rather than trimmed — a marched rigid body against a collocated
  point mass.
- **`aircraft-notebook`** — the earlier McEagle-derived design, including the
  as-built reconciliation and the first-flight comparison.

## Render and view a notebook

Install the following:

- [uv](https://docs.astral.sh/uv/)
- [Quarto CLI](https://quarto.org/docs/download/) (tested on 1.8.27)

Then, from the repository root:

```bash
uv run quarto preview optimised-glider-notebook --port 4321
```

This renders the site, opens it in a browser at `http://localhost:4321/`, and
live-reloads on edits. The `--port` is worth passing: without it Quarto picks a
random port between 3000 and 8000 and prints it. It is not a suggestion — if
something else already holds the port, Quarto exits rather than moving. For
static output instead:

```bash
uv run quarto render optimised-glider-notebook
open optimised-glider-notebook/_site/index.html
```

Each notebook's `_freeze/` is committed, so a fresh clone renders without
re-running any solve. Swap the directory name to render `aircraft-notebook`.

## Using the skill with Claude

Requires [Claude Code](https://claude.com/claude-code). The skill is
project-scoped, so there is no installation step — clone the repo, run `claude`
in its root, and `design-notebook` is available. Invoke it with
`/design-notebook`, or just describe the analysis you want and it triggers on its
own. On the first launch Claude will ask whether to trust the project's
`.mcp.json`; approve it to give the skill its AeroSandbox lookup server.

It works in a loop: explore in `_scratch/`, then propose an entry title and its
figures, and write nothing into the notebook until you agree.
