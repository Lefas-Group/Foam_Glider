# Fit the silhouette, check it without measuring it

Written 2026-10-06, from the two `tubby-b-17` reconstruction transcripts read
turn by turn, and from about thirty camera-fitting experiments run against the
same two photographs. Supersedes both earlier drafts of this file; their
unfinished items are carried forward at the end.

Two constraints are fixed by the user and everything here is built inside them:

- **Never measure dimensions off an image by hand.** Not to set a constant, not
  to check one. Measured over this session, 2 of 8 hand measurements survived
  scrutiny — a propeller blade taken for a wingtip, a tailplane point placed on
  the fuselage, a landmark that was occluded and invisible, a dihedral figure
  that sampled only outboard columns.
- **No plan sheets.** The reconstruction must work from photographs and
  published scalars alone.

Together these settle the architecture: **geometry comes from optimising the
whole silhouette** — thousands of boundary pixels, no human feature
identification anywhere — and correctness is established by checks that need no
measurement at all.

## What the transcripts showed

`20261005-212756-0e08` (reconstruct) and `20261005-214940-20e5` (photo match):

| | run 1 | run 2 |
|---|---|---|
| model turns / probes | 125 / 72 | 39 / 23 |
| pose fits returned | 12 | 10 |
| …that re-derived a camera already known | 7 of 8 head-on | 9 of 10 |
| cold start on the oblique view | 65.2° elev, DOUBTFUL | 42.6°, DOUBTFUL |
| `_model.py` changed | written once | **not at all** |

Four defects, each verifiable:

**A constant contradicted the run's own measurement.** At t33 run 1 measured
the mask scale correctly; at t37 it measured the nose cone at 282 mm; at t43 it
wrote `width=0.185`, matching neither. That number survived four rebuilds and
was declared at t83 as "fuselage loft stations: width 185 mm".

**The model that was validated is not the model that was committed.** At t79 the
run reported "span 0.00%, length 0.00%, dry mass −0.41%, CG +0.06% … the worst
error across the board is a measly 0.41%". The committed entry reports **5.86%**.
Between them, `_model.py` was rewritten whole, from the agent's memory, rather
than from the probe objects it had just verified. Nothing compared the two.

**The assumptions gate fires too late.** The skill says it fires *"before
`_model.py` is written, so a correction costs about one probe, not a
re-render"*. It fired at t82-87, after the t76 write — which is precisely why a
correction at that gate forced the t94 rewrite that lost the 0.41% configuration.

**A finding has nowhere to go.** Run 2 found the outer wing chord too narrow,
committed a `.qmd`, and `_model.py` is byte-identical from `3069cef` through
Q5. Three performance entries computed on geometry already known to be wrong.

## What the experiments showed

### 1. The optimiser was the problem, not the model

Minimising mean chamfer across both photographs, with CMA-ES replacing the
hand-rolled search:

```
baseline  (committed geometry, hand-seeded poses)   19.94 px
A         geometry UNTOUCHED, poses by CMA-ES       13.77     <- 85% of the gain
C         6 wing dimensions free                    12.60
```

**Five sixths of the apparent gain needs no model change at all.** Run A's
head-on fit is the best that view has had — 13.30 → 9.64 px, IoU 0.550 → 0.682
— with `_model.py` exactly as committed.

### 2. Seed density was never the issue

```
36 seeds, ranked by raw cost   (what nb does today)   FAILS   44°
1485 seeds, ranked by raw cost                        FAILS   44°
36 seeds, ranked by SHORT DESCENT                     works   24.5°
dual annealing                                        unreliable — failed 3 of 4 subsets
CMA-ES                                                works, fastest, no seed grid
```

Forty times more seeds changed nothing; re-ranking the *original* 36 fixed it.
A raw seed's score says nothing because its scale and translation come from the
mask bounding box. **Delete the seed grid and call CMA-ES.**

### 3. The objective was measured in the wrong units

The single most consequential finding, and it came from the user.

```
                      RAW PIXELS          AREA-NORMALISED %
                    mean      max        mean      max
A (model fixed)    13.77    17.90       2.806    2.917
C (6 wing free)    12.59    13.93       2.865    3.894

raw  : C wins on BOTH aggregators  -> accepts distorted geometry
norm : A wins on BOTH aggregators  -> rejects it
```

The head-on silhouette is a third the area of the three-quarter, so in raw
pixels **damage to it was cheap**. Normalising each view's residual by
`sqrt(mask area)` — the units `_POSE_DOUBTFUL` already uses — flips the verdict
under *both* mean and minimax. The normalisation matters more than the
aggregator; minimax alone does not fix it.

### 4. Things that look like success and are not

Every failure this session had this shape. The list is the specification for
what the system must catch:

- **A railed parameter.** The three-quarter pose quoted as "best" all session
  had perspective distance pinned at its bound of 20.0 — effectively
  orthographic, which `_project`'s own docstring warns against — and nobody
  noticed. A parameter on a bound is not converged.
- **A frozen optimiser.** Nelder-Mead's default simplex gives a coordinate
  seeded at exactly 0.0 an absolute step of 0.00025. A nacelle-shift test
  reported "+0 mm" three times running. This is documented in `_fit_pose`'s own
  source; it was read earlier the same session and walked into anyway.
- **Mislabelled correspondences scoring better than correct ones.** Three of
  seven wireframe edges were labelled wrong; the fit converged at 11.8 px RMS
  against the correct labelling's 17.4, on a pose with IoU 0.230.
- **A post-fit residual standing in for agreement.** Four symmetric-pair lines
  that should meet at one vanishing point gave six pairwise intersections
  scattered over 900 px. The least-squares fit averaged that away and reported
  a reassuring 4.1 px.
- **A false "good" pose.** A head-on fit at azimuth 1.6° — the view from
  directly behind — scored "Pose: good" at 16.9 px.

### 5. Things tested and rejected

Scale pinned to the mask caliper; dense seed grids; component subsets (wing
only — degenerate one-sided objective; wing+fuselage; wing+fuselage+tail — all
lose orientation accuracy); `dual_annealing` at low budget; annealing directly
at the fine raster. Also: the coarse raster is **not** a speed trade — it is
13% cheaper per evaluation and annealing at 220 px was *worse* (28.5 vs 18.7
px). It works by smoothing the landscape. Document it as graduated
non-convexity, not as an optimisation.

## The changes

### Tier 1 — the metric and the search

1. **Normalise every chamfer by `sqrt(mask area)` of its view.** Report it that
   way, flag DOUBTFUL that way, and use it in any objective. This is one
   function and it is the highest-value change in the document.
2. **Replace `_fit_pose`'s seeding with CMA-ES.** Deletes the 36-seed grid, the
   ranking logic, the explicit-simplex workaround, and the implicit "camera is
   above the aircraft" assumption baked into the elevation range. Net deletion
   of code.
3. **Refuse to return a pose with any parameter on a bound.** Report which one.
4. **Multi-view by default.** Fit shared geometry against every available
   photograph at once, each view normalised. **Aggregate with the mean until
   minimax is shown to be worth it** — see "Is minimax worth anything?" below.
   An earlier draft of this file said "max, not mean"; that was unsupported.

### Tier 2 — provenance

Every dimensional constant in `_model.py` is one of four kinds, machine-checkable:

| kind | means | check |
|---|---|---|
| `fitted(views, objective)` | produced by the silhouette fit | re-runnable; carries its residual and its bound-status |
| `published(source)` | from the brief | must match a `specified:` row verbatim |
| `calibrated(target)` | solved to hit a published target | mass, CG — the bench-measurable things |
| `invented(why)` | a declared guess | **this is what the assumptions gate shows** |

This kills the 185 mm defect (a fitted constant cannot disagree with the fit)
and the 0.41%→5.86% defect (there is no rewrite-from-memory step; the model is
one artifact). It also **moves the assumptions gate to first geometry build**,
where the skill already claims it is.

Belt and braces, independently: `reconstruct` records the best target table seen
in any probe and refuses to silently commit a strictly dominated result.

### Tier 3 — checks that need no measurement

The system cannot verify geometry by measuring the photograph. These four can
all be computed without reading a pixel as a dimension:

- **Physical plausibility.** A camera below an aircraft resting on a surface is
  refuted by configuration, not measurement. Run C put the head-on camera at
  elev −6.4°. Encode the reference `.txt`'s stated hemisphere as a hard bound.
- **Start-point invariance.** A real geometric error is pose-invariant. A
  nacelle shift that wants −40 mm, −20 mm and 0 mm from three different
  starting poses is absorbing pose error. Run the fit from several starts and
  report the spread, not the best.
- **Cross-view consistency**, in normalised units. A change that improves one
  view and degrades another is a trade, not a finding.
- **Independent-estimate scatter, never post-fit residual.** Where a quantity
  can be estimated more than one way, report the disagreement between the
  estimates. The 900 px vanishing-point scatter was invisible in the 4.1 px
  residual.

### Tier 4 — a finding must be able to change something

An entry can emit a structured model defect naming the constant and the
evidence. It appears in the chapter manifest every later run is shown, and the
chapter carries a visible `known defects: n` until an entry supersedes it.
**Not auto-fix** — append-only is worth more than the turns it costs — but
visible and cheap to act on.

### Tier 5 — small, unambiguous

- Return the figure inline from `probe`. Every look costs two turns today, and
  the turn in between is spent speculating about an image that has not arrived
  ("likely the torque of wheels… strain data, deformation, or even temperature
  distributions" — run 1, t53, on an overlay it had just written).
- Report mask pixels far from every model component, so an unmodelled
  appendage announces itself instead of becoming an unexplained fit floor.
- Normalise a leading `chapters/` in `search_files`. Both runs' first call
  failed identically.
- **Run long fits unbuffered** (`python -u` or an explicit flush). Redirected
  stdout is block-buffered, so a fit that is working looks identical to a fit
  that has hung -- four minutes of progress sat invisible in a buffer during
  this session while its process ran at 85% CPU.

## Is minimax worth anything?  (answered: barely)

Both aggregators run to convergence on the same six parameters:

```
                         mean      worst view
Cnm  normalised MEAN     1.875%     2.007%
Cmn  normalised MINIMAX  1.899%     1.902%
A    committed model     2.806%     2.916%
```

Each wins its own objective. Minimax buys **0.105%** on the worst view, a 5%
relative improvement, against a gap from the baseline of nearly 1%.
**Normalisation was the fix; minimax is a marginal refinement.** Default to the
normalised mean -- it is smooth, easier to search, and within a tenth of a
percent. Offer minimax where worst-case matters.

The two objectives do land on measurably different geometry (root chord 0.346
vs 0.416, dihedral 5.3 vs 4.3 deg), which is itself useful: that disagreement
is part of the cross-run spread that tells you which parameters are supported.

The original observation still stands -- normalisation flips the A-vs-C verdict
under **both** aggregators:

```
raw   mean:  C 12.59  <  A 13.77   -> accepts distorted geometry
raw   max :  C 13.93  <  A 17.90   -> accepts distorted geometry
norm  mean:  A 2.806  <  C 2.865   -> rejects it
norm  max :  A 2.917  <  C 3.894   -> rejects it
```

Minimax contributed nothing here, and it carries two costs: it **equalises**,
dragging the better view down toward the worse one rather than protecting it;
and `max` is non-smooth at the crossover, which makes the search harder than a
mean. A direct comparison (six wing parameters under normalised mean vs
normalised minimax) is running; until it says otherwise, **use the normalised
mean**.

## What optimisation costs, and which kinds to allow

`_fit_pose` is already an optimisation — 36 seeds and a Nelder-Mead descent per
`compare_to_photo` call, which both transcripts complained costs 8-10 s. The
question is not whether to allow optimisation but which.

| | parameters | measured cost | verdict |
|---|---|---|---|
| pose fitting | 7 per view | 16-60 s | already present; switch to CMA-ES in normalised units |
| geometry fitting | 20-36, shared | **880 s** | three times an entire entry's probe pool |

**The cost lever is the mesh, not the raster.** Measured on the 12-component
model (2285 vertices, 1956 faces):

```
raster at 110 px:  30.5 ms
raster at 200 px:  34.7 ms      <- four times the pixels, 14% more time
```

Cost is dominated by drawing ~2000 polygons, so shrinking the working raster --
what `_fit_pose` does today, and what every experiment in this session did --
buys almost nothing. Decimating the mesh does, up to a point. AeroSandbox
meshes at resolution 36 by default; sweeping it down, at the same pose:

```
res   faces  raster ms  speedup  silhouette IoU vs res 36
 36    1956     27.0      1.0x       1.0000
 16     876     16.2      1.7x       0.9966
 12     660     12.7      2.1x       0.9932
  8     444     11.8      2.3x       0.9899
  6     336     11.0      2.4x       0.9836
  5     282     15.0      1.8x       0.9796
  4     228      8.8      3.1x       0.8770   <- cliff
```

### Tolerances buy nothing; popsize buys reliability

Tested on the 7-parameter pose problem, three seeds each, every result scored
at full mesh resolution:

```
config                     evals   time   full px   3-seed spread
defaults                    1564   15.7s   18.20    0.24 px, 1.1 deg
tolfun 1e-2                 1528   15.1s   18.20    0.24 px, 1.1 deg   (98%)
tolfun 1e-2 + tolx 1e-4     1516   15.1s   18.20    0.24 px, 1.1 deg   (97%)
popsize 8                   1336    9.7s   18.15    0.49 px, 1.2 deg   (85%)
popsize 20                  2160   17.0s   18.17    0.13 px, 0.3 deg  (138%)
```

CMA-ES defaults to `tolfun` 1e-11. **Set it in the objective's own units, at
the precision you would report.** The objective here is a percentage of
`sqrt(mask area)` with a value near 1.9, reported to three decimals, so
report-precision is 1e-3 and 1e-2 is ten times looser -- which on the
three-quarter view (`sqrt(area)` = 614) works out at 0.06 px. If the normaliser
changes, the right `tolfun` changes with it. On this 7-parameter problem nothing
changes, because it terminates on `tolflatfitness` first -- but **that result
does not generalise**. Repeated on the 20-parameter geometry problem, where the
real cost lies:

```
config         evals  best found at  wasted   result    termination
default         5508       4244       23%     1.876%    tolflatfitness
tolfun 1e-3     5508       4244       23%     1.876%    never fired
tolfun 1e-2     4842       4244       12%     1.876%    tolfun
                        fitted geometry identical to 4 decimal places
```

**Set `tolfun` to about 0.5% of the expected objective value** -- here 1e-2
against a final near 1.9. That gives 12% fewer evaluations and a bit-identical
answer, and it stops 598 evaluations *after* the best solution was found, so it
is not cutting anything short.

State it as a fraction, not an absolute. Swap the normaliser from
`sqrt(mask area)` to perimeter and the objective drops from ~1.9 to ~0.4,
making the same absolute `tolfun` five times looser with nothing to warn you.

Tightening is pointless: `tolfun=1e-3` never fires at all, reverting to the
default `tolflatfitness` at 5508 evaluations. The dimension decides which
criterion fires, so tolerance tuning matters on the expensive problem and not
on the cheap one.

The remaining 12% is unreachable by any tolerance value. CMA-ES requires the
objective range to hold below tolerance across `10 + ceil(30n/lambda)`
generations -- 44 of them at n=20, lambda=18 -- so nothing can fire until long
after progress stops. **The history window is the binding constraint, not the
tolerance.** A custom callback ("stop if no improvement over 15 generations")
is a few lines and would recover most of the rest.

`popsize` is the real knob, and it trades evaluations for **reliability**, not
speed for accuracy: popsize 8 saves 15% and doubles the cross-seed spread;
popsize 20 costs 38% and halves it. Given how many single-run artefacts this
session produced, pay the 38%.

(Measured on a 7-parameter problem seeded near the answer; the 20-parameter
cold start may behave differently, and popsize is exactly the knob that should
matter more there.)

**Use resolution 6-8 for POSE fitting**: about 2.3x faster, silhouette within
1% of the full mesh, and a 7-parameter pose fit lands within 1 degree and
0.5 px of the resolution-36 answer.

**Never for geometry fitting.** The same 20-parameter fit, same objective,
same seed, run at the two resolutions and then both scored at FULL mesh:

```
                  three-quarter      head-on        mean
fitted at res 36   10.70 px 1.743%   7.18 px 2.007%  1.875%
fitted at res  8   12.41 px 2.022%   7.85 px 2.193%  2.108%   <- 12% worse
```

**This single comparison does not establish that the mesh caused it.** The
cross-run spread already measured on `c_outb` is 11% across five fits; the
resolution-36-vs-8 difference is 7.5%, which is inside that scatter. Two runs
with different search trajectories differ by about this much for reasons that
have nothing to do with the mesh. Three seeds at each resolution are running to
separate the two.

In absolute terms the difference is also small -- 1.7 px on a 1056 px subject
-- and invisible in the overlays. Put another way, the decimated search
captures 75% of the available improvement over the committed model for 43% of
the cost, which may well be a good trade.

PENDING: until the seed study lands, treat "decimate for pose, full mesh for
geometry" as a precaution rather than a finding. The speedup plateaus there because fixed costs (distance
transform, array work) take over; resolution 4 is where the shape genuinely
breaks, the fuselage becoming a square tube.

That puts a joint geometry fit near **380 s** -- too much for an entry's probe
pool, workable for a dedicated command.

An earlier draft of this section claimed 3.4x and a cliff at resolution 5. Both
were wrong: 3.4x was fit *wall-time*, which measures convergence luck as much as
speed, and the resolution-5 "collapse" was contamination -- a `cma_signals.in`
stop file written to halt other runs was read by the still-running sweep, which
quit after one generation. Re-run clean, resolution 5 works.

**So: geometry fitting belongs in its own command with its own budget**, the way
`nb reconstruct` already is -- never inside `ask`, and every constant it
produces labelled `fitted(...)`.

The case for allowing it at all is only this, and the plan should not overstate
it: with no plan sheet and no hand measurement, the alternative is **invention**.
The run currently makes up chord, taper, dihedral and nacelle stations from
nothing and declares them. A number constrained by two photographs beats a
number constrained by none. That is a weaker claim than "it measures the
aircraft", and nothing in this session supports the stronger one.

## Model/mask symmetry

The masks contain four propellers and the landing gear; the committed model has
neither. Gear was added during this session from published figures (4.3 in
wheels) and is worth **1.2% of the silhouette** — it did not rescue the cold
start. The propellers are the remaining asymmetry and they are large.

**Add the propellers to the model; do not edit the mask.** Diameter is
published (9×4.5 → 228.6 mm) and the hub is the nacelle front, already modelled.
The only unknown is each propeller's rotational angle, which is a nuisance
parameter — four props × one angle per view — fitted alongside the camera. No
image measurement, no mask surgery.

## What the fits actually produced

Five runs, all scored in normalised units so the rows are comparable:

```
run                      geometry free   dihedral   3/4      head-on   norm worst
A   committed model      none              2.00°    2.92%     2.70%      2.916%
C   mean, raw px         6 wing            6.67°    1.84%     3.89%      3.894%   head-on BROKEN
D   mean, raw px         6 wing + 5 nac    4.47°    1.78%     1.75%      1.780%   best
Cmn minimax, normalised  6 wing            4.26°    1.90%     1.90%      1.902%
FREE mean, raw px        22 params         4.75°    1.49%     2.31%      2.309%   tail distorted
```

**D and Cmn improve BOTH views at once.** That is the distinction that matters:
C bought the three-quarter by wrecking the head-on (visible in the overlay — the
model splayed flat, camera below the aircraft), while D and Cmn beat the
committed model on both photographs simultaneously. D is the best result of the
session: **1.78% worst-view against 2.92%**, with no part visibly deformed.

**FREE shows the ceiling.** Twenty-two free parameters give the best
three-quarter of any run (IoU 0.878) while visibly splaying the tailplane in
the head-on view. More freedom keeps improving the objective and degrading the
model. Keep the parameter set small.

### Cross-run agreement is the usable check

Five fits with different parameter sets, objectives and units. A parameter they
agree on is supported; one that scatters is not. **This needs no measurement**
and is the practical form of the Tier 3 invariance check.

```
param     committed |      C      D     Cmn     Cnm    FREE | spread
c_outb       0.200  | 0.2858 0.2964  0.3062  0.2751  0.2960 |  11%  CONSISTENT
c_inb        0.265  | 0.2891 0.2806  0.3557  0.3114  0.3380 |  24%  moderate
x_le         0.304  | 0.2838 0.2912  0.2835  0.2894  0.2340 |  21%  moderate
c_tip        0.145  | 0.2154 0.2288  0.2767  0.2490  0.2178 |  26%  scattered
c_root       0.330  | 0.2880 0.3315  0.4156  0.3259  0.3955 |  36%  scattered
dihed        2.00   | 6.669  4.470   4.256   5.158   4.746  |  48%  scattered
```

**`c_outb` is the one well-supported finding**: every run puts the outer chord
at 275-306 mm against the committed 200 mm, a +43% increase, at 11% spread.
It corroborates entry 02's independent visual finding by a completely different
route. That is two methods agreeing, which is the strongest evidence this
session produced about the aircraft.

**Dihedral is more than 2°** — all five runs say so — but the magnitude scatters
4.3-6.7° and is therefore a direction, not a value. Report it as such.

The central question, honestly: **it is no longer established that optimising
against the silhouette corrupts geometry.** That claim rested on a dihedral
figure measured by hand — the evidence this plan forbids, and probably wrong.
What survives are the measurement-free checks: under those, C is refuted
(camera below an aircraft resting on a surface) and FREE is suspect (tail
deformation), while D and Cmn are not refuted by anything.

Still open: the minimax-vs-mean control was stopped early (1746 evaluations
against Cmn's 6390) and is being rerun.

## A geometry-fitting tool the agent can use in one call

Everything above is useless if fitting geometry means the agent writing a
CMA-ES driver. It wrote its own pose seeder twice in the original transcripts
and both attempts were killed by the probe budget; it must not now be asked to
write an optimiser as well. The whole capability has to be **one function with
guard rails baked in**, because every protection in this plan is one the agent
would otherwise have to remember.

### The call

```python
fit = fit_geometry(
    free = {
        # name          lower   upper   why it is a candidate
        "chord_outb":  (0.12,   0.34,  "entry 02: real outer TE lies aft of the model's"),
        "dihedral_deg":(-3.0,   9.0,   "head-on overlay shows more V than modelled"),
    },
    reliability = "normal",     # -> popsize and seed count
)
```

`views` is not a parameter: it always uses every reference with a mask, always
normalised by `sqrt(mask area)`, always aggregated as the mean. Those are the
three things that took a full session to get right and they are not the agent's
to re-decide.

### What comes back

A result that **prints as evidence, not as a number**:

```
fit_geometry — 2 free parameters, 2 views, 5 seeds, 412 s

parameter      committed    fitted   cross-seed    verdict
chord_outb        0.2000    0.2951   +/- 0.009    CONSISTENT
dihedral_deg      2.0000    4.83     +/- 1.21     SCATTERED  (direction only)

view            before    after
threequarter    2.92%     1.78%
headon          2.70%     1.75%
                                    both views improved

no parameter on a bound · no camera outside its stated hemisphere
```

Four things that are not optional:

- **Multi-seed always.** The cross-seed spread is the evidence; a single run is
  not a result. Five artefacts this session were single runs that looked like
  findings.
- **A verdict per parameter**, from that spread. `CONSISTENT` is reportable;
  `SCATTERED` is a direction, not a value, and must be declared as such.
- **Both-views-improved is stated explicitly.** A fit that improves one view and
  degrades another is a trade; the agent should see that without computing it.
- **Railed parameters and out-of-hemisphere cameras block the read**, the way
  `compare_to_photo` already refuses an untrustworthy pose.

### Guard rails the function enforces

| rail | why |
|---|---|
| at most ~8 free parameters | 22 free parameters gave the best three-quarter score of any run while visibly splaying the tailplane |
| every free parameter needs a written reason | forces the candidate to come from a finding, not from scanning for whatever moves the number |
| refuse if mask/model asymmetry exceeds a threshold | the four unmodelled propellers are the asymmetry the camera currently absorbs; fitting geometry against them fits the geometry to propellers |
| mesh resolution 6-8, popsize from `reliability` | the agent should not be choosing these |
| hard wall-clock budget, reported up front | ~400 s for a handful of parameters at resolution 6-8 |

### How the result enters the model

Each accepted parameter becomes a `fitted(...)` constant carrying its views,
its residual and its cross-seed spread — so the provenance scheme in Tier 2
does the rest, and the entry's declaration reads "fitted to 2 photographs,
+/- 0.009" rather than a bare number. A `SCATTERED` parameter cannot be written
as a value at all; it is declared as a direction, or left `invented`.

### Where it lives: inside `reconstruct`, not beside it

An earlier draft proposed a separate `nb refine`. That was wrong. The
reconstruction is what every later chapter forks, so the best model has to
exist from the start -- and a separate command recreates the exact failure the
transcripts showed, where run 2's wing finding sat in a `.qmd` while three
entries computed on geometry known to be wrong.

It is also what the 2026-10-03 plan already argued for: *"reconstruction is a
once-per-programme investment and every later chapter forks the model it
produces, so quality is worth far more than turns."* Fitting is that
investment.

**Which parameters should be free?** In `reconstruct` there are no prior
findings to justify a candidate -- but the system already knows the answer:
**the constants the run would otherwise invent.** The assumptions gate exists
to show the coordinator exactly those. Fit them instead of guessing them, and
the gate changes from a request to rubber-stamp a guess into a report of
evidence:

```
BEFORE   wing taper ratio: 0.704                   (invented -- accept?)

AFTER    chord_outb   0.200 -> 0.295  +/- 0.009    CONSISTENT  (5 seeds, 2 views)
         dihedral     2.0   -> 4.8    +/- 1.2      SCATTERED   (direction only)
```

A `CONSISTENT` parameter is committed as `fitted(...)`. A `SCATTERED` one
stays `invented`, with its direction recorded -- which is strictly more than
the coordinator gets today.

### So `reconstruct` runs several optimisations, of two kinds

| | cost | when |
|---|---|---|
| pose fit, 7 params per view | seconds | every overlay, throughout |
| joint geometry + pose fit | ~400 s | once, after the first model builds |
| a second joint round | ~400 s | only if the first moved geometry enough to open a different pose basin |

This is the main argument for the larger `reconstruct` budget the previous plan
asked for, and it is now a concrete number rather than a principle: roughly
15 minutes of fitting on top of the existing probe work, bought once per
aircraft, inherited by every chapter that forks it.

## Carried forward

- **Derive rather than assign** (2026-10-03, items 1–2). A target is only a
  check if computed from something more primitive than itself; the v1.0
  reconstruction assigned seven of eight. More important now, not less, since
  fitted geometry makes assignment easier to hide.
- **Target baseline** (item 7). Has its first real drift to justify it:
  0.41% → 5.86% within one run, uncaught.
- **Uncertainty bands** (alternative B). Still the strongest unexplored idea in
  the repo, and this session sharpens it: every performance number in
  `tubby-b-17` rests on a wing the notebook records as wrong in a known
  direction, and a band would say so in the entry rather than in a coordinator's
  note.

## Outstanding defects in the committed notebook

- `_model.py` carries a wing the notebook itself records as too narrow at the
  outer panel, and three performance entries computed on it.
- Entry 01 reports 5.86% when the run had 0.41% in hand.
- The 255 mm fuselage width in `_model.py` came from a hand measurement at the
  Q1 assumptions gate and has never been independently checked. Under this
  plan's rules it should be re-derived by fitting, or declared `invented`.
