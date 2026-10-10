# Foam glider

Designing foam aircraft with [AeroSandbox](https://github.com/peterdsharpe/AeroSandbox),
so a design can be built and flown against what the notebook predicted — and
reconstructing ones that already exist, so the prediction can be checked against
numbers somebody else published first.

Three layers, each one the previous one distilled:

| | what it is |
|---|---|
| **`coordinate-design`** | a Claude Code skill. You give a direction; it runs the questions |
| **`nb`** | an agent. One command turns one question into one notebook entry |
| **the notebooks** | Quarto sites. One entry per question, rendered from code that recomputes its own numbers |

You watch it all from one place: `nb open` — the board in a window, the site
in a browser tab that keeps itself current.

## Setup, from nothing

Four binaries on PATH, one API key, and Claude Code if you want the skill.

| | why | |
|---|---|---|
| **[uv](https://docs.astral.sh/uv/)** | runs everything; installs Python 3.13 and the deps itself | required |
| **[Quarto CLI](https://quarto.org/docs/download/)** | renders the notebooks | required |
| **git** | `nb` commits each entry, and scopes freezes by diff | required |
| **[Node](https://nodejs.org/)** | `nb` drives its file edits through `npx @modelcontextprotocol/server-filesystem` | required by `nb`, not by rendering |
| **[Claude Code](https://claude.com/claude-code)** | runs the `coordinate-design` skill | only for the skill |

The API key is read from the environment — there is no `.env`. Runs detach into
the background, so it has to be exported in the shell that launches them:

```bash
export GEMINI_API_KEY=...        # aistudio.google.com/apikey
```

Then check the whole lot at once, which is faster than finding out mid-run:

```bash
uv run --group nb python -m nb.preflight <notebook>
```

It reports every missing binary, an unset key, and anything wrong with the
notebook's own structure. `preflight ok` means `nb ask` will get as far as the
model. No separate install step: `uv run` syncs from `uv.lock` on first use.

Rendering a notebook needs only uv and Quarto — the `nb` group, Node and the key
are for running the agent.

## `coordinate-design` — start here

Give Claude a direction rather than a question, and the skill drives the rest:
it reads what the notebook has already answered, picks the next question, routes
it to a chapter, launches `nb`, answers what the run asks while it works, and
reports what came back.

It answers budgets, assumption reviews, new chapters and refactors on its own.
**It will not invent a Specified input** — one where a different answer changes
what is being built. If your direction settles it, the skill answers and says
so; if not, it asks you **at the board** and waits.

Several runs go at once, one per chapter. See
[`.claude/skills/coordinate-design/SKILL.md`](.claude/skills/coordinate-design/SKILL.md).

## `nb open` — where you sit

```bash
uv run --group nb python -m nb open <notebook>
```

The board opens in its own window and the site opens in a browser; the page
holds a connection, so one tab stays current for a whole programme and a
committed entry brings the tab to it. `nb board <notebook>` is the board
alone, on the terminal you are already in.

The programme as a conversation: your direction, then every question an agent
asked, every answer and who gave it, every decision the coordinator took, and
every entry that committed — in order, with a live line per working agent at
the bottom. Questions escalated to you arrive here, and you answer them here.

It is a view, not a supervisor. Close it and the runs carry on; `nb answer`
reaches them from any terminal.

## `nb` — one question, one entry

```bash
uv run --group nb python -m nb ask <notebook> \
  --chapter NN-name "How much does 3 mm foam cost in sink rate?"
```

Probes the chapter's model, writes the entry, lints it against a 49-rule
contract, renders it, and commits — about five minutes. It stops only for a new
chapter or a refactor, both of which later entries would be built on.

[`nb/README.md`](nb/README.md) is the real documentation: the loop, the rules,
the budgets, and why each is shaped the way it is.

## Reconstructing an aircraft that exists

Half the programmes here start from somebody else's aeroplane. A Flite Test
plan is free, and page one of it is a specification table — length, span, area,
dry weight, CG, wing loading — so the model can be held to numbers nobody in
this repo chose.

The brief carries those as `--target` rows with a tolerance each, and one
command converges the vehicle onto them:

```bash
uv run --group nb python -m nb reconstruct <notebook> \
  --chapter NN-name
```

One entry comes out, reporting every target against its tolerance with the
worst error as the headline, a three-view of what was built, and a bar per
target. A target that cannot be hit is a finding, not something to hide; a
tolerance is never loosened, and a marketing CLAIM — "endless vertical climb" —
is never a target, because judging it is what the programme is for.

**Put the plan in `<notebook>/_reference/`.** The agent has no network. Every
dimension you do not give it, it supplies from memory, and in the finished
entry that looks exactly like one you measured. See `nb/README.md` for what
happened the one time nobody did this.

## The notebooks

```bash
uv run quarto preview <notebook> --port 4321
```

Each `_freeze/` is committed, so a fresh clone renders without re-solving
anything.

**Every top-level directory with a `chapters/` is a notebook**, and that is the
whole of the convention — there is no register to keep in step. Each one's
`index.qmd` is its front page: the brief it is held to, and the diagram of how
its chapters fork one another. `_inputs.yml` beside it is the brief itself,
written by a person, and the fastest way to see what an aircraft is being asked
to be. Notebooks come and go as programmes finish, so they are not listed here.
