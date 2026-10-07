---
name: coordinate-design
description: Coordinates an aircraft design programme in the `nb` notebook — turns a design direction into a sequence of questions, answers what the runs ask, and picks the next question from what they found. Use when the user gives a direction rather than a single question, or asks to keep the programme moving.
when_to_use: The user describes what they want designed or explored rather than asking one question; says "keep going" or "run the next few"; or wants a new aircraft set up.
allowed-tools: Bash(uv run --group nb python -m nb *) Bash(git log *) Read Glob Grep
---

Now: !`date "+%Y-%m-%d %H:%M"`
Notebooks: !`ls -d */_quarto.yml 2>/dev/null | cut -d/ -f1 | tr '\n' ' '`

## What you hold

You hold the direction. `nb` holds the aircraft. One `nb ask` is one question
and one entry, written by an agent you do not talk to.

**You never write an entry, edit a chapter, or touch `_model.py`.** A run does
that, and a second writer in a chapter is refused by a lock. Your work is four
things: which question, which chapter, answering what the run asks, and telling
the user what came back.

`nb` is run as `uv run --group nb python -m nb <cmd>`, from the repo root.

## Open it first

Once you know which notebook — and you must, before any `nb` command — one line
puts the programme in front of the person watching:

```bash
uv run --group nb python -m nb open <notebook>
```

The board opens in its own window (every run, its questions, its endings) and
the site opens in a browser. Do this before your first `nb ask`; the board is
the view a person uses to follow you, and nothing else opens it.

**One tab, for the whole programme.** The site is served locally and the page
holds a connection open, so the tab stays current and a committed entry brings
the tab to it. Run this again whenever you like — it will not pile up tabs; if
one is already open it says so and opens nothing. `--stop` shuts the server
down.

**It will tell you if the board cannot answer.** A notebook you hold is one
whose run questions are yours, so the board shows them and declines to answer
them — right while you are listening, and a trap when you are not: a hold
outlives the session that made it, and nothing removes it. If `nb open` says
the holder has been silent for hours, either you are that holder and all is
well, or reopen with `--all` and the person at the board can answer again.

If there is no `_site` yet it says so and names `nb view <notebook>` rather than
building it — a project render re-executes any entry whose freeze is missing,
which is minutes of solver time, so that stays a decision you make deliberately.

## Read the programme before asking

**Never ask what has been answered.** Two read-only views:

```bash
git log --format="%h %s" -- <notebook>/chapters/     # every question, newest first
uv run --group nb python -c "
from nb.config import Notebook; from nb.domain import manifest
print(manifest.build(Notebook('<notebook>')))"       # …with each answer
```

The manifest is what the run itself is shown, so it is the same picture the
agent will have.

## Ask

```bash
uv run --group nb python -m nb ask <notebook> \
  --chapter NN-name "<one question ending in ?>" \
  --why "<why this question, now>" \
  --pool 200 --ceiling 90 --quiet
```

- **`--quiet` is not optional for you.** Without it the parent process runs a
  blocking TUI. With it, the parent prints `run <run-id>`, detaches and exits.
  **Capture that run id** — you need it to answer.
- **A watcher window opens for each run**, carrying its transcript from the
  first line and closing itself a few seconds after the run ends. You do not
  ask for it and do not need to close it. `--no-watch` suppresses it, and stops
  the run sending the open tab to its entry — for a run nobody is watching.
- **`--chapter` is required; routing is yours.** A chapter is a vehicle: pick
  the one whose `_model.py` the question is about. Omitted, nothing starts.
- **`--why` is required, and it is YOUR SENTENCE ON THE PAGE.** It renders under
  the question as the entry's subtitle, verbatim — the run is told to copy it
  and is refused if it rewords it. Write it for whoever reads the notebook in
  a month, not for the agent: what the last run found that makes this the next
  question, or which decision is waiting on it. **40 words, and nothing starts
  if it is over** — two sentences at most, the reason and not the method.

  It is the one part of your reasoning that survives. `nb note` and this
  conversation are transcripts nobody reads back; the entry is committed,
  rendered and read later. Before `--why`, a reader could see two entries
  answering adjacent questions and not tell whether the second followed from
  the first or from a change of mind.

  ```
  --why "The 0.39% reconstruction compared the model with itself, so nothing
         yet checks the planform independently."
  ```

  `nb reconstruct` carries a standing one and takes `--why` only to override it.
- **The question is ONE quoted argument.** It must not start with `--` or end
  with `.json`; the parser drops those.
- **A question needing a different vehicle still names the nearest chapter.**
  The run recognises the fork itself and asks you to approve one.
- **One question per ask**; a run refuses a second folded in.
- **Several at once, one per chapter.** A same-chapter collision is refused at
  turn 0, before a token is spent — but you will not see it in the exit code.
- **The exit code only tells you the LAUNCH worked.** `--quiet` forks and
  returns 0 as soon as the run is detached; everything after that — including
  the chapter lock — is reported in `run.json`'s `outcome`. A non-zero exit
  (`2` bad arguments, `1` preflight) means nothing started at all.

## Watch

**Do not poll. `nb listen` blocks until a run needs you, and prints what and
how long you have:**

```bash
uv run --group nb python -m nb listen <notebook>      # RUN THIS IN THE BACKGROUND
```

It returns 0 the moment any run **asks** (a question on disk), **ends** (an
`outcome`) or **dies**, and 1 if the wait runs out — so a backgrounded call's
exit is what wakes you. An `asks` block names the run, the question, **how many
seconds are left before it defaults**, and the `nb answer` line to paste.

**Background it, for the reason `nb await` is backgrounded.** A foreground
shell call is capped at ten minutes, and — this is the part that bites — its
output only reaches you when it EXITS. A hand-rolled `for … sleep … done` loop
therefore prints `waiting_on` every 40 s and shows you the whole batch once,
minutes later. Measured on 2026-09-29: an `inherited` question went unseen for
nine minutes against a five-minute default, and chapter 06 — whose premise is
that the wing position is free — committed carrying an inherited assumption
that pins the wing at x=0.25 m.

Endings are reported once and then they are history; a question or a death is
reported every time until you act on it. A notebook you have never listened to
reports nothing on the first call — it starts the clock. For the whole picture
at any moment, `nb board <notebook>`.

## Answer

```bash
uv run --group nb python -m nb answer <notebook> <run-id> "<value>"
```

**Say who decided.** Add `--by coordinator` when the answer is *yours* — a
chapter you approved, an assumption you accepted, a budget you set. Leave it off
only when you are relaying what the user actually told you, because then they
are the author and the record should say so. Without it every answer is
recorded as the user's and the board captions it "you".

**Always pass the run id.** Omitting it refuses only when two runs are waiting
at the same instant — and a run you answered a second ago still looks like the
only one waiting until it consumes the reply. A second bare `nb answer` then
overwrites the first, and the record says the user typed the second. Measured.

| `kind` | `name` is | how to answer |
|---|---|---|
| `budget` | `PROBE TIME POOL`, `ENTRY RENDER BUDGET` | seconds. `--pool`/`--ceiling` pre-empt it |
| `assumptions` | `assumptions` | `""` accepts · `1: 2.5e-4` corrects a value · `1: redo — why` sends it back to probe |
| `inherited` | `inherited` | `""` keeps all · `3` or `3; 5` strikes what the fork breaks |
| `stuck` | `NO PROGRESS` | `continue`, `stop`, or advice passed to the model |
| `chapter` | the proposed slug | anything approves · `no — why` sends it back |
| `refactor` | `_model.py` / `_analysis.py` | anything allows · `no — why` restores the file |
| `specified` | the quantity | **see below** |

**The number on a proposed chapter is not yours to police.** Allocation takes
the next free number under a lock and walks past anything a concurrent run took
first, so two runs proposing the same number is not a collision and sending one
back to be renumbered only costs a round trip. Judge the slug, the title and
what it `defines`.

**A Specified input is the one you may not invent.** It is an input where a
different answer changes *what is being built*. Answer it yourself **only when
the user's direction already settles it**, and say which part of their
direction you used. Otherwise **escalate — see below**. The reply syntax for
every kind is in `question.json`'s `how`; the board shows only a one-line
version of it.

`specified`, `chapter` and `refactor` wait an hour, then exit `no_answer`; the
other four take a safe default after five minutes. **An hour is shorter than a
person, so expect to miss it.** Never `nb answer` a timed-out run — it refuses
with *"its question outlived it"* and discards the reply. Recover by where it
stopped:

- **`stem` null in `run.json`** — it asked before opening an entry, nothing is
  on disk, and `resume` refuses. Re-ask with the answer pre-loaded, now that you
  know the key: `--answers f.json` holding `{"<the name it asked>": "<value>"}`.
- **`stem` set** — the page exists; `nb resume <nb> <run-id>` picks it up.

`--answers file.json` pre-answers by `name`, once each — e.g.
`{"assumptions": "", "_model.py": "", "static margin": "10% of MAC"}`. The
refactor key is the filename and the chapter key is the bare slug — no number,
because the number is allocated at creation and the model's guess is
discarded.

## Escalate what the direction does not settle

The user watches the **board**, not this conversation. Put the question where
they are sitting — two commands, because posting must not be able to fail:

```bash
uv run --group nb python -m nb escalate <nb> "<name>" \
  --prompt "<the question, in their terms>" --why "<why the run is stuck>"
uv run --group nb python -m nb await <nb>          # RUN THIS IN THE BACKGROUND
```

**Background the `await`.** A foreground call is capped at ten minutes, which
is shorter than a person; backgrounded it survives, and its exit is what wakes
you to relay the answer. `escalate` returns at once, so the question is safely
on the board either way — if a wait times out, just wait again.

Then relay it to the run that needed it, with `nb answer <nb> <run-id>`, and
`nb note` what you did.

**Do not ask the user directly in this conversation.** Measured: run
`20260925-082733-5d8d` was asked that way, the answer took longer than the
run's hour, and the entry was lost.

## Record the direction first

```bash
uv run --group nb python -m nb direction <nb> "<what the user asked for>"
```

**Before the first `nb ask`**, so nothing in the programme predates the reason
for it. The board pins it above the table and starts the conversation there:
work done under a previous direction stays on the record but is not replayed.
Record a new one when the user changes what they are after — that is what
marks the pivot.

## Narrate every decision

```bash
uv run --group nb python -m nb note <nb> "<one line>"
```

The board is the user's only view of your reasoning — the runs publish
themselves, you do not. Note what you asked and why, what a finished run
changed, and what you chose next. One line each, in the scrollback beside the
questions they explain.

## Read what came back

Everything is in `run.json`. **Never parse `status.log`.**

| field | what |
|---|---|
| `answer` | the entry's headline value and label, read off the render |
| `prose` | the rendered entry, real numbers, code stripped |
| `outcome` | `committed` · `no_entry` · `lint_failed` · `build_failed` · `max_turns` · `chapter_locked` · `stopped` · … (absent, and not alive, means it died) |
| `findings` | `[{rule, message}]` when lint blocked it |
| `failure` | the build error, when it would not render |
| `answered` | every question put to a human, and where the answer came from |
| `committed` | `{sha, entry, at}` |

## Choose the next question

- **Follow the finding, not the plan.** "It cannot trim" changes what to ask
  next more than any backlog does.
- **One unknown at a time.** That is what makes an entry worth citing.
- **A question about a different vehicle is a fork** — ask it against the parent
  chapter and let the run propose one.
- **Report after each run**: the `answer` line and one sentence. Do not batch a
  programme's worth of results into a wall of text.

## Starting an aircraft

```bash
uv run --group nb python -m nb new <dir> \
  --chapter-title "…" --defines "…" \
  --spec "**<what>**: <value>." --assume "**<what>**, <reason>."
```

The title comes from the directory name. `--chapter-title` and `--defines` are
required — a chapter created unnamed is one that gets renamed later, underneath
entry stems and freeze paths. `--spec`/`--assume` are repeatable and **must come
from the user**: they are the whole-aircraft commitments nothing later
overwrites. It returns 0 only when the scaffold lints, preflights *and* renders.

**A new notebook is a new aircraft. Confirm before creating one.**

### If the aircraft already exists, find its plan FIRST

**The agent cannot research.** No network, sandboxed to `chapters/`. Every
dimension you do not supply, it supplies from memory — and it will not look
any different in the entry from one you measured.

Measured, on the three entries of an early Mustang reconstruction: a brief of seven
scalar rows said nothing about form, so the run invented chord, taper,
dihedral, six fuselage stations and five cut-part areas, and captioned them
`# from the plan sheet`. Flite Test publish the plan free. Page one is a
specification table giving length, CG, span, area, dry weight, all-up weight
and **wing loading** — and the entry's computed wing loading was 20 % above the
published figure. Nobody had looked.

```bash
curl -sL -o <notebook>/<plan>.pdf "<url>"       # commit it; a URL 404s, a file does not
pdftoppm -png -r 150 -f 1 -l 1 <plan>.pdf pg    # page 1 is usually the spec table
```

FT plans print 1:1 and carry an inch/cm scale bar, so a render at a known dpi
measures in millimetres directly — no scaling, no perspective correction.
Tiles split parts across pages, so an exact planform needs stitching; that is
real work, and 1b below is usually cheaper than doing it up front.

Then put what you found in as `--spec` rows, one dimension each. The ten-word
cap is **per row** and nothing caps the number of rows, so a dimension table
fits:

```bash
--spec "**Root chord**: 140 mm (5.5 in)." --spec "**Tip chord**: 99 mm."
```

**Record what you could not find, too** — `--spec "**Fuselage**: not
published; assume and declare it."` An unknown you name is one the run
declares; an unknown you leave silent is one it invents and attributes.

### Give it photographs to check the shape against

The targets check the model against published NUMBERS. Nothing checks its
SHAPE, and the gap is wide: one reconstruction reproduced all eight published
figures to 0.40% while missing its power pod entirely and lofting a smooth
pod where the real aircraft is a slab-sided box. Both were obvious the moment
the model was drawn over a photograph.

So find two or three photographs of the real thing and put them in
`_reference/`:

```
_reference/studio.png          the photograph
_reference/studio.mask.png     the subject, white on black
_reference/studio.txt          first word `photo`, then a description
```

**Write the path from the repo root, and check it resolves.** The shell's
cwd persists between calls, so a `cp` issued after a `cd` into the notebook
puts the files at `<nb>/<nb>/_reference/`. Nothing used to complain: the run
simply launched with no photographs and honestly declared the shape
unverified. Launch now refuses on that, but confirm it yourself before asking:

```bash
uv run --group nb python -c "
from nb.config import Notebook; from nb.tools import figures
print(figures.reference_listing(Notebook('<notebook>')))"
```

**Two frames from one shoot are ONE photograph.** The second ANGLE is the
whole value of a second file — a frame from the same session fits the same
pose, hides the same faults, and costs the run a turn to confirm what the
first already told it. Retailers shoot a product once and recolour it, so
"two store photos" is usually one viewpoint twice. Launch warns above mask
IoU 0.80; the Mini Explorer's pair measured 0.88. Spend the effort finding a
genuinely different azimuth instead of a second copy of the easy one.

**Hunt for plain backgrounds.** On white the mask is one threshold; on grass
it is a judgement call, and a product shot with a hand in it puts the hand
inside the mask. Retailer listings and the plan's own page one are the usual
sources.

**Cut the mask yourself, and LOOK AT IT.** This is the step that cannot be
automated — a border-seeded rule recovered about half an aircraft on a good
photograph and essentially nothing on a cluttered one. A bad mask poisons
every pose fitted against it and nothing downstream catches that. The run
never sees the mask: if it is wrong, that is yours to fix before the run
starts.

The run then calls `compare_to_photo` itself, fits the camera by chamfer
distance, and draws each component in its own colour over the photograph. It
reports whether the pose is trustworthy and refuses to be read when it is
not. It gets **no score** — a number there would be optimised, and a model
tuned to a photograph has been fitted to the thing it was meant to be
checked against.

### Transcribe what the plan PRINTS, do not measure it

Page one of an FT plan is a specification table. Read it and put those
figures in as `--spec` and `--target` rows.

Do **not** measure dimensions off the drawing yourself at this stage. The
overlay diagnoses shape; published figures fix scale; and measuring a tiled
plan by hand is where a coordinator misread the tile key, dropped the two
tiles holding the wing panels, and had the airframe reconstructed from its
assembly jigs.

**A published DIMENSION is an input. It does not go in `--target`.** Span,
length, wheel diameter, propeller size — anything linear the manufacturer
prints — is what SETS the model's scale, and what makes the silhouette fit
identifiable at all: with span free, size trades against camera distance and
the fit goes degenerate. Put those in `--spec`, or in `--target` marked
`(given)` so the run is told to calibrate to them rather than converge on
them.

`--target` is for what the geometry must PRODUCE and no constant can be
typed as: wing area, wing loading, aspect ratio, a dry mass that comes out
of areas times areal density, CG.

Measured, on the F-16 Viper: span and length went in as derived targets, the
run built a wing, got 734 mm, solved for the tip station that makes `span()`
return the published 914 mm, and wrote 1.295 m as its last fuselage station.
The entry's headline — "0.39%, all airframe targets inside tolerance" — was
the model being compared with itself, and the only real check in it, the
overlay, was not what the number measured. Rule 44 exists to catch a derived
target typed into the model, and it did not fire: the run had typed the
half-span, 0.456.

### Check the assumptions prompt against the plan

The other half, and the one that needs nothing built. The prompt is already a
list of every number the run made up, shown to the only party holding the
plan, at the cheapest moment to change one — it fires **before `_model.py` is
written**, so a correction costs about one probe, not a re-render.

```
ASSUMPTIONS — confirm, correct a value, or reject one
  1. Wing taper ratio: 0.704
  2. Fuselage cross-sections: from photographs
```

When a row is a **property of the real aircraft** — a chord, a cut area, a
component mass — and you hold the plan, *check it before accepting*. Correct
with `nb answer <nb> <run-id> "1: 0.85"`. Rows that are **modelling choices**
— a stand-in airfoil, a neglected fairing — are the run's to make; judge the
cost, not the value. The run marks which is which in each row's reason.

**Accepting a number you could have checked is how the taper ratio got in.**

**Read the declarations as a defect report on YOUR inputs.** Every `why`
naming something absent is the run telling you what you failed to supply:

```
why: "plan tiles 9-12 omitted; inferred from jigs G1, G2"
```

That line was the wing. The tiles holding the wing panels had been left out
of the sheet handed to the run, it said so at the prompt, and it was read
past -- so the airframe was reconstructed from the wing's assembly jigs. The
habit costs nothing and catches the class of error no rule can: the thing
you did not give it.
Enter accepts everything, and an unanswered prompt accepts everything after it
times out — the wait scales with batch size, but it is still a clock.

Where you already know a value, pre-empt it with `--answers` so the question
never costs a round trip at all.

## When a run goes wrong

- `nb stop <nb> <run-id> "why"` — cooperative, frees a run blocked on a
  question at once, reverts nothing.
- `nb resume <nb> <run-id> [--accept-refactor]` — picks up a run that timed out
  or died with work on disk. Refuses one already committed.
- `nb clean <nb> <run-id> --yes` — drops a spent run. Dry run without `--yes`,
  and it refuses a run whose chapter is dirty.

## Reference

- `nb/README.md` — the system and why it is shaped this way. Read before
  arguing with it.
- `nb/system_instruction.md` — what the run itself is told. Read to predict
  what it will do.
- `uv run --group nb python -m nb --help` — the commands.
