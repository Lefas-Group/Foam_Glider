# =============================================================================
# Duration glider model.
#
# A 30 cm-span hand-launched glider cut from flat Styrofoam food tray, in the
# McEagle tradition: every surface is a single sheet of tray stock, flat, with
# the leading and trailing edges razor-bevelled to a point. Nothing is cambered
# and nothing is heat-formed, so the section is fully described by the sheet
# thickness and the two bevel lengths.
#
# This file defines the chapter. A different model gets its own directory and
# its own _model.py, sharing nothing with this one.
#
# Loaded two ways, both by exec into the caller's namespace: entries via the
# _model.qmd shim, scratch scripts via _scratch/probe.py.
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
# sits near 2e4, where the section polar moves fast enough that a coefficient
# without its speed means nothing.
ATMOSPHERE = asb.Atmosphere(altitude=0.0)
G = 9.81  # m/s^2

# Hand launch. Duration is launch height divided by sink rate, so the chapter
# needs a launch height to have an objective at all. Modelled as a ballistic
# zoom from a javelin-style throw: the glider converts a fraction ZOOM_EFF of
# its launch kinetic energy into height before it noses over into the glide.
V_LAUNCH = 12.0  # m/s, a hard overarm throw
ZOOM_EFF = 0.55  # fraction of launch KE recovered as height

##### Material
#
# Styrofoam food tray. The flat floor of the tray is the only usable stock; its
# thickness is what sets both the section and the mass, so it is the single most
# load-bearing assumption in the chapter.
FOAM_T = 1.6e-3  # m, tray sheet thickness
FOAM_RHO = 65.0  # kg/m^3, expanded-polystyrene tray stock
FUSE_PLIES = 2  # fuselage is laminated from this many sheets

# Angle of attack at which stability derivatives are taken -- mid lift curve,
# well clear of the plate's stall, so the neutral point is a property of the
# aircraft rather than of wherever it happens to be trimmed.
ALPHA_LINEAR = 2.0  # deg


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


def glider(
    span=0.30,
    aspect_ratio=6.0,
    taper=1.0,
    dihedral=9.5,
    tail_arm_ratio=0.60,
    h_tail_ratio=0.22,
    v_tail_ratio=0.08,
    h_tail_incidence=-2.0,
):
    """
    The airframe, as a set of ratios a builder can lay out on a tray.

    Defaults reproduce McEagle proportions at a 30 cm span. Everything is
    dimensionless against span or wing area so the same call serves as both the
    baseline and the design vector.

    Args:
        span: m, tip to tip. Fixed by the brief at 0.30.
        aspect_ratio: span^2 / wing area.
        taper: tip chord / root chord.
        dihedral: deg, per panel, measured from the horizontal.
        tail_arm_ratio: quarter-chord to quarter-chord distance, as a fraction
            of span.
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
    section = flat_plate(c_root)

    arm = tail_arm_ratio * span
    S_h = h_tail_ratio * S
    c_h = np.sqrt(S_h / 3.0)  # tail panels are AR 3, as McEagle's is
    b_h = S_h / c_h
    S_v = v_tail_ratio * S
    c_v = np.sqrt(S_v / 1.5)  # fin is AR 1.5
    b_v = S_v / c_v

    # Fuselage runs from a nose ahead of the wing to the tail trailing edge.
    nose = 0.25 * span
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

    Returns:
        dict of asb.MassProperties per part, plus the sum under key "total".
    """
    sheet = FOAM_T * FOAM_RHO  # kg per m^2 of single-ply stock
    parts = {
        "wing": asb.MassProperties(
            mass=layout["S"] * sheet,
            x_cg=layout["x_wing_le"] + 0.4 * layout["c_root"],
        ),
        "h_tail": asb.MassProperties(
            mass=layout["S_h"] * sheet,
            x_cg=layout["x_h_le"] + 0.4 * layout["c_h"],
        ),
        "fin": asb.MassProperties(
            mass=layout["S_v"] * sheet,
            x_cg=layout["x_v_le"] + 0.4 * layout["c_v"],
        ),
        "fuselage": asb.MassProperties(
            mass=layout["fuse_len"] * layout["fuse_h"] * FUSE_PLIES * sheet,
            x_cg=0.5 * layout["fuse_len"],
        ),
    }
    parts["total"] = sum(parts.values(), asb.MassProperties(mass=0.0))
    return parts


def launch_height(v_launch=V_LAUNCH, eff=ZOOM_EFF):
    """
    Height won from the throw, as a ballistic zoom at efficiency `eff`.

    Mass does not appear: a ballistic zoom trades speed for height at a rate
    independent of it. That is the model's weakest point, because a lighter
    glider is thrown faster and decelerates harder in the climb, and neither
    effect is here.
    """
    return eff * v_launch**2 / (2 * G)


##### The analysis
def glide(airplane, layout, ballast=0.0, static_margin=0.20,
          alpha_bounds=(-2, 7), verbose=False):
    """
    Trim the glider and return its steady glide, sink rate and duration.

    The chapter's one analysis. Ballast is lead at the nose -- McEagle's taped
    dime -- and is what places the CG; here the CG is instead placed by the
    requested static margin and the ballast solved for, because a duration
    glider wants the least ballast that still trims where it should.

    Args:
        airplane, layout: from glider().
        ballast: kg. If 0, solved for so the CG sits at the requested margin.
        static_margin: (x_np - x_cg) / MAC.
        alpha_bounds: deg, the trim search range. Capped below the flat plate's
            ~7 deg stall: past it the lift curve turns over, dCm/dalpha changes
            sign, and the neutral point the solver is chasing stops meaning
            anything.
        verbose: pass the solver's log through.

    Returns:
        dict: alpha, V, CL, CD, LD, sink, duration, mass, ballast, x_cg, x_np.
    """
    opti = asb.Opti()
    alpha = opti.variable(init_guess=4.0,
                          lower_bound=alpha_bounds[0], upper_bound=alpha_bounds[1])
    V = opti.variable(init_guess=6.0, lower_bound=0.5, upper_bound=30.0)
    m_ballast = ballast if ballast else opti.variable(init_guess=2e-3, lower_bound=0.0)

    # Ballast is lead taped at the very nose, x = 0 -- the furthest forward it
    # can go, so it is also the least of it that will do the job.
    empty = structural_mass(layout)["total"]
    total = empty + asb.MassProperties(mass=m_ballast, x_cg=0.0)
    mass, x_cg = total.mass, total.x_cg
    weight = mass * G

    # Reference area and chord come from the Airplane, not from layout: with
    # dihedral, Wing.area() returns the true panel area (152.1 cm^2 here), which
    # is 1.4% larger than the projected span*chord the layout records. Every
    # coefficient below is nondimensionalised on the former, so the force
    # balance must be too.
    S_ref, mac = airplane.s_ref, airplane.c_ref
    ref = [x_cg, 0, airplane.xyz_ref[2]]

    def solve_aero(op, derivatives):
        t0 = time.perf_counter()
        ab = asb.AeroBuildup(airplane=airplane, op_point=op, xyz_ref=ref)
        out = (ab.run_with_stability_derivatives(
                   alpha=True, beta=False, p=False, q=False, r=False)
               if derivatives else ab.run())
        aero_cost["calls"] += 1
        aero_cost["seconds"] += time.perf_counter() - t0
        return out

    # The neutral point is measured at a FIXED linear-range alpha, not at trim.
    # Taken at trim it is not a property of the aircraft at all: as the trim
    # point approaches the flat plate's ~7 deg stall, dCm/dalpha bends over and
    # x_np ran from 107 mm to 122 mm across a 0.2 g ballast change, which made
    # any static-margin constraint non-monotonic and the solve infeasible.
    d = solve_aero(
        asb.OperatingPoint(atmosphere=ATMOSPHERE, velocity=V, alpha=ALPHA_LINEAR),
        derivatives=True,
    )
    x_np = x_cg - d["Cma"] / d["CLa"] * mac

    aero = solve_aero(
        asb.OperatingPoint(atmosphere=ATMOSPHERE, velocity=V, alpha=alpha),
        derivatives=False,
    )

    CL, CD = aero["CL"], aero["CD"]
    gamma = np.arctan2(CD, CL)  # glide path angle below the horizon

    opti.subject_to([
        aero["Cm"] == 0,  # trimmed
        CL * 0.5 * ATMOSPHERE.density() * V**2 * S_ref == weight * np.cos(gamma),
    ])
    if not ballast:
        opti.subject_to((x_np - x_cg) / mac == static_margin)

    sol = opti.solve(verbose=verbose)

    CL, CD = sol(CL), sol(CD)
    V, gamma, mass = sol(V), sol(gamma), sol(mass)
    sink = V * np.sin(gamma)
    return dict(
        alpha=sol(alpha), V=V, CL=CL, CD=CD, LD=CL / CD,
        gamma_deg=np.degrees(gamma), sink=sink,
        duration=launch_height() / sink,
        mass=mass, ballast=sol(m_ballast),
        x_cg=sol(x_cg), x_np=sol(x_np),
        static_margin=(sol(x_np) - sol(x_cg)) / mac,
        Re=ATMOSPHERE.density() * V * mac / ATMOSPHERE.dynamic_viscosity(),
    )
