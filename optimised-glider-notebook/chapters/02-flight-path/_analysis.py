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
def simulate(airplane, layout, ballast, launch_angle, alpha_release=0.0,
             v_launch=V_LAUNCH, h_release=H_RELEASE, dt=0.02, t_max=15.0):
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

    def deriv(s):
        dyn = asb.DynamicsRigidBody2DBody(
            mass_props=total, x_e=s[0], z_e=s[1], u_b=s[2], w_b=s[3],
            theta=s[4], q=s[5])
        speed = float(np.sqrt(s[2] ** 2 + s[3] ** 2))
        alpha = float(np.degrees(np.arctan2(s[3], s[2])))
        # The pitch rate must go into the operating point, not just the state.
        # Without it AeroBuildup returns static coefficients only, the aircraft
        # has no pitch damping at all, and an oscillation that should decay runs
        # forever -- Cmq is -12.7 /rad here, so this is not a small term.
        aero = asb.AeroBuildup(
            airplane=airplane, xyz_ref=ref,
            op_point=asb.OperatingPoint(atmosphere=ATMOSPHERE,
                                        velocity=max(speed, 0.05), alpha=alpha,
                                        q=float(s[5])),
        ).run()
        calls[0] += 1
        dyn.add_force(Fx=aero["F_b"][0], Fz=aero["F_b"][2], axes="body")
        dyn.add_moment(My=aero["M_b"][1], axes="body")
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
        if s[1] >= 0:                       # z_e is positive DOWN: ground
            landed = True
            break
    aero_cost["calls"] += calls[0]
    aero_cost["seconds"] += time.perf_counter() - t0

    h = np.array(hist)
    alpha = np.degrees(np.arctan2(h[:, 3], h[:, 2]))
    # The lowest approach BEFORE the final descent. A glider that skims the
    # ground and balloons back up has, on grass, landed -- and the integrator
    # will happily fly on if it misses by a centimetre, so the duration alone
    # can quietly describe a flight nobody gets. Reported so the caller can
    # judge rather than have a contact threshold chosen for them.
    _alt = -h[:, 1]
    _i = int(np.argmin(_alt[: max(2, int(len(_alt) * 0.8))]))
    # Linear interpolation onto the ground, so duration is not quantised by dt.
    duration = t[-1]
    if landed and len(t) > 1 and h[-1, 1] != h[-2, 1]:
        f = -h[-2, 1] / (h[-1, 1] - h[-2, 1])
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
