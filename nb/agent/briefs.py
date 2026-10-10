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

BRIEF = """\
The question:

    {question}

Why it was asked, in the coordinator's own words:

    {why}

That sentence is the entry's `subtitle` and you copy it VERBATIM (rule 46).
It is a record of somebody else's decision, so rewriting it into your own
register destroys the thing it is for. If it is wrong or over its budget, say
so in your final message and write it anyway.

You are in **chapters/{chapter}**. It is settled, it is claimed for this run,
and its model is quoted above in full. Probe it and write into it.

**Everything about this notebook is already in front of you.** Your chapter's
`_model.py` is quoted in full; every chapter's specifications, assumptions and
lineage are listed as data; every `_analysis.py` signature is given; and every
entry that exists is there with the answer it reached. Do not go looking for
what you have already been given -- reading `_model.py`, listing directories,
or grepping for a term costs turns and tells you nothing new.

Probe for the answer. `probe` takes Python with the chapter already loaded
and the solve budget already armed: do not import the chapter, and do not use it
to explore the filesystem. `chapter` is required -- the wrong one silently
answers about a different aircraft. End your probes with `aero_report()`.

# The calls that move the run forward

    declare_input  one input, the moment you assume or decide it. Not a list
                   you fill in at the end: four of eight recorded runs reached
                   the end having declared nothing at all.
    open_entry     probing is over, this is the question. It allocates the
                   filename, puts your assumptions to the user, and hands back
                   the instructions for writing.
    fork_chapter   ONLY if answering this would need a different `_model.py`
                   from the one quoted above. It stops the run for the user's
                   approval. A new objective, different bounds, a multistart,
                   a finer sweep or any new measurement of the SAME aircraft
                   is not a fork -- it belongs where you already are.

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
question uses four or five to reach `open_entry`: probe for the answer, probe
once more to check it, declare what you assumed, open the entry. Spending twenty on orientation is the failure mode this brief exists to
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

FRONT MATTER IS THE TITLE AND THE SUBTITLE, and the subtitle is the
justification quoted to you above — copied verbatim, never reworded (rule 46):

    ---
    title: "{title}"
    subtitle: "{why}"
    ---

THE FOOTER CELL CARRIES `method=` (rule 47) — one or two sentences, 60 words at
most, on what your code COMPUTES and which shared helpers did it. It renders in
its own collapsed box directly above the source `footer()` already shows, so it
costs the answer none of its words and a reader decides from it whether to
unfold the code. A plain string: it describes the method, not the result, so
never build it from the numbers.

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

ADDING a function to `_model.py` or `_analysis.py` is free — that is how a
chapter grows, and it is what rule 2 means by promoting repeated code. CHANGING
the body of one that was already there is a refactor: every sibling entry that
reaches it gets re-solved to prove its answers held, so the run stops and asks
the user the moment you do it. Call `declare_refactor` with one line saying what
changed BEFORE you make the edit — they are shown it beside the decision, and
"(nothing — declare_refactor was not called)" is a poor case to put to someone
being asked for minutes of solving.

A number taken from ANOTHER chapter is assigned in your code cell with a comment
naming the entry it came from, and your prose links that entry:
[its title](YYYY-MM-DD-NN-slug.qmd). Nothing recomputes it, so the link is the
only trail back when someone asks where 0.36 came from.

Under New user specifications go ONLY inputs that were put to a person and
answered — which includes any `ask_specified` answer from this run. Anything
inherited from an earlier chapter, or read out of the question, is stated
without a claim that anyone was asked. Write NO lead-in line above the
numbered items of either callout: the heading already says what the list is,
and a date there dates the asking rather than the entry, which is dated
already.

Anything interesting you were NOT asked about goes to the human in your final
message, never into the entry.

`probe` is still available and is how you try something out — it runs in the run
directory with `{chapter}` loaded and writes nothing here. {left} s of pool left.

Today is {today}. Call `lint` with chapter `{chapter}` and fix what it reports;
each message names its own fix.

STOP WHEN LINT IS CLEAN AND YOU HAVE LOOKED AT YOUR FIGURES. That is the whole
gate, and both halves are reached by rendering the ONE entry and calling
`read_figure` on what it drew. After that there is nothing left for you to do:
the chapter index, the front page and the commit are all done for you once you
finish, and a whole-notebook `render` of your own re-serves them from cache and
tells you nothing. Nor does linting a chapter you have not edited since the
last call — it is the same answer and it costs a turn to hear it again.

A lint finding in a NOTEBOOK-level file — `_inputs.yml`, `_quarto.yml`,
`index.qmd` — arrives as a warning and is not yours to fix. You have no tool
that reaches those files and must not reach around one. Name it in your final
message so the coordinator can act on it, and carry on.
"""


# `nb resume`, which is now only the crash path and the two approvals. It gets
# no conversation -- nothing persists one across a process boundary -- so it
# gets the entry on disk plus what the run recorded about itself. For the
# common case, entry written and lint clean, this is never sent at all: the
# loop is skipped entirely.
RESUME = """\
This run is being RESUMED. You worked on it in an earlier process, and that
conversation is gone.

The question was:

    {question}

WHAT IS ACTUALLY ON DISK, read just now -- trust this over any expectation
about what you had finished:

{state}

The filename is allocated and the chapter is claimed, so do not start a
different entry. Fix what is below and stop; do not rewrite what is already
good.

{why}
"""


# =============================================================================
# `nb reconstruct` -- the third brief into `_execute`, after BRIEF and RESUME.
#
# Reconstruction is a DIFFERENT ACTIVITY from answering a question, and the
# ordinary contract is built for the latter: rule 5 bans a `range()` loop
# around a solve, rule 6 caps prose at 100 words, and the closing gate is
# "lint clean" rather than "targets met". Converging a model onto a published
# spec sheet is iterate-to-tolerance, so it gets its own opening brief and its
# own gate, and shares everything else.
#
# The ENTRY it writes is ordinary. A question, a hero, two visuals -- which is
# what rule 14 already allows when one of them draws the aircraft. No new
# output format and no contract exception.
# =============================================================================
RECONSTRUCT = """\
Build this chapter's vehicle, and prove it is the aircraft the brief
describes.

You are in **chapters/{chapter}**. It is claimed for this run. Write
`_model.py` so that it reproduces every TARGET row in the brief above, each
inside the tolerance it states.

**Everything about this notebook is already in front of you.** The brief, its
targets, this chapter's `_inputs.yml`, `_active.yml` and `_model.py` are all
quoted above as data. Do not go looking for what you have already been given
-- the first live reconstruct run spent seven of its eighty turns on
`list_directory`, three `search_files` globs and three reads of files that
were already in its context, and then hit the turn cap with the entry
unwritten.

{targets}

{reference}

# What you are being asked for

ONE ordinary entry, titled as a question -- "Can we reconstruct the <aircraft>
within tolerance?" -- answering it with the worst error across the targets as
the hero value. The entry carries TWO visuals, which rule 14 allows because
one of them draws the aircraft:

{aircraft_visual}
  * a chart of error against tolerance, one bar per target, so a reader sees
    at a glance which targets passed.

Report EVERY target, including the ones that passed. A target you cannot hit
is a finding, not a failure to hide: say by how much and what you think is
wrong. Never loosen a tolerance, and never adjust the model to make a CLAIM
come true -- a claim is under Assumed, it is what the programme exists to
judge, and fitting the model to one is how a notebook comes to agree with
marketing.

# Before you open the entry

**WRITE THE AEROPLANE FIRST. Before you probe anything.**

Your first probe should be the one that builds a crude `_model.py` out of the
brief's dimensions alone -- a wing, a fuselage, the stations you are confident
about -- and draws it. Not a camera fit, not a reading of the targets, not a
plan for what the model will have to satisfy. The file, on disk, wrong in
places.

Everything after that is cheaper for it existing. An overlay tells you which
station is wrong in one turn; `fit_geometry` can free a constant only once the
constant has a name; the assumptions prompt has something to show the person
holding the plan. None of that is reachable from a stub.

MEASURED, three runs on two aircraft, none of which ever wrote a line of
geometry. One spent 54 turns reading the lint rules it was about to be graded
by. One spent 77 turns probing -- 56 of them reading pixel coordinates off a
mask by eye and deriving a camera from them with arctan, which is precisely
what `compare_to_photo` does properly and what the photographs page tells you
never to do by hand. One spent 54 turns and reached for `git show` when the
first door was shut. All three hit the turn cap with `_model.py` at its
seven-line stub and nothing committed.

They were not confused and they were not short of budget. Each was preparing,
and preparation is not progress. If you are twenty turns in and the file has
not changed, you are in that failure now: stop, and write the aeroplane.

**DRAW THE AIRCRAFT.** The assumptions prompt lists every picture this run
has made -- newest first, by path -- to the person who holds the plan, and it
is the only chance they get to catch a shape error while it is still cheap,
before `_model.py` is written into the entry. A run that has drawn nothing
puts `NO PICTURE` in front of them and asks them to approve a shape they
cannot see.

There is no filename to get right: `fig.savefig("overlay.png")` in a probe
lands in the run directory, which is where this reads from. Save the picture
that ANSWERS THE QUESTION. An overlay on a photograph beats a three-view,
because it compares the model against the aircraft rather than against the
reader's memory of it -- unless the note says DOUBTFUL or there is no
photograph at all, and then the three-view is the only honest thing to show.

Targets are numbers, and numbers do not see shape: a model can hit area, mass
and wing loading with a completely wrong fuselage. That has happened here --
a reconstruction passed its mass checks as a smooth pod where the real
aircraft is a slab-sided foam box. So the picture comes first, and the
numbers after.

**EVERY COMPONENT YOU BUILD MUST BE IN A PHOTOGRAPH.** Before you open the
entry, run `completeness` on each view and read the two lists it prints
beside the gaps: what you drew OUTSIDE the photograph, and what the
silhouette CANNOT SEE because it sits inside the body. A component named in
either list, in every view, is one the photographs do not justify. Delete it,
or keep it and `declare_input` what does justify it -- those are the two
honest endings and silence is not a third.

An unseen component is the quieter failure and the one that survives. It
costs nothing in the overlay, because it draws nothing; it costs mass, area
and -- if you built it as an `asb.Wing` -- LIFT, in every entry that comes
after. Measured here: an A-10 reconstruction carried a 160 x 104 mm plate
between fuselage and nacelle, invisible in all three photographs, as a
lifting surface. It passed the overlay, the assumptions prompt and two
performance questions built on top of it.

`ablate(airplane, "<name>")` answers "would the silhouettes rather not have
this?" in one probe, at a fixed camera, without editing anything.

**The residual carriers in a pose note are a WORK LIST.** "Error sits on:
Fuselage 23%, Main Wing 23%" names the components whose constants
`fit_geometry` should free next, in that order. It is not a footnote on a
number you have already accepted. A reconstruction that reads that line,
frees ONE constant somewhere else, and writes the entry has used the
photographs to confirm the model rather than to obtain it.

**Write `_model.py` so the photographs can ARGUE with it.** Every dimension
a silhouette could have an opinion about -- a station, a chord, a sweep, a
cross-section width -- is a NAMED MODULE-LEVEL CONSTANT, assigned at the top
and referenced below. `fit_geometry` can only free names, so a number written
inline is one the photographs cannot reach:

    fuse_station_3  = 0.35                      # fittable
    fuse_width_3    = 0.12
    ...
    asb.FuselageXSec(xyz_c=[fuse_station_3, 0, 0.005],
                     width=fuse_width_3, height=fuse_height_3)

    asb.FuselageXSec(xyz_c=[0.35, 0, 0.005],    # NOT fittable: no name
                     width=0.12, height=0.10)

Measured: a reconstruction wrote every fuselage, canopy and intake station as
a literal inside `asb.FuselageXSec(...)`. The overlay then put 28% of its
residual on the fuselage, the next run read that, reached for `fit_geometry`
-- and got `KeyError: not a module-level constant`. There was nothing to
free. It hand-set the loft by eye instead, which is the model being fitted to
the photograph by a person, and that is the failure the overlay exists to
prevent. Rule 43 counts this for you: a chapter fixing dozens of constants
while declaring a handful of inputs is one whose geometry is mostly
unreachable.

A number the photographs cannot see -- a material density, a solver
tolerance, a reference area -- does not need a name for this reason. Judge
by whether a silhouette could disagree with it.

**The photographs are how the geometry is OBTAINED, not only how it is
checked.** `read_reference("photographs")` is the one page on this; read it
before your first overlay. The short version: fit the camera with
`compare_to_photo`, look at the overlay, and if the residual sits above
about 1.2% after ONE reseed, the camera is converged and what is left is
shape -- which is `fit_geometry(free={{...}}, poses={{...}})`, freeing the few
`_model.py` constants a fault in the picture actually points at, seeded
with the poses you just read off the notes. Never free a published
dimension: span and length are the scale reference. A reconstruction that
hand-sets every station and uses the photographs only to confirm them has
checked the model against itself.

**Declare every dimension you had to supply yourself.** The brief gives what
was measured; everything else -- a station table you inferred, a dihedral
nobody read off the plan, a stand-in airfoil -- is `declare_input` with
`source='guessed'`, saying in `why` that it was not measured. Those rows are
what the prompt puts in front of someone who can go and check them.

If they reject one with `redo`, rebuild under what they said, render the
three-view again and open the entry again. That loop is the point of the
prompt; it is not an error.

{question}

Why it was asked, in the coordinator's own words. This is the entry's
`subtitle` and you copy it VERBATIM (rule 46):

    {why}
"""
