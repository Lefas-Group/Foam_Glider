# Reconstruct: derive it, do not assign it

Written 2026-10-03, after `nb reconstruct` shipped and ran twice -- once on
the Corsair MKR2 with no plan, once on the Mini Corsair v1.0 with a stitched
plan sheet in `_reference/`. Nothing here is implemented yet.

## What the last plan bought, and what it did not

| | MKR2, no sheet | v1.0, with sheet |
|---|---|---|
| declared assumptions | 6 | 4 |
| orientation calls (`search_files`, `list_directory`) | 7 | **0** |
| published targets | 3 | 8 |
| worst reported error | 1.1 % | **0.54 %** |
| targets actually *predicted* | 1 of 3 | **1 of 8** |

The machinery works. `read_reference_image` was called twice to orient, then
92 probes measured in code; the reject-at-prompt loop caught a bad
measurement before it reached the model; the targets gate caught an entry
that reported three of eight.

**And the headline number is close to meaningless.** From the run's own final
table:

```
Length        | 482.00 | 482.00 | +0.00%
Wing span     | 610.46 | 610.00 | +0.08%
Wing area     |   6.90 |   6.90 | +0.01%
CG aft of LE  |  38.00 |  38.00 | -0.00%
Dry weight    | 156.00 | 156.00 | +0.00%
All-up weight | 222.00 | 222.00 | +0.00%
```

Five exact zeroes. `_model.py` contains `x_cg_target = 0.085 + 0.038`, a
component list summing to exactly 156 g, and the comment
`# Battery: mass computed from published AUW minus dry weight`. Seven of
eight targets were **assigned**, not predicted. Only span, at 0.08 %, carries
independent error.

The run said so itself -- `why: "component masses estimated to match
published AUW"` -- which is the declaration discipline working. But an entry
headed "0.54 % worst error across eight published targets" reads as
verification when almost nothing was verified.

## The problem in one line

**A target is only a check if the quantity is computed from something more
primitive than itself.** Nothing in the system distinguishes a derived number
from an assigned one, and assigning is the easier path.

## 1. Targets are OUTPUTS. Requirements are inputs.

Two different things were sharing one block.

| | lives in | the model |
|---|---|---|
| **verification target** -- a published fact about a real object | `targets:` | must **predict** it |
| **design requirement** -- a goal for something not yet built | `specified:` | honours it as an input |

`RADICAL-GLIDER` already has one, and it landed on the right side without
anyone designing for it: `flight-time target: 2 s -- Determines if
requirements are met` was declared by a RUN, at entry level in
`01-first-chapter`, and renders as **Specified** rather than as a target. The
distinction is natural rather than imposed, which is the best evidence it is
the correct one. This codifies the repo rather than changing it, and leaves
`targets:` meaning exactly one thing: numbers that must fall out.

**But "never assign" is too crude**, and the first draft of this would have
made the model worse. The v1.0 run assigned the mass split to reach the
published 222 g and set the CG to the published 38 mm -- and that is not
cheating, it is calibration. Total mass and balance are what you measure and
adjust on a bench, they are what almost every downstream answer depends on,
and a derived mass model landing 10 % out would have made stall, loading and
climb all worse. A blanket rule would have forced exactly that.

So the split is on what KIND of quantity it is:

| | example | treatment |
|---|---|---|
| a **consequence of the geometry being reconstructed** | wing area, MAC, tail volume, length | must be **derived**. Assigning it destroys the only check on the planform, and the planform drives every aerodynamic answer |
| a **property you would measure or adjust on the bench** | total mass, CG | may be **given**. That is calibration |

And one case looks like mass but is really geometry: **dry weight derived
from area times areal density is a check on the GEOMETRY**, because the areas
come from the reconstruction. That is the version worth having -- derive dry
weight to test the airframe, then calibrate battery position to reach the
published all-up weight and CG, which is what you would physically do.

**The mechanical check, narrowed accordingly.** A target's value may not
appear as a literal in `_model.py` *for targets of the first kind*. Rule 43
already walks that file's module-level numeric constants with `ast`, so this
is an exact comparison, not a fuzzy match, and it ignores comments for free.
`x_cg_target = 0.085 + 0.038` would be allowed under the split above; a
chord tuned until `wing.area()` returns 6.90 would not.

Which kind a target is belongs in the brief, not inferred: a `targets:` row
is derived unless marked `given`.

## 2. A target derives from something more primitive

The companion instruction, phrased as a principle because the materials
change and the principle does not:

- **airframe mass** from geometry and material -- areas times areal density;
- **bought components** from catalogue figures, which are facts;
- **areas, loadings, tail volumes** from the geometry.

If the primitive is not available -- no published density, nothing to derive
from -- then that quantity is not a derived target. Mark it `given`, or move
it to `specified:`. The coordinator decides per aircraft, which is where that
judgement belongs.

**"Later entries can refine it" is true, and not a reason to defer.** Forking
is exactly how a mass model improves. But every later chapter forks THIS
model, so a structural flaw -- mass that can never be a geometry check
because it was never derived from geometry -- propagates to all of them.
Precision can come later; the structure cannot.

## 3. The run does the raster, the stitch and the measuring

Every piece of code the coordinator wrote this session was a liability, and
the worst was the stitch: tiles 1-8 were assembled from a misread tile key,
and **tile 10 holds the LEFT WING part**. The most important aerodynamic
surface was reconstructed from its assembly jigs because of that.

The run can do all of it, and the environment already allows it:

- `probe` is **not sandboxed** -- `kernel.py:156` starts it with
  `cwd=run_dir` and no path guard. Only the MCP file tools are confined.
- The kernel inherits the full environment: `env = dict(os.environ, ...)`, so
  `pdftoppm` is on PATH and PIL, numpy and scipy are in the venv.
- `NB_ROOT` is **already exported**, so `_reference/` is locatable without
  being told a path. That also retires the absolute-path bug in the current
  brief, which cost the v1.0 run three probes and a `FileNotFoundError`.

So: put the RAW source in `_reference/` -- the PDF, the photographs -- and
write nothing. The run rasterises every page, stitches them all, and measures
with `scipy.ndimage.label`. It cannot misread a tile key nobody read to it.

## 4. Let the run read back an image it produced

The one addition that makes item 3 possible. `read_figure` globs only the
freeze directory, so an intermediate the run creates in a probe -- a stitched
sheet, a crop, an overlay -- is invisible to it. It can measure an image it
built and cannot look at one.

Closing that is a small extension of an existing tool, and it generalises
beyond reconstruction to any figure a run wants to inspect mid-probe.

## 5. Structured labels, so the brief can route

Each asset gets a kind token on the first line of its `.txt`, not prose:

```
plan 1:1 100dpi      -> measurable; measure in code, never by eye
photo                -> proportions and layout only; no dimensions
scan uncalibrated    -> topology only; calibrate against a published figure first
(no _reference/)     -> build from the brief; declare every dimension
```

`_reference_brief` then emits deterministic instructions per kind instead of
hoping a paragraph is read correctly. Degrades cleanly to the empty case,
which already works.

## 6. A much larger budget for reconstruct

Reconstruction is a once-per-programme investment and **every later chapter
forks the model it produces**, so quality is worth far more than turns. The
current `MAX_TURNS * 2` is too tight -- the v1.0 run took 123 model turns and
two resumes to rasterise, stitch, survey, measure, cross-check and iterate.

Raise it well beyond that, and spend the turns on verification: measure a
part twice by different routes, cross-check against a published figure before
trusting the scale, re-render and look again after a correction.

This also retires the main argument for an autonomous builder loop, which was
coordinator-turn cost. With cost acceptable, coordinator-in-the-loop is
simply better -- the coordinator holds the reference and the judgement.

## 7. A target baseline, so drift fails loudly

**Rendering recomputes; it does not assert.** Rule 12 keeps a committed
page's freeze no older than its model and the refactor gate re-renders every
sibling reaching a changed function, so the numbers are always current. But
if a change pushes wing area from 0.01 % to 15 %, the entry renders happily:
the chart draws a longer bar and the prose reads 15 %, because rule 1 made it
an inline expression. **Nothing fails. Someone has to look.**

So today no target VALUE is checked by anything. The gate added last time
checks only that each target is mentioned, and deliberately so -- a missed
target is a finding worth reporting, not an error to suppress.

Which hides a tension worth separating:

| | a missed target is | should it fail? |
|---|---|---|
| the first reconstruction | a **finding** -- "area is 7 % under, the stab is the likely cause" | no |
| after the model is accepted | a **regression** -- something drifted | yes |

Same signature, opposite meanings. That is why "fail when out of tolerance"
would be wrong as a blanket rule, and why rendering cannot be the mechanism.

**`nb.corpus` already solves this exact shape** for lint: it records the
expected finding count per notebook and fails when one moves, requiring the
baseline to be updated in the same commit that justifies the change. It
printed `corpus unchanged` after every change made today, and caught two that
would otherwise have gone unnoticed.

The same for targets. Record the accepted error per target when a
reconstruction commits; a later render that worsens one beyond a threshold
fails until the baseline is updated with a reason. A first reconstruction has
no baseline, so a miss stays a finding; once accepted, a worsening is a
regression.

It also closes the fork-drift gap: a fork that changes the geometry either
re-verifies against the baseline or overwrites the target, and has to say
which.

**Worth waiting for one real drift before building it.** Nothing has drifted
yet -- this is reasoning about a failure that has not happened, which is the
standard everything else here was held to. Recorded now because the mechanism
is already in the repo and the next person should not have to rediscover it.

## 8. Read the declarations as a defect report

Skill text, no code. Every `why` naming something absent is the run telling
the coordinator what they failed to supply:

```
why: "plan tiles 9-12 omitted; inferred from jigs G1, G2"
```

That is the wing error, reported by the run, at the prompt, and read past.
The habit costs nothing, works with no plan and no aircraft, and would have
caught the single worst defect in this reconstruction.

## Rejected

- **Web search for the run.** Cost is no longer the objection and the honesty
  discipline held up -- but a fetched fact is **neither Specified nor
  declared**. It looks sourced, so it is not declared; nobody chose it, so it
  is not Specified; and it enters the model unexamined. With every later
  chapter forking that model the blast radius is the whole programme. The
  cases this session were not subtle: retailers quote 200 g for a Maker Foam
  sheet where Flite Test measure 115 g, and two different aircraft share the
  name "Mighty Mini Corsair" at 610 mm and 737 mm. Mid-run discovery is
  already covered by `ask_specified` and escalation, at a cost now acceptable.
  If escalation round trips ever become the bottleneck, the narrow version is
  a search whose results are `declare_input(source='guessed')` with the URL --
  never treated as fact.
- **Part-finding furniture in `_notebook.py`.** I was about to build it. Told
  to use `ndimage.label`, the run found 4,171 components and picked correctly.
  A line of brief text was enough.
- **Coordinator stitching and measuring.** See item 3. It produced the wing
  error.
- **A reference image rendered into the entry.** Ruled out: it would be a
  third visual against rule 14, and the reference belongs to how the model was
  built rather than to what the entry concluded.

## Two radically different alternatives

Both reject the premise that a model should be built by judgement and checked
against targets. They are the two poles this plan sits between, and naming
them says what it is trading.

### A. Mechanical extraction -- the plan IS the model

The plan is vector: 380 `<path>` elements on a single tile, exact
coordinates. Rather than looking at a raster and measuring it, parse the paths
and generate `_model.py` directly -- wing outline to `WingXSec` chords, the
fuselage side profile to station heights, formers A/B/C to station widths.
A CAD importer, not a modelling exercise.

*Pros.* Exact, with no estimation, no assignment and therefore no tautology --
the problem this whole plan exists to solve would not arise. Deterministic and
re-runnable. The formers are literally the cross-sections `FuselageXSec`
wants. Removes the coordinator and most of the agent's judgement at once.

*Cons.* **It only works when a vector plan exists**, which fails the
generality requirement outright -- no plan, a photograph, a scan or a
from-scratch design all get nothing. Part identification is still unsolved:
knowing which of 4,171 paths is the wing is the hard half, and it is the half
that needs judgement. The transform and coordinate-space traps are real -- two
naive attempts this session produced 1156 mm parts on a 190 mm tile. And it is
a large build for a narrow case.

*Verdict.* Worth keeping as a possible accelerator **inside** item 3 -- if the
source is a vector PDF, prefer paths over pixels -- but not as the
architecture.

### B. Stop pursuing fidelity -- declare the approximation and propagate it

The opposite move. Accept that the model is approximate, stop trying to match
the aircraft, and make the **uncertainty** the product. Build a plausible
airframe, declare the uncertain inputs with ranges rather than values, and
report every answer as a band: *"stall 8.8 +/- 0.9 m/s, given +/-10 % on wing
area and +/-15 % on the airfoil."*

*Pros.* Fully general -- needs no plan, no photograph, no published spec, and
works identically for a foam warbird, a pig and a from-scratch glider. Honest
in a way a point estimate never is: the first Mustang programme's 8.80 m/s was
precise and wrong, and a band would have said so. Turns the unmeasured items
from defects into quantified uncertainty, which is what they actually are.
Cheap -- no stitching, no measuring, no reference material. And it composes
with the claims under test: a claim is refuted only when it falls outside the
band.

*Cons.* Bands may be too wide to settle anything -- *"somewhere between 8 and
11 m/s"* does not decide whether it flies slow, which was the whole question.
Sensitivity costs solves, and the entry contract allows one hero value, not a
distribution. It characterises the model rather than improving it, so a
programme could run for ten entries without the airframe getting any closer to
the real aircraft. And a wide band is easy to hide behind.

*Verdict.* The strongest idea in this document that is not in the plan.
**It is not an alternative so much as a missing complement**: this plan makes
the model better, and B says how much to trust it. Worth running as an
experiment on one entry -- report a band beside the point value and see
whether it still settles the claim.

## Order

1. **Items 1 and 2** -- derive rather than assign. Without these the targets
   measure nothing, and everything else is polish.
2. **Items 3 and 4** -- the run does the image work; it can see what it made.
3. **Items 5, 6, 8** -- routing, budget, and the reading habit.
4. **Item 7** -- the baseline, once something has actually drifted.
5. **Try B on one entry** before deciding whether uncertainty bands belong in
   the contract.

## Outstanding

- The v1.0 reconstruction was built **without the wing panels**, which are on
  tiles 9-12 and were omitted from the stitch. Items 3 and 8 both address the
  cause. The entry is worth re-running once they land, with every tile
  included.
- Seven of its eight targets were assigned rather than predicted, so the
  0.54 % headline does not mean what it says. Items 1 and 2 are the fix; the
  entry should be re-run and will almost certainly report a larger and more
  honest number.
- The FT Mighty Mini Mustang programme still has its +74 % top-speed gap
  unexplained, surviving a propeller-polar calibration against APC data.
  Either the claim is not a top-speed figure or the drag model is badly low.
