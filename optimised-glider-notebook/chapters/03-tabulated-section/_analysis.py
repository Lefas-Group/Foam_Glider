# =============================================================================
# How this chapter measures the duration glider -- with the section polar read
# from a table instead of from NeuralFoil.
#
# FORKED FROM chapters/01-duration-glider at c55172e. A fidelity fork, so the
# difference is confined to THIS file and _model.py is byte-identical to its
# parent: `diff` the two models and an empty result is the positive check that
# the aircraft did not move, leaving the aerodynamic method as the only variable.
#
# The deliberate differences, all of them:
#   1. section_table() samples NeuralFoil once over (alpha, Re, t/c) and fits a
#      CasADi B-spline to each of CL, CD, CM.
#   2. CachedPlate serves those splines through the one method AeroBuildup uses
#      to reach a section, so nothing else in the aero path changes.
#   3. optimise() takes `table=`, and swaps the sections after glider() has
#      built the aircraft -- so both arms optimise the same geometry.
# Chapter 01's answers stay true of exact NeuralFoil; this chapter exists to be
# compared against them, which is why it is a fork rather than an edit.
#
# It takes the DEFAULT solve budget: unlike its parent, nothing here is frozen
# yet, so there is no published number a budget could truncate.
#
# The vehicle is next door in _model.py; this file is every way of measuring it.
# The split is the tier rule: a measurement lives here once a SECOND entry
# reaches for it, and two entries reached for glide() while four reached for
# optimise().
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
import casadi as ca
import numpy as onp  # the real one: building the table is numeric, never traced

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
##### The tabulated section
#
# Grids sized to what this chapter's design space actually reaches, not to what
# an airfoil could see. Aspect ratio 2.5..12 on a 300 mm span puts the root
# chord between 120 and 25 mm, so t/c is pinned between 4% and 20% by the stock
# thickness; trimmed speeds of 4..8 m/s over those chords put Reynolds inside
# 1e4..1e5. Alpha runs wider than the solve's own bounds because AeroBuildup
# asks each surface for its own local angle, not the aircraft's.
#
# Reynolds gets the most points on purpose. Sampling one axis at a time against
# NeuralFoil put essentially all the interpolation error on it -- the stall knee
# moves fast with Re down here, while alpha and t/c are smooth -- so a grid that
# spends its points evenly would be refining the two axes that did not need it.
TABLE_ALPHA = np.arange(-25.0, 35.01, 1.0)
TABLE_LOGRE = np.linspace(3.6, 5.2, 24)
TABLE_TC = np.linspace(0.04, 0.21, 9)


def section_table():
    """
    Sample NeuralFoil over (alpha, Re, t/c) once, and fit a spline to each of
    CL, CD, CM.

    Cheap to sample and dear to fit, which is the whole shape of the idea: an
    AeroBuildup-style call costs the same for one operating point as for
    thousands, so the entire grid comes back in a handful of calls -- one per
    t/c station, since t/c is the only thing that changes the aerofoil.

    The section is a ONE-PARAMETER family, which is what makes three axes
    enough: _model.py scales every Kulfan weight linearly from one reference
    fit, so t/c fixes the shape completely. A fixed catalogue aerofoil would
    need only two axes; a camber or bevel variable would need four, and the fit
    cost grows faster than the grid does.

    CD is fitted in log, because it spans more than two decades across the
    tabulated alpha range and a linear fit would spend its resolution on the
    stalled end nobody trims at.

    Returns:
        {"CL": f, "CD": f, "CM": f}, each callable on a 3xN of
        (alpha_deg, log10 Re, t/c), plus "seconds" and "points".
    """
    t0 = time.perf_counter()
    grid_a, grid_re = np.meshgrid(TABLE_ALPHA, 10 ** TABLE_LOGRE, indexing="ij")
    shape = (len(TABLE_ALPHA), len(TABLE_LOGRE), len(TABLE_TC))
    raw = {k: onp.zeros(shape) for k in ("CL", "CD", "CM")}
    for k, tc in enumerate(TABLE_TC):
        polar = plate_section(chord=FOAM_T / tc).get_aero_from_neuralfoil(
            alpha=grid_a.ravel(), Re=grid_re.ravel(), mach=0.0, model_size="large")
        for key in raw:
            raw[key][:, :, k] = onp.array(polar[key]).reshape(grid_a.shape)

    axes = [TABLE_ALPHA.tolist(), TABLE_LOGRE.tolist(), TABLE_TC.tolist()]
    fit = {k: ca.interpolant(k, "bspline", axes,
                             (onp.log(raw[k]) if k == "CD" else raw[k])
                             .ravel(order="F").tolist())
           for k in raw}
    fit["seconds"] = time.perf_counter() - t0
    fit["points"] = int(onp.prod(shape))
    return fit


class CachedPlate(asb.KulfanAirfoil):
    """
    A plate section whose polar comes from the table rather than the network.

    Overrides the ONE method AeroBuildup uses to reach a section, so everything
    above the section -- strip integration, induced drag, the tail, the balance
    -- is untouched and the comparison isolates the aerofoil. Only CL, CD and CM
    are read from the returned dict, which is why nothing else is provided.

    Subclasses rather than duck-types, because the wing still asks the aerofoil
    for its coordinates and its camber elsewhere.

    `tc` may be a CasADi expression: it is an INPUT to the spline, not a
    property of it, so a chord that is still a design variable differentiates
    through the table exactly as it did through the network.
    """

    def get_aero_from_neuralfoil(self, alpha, Re, mach=0.0,
                                 control_surfaces=None, **kwargs):
        log_re = np.log10(np.fmax(Re, 10 ** TABLE_LOGRE[0]))
        cols = [alpha, log_re, self.tc]
        n = max(c.numel() if np.is_casadi_type(c) else onp.size(c) for c in cols)
        if any(np.is_casadi_type(c) for c in cols):
            stacked = ca.horzcat(*[
                ca.reshape(c if np.is_casadi_type(c) else ca.DM(onp.asarray(c, float)),
                           n, 1) if (np.is_casadi_type(c) or onp.size(c) > 1)
                else ca.DM.ones(n, 1) * float(c)
                for c in cols]).T
        else:
            stacked = onp.stack([onp.broadcast_to(onp.asarray(c, float), (n,))
                                 for c in cols])
        out = {k: self.table[k](stacked) for k in ("CL", "CD", "CM")}
        flat = (lambda v: v.T) if np.is_casadi_type(stacked) else (
            lambda v: onp.asarray(v).ravel())
        return {"CL": flat(out["CL"]), "CD": np.exp(flat(out["CD"])),
                "CM": flat(out["CM"])}


def section_error(table, n=200, seed=0):
    """
    Worst CL the table gets wrong, sampled where a spline is worst.

    Between its own nodes, never on them: an interpolating spline reproduces its
    grid exactly, so agreement at a node tests the plumbing and says nothing
    about resolution. Sampling uniformly inside the box tests the thing that
    matters, and one call covers every sample because cost is per call.

    Args:
        table: from section_table().
        n: sample count.
        seed: fixed, so the number an entry quotes is the number it re-renders.

    Returns:
        max absolute error in CL across the sample.
    """
    rng = onp.random.default_rng(seed)
    a = rng.uniform(TABLE_ALPHA[0], TABLE_ALPHA[-1], n)
    lre = rng.uniform(TABLE_LOGRE[0], TABLE_LOGRE[-1], n)
    tc = rng.uniform(TABLE_TC[0], TABLE_TC[-1], n)

    worst = 0.0
    for value in onp.unique(tc):            # one aerofoil per t/c, as when built
        pick = tc == value
        truth = plate_section(chord=FOAM_T / value).get_aero_from_neuralfoil(
            alpha=a[pick], Re=10 ** lre[pick], mach=0.0, model_size="large")
        got = onp.asarray(table["CL"](
            onp.stack([a[pick], lre[pick], onp.full(pick.sum(), value)]))).ravel()
        worst = max(worst, float(onp.max(onp.abs(
            got - onp.asarray(truth["CL"]).ravel()))))
    return worst


def tabulate(airplane, layout, table):
    """
    Swap every surface onto the tabulated section, in place.

    ONE section built from the root chord, reused on tail and fin, because that
    is what _model.py does -- an earlier attempt gave each surface its own t/c
    and doubled the drag at high aspect ratio, where the tail chord is smallest.
    A cache has to reproduce what the model does, not what looks reasonable.
    """
    exact = plate_section(layout["c_root"])
    cached = CachedPlate(
        name="tabulated-plate", upper_weights=exact.upper_weights,
        lower_weights=exact.lower_weights,
        leading_edge_weight=exact.leading_edge_weight,
        TE_thickness=exact.TE_thickness)
    cached.tc = FOAM_T / layout["c_root"]
    cached.table = table
    for wing in airplane.wings:
        for xsec in wing.xsecs:
            xsec.airfoil = cached
    return airplane


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
             alpha_bounds=(-2, 9), hold=None, verbose=False, table=None):
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
        table: from section_table(). None runs the exact network, which is what
            chapter 01 does and what this chapter's answers are measured against.

    Returns:
        dict of the design, its trim state and its performance.
    """
    opti = asb.Opti()
    v = _design_vector(opti, start, hold or {})
    airplane, layout = glider(span=span, **v)
    if table is not None:
        # After glider(), so both arms optimise the same aircraft and the
        # section is the only difference between them.
        tabulate(airplane, layout, table)
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
