"""
What the model is told, and when.

ONE CONVERSATION, two briefs. The run used to be two processes' worth of
conversation with `proposal.json` between them, and the write half opened with
a 200-line brief as its first user turn -- read in the abstract, by a model
that had just been handed a JSON document and no history. Now the same text
arrives from `open_entry`, at the moment probing stops and writing starts, with
the probe that produced the answer still above it.

They live here rather than beside either phase because `tools/interact.py`
returns the write brief as `open_entry`'s result and `phases/run.py` sends the
opening one. A module either of them can import is the way to keep that from
being a cycle.
"""

ROUTING_FREE = """\
Pick the chapter from what is above, and OPEN IT with `open_chapter` before you
write anything. If two look plausible, `probe` is how you tell them apart --
load one and look at the names it defines. That is one turn; reading files to
infer it is many."""

# Pinned by `--chapter`. Routing to an EXISTING chapter is a coordinator's
# instruction, not a finding -- it costs probe turns to rediscover and getting
# it wrong answers about a different aircraft. Creating a chapter is a
# different decision and stays the user's, at `open_chapter`.
ROUTING_PINNED = """\
The chapter is already decided: **{chapter}**. `open_chapter` it, probe it,
write into it, and do not route elsewhere. If the question genuinely does not
belong there, say so in the entry's rationale rather than moving it."""

BRIEF = """\
The question:

    {question}

**Everything about this notebook is already in front of you.** Every chapter's
`index.qmd` is quoted above, in full, along with every `_analysis.py` signature
and every entry that already exists with the answer it reached. Do not go
looking for what you have already been given -- re-reading an index.qmd, listing
directories to see which chapters exist, or grepping for a term costs turns and
tells you nothing new.

{routing}

Then probe for the answer. `probe` takes Python with the chapter already loaded
and the solve budget already armed: do not import the chapter, and do not use it
to explore the filesystem. `chapter` is required -- the wrong one silently
answers about a different aircraft. End your probes with `aero_report()`.

`bash` is an escape hatch for when something breaks, not a way to look around.
Git archaeology is almost never the answer to a design question.

# The three calls that move the run forward

    open_chapter   which aircraft this is about. FIRST -- nothing may be
                   written until it has been called, and a new one stops the
                   run for the user's approval.
    declare_input  one input, the moment you assume or decide it. Not a list
                   you fill in at the end: four of eight recorded runs reached
                   the end having declared nothing at all.
    open_entry     probing is over, this is the question. It allocates the
                   filename, puts your assumptions to the user, and hands back
                   the instructions for writing.

`ask_specified` is the fourth, and it is not on that list because it has no
place in the sequence: call it the moment you hit an input where a different
answer would change WHAT IS BEING BUILT. Do not save it.

Write nothing into the notebook before `open_entry`. Until then you are
deciding what to write, and a write to anything but this chapter's own files is
refused -- scratch code is `probe`, which runs in the run directory and leaves
nothing behind.

ONE question, one entry. If the ask really contains several distinct questions,
answer the first and say at the end what the others are, for the human to ask
separately.

# How to spend your turns

You have {max_turns} for the whole run -- probing AND writing. A well-run
question uses five or six to reach `open_entry`: pick the chapter, probe for
the answer, probe once more to check it, declare what you assumed, open the
entry. Spending twenty on orientation is the failure mode this brief exists to
prevent.

Before your first call, decide two things and say them in one sentence: which
chapter, and what you are going to compute. Then do that.

Reading existing entries tells you what was already answered, not how to answer
this. You have every entry's title and result above; that is enough to know
whether you are repeating one. Open an entry only to link it (rule 10) or to
check a number you think you are contradicting.

If a probe errors, read the traceback and fix the probe. Do not go looking
through the notebook for why -- the traceback already says.
"""

# Returned by `open_entry`, as its result. It is the same text the write phase
# used to open with, minus the parts that only made sense across a process
# boundary: there is no proposal to quote, because the conversation above IS
# the proposal, and no "the probe that produced this is gone", because it is
# not.
WRITE = """\
The entry is open. Write it at `{chapter}/{stem}.qmd`.

{inputs}

1. Use `write_file` for the initial version, then `edit_file` for every change
   after that. The entry is the ONLY file you create: `index.qmd`, `_model.py`
   and `_analysis.py` already exist, scaffolded, so `edit_file` them. A
   `write_file` over `index.qmd` silently drops the `## The model` block it
   ships with, which is the only place a reader sees the aircraft (rule 30).
   Its FIRST code cell must open with exactly these four lines (rule 28):

       ENTRY_CEILING = {ceiling}   # s for this render, granted by the user
       SOLVE_BUDGET = {solve}     # s for any one solve
       PROBE_POOL = {pool}        # s granted for the probe
       PROBE_SPENT = {spent}      # s the probe actually used

   Your probes cost {cost} s of solving, timed rather than estimated -- size
   SOLVE_BUDGET from that. A 0.0 means you ran no solves at all, so it tells
   you nothing about what this entry will cost; it does not mean free.

   ENTRY_CEILING is not yours to choose -- it is what the user granted at the
   prompt, the commit is refused if you change it, and it is the execution time
   the render is killed at, directly and with no slack. SOLVE_BUDGET is yours:
   pick what one solve needs, knowing it cannot outlive the render that
   contains it. `footer()` prints all four at the foot of the page, so they do
   NOT go in the `## Specified` callout -- that callout is for what the DESIGN
   was committed to, and budgets in it crowd out the thing it exists for
   (rule 18).

   OMIT a callout that would be empty. A box containing the word "None." is
   furniture: it takes a heading and four lines to say that nothing happened,
   and a reader scanning for what was assumed has to read it to find that out.
   No Specified inputs and no Assumptions means neither callout appears.
   If the work genuinely cannot fit, ask for more with `ask_specified` rather
   than writing a different number.
2. Its code must recompute the answer, not restate it. Every number in prose is
   an inline `{{python}}` expression, never typed out (rule 1).
3. Call `lint` with chapter `{chapter}` and fix what it reports. Each message
   names its own fix. Lint runs again after you stop regardless, so there is
   nothing to gain by stopping early.
4. If your entry repeats three or more consecutive code lines from a sibling
   (rule 2), promote them to `{chapter}/_analysis.py` and call from there --
   change only YOUR entry, never the earlier one -- then pass the promoted
   function to `footer(...)` (rule 13).
5. The vehicle lives in `{chapter}/_model.py`, never in the entry cell (rule
   19). If that file is still the bare scaffold, fill it: the aircraft, its
   operating conditions, its derived quantities. A parametric vehicle is a
   FUNCTION there taking the design variables and returning the `Airplane`;
   the entry calls it.

   HOW THE CHAPTER COMPOSES, because nothing else will tell you and a brand new
   chapter has no sibling to copy: `_model.qmd` EXECS both `_model.py` and
   `_analysis.py` into the page namespace. Every name in them is already in
   scope -- in your entry cell, and in each other. They are not modules and are
   not importable; `from _analysis import solve_it` raises ModuleNotFoundError
   at render and is rule 29. Call the name directly.

   A number taken from ANOTHER chapter is assigned in your code cell with a
   comment naming the entry it came from, and your prose names and links that
   entry: [its title](YYYY-MM-DD-NN-slug.qmd). There is no mechanism that
   recomputes it, so the link is the only trail back when someone asks where
   0.36 came from -- and the only warning anyone gets if that chapter is
   re-rendered and the number moves.

   Comments in those two files explain the MODEL, not your reasoning about
   where to put things. They are rendered verbatim by the chapter index.

   `_analysis.py` IS YOURS TO EDIT. Adding a function to it is free and is how
   a chapter grows; `_model.py` is the guarded one, and a write to it is
   refused once the chapter has entries. Rule 2 tells you to promote repeated
   code INTO _analysis.py -- it has been read backwards, as a ban on touching
   it, which leaves each entry carrying its own copy of the same workaround.

   If you EDIT a function that was already in either file -- as opposed to
   adding a new one -- call `declare_refactor` with one line saying what
   changed and why. Editing one means every sibling entry that reaches it gets
   re-solved to prove its answers held, and the user decides whether to accept
   that; they are shown your line beside the diff. Adding a function needs
   nothing, which is the cheaper path when it is available.

6. A helper that solves takes `verbose=False` and passes it to `opti.solve()`
   (rule 23). IPOPT prints a sixty-line convergence table otherwise, and an
   entry that publishes one has buried its answer under the working. Keep it a
   PARAMETER rather than hard-coding False, so a probe can still turn it on.

7. Anything true of EVERY entry in `{chapter}` belongs to the CHAPTER, not to
   your entry -- the section, the objective, the fixed dimensions, what is left
   out. Your entry keeps what THIS question produced. If the index still holds
   template placeholders, fill them (rule 24).

   The chapter's Specified and Assumed items live in
   `{chapter}/_inputs.yml`, as `- <id>: <text>` under `specified:` and
   `assumed:`. The index RENDERS them; it does not contain them. Do not write
   those callouts into index.qmd -- rule 39 refuses it, because an item in both
   places is on the page twice. If this chapter replaces something an earlier
   chapter declared, name it in `{chapter}/_fork.yml` under `overwrites:` as
   `NN-name/their-id`. It renders on THIS chapter's page as "Overwritten
   from …", listing the OLD item only — what replaced it is your own
   `_inputs.yml`, so do not restate it. The chapter you overwrote keeps its own
   items, because they are still true under it. Your ENTRY's own callouts are
   still markdown, written in the entry.

   Attribute each item to where it actually came from. "Asked of the user,
   {today}:" covers ONLY what was put to them and answered -- which includes
   any `ask_specified` answer from this run, and that answer belongs in a
   Specified callout, because it is usually the reason the chapter exists at
   all. Commitments inherited from an earlier chapter, or read out of the
   question, are stated without a claim that anyone was asked.

8. Interesting things you were NOT asked about go to the human at the end of
   the run, in your final message. They do not go in the entry: an entry
   answers the question asked and stops.

`probe` IS STILL AVAILABLE, and it is how you try something out. It runs your
Python in the run directory with `{chapter}` already loaded, prints what you
ask it to, and writes nothing into the notebook. Never write a scratch file
into the notebook -- a write to anything but this chapter's own files is
refused. What is left of the probe pool is {left} s.

Today is {today}, so the entry stem is already dated for you. Stop when lint is
clean; rendering and committing are handled after you finish.
"""

# `nb resume`, which is now only the crash path and the two approvals. It gets
# no conversation -- nothing persists one across a process boundary -- so it
# gets the entry on disk plus what the run recorded about itself. For the
# common case, entry written and lint clean, this is never sent at all: the
# loop is skipped entirely.
RESUME = """\
This run is being RESUMED. Its entry is already on disk at
`{chapter}/{stem}.qmd` -- you wrote it in an earlier process, and that
conversation is gone.

The question was:

    {question}

Read the entry first; it is the record of what you decided. Then fix what is
below and stop. Do not rewrite what is already there, and do not start a
different entry: the filename is allocated and the chapter is claimed.

{why}
"""
