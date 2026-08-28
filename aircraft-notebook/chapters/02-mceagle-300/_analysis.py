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
# this, delete _freeze/chapters/02-mceagle-300/ and render normally.
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
    `run_with_stability_derivatives()` returns x_np from the identical formula,
    but by finite-differencing at a point; at this Reynolds number Cm against CL
    is genuinely curved, so that answer moves with the angle you take it at --
    147 to 197 mm across the same band. This returns the average slope over a
    stated range instead. Neither removes the choice, so `band` is an explicit
    argument every entry declares.
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
