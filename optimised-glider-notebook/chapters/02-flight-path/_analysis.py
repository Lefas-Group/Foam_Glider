# =============================================================================
# How this chapter measures the duration glider: by integrating the flight path.
#
# COPIED from chapters/01-duration-glider/_analysis.py at commit 41ff401, and
# this file is where the fork's deliberate difference lives. The parent measures
# a steady trimmed glide and assumes the launch is a ballistic zoom at a fixed
# efficiency; this one integrates the whole flight as a 3-DOF rigid body and
# assumes neither.
#
# The parent's trim machinery -- design_problem(), glide(), optimise(), sweep()
# -- is kept unchanged, because it is the arm this chapter compares against, and
# chapters share nothing at runtime so it cannot be borrowed from next door.
# Everything under "The flight path" is new.
#
# The vehicle is next door in _model.py; this file is every way of measuring it.
#
# It also makes the chapter discoverable. api() filters to this file, and
# _scratch/probe.py prints api() on every run -- so while everything lived in
# _model.py that listing was empty, which is how a near-duplicate of the design
# solve came to be written in a probe.
#
# Loaded by exec into the caller's namespace, AFTER _model.py: entries via the
# _model.qmd shim, scratch scripts via _scratch/probe.py. Nothing at _model.py
# top level may reference a name defined here.
#
# Quarto's freeze tracks page files, not their includes -- so after editing
# this, delete the chapter's _freeze/ directory before re-rendering.
# =============================================================================

##### Imports
import time

import aerosandbox as asb
import aerosandbox.numpy as np

##### Measurement conventions
# Angle of attack at which stability derivatives are taken -- mid lift curve,
# well clear of the plate's stall, so the neutral point is a property of the
# aircraft rather than of wherever it happens to be trimmed.
ALPHA_LINEAR = 2.0  # deg

# What the design solve is allowed to move, and how far. Dihedral and fin are
# absent on purpose: the model has no lateral dynamics, so their only benefit is
# invisible to it while their cost in span, wetted area and mass is fully
# visible, and an optimiser would delete both.
#
# Read at CALL time, never captured as a default: an entry widens a box in place
# to ask whether a bound is shaping the answer, and freezing this would turn that
# study into identical solves all reporting no gain -- a passing test measuring
# nothing.
DESIGN_BOUNDS = dict(
    aspect_ratio=(2.5, 12.0),
    tail_arm_chords=(1.5, 8.0),
    h_tail_ratio=(0.08, 0.45),
    h_tail_incidence=(-6.0, 2.0),
)


##### The analysis
def design_problem(opti, airplane, layout, ballast=None, static_margin=None,
                   alpha_bounds=(-2, 9), v_guess=6.0, ballast_guess=2e-3,
                   ballast_max=None):
    """
    State the trimmed glide on a given Opti, and return its expressions.

    The one statement of the physics in this chapter. Trimming a fixed geometry
    and designing a new one differ in what is free, not in what is true, and
    while both spelled the physics out separately a zero-lift degeneracy had to
    be found and fixed twice. Everything below is written once.

    Takes the Opti rather than making one, because a parameter belongs to
    exactly one instance -- that is what lets sweep() hold a design variable
    symbolic across many solves.

    ORDER IS LOAD-BEARING. asb.Opti.variable derives each variable's scale from
    its init_guess, and IPOPT's iterate path depends on that scaling and on the
    column order of x. So the creation order below, and each caller's differing
    guesses, are part of the answer rather than presentation -- do not tidy them
    into agreement. In particular `gamma` is created AFTER the two AeroBuildup
    calls, which is where both original functions put it.

    Args:
        opti: the caller's Opti. Any design variables must already be created on
            it, so the variable vector is the design vector followed by
            alpha, V, ballast, gamma.
        airplane, layout: from glider().
        ballast: kg, fixed. If None, solved for.
        static_margin: (x_np - x_cg) / MAC, imposed. If None, not constrained --
            which is what a fixed-ballast trim wants, since the CG is then
            already determined.
        alpha_bounds: deg. Capped below the whole-aircraft stall, near 10 deg on
            5 mm stock: past it the lift curve turns over, dCm/dalpha changes
            sign, and the neutral point the solver is chasing stops meaning
            anything. Stock-dependent -- 1.6 mm stock stalls three degrees
            earlier.
        v_guess, ballast_guess, ballast_max: per-caller initial guesses and the
            ballast cap. See the ORDER note above.

    Returns:
        dict of scalar expressions, so every caller reports with one
        comprehension over sol().
    """
    alpha = opti.variable(init_guess=4.0, lower_bound=alpha_bounds[0],
                          upper_bound=alpha_bounds[1])
    V = opti.variable(init_guess=v_guess, lower_bound=0.5, upper_bound=30.0)
    # Ballast is lead taped at the very nose, x = 0 -- the furthest forward it
    # can go, so it is also the least of it that will do the job.
    m_ballast = (ballast if ballast is not None else
                 opti.variable(init_guess=ballast_guess, lower_bound=0.0,
                               upper_bound=ballast_max))

    total = structural_mass(layout)["total"] + asb.MassProperties(mass=m_ballast, x_cg=0.0)
    # Reference area and chord come from the Airplane, not from layout: with
    # dihedral, Wing.area() returns the true panel area, which is ~1.4% larger
    # than the projected span*chord the layout records. Every coefficient below
    # is nondimensionalised on the former, so the force balance must be too.
    S_ref, mac = airplane.s_ref, airplane.c_ref
    ref = [total.x_cg, 0, airplane.xyz_ref[2]]

    # Counted as two solves, though what is timed is CasADi graph construction
    # rather than evaluation -- the graph is built once and then walked by every
    # IPOPT iteration, so it is still the number that predicts what a page costs.
    #
    # The neutral point is measured at a FIXED linear-range alpha, not at trim.
    # Taken at trim it is not a property of the aircraft at all: as the trim
    # point approaches the plate's stall, dCm/dalpha bends over and x_np ran from
    # 107 mm to 122 mm across a 0.2 g ballast change, which made any
    # static-margin constraint non-monotonic and the solve infeasible.
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
    sink = V * np.sin(gamma)

    opti.subject_to([
        aero["Cm"] == 0,  # trimmed
        CL * q * S_ref == total.mass * G * np.cos(gamma),
        CD * q * S_ref == total.mass * G * np.sin(gamma),
    ])
    if static_margin is not None:
        opti.subject_to((x_np - total.x_cg) / mac == static_margin)

    return dict(
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
    )


def _design_vector(opti, start, hold):
    """
    The four design variables, or a held value in place of any of them.

    A held value passes straight through to glider(), so it may be a float or an
    Opti parameter -- which is the whole of the sweep mechanism.
    """
    if set(hold) - set(DESIGN_BOUNDS):
        raise KeyError(f"hold: not design variables: {set(hold) - set(DESIGN_BOUNDS)}")
    v = {}
    for i, (name, (lo, hi)) in enumerate(DESIGN_BOUNDS.items()):
        v[name] = (hold[name] if name in hold else
                   opti.variable(init_guess=start[i], lower_bound=lo, upper_bound=hi))
    return v


def glide(airplane, layout, ballast=0.0, static_margin=0.30,
          alpha_bounds=(-2, 9), verbose=False):
    """
    Trim a given geometry and return its steady glide, sink rate and duration.

    Ballast is lead at the nose -- McEagle's taped dime -- and is what places the
    CG. Passing 0 instead solves for the least ballast that puts the CG at the
    requested static margin, because a duration glider wants no more than that.

    Args:
        airplane, layout: from glider().
        ballast: kg. If 0, solved for so the CG sits at the requested margin.
        static_margin: (x_np - x_cg) / MAC. The default is large for a chuck
            glider, and is forced rather than chosen: on 5 mm stock the baseline
            -2 deg tail incidence will not trim inside the alpha bounds at 20%.
            That is a symptom of the tail rigging, not a preference.
        alpha_bounds: deg, the trim search range.
        verbose: pass the solver's log through.

    Returns:
        dict of the trim state and performance. See design_problem().
    """
    opti = asb.Opti()
    prob = design_problem(
        opti, airplane, layout,
        ballast=ballast or None,
        static_margin=None if ballast else static_margin,
        alpha_bounds=alpha_bounds, v_guess=6.0, ballast_guess=2e-3,
    )
    sol = opti.solve(verbose=verbose)
    return {k: float(sol(x)) for k, x in prob.items()}


def optimise(span=0.30, static_margin=0.10, start=(6.0, 3.6, 0.22, -2.0),
             alpha_bounds=(-2, 9), hold=None, verbose=False):
    """
    Minimum sink over the four design variables, trimmed, in one solve.

    Same physics as glide() -- they share design_problem() -- with the geometry
    made symbolic and sink minimised rather than reported. Static margin is a
    constraint, not an objective term: left free it goes to zero, since nothing
    here penalises being twitchy.

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
        dict of the design, its trim state and its performance.
    """
    opti = asb.Opti()
    v = _design_vector(opti, start, hold or {})
    airplane, layout = glider(span=span, **v)
    prob = design_problem(
        opti, airplane, layout, static_margin=static_margin,
        alpha_bounds=alpha_bounds, v_guess=4.5, ballast_guess=1.5e-3,
        ballast_max=2e-2,
    )
    opti.minimize(prob["sink"])
    sol = opti.solve(verbose=verbose)
    return {**{k: float(sol(x)) for k, x in v.items()},
            **{k: float(sol(x)) for k, x in prob.items()}}


def sweep(over, values, span=0.30, static_margin=0.10,
          start=(6.0, 3.6, 0.22, -2.0), alpha_bounds=(-2, 9), hold=None,
          verbose=False):
    """
    optimise() at each value of one design variable, from a single graph build.

    The swept variable becomes an Opti parameter rather than a constant, so the
    CasADi graph is built once and re-solved per point. Measured over nine
    aspect ratios: 29.5 s this way against 46.8 s rebuilding the problem each
    time, agreeing to 2e-11. Graph construction was about a third of the old
    cost and is now paid once.

    Deliberately NOT warm-started. solve_sweep can carry each solution into the
    next as an initial guess, and it was both slower (34.7 s) and less
    trustworthy: at one point the continuation landed in a different basin than
    an independent solve, which stops the sweep being the nine independent
    answers it is read as.

    The other three variables still optimise around the held one, so each point
    is a fair comparison rather than a rival that was never allowed to adapt.

    Args:
        over: name of the design variable to sweep.
        values: the values to sweep it over.
        span, static_margin, start, alpha_bounds, hold, verbose: as optimise().

    Returns:
        list of dicts, one per value, shaped exactly like optimise()'s return.
    """
    opti = asb.Opti()
    p = opti.parameter(float(values[0]))
    v = _design_vector(opti, start, {**(hold or {}), over: p})
    airplane, layout = glider(span=span, **v)
    prob = design_problem(
        opti, airplane, layout, static_margin=static_margin,
        alpha_bounds=alpha_bounds, v_guess=4.5, ballast_guess=1.5e-3,
        ballast_max=2e-2,
    )
    opti.minimize(prob["sink"])

    # verbose=False to solve_sweep ITSELF: its default prints a progress line
    # per run, which Quarto would capture into the calling entry's output. The
    # caller's verbose goes to the individual solves instead. max_iter matches
    # Opti.solve's default of 1000 rather than solve_sweep's 200, so the sweep's
    # settings are identical to the per-point solves it replaces.
    sols = opti.solve_sweep(
        {p: np.asarray(values, dtype=float)},
        verbose=False,
        solve_kwargs=dict(verbose=verbose, max_iter=1000),
    )
    sols = list(np.asarray(sols).ravel())
    # A failed run comes back as None, which would otherwise reach the caller as
    # a TypeError on min() or, worse, a NaN in a rendered table.
    if any(s is None for s in sols):
        failed = [x for x, s in zip(values, sols) if s is None]
        raise RuntimeError(f"sweep({over!r}): no solution at {failed}")
    return [{**{k: float(s(x)) for k, x in v.items()},
             **{k: float(s(x)) for k, x in prob.items()}} for s in sols]


def design_geometry(opt, span=0.30):
    """
    Rebuild the airplane that a design solve returned.

    optimise() and sweep() report the design vector as plain numbers, so an
    entry wanting to look at that aircraft -- draw it, or measure something else
    about it -- has to hand them back to glider(). Written inline that is three
    lines which then exist in every such entry.
    """
    return glider(span=span, **{k: opt[k] for k in DESIGN_BOUNDS})


##### The flight path
#
# What this chapter adds, and the whole of its difference from chapter 01.

# Height of the CG at which the flight is over. Not zero, and the difference
# matters: the best trajectory found here descends to 16 mm and balloons back to
# 0.7 m, which over grass is a landing and in a bare integration is another
# second of flight. Any optimiser handed time aloft as an objective will find
# that and live in it, the same way one found a zero-lift vertical dive when the
# drag equation was not imposed. 50 mm is roughly grass plus the depth the
# fuselage hangs below the CG.
GROUND = 0.05  # m

# What "flies sensibly" means, as numbers. Past ~15 deg the plate is stalling and
# no section model here is fitted; past 180 deg of pitch it has gone over the top.
CLEAN_ALPHA, CLEAN_PITCH = 15.0, 180.0

# The tabulated grid. Alpha is deliberately narrow: a flight that leaves it has
# stalled, which disqualifies the design anyway, so the table's edge doubles as
# the cleanliness constraint rather than needing a separate check.
TABLE_ALPHA = np.linspace(-30.0, 30.0, 61)
TABLE_SPEED = np.linspace(0.4, 11.0, 23)
Q_REF = 1.0  # rad/s, the offset the damping slope is measured across
SM_SPEED = 4.0  # m/s, the speed static margin is evaluated at

# What a launch-optimised design may move, and how far. Ballast is free here,
# unlike chapter 01 where it followed from a pinned static margin: trim speed
# against launch speed is the whole problem, and ballast is the lever on it.
#
# aspect_ratio and launch_angle are wider than chapter 01's: a first search sat
# on both floors, and widening moved aspect ratio to an interior 3.3 while the
# angle stayed at zero -- which a sweep then showed is a genuine maximum, with
# -4 deg and +4 deg both worse. A bound is only trustworthy once the answer has
# been shown not to be resting on it.
LAUNCH_BOUNDS = dict(
    aspect_ratio=(1.2, 12.0),
    tail_arm_chords=(1.5, 8.0),
    h_tail_ratio=(0.08, 0.45),
    h_tail_incidence=(-6.0, 2.0),
    ballast_g=(0.3, 8.0),
    launch_angle=(0.0, 60.0),
)
SM_FLOOR = 0.10  # static margin the design must keep, measured at SM_SPEED


def aero_table(airplane, layout, ballast):
    """
    Tabulate this geometry's coefficients once, so a trajectory costs nothing.

    Takes the BALLAST and derives the CG itself, rather than accepting a
    reference point. An earlier version took x_cg from the caller, who passed
    the trim solve's CG while simulating a differently ballasted aircraft: 16 mm
    apart, 19% of the chord, and since Cm is measured ABOUT that point the
    pitching moment was wrong from the first step. Two places computing the same
    CG is the bug; one place is the fix, and simulate() checks the table it is
    handed came from the same aircraft.

    A direct AeroBuildup call is ~36 ms, and one trajectory needs ~460 of them,
    so a trajectory costs ~17 s and any design search costs hours. But the same
    369-point grid comes back from ONE call in 70 ms, because cost is per call
    and not per point. Tabulating therefore buys about a hundredfold, which is
    the difference between a design optimisation being minutes and being
    unaffordable.

    Damping is MEASURED, not assumed. The obvious route -- take Cmq from
    run_with_stability_derivatives and apply Cm += Cmq * q * c / (2V) -- was
    wrong by a factor of five, because that is a guess at how the library
    normalises the derivative. Instead the whole grid is evaluated twice, at
    zero pitch rate and at Q_REF, and the slope is the difference. Two calls
    instead of one, no convention assumed, and exact to linear order in q --
    which is all a buildup has anyway.

    Returns:
        dict of interpolators over (alpha, speed), plus reference dimensions.
    """
    from scipy.interpolate import RegularGridInterpolator

    total = structural_mass(layout)["total"] + asb.MassProperties(mass=ballast,
                                                                 x_cg=0.0)
    ref = [total.x_cg, 0, airplane.xyz_ref[2]]

    A, S = np.meshgrid(TABLE_ALPHA, TABLE_SPEED, indexing="ij")
    op = lambda q: asb.OperatingPoint(  # noqa: E731
        atmosphere=ATMOSPHERE, velocity=S.ravel(), alpha=A.ravel(), q=q)

    t0 = time.perf_counter()
    r0 = asb.AeroBuildup(airplane=airplane, xyz_ref=ref, op_point=op(0.0)).run()
    rq = asb.AeroBuildup(airplane=airplane, xyz_ref=ref, op_point=op(Q_REF)).run()
    aero_cost["calls"] += 2
    aero_cost["seconds"] += time.perf_counter() - t0

    grid = (TABLE_ALPHA, TABLE_SPEED)

    def interp(values):
        return RegularGridInterpolator(grid, np.array(values).reshape(A.shape),
                                       bounds_error=False, fill_value=None)

    out = {k: interp(r0[k]) for k in ["CL", "CD", "Cm"]}
    # d(coefficient)/dq, in whatever units q is given to OperatingPoint.
    out.update({f"d{k}dq": interp((np.array(rq[k]) - np.array(r0[k])) / Q_REF)
                for k in ["CL", "Cm"]})
    out["c_ref"], out["s_ref"] = float(airplane.c_ref), float(airplane.s_ref)
    out["x_cg"] = float(total.x_cg)
    out["mass"] = float(total.mass)

    # Static margin, straight off the table: SM = (x_np - x_cg)/c and
    # x_np = x_cg - Cma/CLa*c, so it is just -Cma/CLa. Worth having here because
    # a design search must respect the margin, and asking glide() for it would
    # put an Opti solve inside the loop -- a second and a half per candidate,
    # which is more than the whole trajectory costs.
    # Evaluated at SM_SPEED, not at each design's own trim speed, because the
    # latter needs a trim solve. It therefore differs from glide()'s value --
    # agreeing to 0.5% at large margins but under-reading by a few points near
    # 10%, where Re moves the plate's Cm slope most. Under-reading is the safe
    # direction for a floor, and the constraint is stated on THIS quantity so
    # nothing is hidden.
    lo, hi = ALPHA_LINEAR - 1.0, ALPHA_LINEAR + 1.0
    da = np.radians(hi - lo)
    at = lambda k, a: float(out[k](np.array([[a, SM_SPEED]]))[0])  # noqa: E731
    CLa = (at("CL", hi) - at("CL", lo)) / da
    Cma = (at("Cm", hi) - at("Cm", lo)) / da
    out["static_margin"] = -Cma / CLa if CLa != 0 else float("nan")
    return out
def simulate(airplane, layout, ballast, launch_angle, alpha_release=0.0,
             v_launch=V_LAUNCH, h_release=H_RELEASE, dt=0.02, t_max=15.0,
             table=None, ground=GROUND):
    """
    Integrate the flight forward in time, launch to ground. No solver.

    Collocation was tried first and abandoned for this: it states the whole
    flight as one algebraic system, which is efficient and differentiable but
    needs the trajectory to be findable from an initial guess. This one tumbles
    -- thrown at 2.6x its trim speed it pulls up hard, stalls and porpoises --
    and five collocation attempts up to 120 nodes all reached "local
    infeasibility" after as long as 140 s. Forward integration cannot fail to
    converge, because there is nothing to converge.

    What it costs is gradients. Every AeroBuildup call here is numeric, so no
    CasADi graph exists and nothing downstream can be differentiated. That is
    the trade: robustness for a tumbling flight, against the ability to optimise
    a design through it.

    RK4, because the pitch mode has a ~0.45 s period and rates reach several
    hundred deg/s: the flight is stiff enough that a cheap integrator would need
    a smaller step than four evaluations of a good one.

    Args:
        airplane, layout: from glider().
        ballast: kg of nose lead.
        launch_angle: deg above horizontal, of the velocity at release.
        alpha_release: deg between the glider's axis and its flight path at
            release. Zero means thrown along its own axis.
        v_launch, h_release: the throw, as specified.
        dt: s. RK4 step.
        t_max: s. Guard against a flight that never lands.

    Returns:
        dict of arrays over time, plus scalars. `landed` is False if it ran out
        of t_max, in which case nothing else should be believed.
    """
    total = structural_mass(layout)["total"] + asb.MassProperties(mass=ballast, x_cg=0.0)
    ref = [total.x_cg, 0, airplane.xyz_ref[2]]
    calls = [0]
    # A table built about a different CG silently gives the wrong pitching
    # moment, which is a plausible-looking trajectory rather than an error.
    if table is not None and abs(table["x_cg"] - float(total.x_cg)) > 1e-9:
        raise ValueError(
            f"table was built at x_cg={table['x_cg']*1e3:.1f} mm but this "
            f"aircraft has x_cg={float(total.x_cg)*1e3:.1f} mm — rebuild it")

    def deriv(s):
        dyn = asb.DynamicsRigidBody2DBody(
            mass_props=total, x_e=s[0], z_e=s[1], u_b=s[2], w_b=s[3],
            theta=s[4], q=s[5])
        speed = max(float(np.sqrt(s[2] ** 2 + s[3] ** 2)), 0.05)
        alpha = float(np.degrees(np.arctan2(s[3], s[2])))
        if table is None:
            # dyn.op_point derives velocity, alpha AND pitch rate from the state
            # -- so the operating point cannot disagree with the aircraft it came
            # from. Assembling it by hand is where this chapter's bugs lived: the
            # pitch rate was once omitted entirely, leaving an aircraft with
            # Cmq = -12.7 and no damping at all.
            #
            # The atmosphere is pinned back to the chapter's: op_point builds one
            # at the instance's altitude, which is more general but contradicts
            # the stated "sea level, still air", and moved durations by 0.09%.
            op = dyn.op_point
            op.atmosphere = ATMOSPHERE
            aero = asb.AeroBuildup(airplane=airplane, xyz_ref=ref, op_point=op).run()
            calls[0] += 1
            dyn.add_force(*aero["F_b"], axes="body")
            dyn.add_moment(My=aero["M_b"][1], axes="body")
        else:
            # Same thing from the table, with the damping added linearly.
            pt = np.array([[alpha, speed]])
            CL = float(table["CL"](pt)[0] + table["dCLdq"](pt)[0] * s[5])
            CD = float(table["CD"](pt)[0])
            Cm = float(table["Cm"](pt)[0] + table["dCmdq"](pt)[0] * s[5])
            qS = 0.5 * ATMOSPHERE.density() * speed**2 * table["s_ref"]
            a = np.radians(alpha)
            # Wind axes to body: lift is perpendicular to the flight path, drag
            # along it, and body z points DOWN.
            dyn.add_force(Fx=-CD * qS * np.cos(a) + CL * qS * np.sin(a),
                          Fz=-CL * qS * np.cos(a) - CD * qS * np.sin(a),
                          axes="body")
            dyn.add_moment(My=Cm * qS * table["c_ref"], axes="body")
        dyn.add_gravity_force(g=G)
        d = dyn.state_derivatives()
        # np.sum() first: AeroBuildup returns length-1 arrays for a scalar
        # operating point, and float() refuses anything not 0-dimensional.
        return np.array([float(np.sum(d[k])) for k in
                         ["x_e", "z_e", "u_b", "w_b", "theta", "q"]])

    a0 = np.radians(alpha_release)
    g0 = np.radians(launch_angle)
    s = np.array([0.0, -h_release, v_launch * np.cos(a0), v_launch * np.sin(a0),
                  g0 + a0, 0.0])

    t0 = time.perf_counter()
    hist, t, landed = [s.copy()], [0.0], False
    while t[-1] < t_max:
        k1 = deriv(s)
        k2 = deriv(s + 0.5 * dt * k1)
        k3 = deriv(s + 0.5 * dt * k2)
        k4 = deriv(s + dt * k3)
        s = s + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
        t.append(t[-1] + dt)
        hist.append(s.copy())
        if s[1] >= -ground:                 # z_e is positive DOWN: ground
            landed = True
            break
    aero_cost["calls"] += calls[0]
    aero_cost["seconds"] += time.perf_counter() - t0

    h = np.array(hist)
    alpha = np.degrees(np.arctan2(h[:, 3], h[:, 2]))
    # Kept for reporting, though `ground` now ends the flight before a graze can
    # become another second of it.
    _alt = -h[:, 1]
    _i = int(np.argmin(_alt[: max(2, int(len(_alt) * 0.8))]))
    # Linear interpolation onto the ground, so duration is not quantised by dt.
    duration = t[-1]
    if landed and len(t) > 1 and h[-1, 1] != h[-2, 1]:
        f = (-ground - h[-2, 1]) / (h[-1, 1] - h[-2, 1])
        duration = t[-2] + f * dt
    return dict(
        t=np.array(t), x=h[:, 0], altitude=-h[:, 1],
        speed=np.sqrt(h[:, 2] ** 2 + h[:, 3] ** 2), alpha=alpha,
        theta=np.degrees(h[:, 4]), q=np.degrees(h[:, 5]),
        duration=duration, landed=landed, launch_angle=launch_angle,
        apex=float(np.max(-h[:, 1])), range=float(h[-1, 0]),
        alpha_max=float(np.max(alpha)), mass=float(total.mass),
        aero_calls=calls[0],
        skim_altitude=float(_alt[_i]), skim_t=float(t[_i]), skim_x=float(h[_i, 0]),
    )


def evaluate(x, ground=GROUND):
    """
    One design and launch, scored. Returns (dict, penalty); penalty 0 means legal.

    `x` is in LAUNCH_BOUNDS order. Costs about 0.7 s: two tabulating aero calls
    and an interpolated integration, against ~17 s for the same trajectory with
    direct aero -- which is what makes a search possible at all.

    Constraints are returned as a penalty rather than enforced, because the
    search is derivative-free: an infeasible candidate must still be scored, or
    the optimiser cannot see which way to move.
    """
    ar, arm, sh, inc, ball_g, ang = x
    ballast = ball_g * 1e-3
    try:
        airplane, layout = glider(aspect_ratio=ar, tail_arm_chords=arm,
                                  h_tail_ratio=sh, h_tail_incidence=inc)
        table = aero_table(airplane, layout, ballast)
        s = simulate(airplane, layout, ballast=ballast, launch_angle=ang,
                     table=table, ground=ground)
    except Exception as e:                       # a geometry that will not build
        return {"error": repr(e)}, 1e3

    s["static_margin"] = table["static_margin"]
    pitch = float(np.max(np.abs(s["theta"])))
    s["pitch_max"] = pitch
    # Each term is scaled to be comparable in size, so no single constraint
    # dominates the others just by being measured in bigger units.
    s["penalty"] = (
        max(0.0, SM_FLOOR - table["static_margin"]) * 20
        + max(0.0, s["alpha_max"] - CLEAN_ALPHA) / 10
        + max(0.0, pitch - CLEAN_PITCH) / 100
        + (0.0 if s["landed"] else 10.0)
    )
    return s, s["penalty"]


def optimise_launch(start=None, maxiter=140, seed=0, ground=GROUND):
    """
    Maximise integrated time aloft over design AND launch, subject to flying cleanly.

    Nelder-Mead, because `evaluate` is a numeric integration and no gradient
    exists: every aero call inside it passes floats, so there is no CasADi graph
    to differentiate. That is the price of forward integration, and it is why
    this could not be done at all until the aero was tabulated.

    Started from chapter 01's optimum with the ballast the previous entry found,
    which is a legal point -- Nelder-Mead from an illegal start spends its
    budget getting legal.

    Returns:
        (best result dict, scipy result).
    """
    from scipy.optimize import minimize

    lo = np.array([b[0] for b in LAUNCH_BOUNDS.values()])
    hi = np.array([b[1] for b in LAUNCH_BOUNDS.values()])
    if start is None:
        start = np.array([3.49, 1.64, 0.183, -3.37, 2.33, 15.0])
    best = {"duration": -1.0}

    def cost(x):
        xc = np.clip(x, lo, hi)                 # NM ignores bounds; clip instead
        s, pen = evaluate(xc, ground=ground)
        if pen == 0 and s["duration"] > best["duration"]:
            best.clear()
            best.update(s, x=xc.copy())
        # Penalty subtracted from the objective, so an illegal candidate is
        # scored and gradients-by-simplex still point somewhere useful.
        return -(s.get("duration", 0.0)) + pen

    res = minimize(cost, np.asarray(start, dtype=float), method="Nelder-Mead",
                   options=dict(maxiter=maxiter, maxfev=maxiter * 2, xatol=1e-3,
                                fatol=1e-4, adaptive=True))
    return best, res


##### The design solve, collocated
#
# Everything above this line evaluates a design by MARCHING a trajectory forward
# and then searching over designs without gradients. This does both at once.
def _flight_once(n, sm_floor, s0, verbose):
    """One collocated solve from one start. See optimise_flight()."""
    opti = asb.Opti()

    v = {}
    for i, (name, (lo, hi)) in enumerate(list(LAUNCH_BOUNDS.items())[:4]):
        v[name] = opti.variable(init_guess=s0[i], lower_bound=lo, upper_bound=hi)
    ballast = opti.variable(init_guess=s0[4] * 1e-3, lower_bound=0.3e-3,
                            upper_bound=8e-3)

    airplane, layout = glider(**v)
    total = structural_mass(layout)["total"] + asb.MassProperties(mass=ballast,
                                                                 x_cg=0.0)
    ref = [total.x_cg, 0, airplane.xyz_ref[2]]

    # Free final time, log-transformed because a duration is strictly positive.
    T = opti.variable(init_guess=3.0, log_transform=True)
    t = np.linspace(0, T, n)
    g = np.linspace(0, 1, n)

    dyn = asb.DynamicsPointMass2DSpeedGamma(
        mass_props=total,
        x_e=opti.variable(init_guess=g * 15.0),
        z_e=opti.variable(init_guess=-(H_RELEASE + 1.0 * g
                                       - (H_RELEASE + 1.0) * g**2)),
        speed=opti.variable(init_guess=V_LAUNCH - 4.5 * g, lower_bound=0.5),
        gamma=opti.variable(init_guess=-0.1 + 0.0 * g, lower_bound=-1.4,
                            upper_bound=1.4),
        alpha=opti.variable(init_guess=5.0, n_vars=n, lower_bound=-5.0,
                            upper_bound=12.0),
    )

    t0 = time.perf_counter()
    # Pinned to the chapter's atmosphere: op_point would otherwise build one at
    # each node's own altitude, which contradicts "sea level, still air".
    op = dyn.op_point
    op.atmosphere = ATMOSPHERE
    aero = asb.AeroBuildup(airplane=airplane, op_point=op, xyz_ref=ref).run()

    # Static margin, measured exactly as chapter 01 measures it, at one
    # reference condition -- the design must be stable, not merely trimmed.
    d = asb.AeroBuildup(
        airplane=airplane, xyz_ref=ref,
        op_point=asb.OperatingPoint(atmosphere=ATMOSPHERE, velocity=SM_SPEED,
                                    alpha=ALPHA_LINEAR),
    ).run_with_stability_derivatives(alpha=True, beta=False, p=False, q=False,
                                     r=False)
    aero_cost["calls"] += 2
    aero_cost["seconds"] += time.perf_counter() - t0
    mac = airplane.c_ref
    static_margin = -d["Cma"] / d["CLa"]

    dyn.add_force(*aero["F_w"], axes="wind")
    dyn.add_gravity_force(g=G)
    dyn.constrain_derivatives(opti, t)

    opti.subject_to([
        # Trimmed at every node: alpha is what the airframe holds, not a choice.
        aero["Cm"] == 0,
        static_margin > sm_floor,
        dyn.x_e[0] == 0,
        dyn.z_e[0] == -H_RELEASE,
        dyn.speed[0] == V_LAUNCH,
        dyn.altitude > GROUND,
        dyn.z_e[-1] == -GROUND,
    ])
    opti.maximize(T)
    sol = opti.solve(verbose=verbose, max_iter=500)

    out = {k: float(sol(x)) for k, x in v.items()}
    out.update(
        duration=float(sol(T)), ballast=float(sol(ballast)),
        static_margin=float(np.sum(sol(static_margin))),
        mass=float(sol(total.mass)),
        t=np.linspace(0, float(sol(T)), n), x=sol(dyn.x_e),
        altitude=-sol(dyn.z_e), speed=sol(dyn.speed),
        alpha=sol(dyn.alpha), gamma_deg=np.degrees(sol(dyn.gamma)),
        Cm_residual=float(np.max(np.abs(sol(aero["Cm"])))),
        range=float(sol(dyn.x_e)[-1]), apex=float(np.max(-sol(dyn.z_e))),
        iters=int(sol.stats()["iter_count"]),
    )
    # The launch is only as violent as the speed it must shed; report it.
    out["speed_ratio"] = V_LAUNCH / float(np.median(sol(dyn.speed)[n // 2:]))
    return out


# Starts for the multistart below. Not decoration: the collocated solve is
# multi-modal, and which basin it lands in was shown to depend on the alpha box
# -- durations of 3.7, 5.1 and 5.6 s came out of three boxes that differed only
# in a bound nobody had a physical reason to place exactly. Varying the START at
# FIXED bounds is the honest version of that experiment.
FLIGHT_STARTS = [
    (3.5, 3.0, 0.22, -2.0, 2.3),
    (5.0, 5.0, 0.30, -1.0, 1.5),
    (2.8, 2.0, 0.12, -4.0, 3.5),
    (7.0, 6.5, 0.38, +0.5, 1.0),
]


def optimise_flight(n=40, sm_floor=SM_FLOOR, starts=None, verbose=False):
    """
    Maximise time aloft over design AND trajectory, by collocation.

    The whole flight is stated as constraints rather than integrated, so the
    geometry variables sit in the same Opti as the trajectory and IPOPT gets
    exact gradients through the aerodynamics. No tabulated surrogate, so no
    interpolation error and no CG-mismatch failure mode.

    WHY A POINT MASS. Rigid-body collocation does not converge for this
    aircraft. Thrown well above its trim speed it loops and tumbles, and that
    map from initial conditions to final state is chaotically sensitive, so the
    constraint Jacobian is ill-conditioned; seeding from a converged RK4
    trajectory still failed, in 11 s rather than 140 s. A point mass has no
    pitch state to tumble.

    WHAT THAT COSTS. A point mass trims instantly, so it CANNOT loop -- it
    never sees the launch transient that simulate() exists to show. `Cm == 0` at
    every node keeps it honest as far as it goes: alpha is then whatever the
    airframe trims at rather than a pilot's choice.

    MULTISTART IS NOT OPTIONAL. One solve is fast but lands in a local optimum,
    and the basin depends on where it started. That is what the speed is for --
    a hundred seconds a solve is only worth having if several are run.

    NOT GRID-CONVERGED, and the direction matters. A 4-start multistart gives
    4.37 s at n=40 and 4.04 s at n=60 -- 8% apart -- while n=80 does not converge
    at all (286 s to failure). A coarse grid under-resolves the trajectory and
    can therefore OVERSTATE the objective, so the coarse number is not a bound on
    the true optimum in either direction. Treat any duration here as indicative
    of the method, not of the aircraft. The same fragility shows
    in the alpha box: durations of 3.7, 4.2, 5.1 and 5.6 s came out of four
    boxes differing only in bounds nobody had a physical reason to place
    exactly, which is why those bounds are now fixed and the START is varied
    instead.

    Args:
        n: collocation nodes.
        sm_floor: minimum static margin, measured as chapter 01 measures it.
        starts: list of (aspect_ratio, tail_arm_chords, h_tail_ratio,
            h_tail_incidence, ballast_g). Defaults to FLIGHT_STARTS.
        verbose: pass the solver's log through.

    Returns:
        dict of the best solve, plus `attempts` (durations of every start, None
        where it failed) so the spread is visible rather than hidden.
    """
    tried, best = [], None
    for s0 in (starts if starts is not None else FLIGHT_STARTS):
        try:
            r = _flight_once(n, sm_floor, s0, verbose)
        except Exception:            # an infeasible start is data, not an error
            tried.append(None)
            continue
        tried.append(r["duration"])
        if best is None or r["duration"] > best["duration"]:
            best = r
    if best is None:
        raise RuntimeError(f"no start converged: {tried}")
    best["attempts"] = tried
    best["n_converged"] = sum(x is not None for x in tried)
    best["spread"] = max(x for x in tried if x) - min(x for x in tried if x)
    return best
