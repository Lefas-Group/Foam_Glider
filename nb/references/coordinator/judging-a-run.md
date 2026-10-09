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
