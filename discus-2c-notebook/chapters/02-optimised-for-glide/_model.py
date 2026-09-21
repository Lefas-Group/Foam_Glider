# =============================================================================
# Discus-2c optimised for best glide ratio.
#
# FORKED FROM chapters/01-calibrated-discus-2c/_model.py, taken from the
# uncommitted working tree on 2026-09-17 -- chapter 01 had not been committed
# when this fork was made, so there is no parent commit to name here.
#
# Chapter 01 stays valid and is the BASELINE this chapter is measured against:
# it reconstructs the real aircraft and validates it against published figures.
# Here the geometry stops being fixed and becomes free variables, so the two
# answer different questions and both are worth keeping.
#
# Deliberate differences from the parent, and nothing else:
#   * span, the four station chords and the four station twists become design
#     variables (`optimise()` at the end of this file);
#   * the structural proxy `root_bending_proxy()` is added, so the optimizer can
#     be held to the parent's limit-load root bending moment;
#   * DRAG_OFFSET is frozen at the parent's calibrated value and carried across
#     as a property of construction quality rather than of planform -- see the
#     note on it below, because it is the assumption this chapter leans on most.
# `_analysis.py` was copied unchanged and has since gained `best_glide()`, which
# this chapter's entries need and the parent's do not; nothing else differs.
#
# Loaded two ways, both by exec into the caller's namespace: entries via the
# _model.qmd shim, scratch scripts via _scratch/probe.py.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete the chapter's _freeze/ directory before re-rendering.
# =============================================================================

##### Imports
import contextlib
import io

import aerosandbox as asb
import aerosandbox.numpy as np
import matplotlib.pyplot as plt
from aerosandbox.structures.tube_spar_bending import TubeSparBendingStructure

##### Published figures
# These are the targets the reconstruction is held to, not model outputs. The
# first three define the aircraft; the last two are what the calibration and
# its validation are measured against.
SPAN = 18.0                 # m, tip to tip
WING_AREA = 11.36           # m^2, reference area
MASS = 400.0                # kg, unballasted solo -- Specified, 2026-09-17
GRAVITY = 9.81              # m/s^2  (spelled out: `G` has shadowed this before)
LD_MAX_PUBLISHED = 45.0     # best glide ratio, the calibration target
SINK_MIN_PUBLISHED = 0.55   # m/s, minimum sink -- held back as the validation

##### Wing planform
# Four stations over the semi-span. The chord distribution is a reconstruction;
# only its INTEGRAL is published, so the chords below are scaled by a single
# factor that makes the planform area equal WING_AREA exactly rather than
# approximately. Asserting both a shape and an area without reconciling them is
# how a model comes to disagree with its own reference area.
# Named without a leading underscore deliberately: `from _probe_base import *`
# skips underscored names, so a scratch probe could not reach these while an
# entry could -- the probe and the entry would then be looking at different
# models, which is the one thing scratch must never do.
STATION_Y = np.array([0.0, 2.5, 5.5, 9.0])          # m from centreline
STATION_C = np.array([0.855, 0.800, 0.600, 0.320])  # m, before area scaling
STATION_TWIST = np.array([0.0, -0.4, -1.0, -2.0])   # deg, washout to the tip
STATION_TC = np.array([0.164, 0.164, 0.126, 0.126])  # section thickness ratio

_semi_area = np.sum(0.5 * (STATION_C[:-1] + STATION_C[1:]) * np.diff(STATION_Y))
CHORD_SCALE = (WING_AREA / 2) / _semi_area
STATION_C = STATION_C * CHORD_SCALE

DIHEDRAL_DEG = 2.5          # deg, constant along the span
WING_LE_X = 1.70            # m aft of the nose, at the root
CG_MAC_FRACTION = 0.30      # CG as a fraction of MAC -- assumed, typical glider

# Root and tip sections. The real Discus-2 section is not something this model
# knows; these are the Wortmann pairing typical of the generation, with the
# right thickness progression (16.4% root -> 12.6% tip).
AIRFOIL_ROOT = asb.Airfoil("fx61163")
AIRFOIL_TIP = asb.Airfoil("fx60126")
AIRFOIL_TAIL = asb.Airfoil("naca0010")


def _wing():
    """The main wing: four reconstructed stations, unswept at the quarter chord."""
    xsecs = []
    for y, c, twist in zip(STATION_Y, STATION_C, STATION_TWIST):
        xsecs.append(asb.WingXSec(
            # Quarter chord held straight, so leading-edge sweep follows taper
            # alone -- the usual arrangement on a glider of this class.
            xyz_le=[WING_LE_X + 0.25 * (STATION_C[0] - c),
                    y, y * np.tand(DIHEDRAL_DEG)],
            chord=c,
            twist=twist,
            airfoil=AIRFOIL_ROOT if y < 4.0 else AIRFOIL_TIP,
        ))
    return asb.Wing(name="Wing", symmetric=True, xsecs=xsecs)


def _fuselage():
    """Slender fuselage as a body of revolution of equivalent cross-sectional area."""
    x = [0.00, 0.30, 0.90, 1.60, 2.40, 3.50, 4.50, 5.50, 6.50]
    r = [0.02, 0.17, 0.30, 0.345, 0.32, 0.22, 0.15, 0.10, 0.06]
    return asb.Fuselage(
        name="Fuselage",
        xsecs=[asb.FuselageXSec(xyz_c=[xi, 0, 0], radius=ri) for xi, ri in zip(x, r)],
    )


def _tails():
    """T-tail: fin carrying an all-moving tailplane at its top."""
    fin = asb.Wing(name="Fin", symmetric=False, xsecs=[
        asb.WingXSec(xyz_le=[5.35, 0, 0.10], chord=0.95, airfoil=AIRFOIL_TAIL),
        asb.WingXSec(xyz_le=[5.85, 0, 1.00], chord=0.50, airfoil=AIRFOIL_TAIL),
    ])
    tailplane = asb.Wing(name="Tailplane", symmetric=True, xsecs=[
        asb.WingXSec(xyz_le=[5.80, 0.00, 1.02], chord=0.50, airfoil=AIRFOIL_TAIL),
        asb.WingXSec(xyz_le=[5.95, 1.08, 1.02], chord=0.36, airfoil=AIRFOIL_TAIL),
    ])
    return [fin, tailplane]


##### The aircraft
# Built once at import. Rebuilding it per call showed up as the dominant cost
# before this was hoisted -- geometry construction is not free, and nothing
# about it varies with the operating point.
WING = _wing()
MAC = WING.mean_aerodynamic_chord()
XYZ_REF = np.array([WING_LE_X + 0.25 * STATION_C[0]
                    + (CG_MAC_FRACTION - 0.25) * MAC, 0.0, 0.0])

AIRPLANE = asb.Airplane(
    name="Discus-2c (reconstructed)",
    xyz_ref=XYZ_REF,
    wings=[WING, *_tails()],
    fuselages=[_fuselage()],
    s_ref=WING_AREA, c_ref=MAC, b_ref=SPAN,
)


##### Structure
# A spar the real aircraft does not have. AeroSandbox models bending in a tube
# only, and a glider spar is a box with caps at the skin -- so this is a stand-in
# sized to carry a REALISTIC STIFFNESS, not a guess at how the wing is built. Its
# material volume is therefore meaningless as a spar mass: a tube puts material
# at the neutral axis, where it does nothing for bending.
#
# Sized so that peak stress at limit load sits inside carbon's allowable and the
# root EI lands near 1.3e6 N.m^2 -- which independently reproduces the ~3 Hz
# first bending frequency expected of an 18 m sailplane wing. An earlier pass at
# 80% depth and 6 mm walls gave a 3.37 m tip deflection, a third of the
# semi-span, which is how the sizing came to be checked at all.
SPAR_DEPTH_FRACTION = 0.95    # of local section thickness; caps sit at the skin
SPAR_WALL_ROOT = 0.011        # m
SPAR_WALL_TIP = 0.0015        # m
SPAR_MODULUS = 135e9          # Pa, standard-modulus carbon


def wing_spar(station_y, load_per_metre):
    """
    The chapter's spar, loaded by a spanwise airload, solved for bending.

    Wraps the library's Euler-Bernoulli tube rather than integrating by hand, so
    the entries get `bending_moment`, `shear_force`, `stress_axial` and the
    deflected shape from one object. It solves on construction and prints an
    IPOPT banner, which is noise on a rendered page, so that is swallowed here
    rather than in every entry that builds one.

    Args:
        station_y: spanwise stations of the load, m from centreline.
        load_per_metre: airload at those stations, N/m.
    """
    def chord_at(y):
        return np.interp(y, STATION_Y, STATION_C)

    def diameter(y):
        return SPAR_DEPTH_FRACTION * chord_at(y) * np.interp(y, STATION_Y, STATION_TC)

    with contextlib.redirect_stdout(io.StringIO()):
        return TubeSparBendingStructure(
            length=SPAN / 2,
            diameter_function=diameter,
            wall_thickness_function=lambda y: np.interp(
                y, [0.0, SPAN / 2], [SPAR_WALL_ROOT, SPAR_WALL_TIP]),
            bending_distributed_force_function=lambda y: np.interp(
                y, station_y, load_per_metre),
            elastic_modulus_function=SPAR_MODULUS,
        )


##### The analysis
def aero(alpha, speed, altitude=0.0):
    """
    One AeroBuildup call over paired (alpha, speed) arrays.

    Vectorized deliberately: a build-up call costs about the same for one
    operating point as for six hundred, because alpha and velocity ride along
    inside it. So every caller here assembles the whole set of points it wants
    and asks once -- the number of CALLS is what an entry costs, not the number
    of points, and a loop is where calls hide.

    Counted into `aero_cost` so footer() can report what the entry spent.
    """
    started = time.perf_counter()
    op_point = asb.OperatingPoint(
        atmosphere=asb.Atmosphere(altitude=altitude),
        velocity=speed,
        alpha=alpha,
    )
    result = asb.AeroBuildup(
        airplane=AIRPLANE, op_point=op_point, xyz_ref=XYZ_REF
    ).run()
    aero_cost["calls"] += 1
    aero_cost["seconds"] += time.perf_counter() - started
    return result


def trim_polar(speed, mass=MASS, altitude=0.0, tol=1e-6, max_passes=40):
    """
    Angle of attack, CL and CD for steady trimmed glide at each speed.

    Solves L = W*cos(gamma) at every speed at once, by secant iteration on
    alpha. Iterating to a TOLERANCE rather than a fixed pass count is the point:
    a `for ... in range(n)` around a solve either stops short of convergence or
    pays for passes nobody needed, and it hides the call count either way.

    The glide angle is folded into the residual rather than assumed small. It
    is small -- about 1.3 deg at best glide, so cos(gamma) departs from 1 by
    0.03% -- but the model can compute it, so it is not assumed.

    Returns the converged state plus the passes it took, so a caller can see
    the cost rather than infer it.
    """
    speed = np.atleast_1d(np.array(speed, dtype=float))
    weight = mass * GRAVITY
    dynamic_pressure = 0.5 * asb.Atmosphere(altitude=altitude).density() * speed ** 2

    def residual(alpha):
        result = aero(alpha, speed, altitude)
        lift_coeff, drag_coeff = result["CL"], result["CD"]
        # Self-consistent: the lift needed depends on the glide angle, which
        # depends on the lift-to-drag ratio at this same alpha.
        cos_gamma = np.cos(np.arctan2(drag_coeff, lift_coeff))
        required = weight * cos_gamma / (dynamic_pressure * WING_AREA)
        return lift_coeff - required, result

    alpha_prev = np.zeros_like(speed)
    alpha_curr = np.full_like(speed, 4.0)
    res_prev, _ = residual(alpha_prev)
    res_curr, result = residual(alpha_curr)
    passes = 2

    while np.max(np.abs(res_curr)) > tol and passes < max_passes:
        # Secant step, guarded where two passes gave the same residual: that
        # division is 0/0 at a converged point, and unguarded it turns a solved
        # speed back into a NaN that then poisons the max() above.
        slope = res_curr - res_prev
        usable = np.abs(slope) > 1e-14
        step = np.where(usable,
                        res_curr * (alpha_curr - alpha_prev)
                        / np.where(usable, slope, 1.0),
                        0.0)
        alpha_prev, res_prev = alpha_curr, res_curr
        alpha_curr = np.clip(alpha_curr - step, -8.0, 16.0)
        res_curr, result = residual(alpha_curr)
        passes += 1

    return {
        "speed": speed,
        "alpha": alpha_curr,
        "CL": result["CL"],
        "CD": result["CD"],
        "passes": passes,
        "residual": np.max(np.abs(res_curr)),
    }


def glide(polar, drag_offset=0.0):
    """
    Glide ratio and sink rate from a trimmed polar, with a parasite drag offset.

    `drag_offset` is the one calibrated scalar in the chapter: everything the
    build-up does not see -- surface waviness, control-surface and airbrake-cap
    gaps, sealing tape, wing-fuselage interference, the instrument static ports.
    It shifts CD only, so it leaves the trimmed alpha and CL untouched and can
    be applied to an already-computed polar without re-running any aero.
    """
    drag_coeff = polar["CD"] + drag_offset
    glide_ratio = polar["CL"] / drag_coeff
    gamma = np.arctan2(1.0, glide_ratio)
    return {
        "L_over_D": glide_ratio,
        "sink": polar["speed"] * np.sin(gamma),
        "CD_total": drag_coeff,
    }


def calibrate(polar, target_LD=LD_MAX_PUBLISHED, tol=1e-9, max_passes=60):
    """
    The drag offset that makes the model's best glide ratio match the published one.

    Costs NO aero calls. The offset shifts CD without touching CL or the trimmed
    alpha, so the whole calibration runs on arrays the caller already has --
    which is why `polar` is passed in rather than recomputed here.

    THE OFFSET IS SIGNED, and the sign is a result worth reading rather than an
    implementation detail. Positive means the reconstruction is cleaner than the
    real aircraft and needs drag added -- the expected direction, since a
    build-up cannot see sealing tape, gaps or surface waviness. NEGATIVE means
    the reconstruction is draggier than the real aircraft, and says the error is
    in the reconstruction itself: too much wetted area, or a section whose
    predicted laminar run falls short of the real one. An earlier version of
    this searched non-negative offsets only, and on a model that was already
    short of the target it returned zero -- a calibration that silently declined
    to calibrate, reported as success.

    Bisection rather than secant: max(L/D) over a discrete speed grid is
    piecewise-smooth with kinks where the argmax moves between grid points, and
    a secant step lands badly on those. Monotone decreasing in the offset, so
    bisection is unconditionally safe on any bracket that contains the root.
    """
    low, high = -0.02, 0.05
    if np.max(glide(polar, low)["L_over_D"]) < target_LD:
        raise ValueError(
            f"target L/D {target_LD} unreachable: even at drag offset {low}, "
            f"the model peaks at {np.max(glide(polar, low)['L_over_D']):.2f}. "
            "The reconstruction is too far off to be corrected by one scalar."
        )
    passes = 0
    while high - low > tol and passes < max_passes:
        mid = 0.5 * (low + high)
        if np.max(glide(polar, mid)["L_over_D"]) > target_LD:
            low = mid          # not enough drag yet
        else:
            high = mid
        passes += 1
    return 0.5 * (low + high)


##### Optimization
# The design variables, and the constraints the parent chapter's aircraft sets.
#
# Stations stay at fixed FRACTIONS of semi-span, so span scales the whole
# planform rather than letting four break points slide around independently --
# nine variables that mean something, rather than thirteen that overlap.
LIMIT_LOAD_FACTOR = 5.3   # CS-22 limit manoeuvre, the structural constraint case
CHORD_MAX = 1.30          # m, buildability bound on any station chord
CHORD_MIN = 0.12          # m
STATION_FRACTION = STATION_Y / (SPAN / 2)


def _as_float(value):
    """
    One scalar, whatever the analysis handed back.

    AeroBuildup returns shape-(1,) arrays even for a single operating point, and
    numpy 2 refuses float() on those -- so every number this chapter reports goes
    through here, rather than each call site discovering it separately.
    """
    array = np.array(value)
    return float(array.reshape(-1)[0]) if array.ndim else float(array)


def station_grid(subdivisions=1):
    """
    Station fractions of semi-span, with the baseline planform sampled onto them.

    Each baseline PANEL is subdivided rather than a uniform grid being laid down,
    so `subdivisions=1` returns exactly the chapter's four stations and the
    sequence 4, 7, 10, 13 always contains the coarse grid as a subset. A uniform
    grid would move the break points as well as adding freedom, and the two
    effects could not then be told apart.
    """
    fractions = []
    for i in range(len(STATION_FRACTION) - 1):
        for step in range(subdivisions):
            fractions.append(
                STATION_FRACTION[i]
                + (STATION_FRACTION[i + 1] - STATION_FRACTION[i]) * step / subdivisions)
    fractions.append(STATION_FRACTION[-1])
    fractions = np.array(fractions)
    return {
        "fractions": fractions,
        "chords": np.interp(fractions, STATION_FRACTION, STATION_C),
        "twists": np.interp(fractions, STATION_FRACTION, STATION_TWIST),
        "thickness": np.interp(fractions, STATION_FRACTION, STATION_TC),
    }


def build_airplane(span, chords, twists, fractions=None):
    """
    The aircraft with a parametric wing, on numbers or on CasADi variables alike.

    Fuselage and tails come straight off the baseline rather than being rebuilt:
    they are not design variables here, and reconstructing them inside an
    optimizer loop would cost geometry construction on every iteration.
    """
    fractions = STATION_FRACTION if fractions is None else fractions
    stations = [float(fraction) * span / 2 for fraction in fractions]
    xsecs = [
        asb.WingXSec(
            xyz_le=[WING_LE_X + 0.25 * (chords[0] - chords[i]),
                    stations[i], stations[i] * np.tand(DIHEDRAL_DEG)],
            chord=chords[i],
            twist=twists[i],
            airfoil=AIRFOIL_ROOT if fractions[i] < 0.45 else AIRFOIL_TIP,
        )
        for i in range(len(fractions))
    ]
    wing = asb.Wing(name="Wing", symmetric=True, xsecs=xsecs)
    return asb.Airplane(
        name="Discus-2c (optimized)", xyz_ref=XYZ_REF,
        wings=[wing, *AIRPLANE.wings[1:]], fuselages=AIRPLANE.fuselages,
        s_ref=wing.area(), c_ref=wing.mean_aerodynamic_chord(), b_ref=span,
    )


def root_bending_proxy(span, chords, mass=None, fractions=None):
    """
    Limit-load root bending moment as a smooth, cheap function of the planform.

    The exact figure needs a spanwise load distribution from a vortex lattice.
    That is far too expensive to sit inside an optimizer, so this takes the
    additional loading to be proportional to chord -- true of an unstalled wing
    to first order -- making the root moment the limit load times the
    chord-weighted centroid of the semi-span.

    USED RELATIVELY, which is what makes it legitimate: the optimizer is held to
    the BASELINE's own proxy value, so the roughly 5% this runs low against the
    vortex lattice appears on both sides and cancels. The entry then checks the
    optimized design with the real calculation, which is the only thing that can
    catch the proxy being wrong in a way that does not cancel.
    """
    fractions = STATION_FRACTION if fractions is None else fractions
    stations = [float(fraction) * span / 2 for fraction in fractions]
    area, moment = 0.0, 0.0
    for i in range(len(stations) - 1):
        width = stations[i + 1] - stations[i]
        mean_chord = 0.5 * (chords[i] + chords[i + 1])
        arm = 0.5 * (stations[i] + stations[i + 1])
        area = area + mean_chord * width
        moment = moment + mean_chord * arm * width
    mass = MASS if mass is None else mass
    return LIMIT_LOAD_FACTOR * mass * GRAVITY / 2 * moment / area


def baseline_limits(drag_offset):
    """
    The parent chapter's aircraft, expressed as the limits the optimizer inherits.

    Every constraint is taken from the baseline by the SAME code path the
    optimizer will be held to -- the proxy against the proxy, the static margin
    from the same derivative call -- so a systematic error in either appears on
    both sides rather than handing the optimizer free margin.
    """
    started = time.perf_counter()
    speed = float(np.sqrt(2 * MASS * GRAVITY / (
        asb.Atmosphere(altitude=0.0).density() * WING_AREA * 0.65)))
    result = asb.AeroBuildup(
        airplane=AIRPLANE,
        op_point=asb.OperatingPoint(velocity=speed, alpha=3.0),
        xyz_ref=XYZ_REF,
    ).run_with_stability_derivatives(alpha=True, beta=False, p=False, q=False, r=False)
    aero_cost["calls"] += 1
    aero_cost["seconds"] += time.perf_counter() - started

    chords = [float(c) for c in STATION_C]
    return {
        "area": float(WING.area()),
        "span": SPAN,
        "bending": float(root_bending_proxy(SPAN, chords)),
        "static_margin": _as_float(-result["Cma"] / result["CLa"]),
        "drag_offset": drag_offset,
    }


def optimise(limits, washout_monotone=False, reynolds_floor=None,
             mass_model=False, subdivisions=1, verbose=False):
    """
    Maximize trimmed glide ratio over span, chord and twist, inside the baseline's limits.

    One gradient solve from the baseline geometry, not a multistart, so this
    finds A local optimum and cannot say it is THE optimum. Starting from the
    real aircraft is the deliberate choice: the question is whether the design
    can be improved from where it actually sits, not where the global best lies.

    The drag calibration is carried across from the parent unchanged, as a
    property of construction quality rather than of planform. That is the
    assumption this whole chapter rests on -- if the offset is really a section
    modelling error, it should move with the geometry and does not here.

    Constraints are normalized to order one before being handed to the solver.
    Left in newtons and newton-metres, the trim residual and the bending limit
    differ by four orders of magnitude and IPOPT's convergence test stops meaning
    the same thing for both.
    """
    # `subdivisions` refines the station grid without moving the break points, so
    # a coarser run is always a subset of a finer one. Default 1 is the chapter's
    # own four stations, so every entry written before this argument existed is
    # untouched by it.
    grid = station_grid(subdivisions)
    fractions = grid["fractions"]

    opti = asb.Opti()
    span = opti.variable(init_guess=SPAN, lower_bound=10.0, upper_bound=32.0)
    chords = [opti.variable(init_guess=float(c), lower_bound=CHORD_MIN,
                            upper_bound=CHORD_MAX)
              for c in grid["chords"]]
    twists = [opti.variable(init_guess=float(t), lower_bound=-8.0, upper_bound=4.0)
              for t in grid["twists"]]
    alpha = opti.variable(init_guess=3.0, lower_bound=-4.0, upper_bound=10.0)
    speed = opti.variable(init_guess=30.0, lower_bound=18.0, upper_bound=65.0)

    # Buildable: chord may not grow towards the tip.
    for i in range(len(chords) - 1):
        opti.subject_to(chords[i] >= chords[i + 1])

    # Washout only. Without this the optimizer oscillates twist between stations
    # -- it ran -4.4 deg inboard against +4.0 deg at the tip, straight to its
    # bound -- which exploits the piecewise-linear parameterization rather than
    # finding anything a wing could be built to.
    if washout_monotone:
        for i in range(len(twists) - 1):
            opti.subject_to(twists[i] >= twists[i + 1])

    airplane = build_airplane(span, chords, twists, fractions)
    area = airplane.s_ref
    op_point = asb.OperatingPoint(
        atmosphere=asb.Atmosphere(altitude=0.0), velocity=speed, alpha=alpha)
    result = asb.AeroBuildup(
        airplane=airplane, op_point=op_point, xyz_ref=XYZ_REF,
    ).run_with_stability_derivatives(alpha=True, beta=False, p=False, q=False, r=False)

    lift_coeff = result["CL"]
    drag_coeff = result["CD"] + limits["drag_offset"]

    # Make the design pay for the wing it asks for. Implicit, because a heavier
    # aircraft loads its own spar harder: mass is a variable and the constraint
    # closes the loop on it.
    if mass_model:
        mass = opti.variable(init_guess=MASS, lower_bound=0.5 * MASS,
                             upper_bound=3.0 * MASS)
        opti.subject_to(
            mass / (NON_WING_MASS + wing_structural_mass(
                span, chords, mass, fractions, grid["thickness"])) == 1)
    else:
        mass = MASS
    weight = mass * GRAVITY

    opti.subject_to([
        op_point.dynamic_pressure() * area * lift_coeff / weight == 1,
        area / limits["area"] >= 1,
        root_bending_proxy(span, chords, mass, fractions) / limits["bending"] <= 1,
        -result["Cma"] / result["CLa"] >= limits["static_margin"],
    ])

    # Keep the outer wing out of the Reynolds regime where the section data is
    # least trustworthy -- which is exactly where the unconstrained optimum went
    # to buy its gain.
    if reynolds_floor is not None:
        opti.subject_to(
            chords[-1] * speed / KINEMATIC_VISCOSITY / reynolds_floor >= 1)
    opti.minimize(-lift_coeff / drag_coeff)

    started = time.perf_counter()
    sol = opti.solve(verbose=verbose)
    aero_cost["calls"] += 1
    aero_cost["seconds"] += time.perf_counter() - started

    solved_chords = [_as_float(sol(c)) for c in chords]
    solved_twists = [_as_float(sol(t)) for t in twists]
    solved_span = _as_float(sol(span))
    return {
        "span": solved_span,
        "chords": solved_chords,
        "twists": solved_twists,
        "alpha": _as_float(sol(alpha)),
        "speed": _as_float(sol(speed)),
        "area": _as_float(sol(area)),
        "aspect_ratio": solved_span ** 2 / _as_float(sol(area)),
        "CL": _as_float(sol(lift_coeff)),
        "CD": _as_float(sol(drag_coeff)),
        "L_over_D": _as_float(sol(lift_coeff / drag_coeff)),
        "static_margin": _as_float(sol(-result["Cma"] / result["CLa"])),
        "bending": _as_float(sol(root_bending_proxy(span, chords, mass, fractions))),
        "fractions": fractions,
        "stations": len(fractions),
        "mass": _as_float(sol(mass)) if mass_model else MASS,
        "spar_mass": _as_float(sol(wing_structural_mass(
            span, chords, mass, fractions, grid["thickness"]))),
        "tip_reynolds": _as_float(sol(chords[-1] * speed / KINEMATIC_VISCOSITY)),
    }


##### Paying for span
# The first optimization in this chapter grew the wing 26% with the mass held
# fixed, so span cost bending moment but never weight. These close that gap.
#
# A stress-sized tube spar, integrated analytically: for a thin tube the wall
# needed to carry a moment M at radius r and allowable stress sigma is
# t = M / (pi r^2 sigma), so the material per unit span is
# 2 rho M / (r sigma) -- independent of wall thickness, which is what makes this
# cheap enough to sit inside an optimizer. The real beam in `wing_spar()` is an
# Opti solve and cannot be nested inside another one.
SPAR_DENSITY = 1600.0        # kg/m^3, carbon/epoxy laminate
ALLOWABLE_STRESS = 300e6     # Pa at limit load
KINEMATIC_VISCOSITY = 1.4607e-5   # m^2/s at sea level

# Fixed interpolation weights onto a uniform semi-span grid. Precomputed because
# the station FRACTIONS never move -- only the span and the chords do -- so the
# weights are constants and the integration below stays smooth in the design
# variables. np.interp with a symbolic grid would not be.
_MASS_GRID = np.linspace(0.0, 1.0, 41)


def _panel_weights(fractions):
    """Which panel each grid point falls in, and how far along it."""
    weights = []
    for eta in _MASS_GRID:
        i = min(max(int(np.sum(fractions <= eta)) - 1, 0), len(fractions) - 2)
        width = fractions[i + 1] - fractions[i]
        weights.append((i, float((eta - fractions[i]) / width)))
    return weights


def _on_grid(values, weights):
    """Interpolate a per-station quantity onto the fixed semi-span grid."""
    return [(1 - w) * values[i] + w * values[i + 1] for i, w in weights]


def wing_structural_mass(span, chords, mass, fractions=None, thickness=None):
    """
    Mass of a stress-sized spar carrying the limit load, for both wings.

    Smooth in span and chord, so an optimizer can be made to pay for the wing it
    asks for. The loading is taken proportional to chord, exactly as
    `root_bending_proxy` does, so the two cannot disagree about the same wing.

    Depends on `mass` because a heavier aircraft loads its own spar harder, which
    makes this implicit: the caller closes the loop by constraining total mass to
    equal the structure plus everything else.
    """
    fractions = STATION_FRACTION if fractions is None else fractions
    thickness = STATION_TC if thickness is None else thickness
    weights = _panel_weights(fractions)

    semi_span = span / 2
    step = semi_span / (len(_MASS_GRID) - 1)
    chord = _on_grid(chords, weights)
    thickness = _on_grid([float(v) for v in thickness], weights)

    # Load proportional to chord, normalized to the limit load on one wing.
    chord_integral = sum(c * step for c in chord)
    scale = LIMIT_LOAD_FACTOR * mass * GRAVITY / 2 / chord_integral

    # Shear then moment, accumulated inboard from the tip.
    shear, moment, total = 0.0, 0.0, 0.0
    for k in range(len(_MASS_GRID) - 1, -1, -1):
        radius = 0.5 * SPAR_DEPTH_FRACTION * chord[k] * thickness[k]
        total = total + 2 * SPAR_DENSITY * moment / (radius * ALLOWABLE_STRESS) * step
        shear = shear + scale * chord[k] * step
        moment = moment + shear * step
    return 2 * total


# Everything that is not spar: fuselage, tail, skins, systems and pilot. Taken as
# the baseline's total minus its own spar, so the baseline reproduces its
# published mass exactly and only the SCALING with span is being modelled.
NON_WING_MASS = MASS - wing_structural_mass(
    SPAN, [float(c) for c in STATION_C], MASS)
