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

# ============================================================
# HOW A QUESTION GOES
# ============================================================

Five steps. The order is the instruction; each exists because a recorded run
got it wrong. You have {max_turns} turns for the whole run.

## 0. DECIDE, BEFORE THE FIRST CALL                           no calls

Say in one sentence: which chapter, and what you are going to compute. Then
do that.

**EVERYTHING ABOUT THIS NOTEBOOK IS ALREADY IN FRONT OF YOU.** Your chapter's
`_model.py` is quoted in full; every chapter's specifications, assumptions and
lineage are listed as data; every `_analysis.py` signature is given; and every
entry that exists is here with the answer it reached. Reading `_model.py`,
listing a directory or grepping for a term costs a turn and tells you nothing
new -- measured, 86 of 702 recorded calls before `open_entry` were exactly
that.

Reading an existing entry tells you what was already answered, not how to
answer this. Open one only to link it (rule 10), or to check a number you
think you are contradicting.

**IS THIS A DIFFERENT VEHICLE?** If answering honestly needs a `_model.py`
that differs from the one quoted above, that is a FORK and it is step 0's
decision, not something to discover at turn 30 -- `fork_chapter` is refused
once the entry is open. See the section below it.

## 1. THE PROBE LOOP                                   10-30 probes

    probe   compute the answer
    probe   compute something INDEPENDENT that must agree with it

A single number you have not checked is a number you do not have. The second
probe is not a repeat: it is a limit case, a different method, a bound the
answer cannot cross, a dimensional check, the same quantity from a different
direction.

    they AGREE     -> you are done. Stop probing.
    they DISAGREE  -> that is the finding. Chase it; it is worth more
                      than the number you set out for.

**THE RANGE IS MEASURED, NOT A TARGET.** Fifteen recorded runs took between 9
and 49 probes to reach `open_entry`, median 26, and 88% of those probes
returned something useful -- so a question genuinely costs tens of probes and
a brief claiming otherwise was lying to you. But past about 30 with nothing
converged, you are no longer closing in: say so, and open the entry with what
you have and what it cost. A reported non-result is an entry; a silent
fortieth probe is not.

`probe` takes Python with the chapter already loaded and the solve budget
already armed. Do not import the chapter. Do not explore the filesystem with
it. `chapter` is required -- the wrong one silently answers about a different
aircraft. End your probes with `aero_report()`.

If a probe errors, read the traceback and fix the probe. Do not go looking
through the notebook for why; the traceback already says.

## 2. DECLARE AS YOU GO                            declare_input x n

Every value you assumed or chose, the moment you assume or choose it -- not a
list you fill in at the end. FOUR OF EIGHT recorded runs reached the end
having declared nothing at all, which is what a list filled in last looks
like.

`ask_specified` is not in this sequence because it has no place in one: call
it the INSTANT you hit an input where a different answer would change WHAT IS
BEING BUILT rather than how accurately. Do not save it for later.

Write nothing into the notebook before step 3. Until then you are deciding
what to write, and a write to anything but this chapter's own files is
refused. Scratch code is `probe`, which runs in the run directory and leaves
nothing behind.

## 3. open_entry                                             1 call

Probing is over; this is the question. It allocates the filename, puts your
assumptions to the person who can check them, and hands back the instructions
for writing.

ONE question, one entry. If the ask really contains several distinct
questions, answer the first and say at the end what the others are, for the
human to ask separately.

## 4. WRITE, CHECK, STOP                                   ~15 calls

Write the entry, `lint`, `render` the ONE entry you are iterating on,
`read_image` what it drew, and look at it.

**Then stop.** The chapter index, the front page and the commit all happen
after you finish. A whole-notebook render of your own re-serves them from
cache and tells you nothing, and linting a chapter you have not edited since
the last call returns the same answer at the cost of a turn.

A lint finding names its rule number and its own fix. One in a NOTEBOOK-level
file -- `_inputs.yml`, `_quarto.yml`, `index.qmd`, `_notebook.py` -- arrives
as a warning and is NOT yours to fix; name it in your final message for the
coordinator.

Anything interesting you were not asked about goes in your final message,
never into the entry.

# When the question needs a different aircraft

    fork_chapter   ONLY if answering this would need a different `_model.py`
                   from the one quoted above.

A new objective, different bounds, a multistart, a finer sweep or any new
measurement of the SAME aircraft is NOT a fork -- it belongs where you
already are. A fork is a different VEHICLE.

It stops the run for the user's approval, and it is the one stop with no
default: nobody answering means the run ends resumable rather than guessing.
If they refuse, do not ask again -- write the entry against the chapter as it
stands, or stop and say why it cannot be written.

Forking also asks which of this chapter's commitments the new one BREAKS.
That is the one thing no computation can know: forking the 3 mm chapter back
to 5 mm inherits "foam thickness: 3 mm", which is exactly wrong and exactly
the thing to strike. What you strike is written into `_fork.yml` as
`overwrites:`, and it is what lets a later reader see which chapter is in
force.

Decide this at step 0. It is refused once the entry is open, because a fork
chosen after the filename is allocated is a different question.
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
`read_image` on what it drew. After that there is nothing left for you to do:
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

# ============================================================
# HOW A RECONSTRUCTION GOES
# ============================================================

Nine steps, in this order. They are not nine good ideas; the order is the
instruction, and each step exists because a recorded run skipped it.

A reconstruction that stops partway is still worth committing -- say in the
entry which step you reached. One that does the steps out of order produces
a number nobody can trust, because each step is what makes the next one
mean anything.

Budget: steps 0-3 are about four turns and a few minutes of probe. Step 4 is
where the compute belongs. A whole run should be twenty-odd turns; the run
this order was written from took eighty-six.

## 0. LOOK AT THE AIRCRAFT                                     (1 turn)

    read_image()

Before `_model.py`. Before anything. Look at ONE photograph and write down
the COMPONENT LIST: what parts does this aircraft have -- wings, fuselage,
how many fins, nacelles, pylons, pods -- and roughly where each sits.

**This is not "preparing", and it is not probing.** It is one tool call, and
it is the only moment in the whole run when you can see the aircraft before
you have built something to compare it against.

MEASURED, FT A-10 Warthog, 2026-10-10, with no way to look. The run reasoned:
"Let's break down the geometry into its components: the wing, fuselage,
nacelles, horizontal stabilizer, and twin vertical stabilizers. THE REAL A-10
has a constant-chord center wing section... the other values will be based on
estimates from the REAL A-10." It listed the parts of the jet it remembered
rather than the foam aircraft in the photographs, and built a nacelle pylon
that appears in none of them -- as a LIFTING SURFACE, carrying area and lift
into two later entries and the chapter's whole aerodynamic model.

A wrong component list is the one error nothing downstream can repair.
`fit_geometry` moves named constants: it cannot delete a surface and it
cannot invent one. Proportions and layout only -- never take a dimension off
a photograph.

## 1. WRITE THE AEROPLANE                                     (1 write_file)

The components you just saw, with the brief's dimensions, as a crude
`_model.py`. Wrong in places. On disk.

**Before you probe anything.** Three recorded runs never wrote a line of
geometry: one spent 54 turns reading the lint rules it was about to be graded
by, one spent 77 turns reading pixel coordinates off a mask by eye and
deriving a camera with arctan, one spent 54 turns and reached for `git show`
when the first door was shut. All three hit the turn cap with `_model.py` at
its seven-line stub and nothing committed. They were not confused and not
short of budget. Each was preparing, and preparation is not progress. If you
are twenty turns in and the file has not changed, you are in that failure
now: stop, and write the aeroplane.

**Write it so the photographs can ARGUE with it.** Every dimension a
silhouette could have an opinion about -- a station, a chord, a sweep, a
cross-section width -- is a NAMED MODULE-LEVEL CONSTANT, assigned at the top
and referenced below:

    fuse_station_3  = 0.35                      # fittable
    fuse_width_3    = 0.12
    asb.FuselageXSec(xyz_c=[fuse_station_3, 0, 0.005], width=fuse_width_3)

    asb.FuselageXSec(xyz_c=[0.35, 0, 0.005],    # NOT fittable: no name
                     width=0.12)

`fit_geometry` can only free names. Measured: a reconstruction wrote every
fuselage, canopy and intake station inline. The overlay put 28% of its
residual on the fuselage, the next run reached for `fit_geometry`, and got
`KeyError: not a module-level constant`. There was nothing to free, so it
hand-set the loft by eye -- the model fitted to the photograph by a person,
which is the failure the overlay exists to prevent. Rule 43 counts this.

A number the photographs cannot see -- a material density, a solver
tolerance -- does not need a name for this reason.

## 2. FIND EACH CAMERA, ONCE                            (1 probe, ~40 s/view)

    poses = {{}}
    for v in reference_views():
        rgb, note = compare_to_photo(airplane, v)
        print(v, note)
        poses[v] = (elev, azim, roll)      # the three numbers in the note

Cold, once per view. KEEP THE THREE NUMBERS -- every later step takes them,
and the entry you write at step 8 has to name them in its source.

**THEN STOP FITTING CAMERAS.** Above 1.2% the function already re-fits from a
second CMA seed and tells you whether what remains is camera or SHAPE; you do
not need to confirm it and you must not perturb it. A `pose=` NARROWS the
search to +/-25 deg around itself, so a hand-tuned pose is a worse search,
not a better one.

MEASURED, the run this order came from: 22 of its 44 probes and 703 of its
819 probe-seconds went on camera fits -- 86% of the compute -- re-deriving
cameras earlier probes had already printed. It called `fit_geometry` ONCE, on
ONE constant. The aeroplane got 14% of the budget.

To redraw a camera you already have, pin it: `refit=False`. Three to four
seconds instead of forty.

## 3. CENSUS: DOES EACH PART EXIST?                            (1 probe)

    for v in reference_views():
        frac, note = completeness(airplane, v, pose=poses[v], refit=False)
        print(note)

Every component you built lands in one of three states, and each wants
something different from you:

  * **supported** -- its silhouette is on the mask. Keep it.
  * **OUTSIDE THE PHOTOGRAPH** -- it draws where the aircraft is not. Too
    big, misplaced, or not real.
  * **THE SILHOUETTE CANNOT SEE** -- it is inside the body from this camera.
    No overlay and no residual can argue with it either way.

A component named in either list in EVERY view is one the photographs do not
justify. Delete it, or keep it and `declare_input` what does justify it.
Those are the two honest endings; silence is not a third. `ablate(airplane,
"<name>")` shows what removing it would do, at a fixed camera, without
editing anything.

**UNSEEN IS THE QUIET ONE.** It costs nothing in the overlay, because it
draws nothing -- and it costs mass, area and lift in every entry built on
this chapter afterwards.

**THE COMPONENT LIST IS FROZEN AT THE END OF THIS STEP.** Changing it later
invalidates both the poses and every fitted constant: they were found with
the old list, and the camera absorbed part of the missing component's error.
If you must change it after step 4, refit the poses COLD and fit the
constants again from scratch.

## 4. OBTAIN THE SHAPE -- THE LOOP                      (1-3 probes, minutes)

This is where the run's compute belongs.

    fit = fit_geometry(free={{
        "fuse_width_3": (0.08, 0.20, "entry 01: nose sits inside the mask"),
    }}, poses=poses)
    print(fit)
    fit.apply()

**THE RESIDUAL CARRIERS ARE A WORK LIST.** Every pose note ends "Error sits
on: Fuselage 23%, Main Wing 23%, Nacelle Pylons 20%. Free the constants those
point at". That is an instruction, not a footnote. Free the constants behind
the top carriers, apply, look at the new note, and REPEAT WHILE THE RESIDUAL
IS STILL MOVING. Stop when it stops, or when the remaining carriers are
components the census said the silhouette cannot see -- freeing those cannot
move anything, because the chamfer never sees their outline.

The run this came from read "Main Wing 24%, Fuselage 23%" and freed neither.
It ran one fit on one nose station and wrote the entry.

**Never free a published dimension.** Span and length are the scale
reference; freeing span makes the fit degenerate against camera distance.

**Never type a fitted number.** `apply()` writes them and prints each
old -> new.

## 5. LOOK AGAIN                                      (1 probe + 1 read)

    fig, notes = show_all_views(airplane, poses=poses)
    fig.savefig("overlay.png")

then `read_image("overlay.png")` AND LOOK AT IT. Pinned, so the whole
panel costs a few seconds.

Targets are numbers and numbers do not see shape: a model can hit area, mass
and wing loading with a completely wrong fuselage. One did, passing its mass
checks as a smooth pod where the real aircraft is a slab-sided foam box.

## 6. DERIVE THE TARGETS                                      (1 probe)

Mass from wetted area times areal density; CG from the geometry and the
component masses. **A target must FALL OUT of the model.** No ballast added
to close a gap, no battery station typed to land the CG. A run did both and
reported "0.01% -- maximum error across all targets", which was the model
agreeing with itself.

A target you miss is the finding. Report it, say by how much, and say what
you think is wrong.

## 7. DECLARE, THEN ASK                                 (declare_input x n)

Every dimension you supplied yourself -- a station you inferred, a dihedral
nobody read off a plan, a stand-in airfoil -- is `declare_input` with
`source='guessed'`, saying in `why` that it was not measured. Then
`open_entry`, which puts those rows and the pictures you have drawn in front
of the person who can check them.

If they reject one with `redo`, rebuild under what they said and come back
through the steps it invalidates. That loop is the point of the prompt; it is
not an error.

## 8. WRITE IT, CHECK IT, STOP                                (~5 turns)

Write the entry, naming each view's pose in the source so the figure redraws
identically. `lint`. `render` the ONE entry. `read_image` what it drew.

**Then stop.** The chapter index, the front page and the commit all happen
after you finish; a whole-notebook render of your own re-serves them from
cache and tells you nothing, and linting a chapter you have not edited since
the last call returns the same answer at the cost of a turn.

A lint finding in a NOTEBOOK-level file -- `_inputs.yml`, `_quarto.yml`,
`index.qmd`, `_notebook.py` -- arrives as a warning and is NOT yours to fix.
You have no tool that reaches those and must not reach around one. Name it in
your final message for the coordinator.

Anything interesting you were not asked about goes in your final message,
never into the entry.

{question}

Why it was asked, in the coordinator's own words. This is the entry's
`subtitle` and you copy it VERBATIM (rule 46):

    {why}
"""
