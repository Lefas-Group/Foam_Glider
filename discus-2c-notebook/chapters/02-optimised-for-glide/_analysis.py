# =============================================================================
# How this chapter measures the aircraft.
#
# Helpers arrive here by PROMOTION -- when a second entry reaches for something
# an earlier one wrote inline -- never by anticipation. The vehicle itself, and
# the trim/glide/calibration primitives, live in _model.py.
# =============================================================================


def calibrated_polar(speed, mass=MASS, altitude=0.0):
    """
    The trimmed glide polar with this chapter's drag calibration already applied.

    Promoted the moment a third entry wanted it: trimming, calibrating and
    converting to glide quantities is the same three lines everywhere, and three
    consecutive repeated lines is exactly what rule 2 forbids. Keeping it in one
    place also means no entry can quietly calibrate against a different target
    than its neighbours.

    Costs whatever `trim_polar` costs -- about six AeroBuildup calls, regardless
    of how many speeds are asked for, because the secant iterates the whole
    speed array at once. `calibrate` itself costs nothing: the offset shifts CD
    without touching CL, so it runs on arrays that already exist.

    Returns the trimmed polar, the glide quantities and the offset in one dict,
    so an entry can quote the calibration it ran under rather than assume it.
    """
    polar = trim_polar(speed, mass=mass, altitude=altitude)
    offset = calibrate(polar)
    return {**polar, **glide(polar, offset), "drag_offset": offset}


def spanwise_load(total_lift, airplane=None, speed=30.0, alpha=8.0,
                  spanwise=14, chordwise=6):
    """
    Spanwise airload on one wing, from a linear method, scaled to a known total.

    Promoted the moment a second entry wanted it. The panel bookkeeping below is
    the part worth writing once: VLM emits panels ordered CHORDWISE-FASTEST, so a
    reshape recovers the spanwise strips, and grouping on the y coordinate
    instead does NOT work -- twist and dihedral move y by about a millimetre
    across a chord, so every panel looks like its own strip. Both facts are
    asserted rather than trusted.

    A linear method on purpose. Structural load distributions are conventionally
    built from one, because what the wing sees at high load factor is the
    attached-flow ("additional") loading, which is exactly what an inviscid
    method returns. AeroBuildup cannot do this at all: it exposes integrated
    forces per component and no spanwise distribution.

    VLM supplies the SHAPE only. The magnitude is set by `total_lift`, which the
    caller knows exactly from the load factor, so the distribution is normalized
    rather than trusted.

    Args:
        total_lift: lift carried by ONE wing, N.
        airplane: defaults to the chapter's rigid geometry.
        speed, alpha: the operating point the shape is taken at.

    Returns dict of station_y, width, strip_force and load_per_metre.
    """
    airplane = AIRPLANE if airplane is None else airplane
    vlm = asb.VortexLatticeMethod(
        airplane=airplane,
        op_point=asb.OperatingPoint(velocity=speed, alpha=alpha),
        xyz_ref=XYZ_REF, spanwise_resolution=spanwise, chordwise_resolution=chordwise,
    )
    started = time.perf_counter()
    vlm.run()
    aero_cost["calls"] += 1
    aero_cost["seconds"] += time.perf_counter() - started

    on_wing = (vlm.vortex_centers[:, 0] < 4.0) & (vlm.vortex_centers[:, 1] > 0)
    y_grid = vlm.vortex_centers[on_wing, 1].reshape(-1, chordwise)
    width_grid = np.abs(vlm.right_vortex_vertices[on_wing, 1]
                        - vlm.left_vortex_vertices[on_wing, 1]).reshape(-1, chordwise)
    station_y = y_grid.mean(axis=1)
    width = width_grid.mean(axis=1)

    # Had the reshape mixed chordwise panels across strips, the strip stations
    # would not come out monotonic -- a far better invariant than equal panel
    # widths within a column, which twist and dihedral perturb by a few percent
    # and which failed on a valid, strongly twisted geometry.
    assert np.all(np.diff(station_y) > 0), \
        "strip stations are not increasing; the reshape is not recovering strips"
    assert np.max(np.abs(width_grid - width[:, None]) / width[:, None]) < 0.05, \
        "panel widths vary by over 5% within a strip"
    strip_force = vlm.forces_geometry[on_wing, 2].reshape(-1, chordwise).sum(axis=1)
    strip_force = strip_force * total_lift / np.sum(strip_force)

    return {
        "station_y": station_y,
        "width": width,
        "strip_force": strip_force,
        "load_per_metre": strip_force / width,
    }


def reference_point():
    """
    The chapter's best-glide condition: the one point comparisons are made at.

    Promoted because two entries independently rebuilt the same polar to find the
    same lift coefficient, which is three identical lines and rule 2's exact
    case. Keeping it here also means a comparison cannot silently drift onto a
    different reference than the entry it is being compared with.

    Costs one `calibrated_polar`, so about six AeroBuildup calls.
    """
    polar = calibrated_polar(np.linspace(21.0, 55.0, 120))
    best = int(np.argmax(polar["L_over_D"]))
    return {
        "CL": float(polar["CL"][best]),
        "speed": float(polar["speed"][best]),
        "L_over_D": float(polar["L_over_D"][best]),
        "polar": polar,
    }


def drag_at_reference(build, cl_ref, alphas):
    """
    Sweep alpha with one analysis, then read drag off its CL-CD curve at `cl_ref`.

    Comparing methods at a common LIFT COEFFICIENT rather than a common alpha is
    the whole point, and is why this exists instead of a bare sweep: the methods
    here disagree on lift-curve slope by nearly 20%, so a fixed alpha would put
    them at four different flight conditions and call the difference "drag".

    A loop over alpha, because only AeroBuildup accepts an alpha array -- VLM and
    the two lifting-line methods each solve one operating point at a time. This
    is not the convergence loop rule 5 forbids: the pass count is fixed by the
    sweep, not by a tolerance, and every call is a point actually wanted.

    Args:
        build: callable taking one alpha in degrees, returning an analysis dict.
        cl_ref: the lift coefficient to report drag at.
        alphas: the sweep, in degrees, ascending.
    """
    lift, drag = [], []
    for alpha in alphas:
        started = time.perf_counter()
        out = build(float(alpha))
        aero_cost["calls"] += 1
        aero_cost["seconds"] += time.perf_counter() - started
        lift.append(float(np.atleast_1d(out["CL"])[0]))
        drag.append(float(np.atleast_1d(out["CD"])[0]))

    # np.interp extrapolates flat and silently, so a reference CL outside the
    # sweep would come back as an endpoint dressed up as an answer.
    assert min(lift) <= cl_ref <= max(lift), \
        f"reference CL {cl_ref:.3f} outside the sweep {min(lift):.3f}..{max(lift):.3f}"
    return float(np.interp(cl_ref, lift, drag))


def speed_to_fly(polar_result, macready):
    """
    MacCready speed to fly, and the resulting cross-country speed, for each setting.

    The classic construction: the best speed for a given expected climb rate is
    where a line drawn from (0, -macready) is tangent to the sink polar, which
    is the speed satisfying dw/dV = (w + macready) / V. Solved on the polar grid
    by picking the speed that maximises the achieved cross-country speed
    directly -- equivalent, and it cannot land on the wrong branch of the
    tangency condition the way a derivative root-find can near minimum sink.

    Costs no aero: it reads a polar the caller already paid for.

    Args:
        polar_result: output of `calibrated_polar`.
        macready: expected climb rate(s), m/s. Zero means "final glide".

    Returns dict of speed to fly, achieved cross-country speed and glide ratio.
    """
    speed, sink = polar_result["speed"], polar_result["sink"]
    macready = np.atleast_1d(np.array(macready, dtype=float))

    # Cross-country speed for a climb-cruise cycle: the classic result
    # V_xc = M * V / (M + w), undefined only where the climb rate is zero.
    speeds_to_fly, cross_country = [], []
    for setting in macready:
        if setting <= 0.0:
            # Final glide: no climb to trade against, so fly for best glide.
            best = int(np.argmax(speed / sink))
        else:
            best = int(np.argmax(setting * speed / (setting + sink)))
        speeds_to_fly.append(speed[best])
        cross_country.append(
            setting * speed[best] / (setting + sink[best]) if setting > 0 else 0.0
        )

    return {
        "macready": macready,
        "speed_to_fly": np.array(speeds_to_fly),
        "cross_country": np.array(cross_country),
    }


def best_glide(analysis, airplane, speed, offset=0.0, alphas=None, **options):
    """
    Best glide ratio over an alpha sweep, with each method judged on its own terms.

    Promoted from this chapter's first entry when its second wanted the same
    sweep. FORKED CHAPTERS DIVERGE HERE: chapter 01 has no such function, so this
    file is no longer byte-identical to its parent, and the fork header in
    `_model.py` records that.

    The offset is an argument rather than a constant because it belongs to
    AeroBuildup: it was fitted to AeroBuildup's drag on the baseline geometry, so
    handing it to a different method would credit that method with a correction
    for an error it does not make. LiftingLine is therefore read raw, and only
    the RELATIVE change between two aircraft is compared across methods.
    """
    alphas = np.linspace(-1.0, 7.0, 9) if alphas is None else alphas
    lift, drag = [], []
    for alpha in alphas:
        started = time.perf_counter()
        out = analysis(airplane=airplane, xyz_ref=XYZ_REF,
                       op_point=asb.OperatingPoint(velocity=speed, alpha=float(alpha)),
                       **options).run()
        aero_cost["calls"] += 1
        aero_cost["seconds"] += time.perf_counter() - started
        lift.append(float(np.atleast_1d(out["CL"])[0]))
        drag.append(float(np.atleast_1d(out["CD"])[0]) + offset)
    return float(np.max(np.array(lift) / np.array(drag)))


def baseline_setup():
    """
    The baseline aircraft, as everything an optimization entry needs to start from.

    Promoted when a second entry rebuilt the same four lines: the calibrated
    polar, its best-glide point, the drag offset fitted there, and the limits the
    optimizer inherits. Bundled rather than left loose so that two entries cannot
    optimize against subtly different baselines and then compare their answers.

    Costs one `reference_point` plus one derivative call, about seven solves.
    """
    reference = reference_point()
    offset = reference["polar"]["drag_offset"]
    return {
        "drag_offset": offset,
        "speed": reference["speed"],
        "L_over_D": reference["L_over_D"],
        "limits": baseline_limits(offset),
    }


def constrained_redesign(setup=None):
    """
    The redesign that cannot exploit the model, built the same way every time.

    Promoted once a third entry wanted it. The three constraints it applies are
    the ones the unconstrained optimum was found to be abusing: twist that
    oscillated to its bound, a tip chord that collapsed into a Reynolds regime
    the section data does not cover, and span bought without paying for the spar
    that carries it.

    The Reynolds floor is the BASELINE's own tip value, not a number invented
    for the purpose -- the design may not push the section anywhere the real
    aircraft does not already operate -- and it is returned alongside the design
    so an entry can assert the constraint actually bound.
    """
    setup = baseline_setup() if setup is None else setup
    floor = float(STATION_C[-1] * setup["speed"] / KINEMATIC_VISCOSITY)
    design = optimise(setup["limits"], washout_monotone=True,
                      reynolds_floor=floor, mass_model=True)
    return {**design, "reynolds_floor": floor}
