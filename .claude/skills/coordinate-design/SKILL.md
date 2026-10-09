---
name: coordinate-design
description: Coordinates an aircraft design programme in the `nb` notebook — turns a design direction into a sequence of questions, answers what the runs ask, and picks the next question from what they found. Use when the user gives a direction rather than a single question, or asks to keep the programme moving.
when_to_use: The user describes what they want designed or explored rather than asking one question; says "keep going" or "run the next few"; or wants a new aircraft set up.
allowed-tools: Bash(uv run --group nb python -m nb *) Bash(git log *) Read Glob Grep
---

Now: !`date "+%Y-%m-%d %H:%M"`
Notebooks: !`ls -d */_quarto.yml 2>/dev/null | cut -d/ -f1 | tr '\n' ' '`

## The doctrine is NOT in this file

The `nb coordinate` agent does this same job from the same CLI, and two copies
of a lesson learned from a wrong taper ratio is one copy that will still be
wrong next year. So everything that is true of COORDINATING -- rather than of
this harness -- lives in `nb/references/coordinator/` and both of you read it.

**Read it before you start. One command, not five files:**

```bash
uv run --group nb python -m nb doctrine --coordinate   # before the first `nb ask`
uv run --group nb python -m nb doctrine --setup        # before `nb new`
uv run --group nb python -m nb doctrine --list         # what each page is for
```

It covers: what you hold and what a run holds · never asking what has been
answered · `--why` as your sentence on the page · choosing the next question
from the finding · every kind of question a run asks and how to reply · the
assumptions prompt as a defect report on your inputs · Specified inputs ·
researching an aircraft AND the materials its targets rest on · `spec` vs
`target` vs `assume` · angular spread · why the overlay is the only real check
on a mask.

**What stays here is the harness**: the board window, backgrounding a blocking
wait, the ten-minute shell cap, and the cwd trap. Those are true of Claude Code
and of nothing else.

If you change doctrine, change it there. Preflight — which runs before every
`nb ask` and `nb reconstruct` — fails on a sentence duplicated between this
file and a doctrine page.

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

## Ask

```bash
uv run --group nb python -m nb ask <notebook> \
  --chapter NN-name "<one question ending in ?>" \
  --why "<why this question, now>" \
  --pool 200 --ceiling 90 --quiet
```

What `--chapter` and `--why` are FOR is doctrine, and it is in
`nb doctrine --coordinate`. `--why` in particular has a 40-word cap and
renders verbatim as the entry's subtitle; read the page before writing one.
What follows is only how this command behaves from a Claude Code shell.

- **`--quiet` is not optional for you.** Without it the parent runs a blocking
  TUI. With it, the parent prints `run <run-id>`, detaches and exits.
  **Capture that run id** — you need it to answer.
- **A watcher window opens for each run**, carrying its transcript from the
  first line and closing itself a few seconds after the run ends. You do not
  ask for it and do not need to close it. `--no-watch` suppresses it, and stops
  the run sending the open tab to its entry.
- **The question is ONE quoted argument.** It must not start with `--` or end
  with `.json`; the parser drops those.
- **The exit code only tells you the LAUNCH worked.** `--quiet` forks and
  returns 0 as soon as the run is detached; everything after that — the
  chapter lock included — is in `run.json`'s `outcome`. A non-zero exit
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

## When a run goes wrong

- `nb stop <nb> <run-id> "why"` — cooperative, frees a run blocked on a
  question at once, reverts nothing.
- `nb resume <nb> <run-id> [--accept-refactor]` — picks up a run that timed out
  or died with work on disk. Refuses one already committed.
- `nb clean <nb> <run-id> --yes` — drops a spent run. Dry run without `--yes`,
  and it refuses a run whose chapter is dirty.
