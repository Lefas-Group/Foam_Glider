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
right is a shape error.

## The one that FITS GEOMETRY

    fit_geometry(free, reliability="normal", views=None, poses=None) -> _FitResult

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
searched ±25°, and a wrong seed comes back with a worse printed residual
rather than being believed.

Not yours to choose: every reference with a mask is used; each view is
normalised by `sqrt(mask area)` before the views are combined; the views
combine by MEAN; several seeds run.

**Never free a published dimension.** Span and length are the scale
reference, and freeing span makes the fit degenerate against camera
distance.

## Coverage

    completeness(airplane, name, pose=None)

What fraction of the photograph's mask the model covers, and what it covers
outside it. A whole component missing from the model shows here as mask the
model never reaches.
