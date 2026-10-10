# Judging what a run asks you

`wait` hands you the question with its `kind`, its `name`, the seconds left
before it defaults, and a `how` field giving the exact reply syntax. Use it.

| kind | what it is | how to answer |
|---|---|---|
| `budget` | probe seconds or render seconds | a number |
| `assumptions` | every value the run made up | `""` accepts all · `1: 0.85` corrects one · `1: redo — why` sends it back |
| `inherited` | what it carries from a parent chapter | `""` keeps all · `3` or `3; 5` strikes what no longer holds |
| `stuck` | it has stopped getting anywhere | `continue`, `stop`, or advice |
| `chapter` | a new chapter it wants to create | anything approves · `no — why` sends it back |
| `refactor` | an edit to `_model.py` | anything allows · `no — why` restores it |
| `specified` | an input you may not invent | **see below** |

**Say who decided.** `by="coordinator"` when the answer is yours — a chapter
you approved, an assumption you accepted. `by="user"` only when you are
relaying what the user actually told you, because then they are the author and
the record must say so.

**The number on a proposed chapter is not yours to police.** Allocation takes
the next free number under a lock. Judge the slug, the title and what it
defines.

### The assumptions prompt is a defect report on YOUR inputs

It fires before `_model.py` is written, so a correction costs about one probe
rather than a re-render. Every reason naming something absent is the run
telling you what you failed to supply:

    why: "plan tiles 9-12 omitted; inferred from jigs G1, G2"

That line was the wing. Read the declarations before you accept them.

Rows that are **properties of the real aircraft** — a chord, a cut area, a
component mass — are checkable, and accepting one you could have checked is how
a wrong taper ratio gets in. Rows that are **modelling choices** — a stand-in
airfoil, a neglected fairing — are the run's to make; judge the cost, not the
value.

### OPEN A PICTURE BEFORE YOU ANSWER

The prompt lists every overlay the run has drawn, newest first, by path.
`read_image` one of them. This is not optional and it is not the same job as
reading the rows: **the rows are numbers and numbers do not see shape.** It is
the only moment anyone looks at the aeroplane before `_model.py` goes into an
entry that later entries will rest on.

Measured on the FT A-10 Warthog, 2026-10-10. The prompt offered four overlays
including a three-panel comparison. The reasoning for accepting ran entirely
on whether 400 g was a plausible battery; no image was opened. The model being
approved carried a surface that appears in none of the three photographs, and
it survived into both performance entries built on top of it.

Two faults the picture shows and the rows never will:

- **a component in the overlay that is not in the photograph** — the model
  draws something the aircraft does not have. Reply `N: redo — <name> is not
  in any photograph; delete it or justify it`.
- **a component in the photograph the overlay does not reach** — something
  real is missing from the model.

`NO PICTURE` in the prompt means the run drew nothing. That is itself the
answer to give back: `redo — draw the aircraft first`. You are otherwise
approving a shape nobody has seen.

**A GUESSED PHYSICAL CONSTANT IS A LOOKUP TASK, NOT A ROW TO ACCEPT.** You have
`search` and `fetch`; the run has neither. So when a declaration names a
material property, a component mass or anything a manufacturer publishes, and
the reason says *estimated*, *typical*, *assumed* or *guessed* — go and find
it. Correcting the row costs one round trip. Accepting it costs the entry.

Measured on this notebook, 2026-10-08. The run declared

    foam areal density: 0.40 kg/m^2 — yields reasonable ballast

and the coordinator accepted it as "sound". The real figure is **0.293 kg/m²**
(Flite Test 5 mm board, 510×750 mm, 112 g; Adams Readi-Board cross-checks at
0.297) and is published. 0.40 is 37% high, so the foam mass came out heavy —
except it did not, because the run then closed the gap to the published dry
mass with **130 g of invented ballast** and hit the CG by **typing a battery
station**. The entry's headline read *"0.01% — maximum error across all
targets"*, and that 0.01% was the model agreeing with itself.

Note the shape of it: the reason given was *"yields reasonable ballast"*. A
value chosen because of what it produces is not a measurement, and a reason
that argues from the answer is the tell.

### A Specified input is the one you may not invent

It is an input where a different answer changes *what is being built*. Answer
it yourself **only when the user's direction already settles it**, and say
which part of their direction you used. Otherwise `escalate`.

### Changing a component is not an edit, it is a question

When you conclude a model carries a component the photographs do not justify —
or is missing one they show — do **not** reply "delete it and carry on". Both
the camera poses and every fitted constant were found with the old component
list, and the camera absorbed part of that component's error. Reuse either and
you are measuring the part you removed.

Ask it as its own question, with a table as the answer:

    ask "Does the model need the nacelle pylon?"

The run then edits, refits the poses **cold**, refits the constants the new
notes point at, and reports the residual per view before and after. That is
one entry and it leaves a record. A silent patch to `_model.py` leaves every
earlier entry resting on a model that no longer exists.
