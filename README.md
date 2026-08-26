# Aim

To use Claude Code to design a foam chuck glider using [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox). This can then be verified in real life.

The first task has been to provide claude with a 'skill' helping it to create a 'notebook' for the aircraft design, which lists answers to the users design questions in a robust, repeatable manner. Once this system is efficient, the user can be replaced with a higher level agent, which interrogates the design assumptions and outputs, and driveas further decisions. The notebook forms an end to end documentation of the development of the design, which can be human reviewed for trust.

## Structure

```
aircraft-notebook/            An example notebook for the foam chuck glider case
.claude/skills/design-notebook/
  SKILL.md                    how entries get written
  references/                 Quarto + AeroSandbox gotchas, vendored AeroSandbox book
  templates/                  entry and new-notebook scaffolds
```

## Render and view a notebook

Install the following:

- [uv](https://docs.astral.sh/uv/)
- [Quarto CLI](https://quarto.org/docs/download/) (tested on 1.8.27)

Then, from the repository root:

```bash
uv run quarto preview aircraft-notebook
```

This renders the site, opens it in a browser at `http://localhost:4321/`, and
live-reloads on edits. For static output instead:

```bash
uv run quarto render aircraft-notebook
open aircraft-notebook/_site/index.html
```

## Using the skill with Claude

Requires [Claude Code](https://claude.com/claude-code). The skill is
project-scoped, so there is no installation step — clone the repo, run `claude`
in its root, and `design-notebook` is available. Invoke it with
`/design-notebook`, or just describe the analysis you want and it triggers on its
own.

It works in a loop: explore in `_scratch/`, then propose an entry title and its
figures, and write nothing into the notebook until you agree.