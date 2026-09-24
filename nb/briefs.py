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

# Returned by `open_entry`, as its result.
#
# RE-COSTED once the phases merged, and it needed it. Under the split this was
# the opening user turn of a fresh 15-turn conversation -- sent once, cheap.
# Merged, it sits in a conversation that re-sends its whole history every turn,
# so at 7,259 chars it was ~1,814 tokens paid on every turn after `open_entry`:
# about 21,800 tokens across a 25-turn run, more than the entire cached prefix.
#
# WHAT CAME OUT, on two tests:
#
#   * anything the CACHED PREFIX already says. `system_instruction.md` renders
#     at position 0 and is matched by implicit caching at a measured 67%; this
#     is re-sent uncached. A paragraph in both is paid twice, and the second
#     copy is the expensive one. The `_inputs.yml`/`_fork.yml` mechanics, the
#     empty-callout rule and the attribution guidance are all in "Entry format"
#     already.
#
#   * anything LINT CATCHES AND HANDS BACK WITH THE FIX. Rules 1, 2, 13, 19,
#     23, 24, 29, 30 and 32 each had a paragraph here teaching what their own
#     violation message says better, at the moment it matters, about the actual
#     line. Measured: first-pass violations run at 0.03 across 33 write runs,
#     so this text was insurance against something that was not happening.
#
# WHAT STAYED is per-run DATA (the path, the four literals, the measured probe
# cost, the recorded inputs) and the two things neither channel carries: how a
# chapter COMPOSES, which costs a failed render to learn, and that ENTRY_CEILING
# is not the model's to choose, which costs a refused commit.
WRITE = """\
The entry is open. Write it at `{chapter}/{stem}.qmd` — `write_file` once, then
`edit_file`. It is the ONLY file you create; `index.qmd`, `_model.py` and
`_analysis.py` are scaffolded already, so edit those.

{inputs}

Its FIRST code cell opens with exactly these four lines (rule 28):

    ENTRY_CEILING = {ceiling}   # s for this render, granted by the user
    SOLVE_BUDGET = {solve}     # s for any one solve
    PROBE_POOL = {pool}        # s granted for the probe
    PROBE_SPENT = {spent}      # s the probe actually used

Your probes cost {cost} s of solving, timed rather than estimated — size
SOLVE_BUDGET from that. A 0.0 means you ran no solves at all, so it tells you
nothing about what this entry will cost; it does not mean free. ENTRY_CEILING is
NOT yours to choose: the commit is refused if you change it, and it is the
execution time the render is killed at, with no slack. If the work genuinely
needs more, `ask_specified` for it rather than writing a different number.

HOW THE CHAPTER COMPOSES, because nothing else will tell you and a new chapter
has no sibling to copy: `_model.qmd` EXECS both `_model.py` and `_analysis.py`
into the page namespace. Every name in them is already in scope — in your entry
cell, and in each other. They are not modules and are not importable;
`from _analysis import solve_it` raises ModuleNotFoundError at render (rule 29).
Call the name directly.

`_analysis.py` IS YOURS TO EDIT, and adding a function to it is free — that is
how a chapter grows, and it is what rule 2 means by promoting repeated code.
`_model.py` is the guarded one: a write to it is refused once the chapter has
entries, and the refusal says what to do. If you EDIT a function that was
already in either file, `declare_refactor` one line saying what changed.

A number taken from ANOTHER chapter is assigned in your code cell with a comment
naming the entry it came from, and your prose links that entry:
[its title](YYYY-MM-DD-NN-slug.qmd). Nothing recomputes it, so the link is the
only trail back when someone asks where 0.36 came from.

Attribute each input to where it came from. "Asked of the user, {today}" covers
ONLY what was put to them and answered — which includes any `ask_specified`
answer from this run. Anything inherited from an earlier chapter, or read out of
the question, is stated without a claim that anyone was asked.

Anything interesting you were NOT asked about goes to the human in your final
message, never into the entry.

`probe` is still available and is how you try something out — it runs in the run
directory with `{chapter}` loaded and writes nothing here. {left} s of pool left.

Today is {today}. Call `lint` with chapter `{chapter}` and fix what it reports;
each message names its own fix. Stop when it is clean — rendering and committing
are handled after you finish.
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
