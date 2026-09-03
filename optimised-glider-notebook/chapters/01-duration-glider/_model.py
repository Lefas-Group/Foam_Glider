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

    Returns:
        dict of asb.MassProperties per part, plus the sum under key "total".
    """
    sheet = FOAM_AREAL  # kg per m^2 of single-ply stock, as measured
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


def launch_height(v_launch=V_LAUNCH, eff=ZOOM_EFF, h_release=H_RELEASE):
    """
    Height the glide starts from: the hand, plus a ballistic zoom above it.

    Mass does not appear: a ballistic zoom trades speed for height at a rate
    independent of it. That is the model's weakest point, because a lighter
    glider is thrown faster and decelerates harder in the climb, and neither
    effect is here.
    """
    return h_release + eff * v_launch**2 / (2 * G)


##### The analysis
def glide(airplane, layout, ballast=0.0, static_margin=0.30,
          alpha_bounds=(-2, 9), verbose=False):
    """
    Trim the glider and return its steady glide, sink rate and duration.

    The chapter's one analysis. Ballast is lead at the nose -- McEagle's taped
    dime -- and is what places the CG; here the CG is instead placed by the
    requested static margin and the ballast solved for, because a duration
    glider wants the least ballast that still trims where it should.

    Args:
        airplane, layout: from glider().
        ballast: kg. If 0, solved for so the CG sits at the requested margin.
        static_margin: (x_np - x_cg) / MAC. The default is large for a chuck
            glider, and is forced rather than chosen: on 5 mm stock the baseline
            -2 deg tail incidence will not trim inside the alpha bounds at 20%.
            That is a symptom of the tail rigging, not a preference.
        alpha_bounds: deg, the trim search range. Capped below the whole-aircraft
            stall, near 10 deg on 5 mm stock: past it the lift curve turns over,
            dCm/dalpha changes sign, and the neutral point the solver is chasing
            stops meaning anything. This bound is stock-dependent -- the section
            drives it, and 1.6 mm stock stalls three degrees earlier.
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

    # BOTH force equations, with the glide angle as a variable. Writing
    # gamma := arctan2(CD, CL) and imposing lift alone looks equivalent -- the
    # drag equation follows as D = L tan(gamma) = W sin(gamma) -- but that step
    # is 0 x inf at CL = 0, so at zero lift the drag equation quietly stops
    # being implied. A minimiser walks straight into that hole: it found a
    # vertical dive at the speed lower bound, gamma = 90 deg, CL = -5e-13,
    # drag residual 99% of weight, and reported it as the best glider.
    gamma = opti.variable(init_guess=np.radians(10.0),
                          lower_bound=np.radians(0.5), upper_bound=np.radians(80.0))
    q = 0.5 * ATMOSPHERE.density() * V**2
    opti.subject_to([
        aero["Cm"] == 0,  # trimmed
        CL * q * S_ref == weight * np.cos(gamma),
        CD * q * S_ref == weight * np.sin(gamma),
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


# What the design solve is allowed to move, and how far. Dihedral and fin are
# absent on purpose: the model has no lateral dynamics, so their only benefit is
# invisible to it while their cost in span, wetted area and mass is fully
# visible, and an optimiser would delete both.
DESIGN_BOUNDS = dict(
    aspect_ratio=(2.5, 12.0),
    tail_arm_chords=(1.5, 8.0),
    h_tail_ratio=(0.08, 0.45),
    h_tail_incidence=(-6.0, 2.0),
)


def optimise(span=0.30, static_margin=0.10, start=(6.0, 3.6, 0.22, -2.0),
             alpha_bounds=(-2, 9), hold=None, verbose=False):
    """
    Minimum sink over the four design variables, trimmed, in one solve.

    Same physics as glide() -- identical trim, force balance and neutral-point
    treatment -- with the geometry made symbolic and sink minimised rather than
    reported. Static margin is a constraint, not an objective term: left free it
    goes to zero, since nothing here penalises being twitchy.

    There is no fuselage length cap. Length pays for itself through the two-ply
    splice it requires, which is a real cost rather than an invented bound.

    Args:
        span: m, fixed by the brief.
        static_margin: (x_np - x_cg) / MAC, imposed.
        start: initial guess, as (aspect_ratio, tail_arm_chords, h_tail_ratio,
            h_tail_incidence). Vary it to check the optimum is not local.
        alpha_bounds: deg, capped below the whole-aircraft stall.
        hold: {name: value} for design variables to pin rather than free. The
            rest still optimise around them, which is what makes a sweep over
            one variable a fair comparison -- otherwise the swept point is being
            judged against rivals that were never allowed to adapt to it.
        verbose: pass the solver's log through.

    Returns:
        dict of the design, its trim state and its performance, including the
        profile/induced drag split taken from AeroBuildup rather than recomputed.
    """
    hold = hold or {}
    if set(hold) - set(DESIGN_BOUNDS):
        raise KeyError(f"hold: not design variables: {set(hold) - set(DESIGN_BOUNDS)}")
    opti = asb.Opti()
    v = {}
    for i, (name, (lo, hi)) in enumerate(DESIGN_BOUNDS.items()):
        v[name] = (hold[name] if name in hold else
                   opti.variable(init_guess=start[i], lower_bound=lo, upper_bound=hi))
    alpha = opti.variable(init_guess=4.0, lower_bound=alpha_bounds[0],
                          upper_bound=alpha_bounds[1])
    V = opti.variable(init_guess=4.5, lower_bound=0.5, upper_bound=30.0)
    m_ballast = opti.variable(init_guess=1.5e-3, lower_bound=0.0, upper_bound=2e-2)

    airplane, layout = glider(span=span, **v)
    total = structural_mass(layout)["total"] + asb.MassProperties(mass=m_ballast, x_cg=0.0)
    S_ref, mac = airplane.s_ref, airplane.c_ref
    ref = [total.x_cg, 0, airplane.xyz_ref[2]]

    # Counted like glide()'s solves, though what is timed here is CasADi graph
    # construction rather than evaluation -- the graph is built once and then
    # walked by every IPOPT iteration, so it is still the number that predicts
    # what the page costs. Without this the footer reports only the solves the
    # entry's baseline spent, and an optimisation looks free.
    t0 = time.perf_counter()
    d = asb.AeroBuildup(
        airplane=airplane, xyz_ref=ref,
        op_point=asb.OperatingPoint(atmosphere=ATMOSPHERE, velocity=V, alpha=ALPHA_LINEAR),
    ).run_with_stability_derivatives(alpha=True, beta=False, p=False, q=False, r=False)
    x_np = total.x_cg - d["Cma"] / d["CLa"] * mac

    aero = asb.AeroBuildup(
        airplane=airplane, xyz_ref=ref,
        op_point=asb.OperatingPoint(atmosphere=ATMOSPHERE, velocity=V, alpha=alpha),
    ).run()
    aero_cost["calls"] += 2
    aero_cost["seconds"] += time.perf_counter() - t0
    CL, CD = aero["CL"], aero["CD"]

    # Both force equations, glide angle a variable -- see the note in glide().
    # This matters more here than there: glide() only had to find a root, while
    # this function is actively searching for the cheapest way to satisfy the
    # constraints, and the CL = 0 degeneracy was the cheapest way of all.
    gamma = opti.variable(init_guess=np.radians(10.0),
                          lower_bound=np.radians(0.5), upper_bound=np.radians(80.0))
    q = 0.5 * ATMOSPHERE.density() * V**2
    sink = V * np.sin(gamma)

    opti.subject_to([
        aero["Cm"] == 0,
        CL * q * S_ref == total.mass * G * np.cos(gamma),
        CD * q * S_ref == total.mass * G * np.sin(gamma),
        (x_np - total.x_cg) / mac == static_margin,
    ])
    opti.minimize(sink)
    sol = opti.solve(verbose=verbose)

    out = {k: float(sol(x)) for k, x in v.items()}
    out.update({k: float(sol(x)) for k, x in dict(
        alpha=alpha, V=V, CL=CL, CD=CD, LD=CL / CD, sink=sink,
        gamma_deg=np.degrees(gamma), duration=launch_height() / sink,
        mass=total.mass, ballast=m_ballast, x_cg=total.x_cg, x_np=x_np,
        static_margin=(x_np - total.x_cg) / mac,
        chord=layout["c_root"], fuse_len=layout["fuse_len"],
        tc=FOAM_T / layout["c_root"],
        Re=ATMOSPHERE.density() * V * mac / ATMOSPHERE.dynamic_viscosity(),
        # AeroBuildup's own split, nondimensionalised on the same reference as
        # CD, so CDp + CDi recovers it. Not recomputed from a span-efficiency
        # formula -- the point of having the library do the buildup is that its
        # decomposition is the one behind the CD being reported.
        CDp=aero["D_profile"] / (q * S_ref),
        CDi=aero["D_induced"] / (q * S_ref),
    ).items()})
    return out
