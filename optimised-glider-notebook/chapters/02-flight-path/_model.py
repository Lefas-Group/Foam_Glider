# =============================================================================
# Duration glider model.
#
# COPIED VERBATIM from chapters/01-duration-glider/_model.py at commit 41ff401.
# This chapter forks on METHOD, not on the aircraft: chapter 01 measures a steady
# trimmed glide, this one integrates the flight path. So there is deliberately NO
# difference in this file, and `diff` against the parent returning empty is a
# positive check that the two chapters are flying the same glider. The difference
# lives in _analysis.py.
#
# A 30 cm-span hand-launched glider cut from flat Styrofoam food tray, in the
# McEagle tradition: every surface is a single sheet of tray stock, flat, with
# the leading and trailing edges razor-bevelled to a point. Nothing is cambered
# and nothing is heat-formed, so the section is fully described by the sheet
# thickness and the two bevel lengths.
#
# This file is the VEHICLE only -- geometry, material, mass, and the operating
# conditions held fixed. How the chapter measures it is next door in
# _analysis.py. A different aircraft, fidelity or method gets its own directory
# and its own copy of both, sharing nothing with these.
#
# Loaded two ways, both by exec into the caller's namespace: entries via the
# _model.qmd shim, scratch scripts via _scratch/probe.py. Loaded FIRST, before
# _analysis.py, so nothing here may reference a name defined there -- which is
# why plate_section() and _PLATE_REF stay on this side of the split even though
# "the section as analysed" sounds like analysis.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete the chapter's _freeze/ directory before re-rendering.
# =============================================================================

##### Imports
import time

import aerosandbox as asb
import aerosandbox.numpy as np
import matplotlib.pyplot as plt

##### Operating conditions
#
# Sea level, still air. Every number in this chapter is quoted at the trimmed
# glide speed the model solves for -- at 30 cm span the chord Reynolds number
# sits between 1e4 and 2e4, where the section polar moves fast enough that a
# coefficient without its speed means nothing.
ATMOSPHERE = asb.Atmosphere(altitude=0.0)
G = 9.81  # m/s^2

# Hand launch. Duration is launch height divided by sink rate, so the chapter
# needs a launch height to have an objective at all. Height comes from two
# places: the hand it leaves, and the zoom it climbs afterwards, in which the
# glider converts a fraction ZOOM_EFF of its launch kinetic energy into height
# before nosing over into the glide.
#
# A gentle level toss, not a javelin launch. At this speed the release height is
# the larger of the two terms, which is worth knowing before reading any
# duration in this chapter: most of the flight is paid for by the arm, not the
# throw.
V_LAUNCH = 8.0  # m/s, a light overarm toss
H_RELEASE = 1.5  # m, height of the hand at release
ZOOM_EFF = 0.55  # fraction of launch KE recovered as height

##### Material
#
# Styrofoam food tray, measured rather than assumed: 5 mm thick, 174.4 g per
# square metre of sheet. Areal mass is what a kitchen scale and a ruler give you
# and is what every part's mass is computed from; the density below is derived
# from it, and is used nowhere except to state what the foam is.
#
# Both numbers are load-bearing, and in opposite directions. Thickness sets the
# section -- at a 50 mm chord this stock is a 10% thick slab, not a plate -- and
# areal mass sets the wing loading.
FOAM_T = 5.0e-3  # m, tray sheet thickness
FOAM_AREAL = 0.1744  # kg/m^2 of single-ply sheet
FOAM_RHO = FOAM_AREAL / FOAM_T  # kg/m^3, ~35 -- expanded polystyrene

# Two plies, as McEagle has, but for a different reason: a fuselage longer than
# one sheet has to be spliced, and splicing means two plies side by side with
# their joints staggered. Since the fuselage length is a free variable here, the
# splice is assumed always needed, which is the conservative reading -- it prices
# length honestly instead of capping it at an invented number.
#
# The cost is real: 10 mm of width and twice the mass on the heaviest single
# part. That is the term that stops the optimiser asking for an arbitrarily long
# tail arm.
FUSE_PLIES = 2


##### Vehicle
def flat_plate(chord, thickness=FOAM_T, bevel=0.15, n=80):
    """
    The section actually built: a constant-thickness sheet, bevelled to a point.

    Not an aerofoil from a catalogue. A razor bevel over the first and last
    `bevel` fraction of chord leaves a sharp leading and trailing edge with a
    flat-sided slab between them, and at t/c near 3% that shape is what sets the
    drag -- so it is generated here rather than approximated by a thin NACA.

    Args:
        chord: m. Only the thickness-to-chord ratio reaches the polar, but the
            chord is what the builder measures, so it is the argument.
        thickness: m, the sheet.
        bevel: fraction of chord over which each edge tapers to a point.
        n: points per surface.

    Returns:
        asb.Airfoil, symmetric about the chord line.
    """
    t_c = thickness / chord
    x = np.sinspace(0, 1, n)  # clustered at the leading edge, where it matters

    # Half-thickness: linear ramp up over the bevel, flat, linear ramp down.
    y = 0.5 * t_c * np.minimum(
        1.0, np.minimum(x, 1.0 - x) / bevel
    )

    upper = np.stack([x[::-1], y[::-1]], axis=1)
    lower = np.stack([x[1:], -y[1:]], axis=1)
    return asb.Airfoil(
        name=f"foam-plate-{t_c:.3f}",
        coordinates=np.concatenate([upper, lower], axis=0),
    )


# The plate above, fitted once to Kulfan (CST) weights at a reference thickness
# ratio. Everything downstream uses the scaled version below rather than the
# coordinates, for two reasons.
#
# It is not an approximation: Airfoil.get_aero_from_neuralfoil() performs this
# same fit internally on every call, so the coordinates were never what got
# analysed. Doing it explicitly changes nothing and makes visible what is being
# modelled -- see the entry on what section the model actually analyses.
#
# And it makes chord a symbolic variable. A CST section of fixed shape scales
# linearly in every weight with thickness ratio (verified: halving and doubling
# t/c scales all eight weights by exactly 0.5 and 2.0), so the weights can be
# multiplied by an MX and handed to KulfanAirfoil, which is built for it. The
# coordinate path cannot do this -- it would need the fit, itself an
# optimisation, inside the optimisation. That is the difference between the
# whole design solve taking six seconds and needing an outer search.
BEVEL = 0.15  # razor bevel, as a fraction of chord, at each edge
TC_REF = 0.10  # thickness ratio the reference fit is taken at
_PLATE_REF = flat_plate(FOAM_T / TC_REF, bevel=BEVEL).to_kulfan_airfoil().kulfan_parameters


def plate_section(chord, thickness=FOAM_T):
    """
    The section as analysed: Kulfan weights scaled linearly from one reference fit.

    Accepts a symbolic chord, which is what lets the design solve run inside a
    single Opti rather than an outer search.
    """
    k = (thickness / chord) / TC_REF
    return asb.KulfanAirfoil(
        name="foam-plate",
        upper_weights=_PLATE_REF["upper_weights"] * k,
        lower_weights=_PLATE_REF["lower_weights"] * k,
        leading_edge_weight=_PLATE_REF["leading_edge_weight"] * k,
        TE_thickness=_PLATE_REF["TE_thickness"] * k,
    )


def glider(
    span=0.30,
    aspect_ratio=6.0,
    taper=1.0,
    dihedral=9.5,
    tail_arm_chords=3.6,
    nose_chords=1.5,
    h_tail_ratio=0.22,
    v_tail_ratio=0.08,
    h_tail_incidence=-2.0,
):
    """
    The airframe, as a set of ratios a builder can lay out on a tray.

    Defaults reproduce McEagle proportions at a 30 cm span. Everything is
    dimensionless against wing chord or wing area so the same call serves as
    both the baseline and the design vector.

    Longitudinal stations are measured in ROOT CHORDS, not in spans. Span is
    fixed by the brief, so an optimiser moving aspect_ratio is really moving
    chord -- and a tail arm pinned to span then shrinks in chords as the chord
    grows, collapsing the tail volume coefficient at exactly the configurations
    worth exploring. Pinned to chord instead, tail volume is held while aspect
    ratio varies, which is the comparison an aspect-ratio sweep is trying to
    make. The defaults are the span fractions they replace (0.60 and 0.25 of
    span) evaluated at the baseline, so baseline geometry is unchanged.

    Args:
        span: m, tip to tip. Fixed by the brief at 0.30.
        aspect_ratio: span^2 / wing area.
        taper: tip chord / root chord.
        dihedral: deg, per panel, measured from the horizontal.
        tail_arm_chords: quarter-chord to quarter-chord distance, in root chords.
        nose_chords: wing leading edge aft of the nose, in root chords.
        h_tail_ratio: horizontal tail area / wing area.
        v_tail_ratio: fin area / wing area.
        h_tail_incidence: deg, tail rigged nose-down relative to the wing, as
            McEagle's is -- it is what brings the nose up out of a stall.

    Returns:
        (asb.Airplane, dict of the layout dimensions in metres).
    """
    S = span**2 / aspect_ratio
    c_root = 2 * S / (span * (1 + taper))
    c_tip = c_root * taper
    section = plate_section(c_root)

    arm = tail_arm_chords * c_root
    S_h = h_tail_ratio * S
    c_h = np.sqrt(S_h / 3.0)  # tail panels are AR 3, as McEagle's is
    b_h = S_h / c_h
    S_v = v_tail_ratio * S
    c_v = np.sqrt(S_v / 1.5)  # fin is AR 1.5
    b_v = S_v / c_v

    # Fuselage runs from a nose ahead of the wing to the tail trailing edge.
    nose = nose_chords * c_root
    fuse_len = nose + arm + c_h
    fuse_h = 0.05 * span  # slab depth, the tray's usable width
    fuse_w = FUSE_PLIES * FOAM_T

    wing = asb.Wing(
        name="Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0, 0, 0], chord=c_root, airfoil=section
            ),
            asb.WingXSec(
                xyz_le=[
                    0.25 * (c_root - c_tip),
                    span / 2,
                    span / 2 * np.tand(dihedral),
                ],
                chord=c_tip,
                airfoil=section,
            ),
        ],
    ).translate([nose, 0, fuse_h / 2])

    h_tail = asb.Wing(
        name="Horizontal stabilizer",
        symmetric=True,
        xsecs=[
            asb.WingXSec(
                xyz_le=[0, 0, 0], chord=c_h, airfoil=section,
                twist=h_tail_incidence,
            ),
            asb.WingXSec(
                xyz_le=[0, b_h / 2, 0], chord=c_h, airfoil=section,
                twist=h_tail_incidence,
            ),
        ],
    ).translate([nose + arm + 0.25 * c_root - 0.25 * c_h, 0, fuse_h / 2])

    v_tail = asb.Wing(
        name="Fin",
        symmetric=False,
        xsecs=[
            asb.WingXSec(xyz_le=[0, 0, 0], chord=c_v, airfoil=section),
            asb.WingXSec(xyz_le=[0, 0, b_v], chord=c_v, airfoil=section),
        ],
    ).translate([nose + arm + 0.25 * c_root - 0.25 * c_v, 0, fuse_h / 2])

    fuselage = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(
                xyz_c=[x, 0, fuse_h / 2],
                width=fuse_w,
                height=fuse_h,
                shape=10,  # near-rectangular, because the part is a slab
            )
            for x in [0.0, 0.05 * fuse_len, fuse_len]
        ],
    )

    airplane = asb.Airplane(
        name="Foam duration glider",
        xyz_ref=[nose + 0.25 * c_root, 0, fuse_h / 2],
        wings=[wing, h_tail, v_tail],
        fuselages=[fuselage],
    )
    layout = dict(
        span=span, S=S, c_root=c_root, c_tip=c_tip, arm=arm,
        S_h=S_h, b_h=b_h, c_h=c_h, S_v=S_v, b_v=b_v, c_v=c_v,
        nose=nose, fuse_len=fuse_len, fuse_h=fuse_h, fuse_w=fuse_w,
        # Leading-edge stations, kept so structural_mass() can place each part
        # where it actually sits rather than lumping the structure at one point.
        x_wing_le=nose,
        x_h_le=nose + arm + 0.25 * c_root - 0.25 * c_h,
        x_v_le=nose + arm + 0.25 * c_root - 0.25 * c_v,
    )
    return airplane, layout


##### Derived quantities
def structural_mass(layout):
    """
    Mass of the cut parts, from the flat stock they are cut from.

    Deliberately NOT Fuselage.volume(): the fuselage is a rectangular slab, and
    the super-ellipse AeroSandbox integrates for drag under-fills that slab, so
    taking mass from it would under-weigh the heaviest single part. Areas are
    likewise the planform areas that get cut, not projected areas.

    Each part is placed at its own station -- a flat plate's area centroid is at
    40% chord, close enough at this fidelity -- because the tail sits two thirds
    of the airframe length behind the wing and lumping the structure at one
    point moves the empty CG by tens of millimetres on a 300 mm aircraft.

    Each also carries its own inertia as a thin rectangular plate, m/12 times
    the squares of its two in-plane dimensions. Summing MassProperties applies
    the parallel-axis shift, so the total is correct about the combined CG for
    free. A trim solve never reads any of this -- but point masses alone give
    Ixx = 0, a singular inertia tensor, and any rigid-body simulation of this
    aircraft then inverts it to NaN.

    Returns:
        dict of asb.MassProperties per part, plus the sum under key "total".
    """
    sheet = FOAM_AREAL  # kg per m^2 of single-ply stock, as measured

    def plate(mass, x_cg, span, chord):
        """A thin plate lying in the x-y plane, spanwise `span`, chordwise `chord`."""
        return asb.MassProperties(
            mass=mass, x_cg=x_cg,
            Ixx=mass * span**2 / 12,
            Iyy=mass * chord**2 / 12,
            Izz=mass * (span**2 + chord**2) / 12,
        )

    parts = {
        "wing": plate(layout["S"] * sheet,
                      layout["x_wing_le"] + 0.4 * layout["c_root"],
                      layout["span"], layout["c_root"]),
        "h_tail": plate(layout["S_h"] * sheet,
                        layout["x_h_le"] + 0.4 * layout["c_h"],
                        layout["b_h"], layout["c_h"]),
        # The fin stands in the x-z plane, so its "span" is vertical: it
        # contributes to Izz the way the others contribute to Ixx.
        "fin": plate(layout["S_v"] * sheet,
                     layout["x_v_le"] + 0.4 * layout["c_v"],
                     layout["c_v"], layout["b_v"]),
        "fuselage": plate(layout["fuse_len"] * layout["fuse_h"] * FUSE_PLIES * sheet,
                          0.5 * layout["fuse_len"],
                          layout["fuse_h"], layout["fuse_len"]),
    }
    parts["total"] = sum(parts.values(), asb.MassProperties(mass=0.0))
    return parts


def launch_height(v_launch=V_LAUNCH, eff=ZOOM_EFF, h_release=H_RELEASE):
    """
    Height the glide starts from: the hand, plus a ballistic zoom above it.

    Mass does not appear: a ballistic zoom trades speed for height at a rate
    independent of it. That is the model's weakest point, because a lighter
    glider is thrown faster and decelerates harder in the climb, and neither
    effect is here.
    """
    return h_release + eff * v_launch**2 / (2 * G)
