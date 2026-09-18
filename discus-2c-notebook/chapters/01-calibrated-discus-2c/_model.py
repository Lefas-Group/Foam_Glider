# =============================================================================
# Reconstructed Discus-2c model, calibrated against published performance.
#
# This file defines the chapter. A different model gets its own directory and
# its own _model.py, sharing nothing with this one.
#
# THE AIRCRAFT IS NOT PUBLISHED GEOMETRY. Span, reference area and all-up mass
# are taken from published figures; the planform distribution, twist, dihedral,
# section choice, fuselage shape and tail sizes are a RECONSTRUCTION consistent
# with those figures and with the 18 m Class generally. Every entry that quotes
# an absolute number inherits that, which is why the chapter calibrates one
# scalar against a published performance point rather than trusting the
# build-up outright.
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
