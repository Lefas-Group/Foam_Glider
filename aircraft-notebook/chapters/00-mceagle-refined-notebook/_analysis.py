# =============================================================================
# Analysis machinery for the McEagle-300 chapter.
#
# _model.py says what the aircraft IS. This file says how the chapter MEASURES
# it -- the calculations that more than one entry performs. It is exec'd into
# the same namespace as the model, immediately after it, so everything here can
# use `mceagle`, `polars`, `c_w` and the rest without qualification.
#
# What belongs here, and when a helper earns promotion into it, is in the
# skill's "Where machinery lives". Nothing is promoted before a second entry
# needs it. _scratch/probe.py prints
# api() on every run, so what is already here is on screen before anything gets
# written -- four subtly different neutral points existed because nothing
# advertised the first one.
#
# Rendering and discovery helpers are NOT here; they are notebook furniture and
# live in ../../_notebook.py.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete _freeze/chapters/00-mceagle-refined-notebook/ and render normally.
# =============================================================================
##### The standard sweep
# Wide enough to show the stall in both directions, fine enough that a fit over
# any sub-band has plenty of points. Entries that want the whole polar and
# entries that want a slope both work from this, so they cannot disagree about
# resolution.
ALPHA_SWEEP = np.linspace(-15, 15, 121)   # deg


def neutral_point(airplane=None, band=(0.0, 8.0), V=6.0):
    """
    Neutral point [m aft of the nose], from a straight-line fit of Cm vs CL.

    The moment reference is read off the airplane rather than passed in.
    AeroBuildup reports Cm about `xyz_ref`, and the answer is only meaningful
    measured from that same station; sourcing the two separately silently
    biases the result by the offset between them. That error once doubled a
    reported sensitivity before it was caught.

    This is one of the few places worth NOT using the library's own function.
    `run_with_stability_derivatives()` returns x_np from the identical formula
    (`xyz_ref[0] - Cma / CLa * c_ref`), but takes the slope as a one-sided
    finite difference over a hard-coded 0.001 rad. At this Reynolds number Cm
    against CL is genuinely curved -- shrinking that step does not move the
    answer, so the variation is the aircraft rather than the arithmetic -- and
    the point answer therefore moves with the angle you take it at, roughly
    149 to 199 mm across alpha 0-8 deg at the time of writing.

    This returns the average slope over a stated range instead. Neither removes
    the choice, so `band` is an explicit argument every entry declares.

    Those millimetres are a snapshot, not a guarantee: they were 147 to 197
    before the dihedral and c_ref corrections. Recompute before quoting them.
    """
    ap = mceagle if airplane is None else airplane
    p = polars(ALPHA_SWEEP, V=V, airplane=ap)
    CL, Cm = np.array(p["CL"]), np.array(p["Cm"])
    k = (ALPHA_SWEEP >= band[0]) & (ALPHA_SWEEP <= band[1])
    return ap.xyz_ref[0] - np.polyfit(CL[k], Cm[k], 1)[0] * c_w


def ballast_for(x_cg_target, x_ballast=0.0, mp=None):
    """
    Point mass [kg] at `x_ballast` that moves the CG to `x_cg_target`.

    The CG of structure plus ballast is a mass-weighted mean, so the mass
    needed follows from the lever ratio. Defaults to the unballasted airframe.
    """
    m = mass_properties() if mp is None else mp
    return m.mass * (m.x_cg - x_cg_target) / (x_cg_target - x_ballast)


def static_margin(x_cg, x_np):
    """Static margin as a fraction of the mean chord. Positive is stable."""
    return (x_np - x_cg) / c_w


##### Flat patterns
# Outlines for cutting templates, in millimetres because that is what a
# template is measured in. Generated from the same chord tables and depth
# profile the aerodynamics uses, so a template cannot drift from the aircraft.


def sym_surface(eta, chord, semi):
    """
    A symmetric flat pattern [mm]: straight leading edge, chord table swept to
    both tips. Span along x, chord along y -- paper is landscape, so are wings.
    """
    y = np.concatenate([-eta[::-1], eta[1:]]) * semi * 1e3
    c = np.concatenate([chord[::-1], chord[1:]]) * 1e3
    return np.column_stack([np.concatenate([y, y[::-1]]),
                            np.concatenate([np.zeros_like(y), c[::-1]])])


def fin_outline():
    """The fin's flat pattern [mm]: straight trailing edge, swept leading edge."""
    z, c = fin_eta * b_v * 1e3, fin_c * 1e3
    return np.column_stack([np.concatenate([np.zeros_like(z), -c[::-1]]),
                            np.concatenate([z, z[::-1]])])


def fuselage_outline(x0, x1):
    """
    A slice of the fuselage plate between two stations [mm].

    The top edge is straight -- it is what carries the wing -- and the belly
    hangs below it, so the outline is the depth profile mirrored about y = 0.
    """
    xs = np.linspace(x0, x1, 200)
    d = np.interp(xs, fus_x, fus_d)
    return np.column_stack([np.concatenate([xs, xs[::-1]]) * 1e3,
                            np.concatenate([np.zeros_like(xs), -d[::-1]]) * 1e3])


def nest(parts, layout, sheet):
    """
    Place parts at given bottom-left corners and check the packing.

    Raises rather than returning a flag: a template that overhangs the sheet or
    overlaps itself is worse than no template, and it should stop the render.
    """
    placed = {n: p - p.min(axis=0) + np.array(layout[n]) for n, p in parts.items()}
    bb = lambda p: (p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max())
    for n, p in placed.items():
        x0, y0, x1, y1 = bb(p)
        if x0 < 0 or y0 < 0 or x1 > sheet[0] or y1 > sheet[1]:
            raise ValueError(f"{n} falls off the {sheet[0]:.0f}x{sheet[1]:.0f} sheet")
    names = list(placed)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ax0, ay0, ax1, ay1 = bb(placed[a])
            bx0, by0, bx1, by1 = bb(placed[b])
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                raise ValueError(f"{a} overlaps {b}")
    return placed


def trim(mass, x_cg, V=5.0, alpha=None, iters=60, tol=1e-9):
    """
    The angle of attack and speed at which an aircraft of this mass and balance
    flies itself: pitching moment about the CG zero, lift equal to weight.

    Takes mass and CG rather than a MassProperties, so it works for a glider
    that has been built and weighed as readily as for one that has been summed.

    AeroBuildup reports Cm about `xyz_ref`, so it is shifted to the CG first:
    Cm_cg = Cm_ref + CL * (x_cg - x_ref) / c_ref. Iterated rather than solved,
    because CL and V each determine the other and the speed moves the polar
    through Reynolds number.

    `slope` is dCm/dalpha at the crossing -- negative is a restoring moment.
    That is the honest stability test: it needs no neutral point, so it does not
    inherit the ambiguity in defining one.

    Iterates to `tol` rather than a fixed trip count, and raises if it runs out
    of iterations. Each trip is one AeroBuildup call, and calls are the whole
    budget here; a fixed count both pays for trips it does not need and hides
    non-convergence, because a loop that never settled returns exactly like one
    that did.
    """
    a = np.linspace(-2, 14, 161) if alpha is None else alpha
    for _ in range(iters):
        p = polars(a, V=V)
        Cm_cg = np.array(p["Cm"]) + np.array(p["CL"]) * (x_cg - x_qc_w) / c_w
        i = int(np.argmin(abs(Cm_cg)))
        V, V_prev = (2 * mass * 9.81
                     / (1.225 * S_w * float(np.array(p["CL"])[i]))) ** 0.5, V
        # alpha is picked off a fixed grid, so once the index settles the next
        # speed is bit-for-bit the previous one and this is an exact stop, not
        # an approximate one. If the index instead oscillates between two
        # neighbours the difference never falls below tol and the guard fires --
        # which is the point: a silent non-convergence used to look identical to
        # a converged answer.
        if abs(V - V_prev) <= tol * max(1.0, abs(V)):
            break
    else:
        raise RuntimeError(
            f"trim() did not converge in {iters} iterations: speed still moving "
            f"by {abs(V - V_prev):.3g} m/s at mass={mass:.4g} kg, x_cg={x_cg:.4g} m")
    CL, CD = float(np.array(p["CL"])[i]), float(np.array(p["CD"])[i])
    return dict(alpha=a[i], V=V, CL=CL, CD=CD, LD=CL / CD,
                slope=(Cm_cg[i + 1] - Cm_cg[i - 1]) / (a[i + 1] - a[i - 1]),
                Re=p["Re_c"], sink=V / (1 + (CL / CD) ** 2) ** 0.5)


def stall(V, alpha=None):
    """
    Angle of attack where lift first stops rising, and the CL there.

    The FIRST peak, deliberately, not the global maximum. NeuralFoil's curve
    turns over near 10 degrees, dips, and then climbs again well past 20 -- deep
    post-stall behaviour the model is not meant to represent. A global argmax
    picks that second branch at some speeds and reports a stall angle of 16-24
    degrees, which is nonsense for this wing.
    """
    a = np.linspace(0, 24, 241) if alpha is None else alpha
    CL = np.array(polars(a, V=V)["CL"])
    for i in range(1, len(a) - 1):
        if CL[i] >= CL[i - 1] and CL[i] > CL[i + 1]:
            return a[i], float(CL[i])
    return a[int(np.argmax(CL))], float(CL.max())
