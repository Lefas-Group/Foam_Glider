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

## Read the programme before asking

**Never ask what has been answered.** Two read-only views:

```bash
git log --format="%h %s" -- <notebook>/chapters/     # every question, newest first
uv run --group nb python -c "import sys; sys.path.insert(0,'nb/vendor')
from nb.config import Notebook; from nb import manifest
print(manifest.build(Notebook('<notebook>')))"       # …with each answer
```

The manifest is what the run itself is shown, so it is the same picture the
agent will have.

## Ask

```bash
uv run --group nb python -m nb ask <notebook> \
  --chapter NN-name "<one question ending in ?>" \
  --pool 200 --ceiling 90 --quiet
```

- **`--quiet` is not optional for you.** Without it the parent process runs a
  blocking TUI. With it, the parent prints `run <run-id>`, detaches and exits.
  **Capture that run id** — you need it to answer.
- **`--chapter` is required; routing is yours.** A chapter is a vehicle: pick
  the one whose `_model.py` the question is about. Omitted, nothing starts.
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
