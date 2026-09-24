# Foam glider

Designing a foam chuck glider with [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox),
so the design can be built and flown against what the notebook predicted.

Three layers, each one the previous one distilled:

| | what it is |
|---|---|
| **`coordinate-design`** | a Claude Code skill. You give a direction; it runs the questions |
| **`nb`** | an agent. One command turns one question into one notebook entry |
| **the notebooks** | Quarto sites. One entry per question, rendered from code that recomputes its own numbers |

## `coordinate-design` — start here

Give Claude a direction rather than a question, and the skill drives the rest:
it reads what the notebook has already answered, picks the next question, routes
it to a chapter, launches `nb`, answers what the run asks while it works, and
reports what came back.

It answers budgets, assumption reviews, new chapters and refactors on its own.
**It will not invent a Specified input** — one where a different answer changes
what is being built. If your direction settles it, the skill answers and says
so; if not, it asks you.

Several runs go at once, one per chapter. See
[`.claude/skills/coordinate-design/SKILL.md`](.claude/skills/coordinate-design/SKILL.md).

## `nb` — one question, one entry

```bash
uv run --group nb python -m nb ask glider-notebook \
  --chapter 04-thinner-foam "How much does 3 mm foam cost in sink rate?"
```

Probes the chapter's model, writes the entry, lints it against a 39-rule
contract, renders it, and commits — about five minutes. It stops only for a new
chapter or a refactor, both of which later entries would be built on. Needs
`GEMINI_API_KEY`.

[`nb/README.md`](nb/README.md) is the real documentation: the loop, the rules,
the budgets, and why each is shaped the way it is.

## The notebooks

```bash
uv run quarto preview glider-notebook --port 4321
```

Needs [uv](https://docs.astral.sh/uv/) and the
[Quarto CLI](https://quarto.org/docs/download/). Each `_freeze/` is committed,
so a fresh clone renders without re-solving anything.

- **`RADICAL-GLIDER`** — live. The FliteTest X-Wing in flat-plate foam.
- **`glider-notebook`** — live. A 300 mm-span foam glider, six chapters.
- **`optimised-glider-notebook`**, **`aircraft-notebook`** — frozen. Written by
  the older skill, kept as the regression corpus `nb` calibrates its lint rules
  against, so their contents are deliberately not updated.

## `design-notebook` — superseded

The first attempt: a skill that had Claude write the entries itself. `nb` does
that job now, and does it the same way for every run. The skill is still in
`.claude/skills/design-notebook/` because the two frozen notebooks were written
by it, and `nb` keeps its own copies of the shared checkers under `nb/vendor/`
so nothing depends on it.
