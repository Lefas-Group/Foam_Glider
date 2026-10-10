# Checking the model against photographs

`_reference/` holds photographs of the real aircraft, each with a mask the
coordinator cut by hand. Four functions use them, and they are already in
your probe namespace — do not `import` or `getsource` them.

## The two that DRAW

    compare_to_photo(airplane, name, pose=None, fill=0.22) -> (rgb, note)
    show_comparison(airplane, name, pose=None, fill=0.22, ax=None) -> note

`show_comparison` is `compare_to_photo` onto a matplotlib axis and is what an
entry calls. Both fit the camera by symmetric chamfer distance between
outlines, colour each component separately, and return a NOTE. Neither
returns a score, deliberately: a number on the result is a number that gets
chased, and the fit that maximised overlap ran the outline through the
fuselage.

### Reading the note

    camera 36° ABOVE, azim 118°, roll 19.7°. Fit: 2.90% of sqrt(mask area).
    Pose: good. POSE CONVERGED — a second seed agrees to 0.03 pp, so the
    2.90% left is SHAPE, not camera, and no further seed will move it.
    Error sits on: Fuselage 38%, Canopy 21%, Intake 14%. Free the constants
    those point at: fit_geometry(free={...}, poses={'belly': (36.0, 118.2,
    19.7)}).

Residuals are normalised by `sqrt(mask area)` so views of different size are
comparable. **There is no pixel count in the note on purpose** — raw pixels
make damage to a small view look cheap, and two of them side by side invite a
division that means nothing.

**The note does not repeat the view name.** You passed it. A handle is a
coordinator's label and nothing measured it: this notebook's `belly` is a
photograph taken from *above*, and the plain-words viewpoint is there so a
reference description that says "from below" is contradicted rather than
co-signed.

| what the note says | what it means | what to do |
|---|---|---|
| `POSE NOT CONVERGED` | a parameter sat on a bound | read nothing; assert a `pose=` |
| `Pose: DOUBTFUL` (above 4%) | the outline does not track the aircraft | assert a `pose=`, or ask for a better photograph |
| `POSE CONVERGED` | two seeds agree; the rest is the MODEL | `fit_geometry` — see below |
| near 1%, nothing further | converged and clean | read shape from it |

### Do not go looking for a better basin yourself

Above 1.2 % the function fits a second time from a different CMA seed and
tells you which case you are in. You do not need to do this, and you should
not: `_fit_pose` already screens 36 seeds and runs CMA-ES, and a `pose=`
*narrows* the search to ±25° around itself, so perturbing a converged fit can
only make it worse.

Measured on the F-16 Viper, cold start against a reseed:

    studio   2.05%  ->  2.04%     elev 19.9  azim 209.6  roll -13.4
    belly    2.97%  ->  2.90%     elev 36.0  azim 118.2  roll  19.7

The cold search had already found both poses to a tenth of a degree. The run
that read the old note's "try hint=(elev±5, azim±10)" as an instruction wrote
a 3×3 grid, had both probes killed on budget, and the two studio
perturbations that did return were **8.89 %** and **4.79 %**.

You can still tell the two apart by LOOKING: every component displaced in the
same direction is a pose error, one component wrong while the others sit
right is a shape error. Do not start moving geometry until the outline as a
whole lands on the subject.

### What you may conclude from an overlay

**PROPORTIONS, NEVER ABSOLUTES.** A two-degree pose error moves points by 6 mm
on average and 11 mm at worst — the size of the discrepancies you are looking
for. So *"the tailplane chord is 1.4× what it should be relative to the wing"*
is sound and *"the tailplane is 12.7 mm too long"* is not. Absolute dimensions
come from the brief, never from an overlay.

**A PHOTOGRAPH IS NOT A TARGET.** Fix what is structurally wrong — a part
missing, a fuselage section that should be a box and is an ellipse, a canopy
smoothed into the loft — declare what you inferred, and leave the rest. A model
tuned until the overlay looks right has been fitted to the thing it was meant
to be checked against. That is why no function here returns a score.

**DO NOT CITE AN OVERLAY THE NOTE HEDGED.** `POSE HEDGED`, `POSE DISPUTED` and
`Pose: DOUBTFUL` are the tool saying it does not have the evidence. An entry
claiming the overlay *confirms* the shape over one of those is claiming
evidence it was told it did not have. Spend one more fit, or say in the entry
what the note said.

**THE ENTRY SHOWS THE VERDICT, NOT ONLY THE PICTURE.** Bind the note in the
figure cell — `note = show_comparison(airplane, "VIEW", pose=…)` — and put what
it says on the page: the residual, and the pose. A bare call discards it and
leaves the reader an overlay with no way to know whether it can be read. Rule
45 warns about this.

### What each call costs, so you can stop timing them

Measured on the FT A-10 Warthog's three views, one machine, one model:

    compare_to_photo(ap, v)                       cold     41-78 s
    compare_to_photo(ap, v, pose=p)               fitted   10-46 s
    compare_to_photo(ap, v, pose=p, refit=False)  pinned     3-4 s

`refit=False` PINS the camera: the angles are taken as given and only scale,
translation and distance are found. The residual lands within 0.01–0.32 pp of
the fitted one at a pose that had already converged, and the note says **POSE
PINNED** so nobody reads an assertion as a measurement.

Use it to REDRAW a camera you have already converged on and printed — which is
most of the overlays a build loop draws. Fit once per view per shape; pin for
everything after. **A render with a `pose=` pins automatically**, so an entry
pays seconds rather than the ~25 s a panel used to add to `ENTRY_CEILING`.

Do not time these yourself. A run spent four turns measuring exactly the table
above, and the numbers are here so that it is one read instead.

### The panel, in one call

    fig, notes = show_all_views(airplane)                 # probe
    fig, notes = show_all_views(airplane, poses={...})    # entry

Every reference view, side by side, with the notes. In a probe the poses this
run already found are reused; **an entry should name them all**, because at
render there is no probe history and a pose written in the entry is one a
reader can see and a later run can argue with.

Nine turns and ~400 s of one reconstruction went into hand-building this
figure — `plt.subplots(1, 3)`, three calls, `tight_layout`, `savefig` —
rewritten four times after a kernel restart took `plt` away and two probes
were killed on a budget nobody could size yet.

## The one that FITS GEOMETRY

    fit_geometry(free, views=None, poses=None) -> _FitResult

This is how geometry is obtained, and it is what a residual stuck above ~1.2%
is asking for. `free` maps a module-level `_model.py` constant to
`(low, high, why)` — the reason is required, because a parameter freed
because a finding pointed at it is evidence and one freed because it moved
the number is not.

    fit = fit_geometry(free={
        "wing_chord_tip": (0.06, 0.16, "entry 01: outer TE sits aft of the model"),
    }, poses={"belly": (36.0, 118.2, 19.7), "studio": (19.9, 209.6, -13.4)})
    print(fit)
    fit.apply()

**`free` takes NAMES, so the constant has to have one.** A dimension written
inline — `asb.FuselageXSec(xyz_c=[0.35, 0, 0.005], width=0.12, …)` — cannot
be fitted, and `fit_geometry` raises `KeyError: not a module-level constant`.
That is not a naming slip to work around by hand-setting the value; it means
the model is not written in a form the photographs can argue with, and the
fix is to promote those literals to named constants at the top of
`_model.py` first.

`poses` SEEDS each view's camera from a note you have already read, so the
fit cannot settle in a different basin from the picture the free set was
chosen off. A seed is not a setting: elevation and azimuth are still
searched ±25°. The seed residual is printed per view, so a bad seed comes
back as a worse number rather than being believed.

**NEVER TYPE A FITTED NUMBER YOURSELF.** `apply()` writes them into
`_model.py` and prints each old → new, which is how the number in the model
stays the number the fit produced. A run once wrote `width=0.185` six lines
after measuring 282 mm, and then declared the 185.

Read the spread beside each value: CONSISTENT means the photographs constrain
that dimension, SCATTERED means they do not and it stays a declared guess.

**Refit only for a structural reason** — a parameter on a bound, a SCATTERED
parameter to drop, a component the census named. Refitting because you would
like a better number is the one thing this machinery exists to prevent.

Not yours to choose: every reference with a mask is used; each view is
normalised by `sqrt(mask area)` before the views are combined; the views
combine by MEAN; three seeds run.

**Never free a published dimension.** Span and length are the scale
reference, and freeing span makes the fit degenerate against camera
distance.

### What a fit costs, and how to budget it

**This is the expensive call. Budget it in minutes, not tens of seconds.**
Cost goes as `3 seeds × views × free parameters`. Measured, one free
parameter over three views: a 200 s probe spent 195 s and reported **all
three seeds cut short at ~22% of their search**, wanting about 220 s each —
so roughly 650 s to converge. An older measurement on one view put a single
parameter at 334–385 s.

Ask for the budget up front. A fit that is killed loses everything it
computed; a fit that is merely cut short returns its best and SAYS SO:

    >>> 3 of 3 seeds RAN OUT OF PROBE TIME rather than converging.
    >>> The worst managed 76 of 350 iterations -- 22% of the search.
    >>> These values are a best-so-far, and the spread above is not
    >>> evidence that anything is pinned.

**Read that warning when it appears.** A cut-short spread is not a
consistency check — seeds that never finished cannot agree or disagree — so
a value under it is still a guess, however tight the millimetres look. Free
fewer constants, or ask for more pool.

## Coverage

    completeness(airplane, name, pose=None)

What fraction of the photograph's mask the model covers, and what it covers
outside it. A whole component missing from the model shows here as mask the
model never reaches.

It sorts every component you built into three states, and they want three
different things from you:

| state | what the note says | what it means |
|---|---|---|
| supported | nothing | its silhouette is on the mask; the photographs agree with it |
| outside | `OUTSIDE THE PHOTOGRAPH: <name>` | it is drawing where the aircraft is not — too big, misplaced, or not real |
| unseen | `THE SILHOUETTE CANNOT SEE: <name>` | it is inside the body from this camera; no overlay can argue with it at all |

**UNSEEN IS NOT SUPPORTED.** A component buried inside the body contributes
no outline, so a good fit does not confirm it and a bad one does not refute
it — and it is still carrying mass, area and lift. If a component is unseen in
*every* view, the photographs are not what justifies it: either something else
does and `declare_input` says so, or you are modelling a part nobody can check.

**Do not free an unseen component's constants.** `fit_geometry` moves the
residual through the outline, and there is no outline. Measured on the FT A-10
Warthog: its `Nacelle Pylons` drew 3–7 % of the model's outer silhouette and
the pose note charged it 14–20 % of the residual — second or third on every
view, above the tailplane and the fins. That was the note's fault and is fixed;
the shares are now attributed on the union silhouette, so a buried component
scores ~0 %. If you are reading an older entry that freed constants on such a
hint, that fit could not have moved anything.

### Is it earning its place?

    ablate(airplane, "Nacelle Pylons", poses={...})

The residual for every view **with** the component and **without** it, both at
the same pinned camera. One probe, and it edits nothing.

**It gives no verdict on a component the silhouette cannot see**, and that
restriction is the most important thing it knows. A buried part can move the
residual by contributing *area* — closing a gap in the union outline — which is
indistinguishable, in the number, from contributing correct *shape*.

The Warthog's pylon is the case this was written for:

    front-right-above   2.36%  ->  3.88%   worse without  (draws 3% of its outline)
         removing it opens silhouette against: Fuselage, Nacelle Left, …
    rear-left-above     2.83%  ->  2.63%   better without (draws 5% of its outline)
    thumbnail-front-left 1.83% ->  2.07%   worse without  (draws 7% of its outline)

Two views got **worse** without it, which reads as "the photographs want this
part" and is not what it means. The pylon spans the gap between fuselage and
nacelle; delete it and a hole opens that the real aircraft does not have,
because **the fault is next door** — a fuselage too narrow, or nacelles too far
outboard. The plate was patching a neighbour's error, and the chamfer cannot
tell you so: it just sees the hole close.

So read the line underneath instead. **`removing it opens silhouette against:
Fuselage` in every view is the finding** — free the fuselage's constants, not
the pylon's. It is the same move `completeness` makes for a gap in the mask ("a
gap TOUCHING a component means that component is too small"), in the other
direction.

For a component that *does* draw real outline, the three outcomes read as you
would expect: better without it in every view, the silhouettes do not want it;
worse in every view, the photographs are holding it in place — though still
check what the hole runs against; mixed, usually real and the wrong size.

Whether an invisible component belongs at all is a question for the build
documentation, not for the overlay. The photographs have no opinion.

### Changing the component list after a fit

Adding or deleting a component **invalidates the pose and every fitted
constant**. Both were found with the old component list, and the camera
absorbed some of that component's error; reusing either afterwards measures the
part you removed. The order is:

1. edit `_model.py`
2. refit the poses **cold** — do not pass the old ones, do not reuse the store
3. `fit_geometry` again on the constants the new notes point at
4. report the residual before and after, per view

That is an entry's worth of work with a table as its answer — "Does the model
need the nacelle pylon?" — not a silent patch to a model other entries already
rest on.
