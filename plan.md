# Reconstruct by fitting the silhouette

Written 2026-10-07. Replaces all earlier drafts; superseded material has been
cut rather than annotated. Sources: the two `tubby-b-17` reconstruction
transcripts read turn by turn, and about forty camera- and geometry-fitting
experiments against the same two store photographs.

## Premise

Two constraints are fixed, and the architecture follows from them.

- **Never hand-measure a dimension from an image.** Not to set a constant, not
  to check one. Over one session, 2 of 8 hand measurements survived scrutiny: a
  propeller blade read as a wingtip, a tailplane point placed on the fuselage, a
  landmark that was occluded and invisible, a dihedral figure that sampled only
  outboard columns.
- **No plan sheets.** Photographs and published figures only.

So **geometry comes from fitting the whole silhouette** -- thousands of boundary
pixels, no human feature identification -- and correctness is established by
checks that require no measurement.

## What the transcripts showed

`20261005-212756-0e08` (reconstruct) and `20261005-214940-20e5` (photo match).
Four defects, each verifiable in the record:

**A constant contradicted the run's own measurement.** At t33 the run computed
the mask scale correctly; at t37 it measured the nose cone at 282 mm; at t43 it
wrote `width=0.185`. That number survived four rebuilds and was declared at t83
as "fuselage loft stations: width 185 mm".

**The validated model is not the committed model.** At t79 the run reported
"span 0.00%, length 0.00%, dry mass -0.41%, CG +0.06% ... the worst error across
the board is a measly 0.41%". The committed entry reports **5.86%**. Between
them, `_model.py` was rewritten whole from the agent's memory rather than from
the probe objects it had verified. Nothing compared the two.

**The assumptions gate fires too late.** The skill says it fires *"before
`_model.py` is written, so a correction costs about one probe"*. It fired at
t82-87, after the t76 write -- which is why a correction there forced the t94
rewrite that lost the 0.41% configuration.

**A finding has nowhere to go.** Run 2 found the outer wing chord too narrow,
committed a `.qmd`, and `_model.py` is byte-identical from `3069cef` through
Q5 -- three performance entries computed on geometry known to be wrong.

A fifth, from the Mini Explorer: a reconstruction reproduced eight published
figures to 0.40% while **missing the power pod entirely**. Nothing checked that
the model contained everything the photograph does.

## What the experiments established

**The optimiser was the problem, not the model.** Minimising normalised chamfer
across both photographs:

```
baseline  (committed geometry, hand-seeded poses)   19.94 px
A         geometry UNTOUCHED, poses by CMA-ES       13.77     <- 85% of the gain
C         6 wing dimensions free                    12.60
```

**Seed density was never the issue.** 36 seeds ranked by raw cost fails; 1485
seeds ranked by raw cost fails; the *same* 36 ranked by where a short descent
leads works. CMA-ES removes the question entirely -- no seed grid, no hand-tuned
elevation range, fastest of everything tried. `dual_annealing` failed 3 of 4
subsets and is rejected.

**Residuals must be normalised by `sqrt(mask area)` per view.** The head-on
silhouette is a third the area of the three-quarter, so in raw pixels damage to
it was cheap:

```
                      RAW PIXELS          AREA-NORMALISED %
                    mean      max        mean      max
A (model fixed)    13.77    17.90       2.806    2.917
C (6 wing free)    12.59    13.93       2.865    3.894

raw  : C wins on BOTH aggregators -> accepts distorted geometry
norm : A wins on BOTH             -> rejects it
```

This single change flips the verdict under both aggregators. **Minimax adds
almost nothing** once units are right (0.105% on the worst view against a 0.93%
gap from baseline) and it is non-smooth; use the normalised **mean**.

**The seed-noise floor is the yardstick.** Three seeds per arm give a
within-arm sd of **0.024%**. Against that:

```
choice                 effect    in sd   verdict
tolfun 1e-2           0.0000%     0.00   inside noise
tolfun 2e-2           0.0030%     0.13   inside noise
mesh 36 -> mesh 8     0.0190%     0.81   indistinguishable at n=3
tolfun 5e-2           0.0170%     0.72   borderline
tolfun 1e-1           0.0510%     2.16   REAL degradation

the signal being chased: committed -> fitted = 0.926% = 39 sd
```

So: **mesh resolution 8** (2.3x faster, no measurable cost), **tolfun 2e-2**
(14% fewer evaluations), **popsize ~18**. Every one of these knobs is tuned
inside the noise of the thing it tunes; set them once and stop.

**Things that look like success and are not.** This list is the specification
for the checks below -- each is a real event from this work:

- a parameter pinned on its bound (perspective distance railed at orthographic,
  unnoticed through an entire session)
- a frozen optimiser (Nelder-Mead gives a coordinate seeded at exactly 0.0 an
  absolute step of 2.5e-4; a shift test reported "+0 mm" three times running)
- mislabelled correspondences scoring *better* than correct ones (11.8 px RMS
  against 17.4, on a pose with IoU 0.230)
- a post-fit residual standing in for agreement (four lines that should meet at
  one point gave six intersections scattered over 900 px; the fit reported
  4.1 px)
- a false "good" pose at azimuth 1.6deg -- the view from directly behind
- a single-run difference read as an effect (a 12% "mesh penalty" that three
  seeds showed to be noise)

**No single-run result is a finding.** Six of the above were single runs that
looked publishable.

## The workflow

### 1. Published figures are inputs, never fitted

Every dimension the manufacturer publishes is `published` and fixed: span,
length, CG, dry weight, wheel diameter, propeller size -- whatever the source
gives. For some aircraft that will include dihedral, wing area or incidence;
take whatever is there.

This is not only honesty. Span and length make the fit **identifiable**: if span
is free it trades directly against camera distance and the problem goes
degenerate. The published set is the scale reference.

The complement defines the work: **the free set is exactly the dimensions the
run would otherwise invent** -- which is precisely what the assumptions gate
already enumerates. Fit those instead of guessing them.

### 2. Build structure against the cheap check

A pose fit is ~20 s; a geometry fit is ~375 s. Iterate structure against the
cheap one.

Loop: edit `_model.py` -> pose fit on every view -> look at the overlay, and
run the **completeness check**, which names the regions of the photograph no
component covers. That is what catches the missing power pod and the
unmodelled propellers, and it needs no feature identification.

**It has no pass mark, and should not.** Measured on a sound model at a
correct pose -- IoU 0.77 -- 17.5% of the mask was still uncovered, mostly thin
slivers along edges. Any fixed gate rejects good work. The output is *where*,
not *whether*: a compact blob is a component you have not built, a sliver along
an edge is one you have.

**The pose decides whether the number means anything**, so the check refuses to
report when the pose is DOUBTFUL:

```
pose                       resid    uncovered
correct                    3.07%       17.5%
30 deg out in azimuth      7.21%       33.4%
mirrored, from below       6.89%       44.0%
```

An earlier draft proposed telling a missing component from a bad pose by how
*concentrated* the gaps are. Measured, that is backwards -- the bad poses were
more concentrated (88% of the missing area in three regions, against 67% for
the correct pose), because an ill-posed model leaves one huge contiguous slab
uncovered. The pose residual already separates the cases cleanly and costs
nothing; use it.

### 3. Parameterise broadly, fit broadly, keep selectively

Expose many parameters -- you only want to do this once. Free many of them too.
But **keep only what the seed spread says is identifiable**:

```
c_outb   0.2927 +/- 0.0085   (2.9%)   CONSISTENT -> commit as fitted()
dihed    5.215  +/- 0.344    (6.6%)   SCATTERED  -> direction only
c_root   0.3771 +/- 0.0591   (16%)    SCATTERED  -> revert, declare invented
```

Freeing a parameter costs nothing if it reverts; it buys the knowledge of
whether the photographs constrain it at all. Twenty-two free parameters produced
the best three-quarter score of any run *while visibly splaying the tailplane*
-- so the protection has to be the spread and the look, not a smaller free set.

**Multi-seed catches wandering parameters, not stable deformation.** A splayed
tailplane with a compensating wing could reproduce in every seed. The guard is
**per-component residual, before and after**: if the total improves while any
single component's residual worsens, flag it.

### 4. Convergence is self-calibrating

An absolute percentage will not standardise across aircraft -- the 0.024% floor
here comes from this aircraft, these photographs, these masks. Use the measured
spread as the scale instead:

- a parameter is `CONSISTENT` when its spread is small **relative to its own
  value**
- the fit has converged when another round moves the objective by **less than
  the seed spread**
- no constant anywhere

### 5. Reruns need a structural trigger

Allowing "change the parameters and try again" is one step from *keep going
until the number looks good* -- the failure `compare_to_photo`'s no-score design
exists to prevent, and which this session demonstrated repeatedly.

| legitimate trigger | action |
|---|---|
| a parameter railed on its bound | widen that bound, refit |
| a parameter came back `SCATTERED` | drop it, refit |
| completeness check failed | add the component, refit |
| a component's residual degraded | investigate that component |

"I would like a better number" is not a trigger. **Two rounds maximum, and the
trigger is recorded in the entry.**

## The tool

The agent must not write an optimiser. It wrote its own pose seeder twice in the
original transcripts and the budget killed both attempts.

```python
fit = fit_geometry(
    free = {
        # name          lower  upper   why this is a candidate
        "chord_outb":  (0.12,  0.34,  "entry 02: real outer TE lies aft of the model's"),
        "dihedral_deg":(-3.0,  9.0,   "head-on overlay shows more V than modelled"),
    },
    reliability = "normal",      # -> seeds and popsize
)
```

`views` is not a parameter: always every reference with a mask, always
`sqrt(area)`-normalised, always mean-aggregated, always 3 seeds in parallel.
Those took a session to establish and are not the agent's to re-decide.

It returns values the agent can read, and evidence it can act on:

```python
fit.values["chord_outb"]    # 0.2951
fit.spread["chord_outb"]    # 0.0085
fit.verdict["chord_outb"]   # "CONSISTENT"
fit.per_component           # which components improved or degraded
fit.railed                  # [] or the names of pinned parameters

fit.apply()                 # writes CONSISTENT values into _model.py as fitted(...)
                            # reverts SCATTERED ones and declares them invented
```

**The agent never transcribes a fitted number by hand.** `apply()` does the
transfer; the agent reads verdicts to decide whether a rerun is warranted. Hand
transcription is exactly how `width=0.185` came to contradict a measurement of
282 mm in the same run.

The printed form, for the entry:

```
fit_geometry -- 2 free parameters, 2 views, 3 seeds, 375 s

parameter      committed    fitted   cross-seed    verdict
chord_outb        0.2000    0.2951   +/- 0.009    CONSISTENT
dihedral_deg      2.0000    4.83     +/- 1.21     SCATTERED (direction only)

view            before    after     per-component
threequarter    2.92%     1.78%     no component degraded
headon          2.70%     1.75%     no component degraded
                                    both views improved

no parameter on a bound - no camera outside its stated hemisphere
```

**Guard rails the function enforces**, each from a specific failure:

| rail | catches |
|---|---|
| every free parameter needs a written reason | scanning for whatever moves the number |
| refuse if the completeness check has not passed | the missing power pod, the unmodelled propellers |
| refuse to report a railed parameter or an out-of-hemisphere camera | the orthographic-distance case |
| 3 seeds, in parallel, always | single-run artefacts |
| per-component residual reported | stable deformation |
| mesh 8, tolfun 2e-2, popsize 18 chosen internally | knobs the agent should not touch |

## Provenance

Every dimensional constant in `_model.py` carries its origin:

| kind | means | check |
|---|---|---|
| `published(source)` | from the brief | must match a `specified:` row verbatim |
| `fitted(views, spread, seeds)` | from `fit_geometry` | re-runnable; carries its spread |
| `calibrated(target)` | solved to hit a published target | mass, CG -- bench-measurable things |
| `invented(why)` | a declared guess | what the assumptions gate shows |

This kills two transcript defects outright. A fitted constant cannot disagree
with the fit (the 185 mm case), and there is no rewrite-from-memory step because
the model is one artifact (the 0.41% -> 5.86% case). It also moves the
assumptions gate to first geometry build, where the skill already claims it
fires.

## Checks that need no measurement

- **Physical plausibility.** A camera below an aircraft resting on a surface is
  refuted by configuration. Encode the reference `.txt`'s stated hemisphere as a
  hard bound.
- **Cross-seed spread.** The verdict mechanism, and the noise floor.
- **Cross-view consistency** in normalised units. A change that improves one
  view and degrades another is a trade, not a finding.
- **Independent-estimate scatter, never post-fit residual.** Where a quantity
  can be estimated more than one way, report the disagreement between estimates.

## Budget

Measured, at mesh 8 / tolfun 2e-2 / popsize 18:

```
pose fit, 7 params, one view                          20 s
geometry fit, 20 params, 1 seed                      340 s
geometry fit, 3 seeds in parallel                    375 s
```

A reconstruction, worst case:

```
structure loop, ~10 edits x pose check on 2 views     400 s
first geometry fit (3 seeds)                          375 s
verification overlay, both views                       40 s
rerun 1 (structural trigger)                          375 s
rerun 2 (structural trigger)                          375 s
                                              TOTAL  1565 s   (26 min)
```

So **`reconstruct` needs a pool near 1800 s -- six times the present 300 s
default.** That is the concrete form of the standing argument that
reconstruction is a once-per-programme investment every later chapter forks.

Seeds parallelise, which is what makes this affordable: nine concurrent fits on
eight cores ran ~3x slower, so three concurrent cost about 10% over one. The
entire consistency mechanism is a 10% surcharge.

`ask` keeps its present budget. **Geometry fitting lives inside `reconstruct`
only** -- not as a separate command, because anything deferred is something that
does not happen, which is exactly how run 2's wing finding went unused.

## Lint

| rule | catches |
|---|---|
| published dimensions are never free | the identifiability degeneracy |
| every `fitted` constant carries spread and seed count | false precision |
| every freed parameter has a written reason | score-chasing |
| `SCATTERED` parameters are never written as values | the `c_root` +/-16% case |
| completeness check passed before any geometry fit | the missing power pod |
| a figure was read before commit | the overlay being a look, not a score |
| reruns <= 2, each with a recorded structural trigger | the rerun loop |

## Model/mask symmetry: the propellers

The masks contain four propellers and the landing gear; the committed model has
neither. Gear was added this session from published figures (4.3 in wheels) and
belongs in **both** models -- fixed gear really does add drag. Propellers are
different: they belong in the fit and not in the aero.

**Why not in the aero.** `_analysis.py` runs `asb.AeroBuildup`, which takes
parasite drag from the wetted area of every component. Four 9x4.5 propellers are
0.043 m2 against the airframe's 2.007 m2 -- **2.1% more parasite drag** -- and
it is wrong in kind as well as magnitude: AeroBuildup would treat a blade as a
streamlined body, and the propulsion model already accounts for the propeller.
Double counting.

**Why in the fit.** The propellers are in the photograph. They are real
silhouette information, their hub is the nacelle front (already modelled) and
their diameter is published. Excluding them throws away evidence and puts a
hole in the completeness check -- and a hole is somewhere a genuinely missing
component could hide.

**One builder, one flag, aero-safe by default:**

```python
def build(props: bool = False) -> asb.Airplane:
    ...                      # every structural parameter shared

airplane          = build()              # what flies -- no props
airplane_for_fit  = build(props=True)    # what the camera sees
```

`props=False` is the default so that any naive use gets the aero-correct model;
the fitting path has to ask for propellers explicitly. One builder means the two
cannot desynchronise structurally.

**Cost: one blade angle per propeller per view**, since each photograph catches
the blades at a different moment -- 8 nuisance parameters here. They are cheap:
bounded by blade symmetry, local to their own pixels, and independent of
airframe geometry, so they do not absorb airframe error.

**The general rule:** a component the real aircraft has and the aero model
should not have becomes a **silhouette-only component**, included behind the
build flag. Only consider excluding a mask region from comparison when the thing
cannot be modelled at all -- exclusion is a hole in the completeness check and
should be the last resort, not the default.

**A related agent pattern, not a system defect.** `_analysis.py` is created
empty and written entirely by the agent -- there is no template for it. In the
Tubby chapter the agent rebuilt `asb.Airplane` three times in order to deflect a
control surface, and in doing so **retyped the tailplane geometry as literals**:

```python
# _model.py
asb.WingXSec(xyz_le=[0.970, 0.00, 0.055], chord=0.180, ...)
# _analysis.py -- the same numbers again, with a control surface attached
asb.WingXSec(xyz_le=[0.970, 0.00, 0.055], chord=0.180, ..., control_surfaces=[cs])
```

Fitted tail geometry would therefore never reach the aero analysis, and any
component added to `airplane` is silently dropped. This is the 185 mm defect in
another costume: a number restated in a second place.

It is occasional rather than systemic -- 2 of about 30 `_analysis.py` files in
the repo rebuild an `Airplane`, and both do it to deflect a surface. Nothing
steers the agent away from it, so it will recur whenever control surfaces are
analysed.

**Fix: give the agent a correct path, in furniture.** `_notebook.py` is
scaffolded, so a helper there is available to every chapter:

```python
def with_control_surface(airplane, wing_name, name, deflection_deg):
    out = copy.deepcopy(airplane)
    cs  = asb.ControlSurface(name=name, deflection=deflection_deg)
    for w in out.wings:
        if w.name == wing_name:
            for x in w.xsecs:
                x.control_surfaces = [cs]
    return out
```

Verified on the committed model: elevator +-10 deg gives Cm -0.312 to +0.229
against -0.094 undeflected, the source airplane is untouched, every component
is preserved, and **no geometry is named**. Lint should then refuse an
`asb.Airplane(` or a bare `WingXSec`/`FuselageXSec` in `_analysis.py` at all.

**And a trap found while testing it:** a `Fuselage` whose cross-sections differ
only in z has `length() == 0`, and `AeroBuildup` divides by it -- every
aerodynamic number comes back `NaN` behind a `RuntimeWarning` that is easy to
miss. The landing-gear legs written this session hit exactly that. Any strut,
leg or vertical component needs a non-zero x extent.

## Carried forward

- **Derive rather than assign.** A target is only a check if computed from
  something more primitive than itself; an earlier reconstruction assigned seven
  of eight. The distinction that matters is **scale inputs** (span, length --
  use them) versus **consequences of the geometry** (wing area, MAC, tail volume
  -- derive them).
- **Target baseline.** Record the accepted error per target when a
  reconstruction commits; fail a later render that worsens one beyond a
  threshold. Has its first real drift to justify it: 0.41% -> 5.86% in one run,
  uncaught.
- **Uncertainty bands.** Still the strongest unexplored idea. Every performance
  number in `tubby-b-17` rests on a wing the notebook records as wrong in a
  known direction; a band would say so in the entry rather than in a
  coordinator's note.

## Open

- **Everything is calibrated on one aircraft and two photographs.** The noise
  floor, the mesh and tolerance settings, the seed count, the budget. The first
  trial on another notebook should expect to recalibrate, and the seed spread
  does that automatically.
- **Three seeds is a screen, not a measurement.** Enough to separate +/-16% from
  +/-3%, not +/-3% from +/-5%.
- **A finding still has nowhere to go.** An entry should be able to emit a
  structured model defect that appears in the chapter manifest and shows as
  `known defects: n` until superseded. Not auto-fix -- append-only is worth more
  than the turns it costs.

## Outstanding defects in the committed notebook

- `_model.py` carries a wing the notebook itself records as too narrow at the
  outer panel, and three performance entries computed on it.
- Entry 01 reports 5.86% when the run had 0.41% in hand.
- The 255 mm fuselage width came from a hand measurement at the Q1 assumptions
  gate and has never been checked. Under this plan it should be fitted, or
  declared `invented`. The one run allowed to scale the fuselage wanted it
  **11% narrower**.
