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
uv run --group nb python -m nb.preflight mustang-mkr2
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
uv run --group nb python -m nb open RADICAL-GLIDER
```

The board opens in its own window and the site opens in a browser; the page
holds a connection, so one tab stays current for a whole programme and a
committed entry brings the tab to it. `nb board RADICAL-GLIDER` is the board
alone, on the terminal you are already in.

The programme as a conversation: your direction, then every question an agent
asked, every answer and who gave it, every decision the coordinator took, and
every entry that committed — in order, with a live line per working agent at
the bottom. Questions escalated to you arrive here, and you answer them here.

It is a view, not a supervisor. Close it and the runs carry on; `nb answer`
reaches them from any terminal.

## `nb` — one question, one entry

```bash
uv run --group nb python -m nb ask glider-notebook \
  --chapter 04-thinner-foam "How much does 3 mm foam cost in sink rate?"
```

Probes the chapter's model, writes the entry, lints it against a 43-rule
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
uv run --group nb python -m nb reconstruct mustang-mkr2 \
  --chapter 01-airframe-reconstruction
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

## `tools/` — the pose-fitting bench

Hand-driven, outside `nb`, and not part of the agent loop. The question it
answers is *how wrong is the reconstruction*, from a photograph rather than from
a spec sheet.

`tools/pose_fit.py` is the reusable half: fit a camera pose to NAMED landmark
correspondences — "that is the port wingtip, about there" — and each landmark's
residual afterwards is model error in pixels rather than pose and model error
mixed together, which is all a silhouette-area overlay can tell you. It knows
nothing about any particular aircraft; `landmarks()` walks whatever wings and
fuselages an `asb.Airplane` has. The rest of the directory is one-shot scripts
against specific photographs, with their paths hard-coded, kept for the record.

## The notebooks

```bash
uv run quarto preview mustang-mkr2 --port 4321
```

Each `_freeze/` is committed, so a fresh clone renders without re-solving
anything.

- **`mustang-mkr2`** — live, and where the work is. FT Mighty Mini Mustang
  MKR2, reconstructed from the plan to published tolerance.
- **`RADICAL-GLIDER`** — the FliteTest X-Wing in flat-plate foam. Seven
  chapters, the longest chain here.
- **`glider-notebook`** — a 300 mm-span foam glider, six chapters.
- **`optimised-glider-notebook`**, **`aircraft-notebook`** — frozen. Written by
  the older skill, kept as the regression corpus `nb` calibrates its lint rules
  against, so their contents are deliberately not updated.
- **`discus-2c-notebook`** — rendered output only. The source was not kept; the
  site is in the repo because the pages are still worth reading.

## `design-notebook` — superseded

The first attempt: a skill that had Claude write the entries itself. `nb` does
that job now, and does it the same way for every run. The skill is still in
`.claude/skills/design-notebook/` because the two frozen notebooks were written
by it — but nothing in `nb` loads it or reads from it. The vendored copies it
used to depend on are gone; `nb/contract/` is the only lint there is.
