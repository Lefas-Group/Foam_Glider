import aerosandbox as asb
import aerosandbox.numpy as np


def glide_polar(
    airplane: asb.Airplane,
    mass: float = 417.0,
    speeds_kmh: np.ndarray = None,
    rho: float = 1.225,
) -> dict:
    """Compute the steady unaccelerated 1-g glide polar across speeds using AeroBuildup."""
    if speeds_kmh is None:
        speeds_kmh = np.linspace(75, 200, 26)
    speeds = np.array(speeds_kmh) / 3.6
    weight = mass * 9.81
    s_ref = airplane.s_ref

    cls = []
    cds = []
    cd_ind = []
    cd_prof = []
    lds = []
    sinks = []
    alphas_trim = []

    alphas_grid = np.linspace(-2, 10, 61)
    for V in speeds:
        CL_req = 2 * weight / (rho * s_ref * V**2)
        op = asb.OperatingPoint(velocity=V, alpha=alphas_grid)
        aero = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        cl_arr = aero["CL"]
        alpha_t = float(np.interp(CL_req, cl_arr, alphas_grid))
        cd_t = float(np.interp(alpha_t, alphas_grid, aero["CD"]))
        cdi_t = float(np.interp(alpha_t, alphas_grid, aero["D_induced"] / (0.5 * rho * V**2 * s_ref)))
        cdp_t = cd_t - cdi_t
        ld_t = CL_req / cd_t

        alphas_trim.append(alpha_t)
        cls.append(float(CL_req))
        cds.append(cd_t)
        cd_ind.append(cdi_t)
        cd_prof.append(cdp_t)
        lds.append(ld_t)
        sinks.append(float(V / ld_t))

    return {
        "speeds_kmh": np.array(speeds_kmh),
        "alpha": np.array(alphas_trim),
        "CL": np.array(cls),
        "CD": np.array(cds),
        "CD_induced": np.array(cd_ind),
        "CD_profile": np.array(cd_prof),
        "LD": np.array(lds),
        "sink_rate": np.array(sinks),
    }


def evaluate_fidelities(
    airplane: asb.Airplane,
    velocity: float,
    alpha: float,
) -> dict:
    """Compare aerodynamic predictions across VLM, AeroBuildup, and LiftingLine."""
    op = asb.OperatingPoint(velocity=velocity, alpha=alpha)
    ab = asb.AeroBuildup(airplane=airplane, op_point=op).run()
    vlm = asb.VortexLatticeMethod(airplane=airplane, op_point=op, verbose=False).run()
    ll = asb.LiftingLine(airplane=airplane, op_point=op, verbose=False).run()

    return {
        "AeroBuildup": {
            "CL": float(ab["CL"][0]),
            "CD": float(ab["CD"][0]),
            "LD": float(ab["CL"][0] / ab["CD"][0]),
        },
        "VLM": {
            "CL": float(vlm["CL"]),
            "CD": float(vlm["CD"]),
            "LD": float(vlm["CL"] / vlm["CD"]),
        },
        "LiftingLine": {
            "CL": float(ll["CL"]),
            "CD": float(ll["CD"]),
            "LD": float(ll["CL"] / ll["CD"]),
        },
    }


def wing_structural_loads(
    airplane: asb.Airplane,
    mass: float = 565.0,
    load_factor: float = 5.3,
    velocity: float = 55.56,
    wing_dry_mass: float = 140.0,
    water_ballast_mass: float = 148.0,
    ballast_span_extent: tuple = (0.5, 4.5),
    n_eval_stations: int = 100,
) -> dict:
    """Compute spanwise aerodynamic and net structural loads under a specified manoeuvre load factor."""
    g = 9.81
    total_lift_req = mass * g * load_factor

    # Find trim alpha for target lift using VLM
    op0 = asb.OperatingPoint(velocity=velocity, alpha=4.0)
    vlm0 = asb.VortexLatticeMethod(airplane=airplane, op_point=op0, verbose=False).run()
    op1 = asb.OperatingPoint(velocity=velocity, alpha=8.0)
    vlm1 = asb.VortexLatticeMethod(airplane=airplane, op_point=op1, verbose=False).run()

    dL_da = (vlm1["L"] - vlm0["L"]) / 4.0
    alpha_trim = 4.0 + (total_lift_req - vlm0["L"]) / dL_da

    op_trim = asb.OperatingPoint(velocity=velocity, alpha=alpha_trim)
    vlm_sol = asb.VortexLatticeMethod(airplane=airplane, op_point=op_trim, verbose=False)
    vlm_res = vlm_sol.run()

    # Extract starboard main wing panel forces (geometry axes)
    x_c = np.array(vlm_sol.vortex_centers[:, 0])
    y_c = np.array(vlm_sol.vortex_centers[:, 1])
    Fz = np.array(vlm_sol.forces_geometry[:, 2])

    is_sb = (x_c < 4.0) & (y_c >= 0)
    y_panels = y_c[is_sb]
    fz_panels = Fz[is_sb]

    b_semi = float(airplane.b_ref / 2)
    y_stations = np.linspace(0, b_semi, n_eval_stations)

    # Aerodynamic shear and bending moment at stations y_cut
    shear_aero = np.array([np.sum(fz_panels[y_panels >= y]) for y in y_stations])
    moment_aero = np.array([
        np.sum((y_panels[y_panels >= y] - y) * fz_panels[y_panels >= y])
        for y in y_stations
    ])

    # Wing chord distribution
    wing = airplane.wings[0]
    wing_ys = np.array([xsec.xyz_le[1] for xsec in wing.xsecs])
    wing_chords = np.array([xsec.chord for xsec in wing.xsecs])
    chords_eval = np.interp(y_stations, wing_ys, wing_chords)

    # Dry wing mass distribution proportional to chord
    half_area = np.trapezoid(chords_eval, y_stations)
    m_wing_semi = wing_dry_mass / 2.0
    dm_wing_dy = m_wing_semi * chords_eval / half_area
    df_wing_dy = dm_wing_dy * load_factor * g

    # Water ballast distribution in tank extent
    m_ballast_semi = water_ballast_mass / 2.0
    tank_mask = (y_stations >= ballast_span_extent[0]) & (
        y_stations <= ballast_span_extent[1]
    )
    ballast_chord_sq = np.where(tank_mask, chords_eval**2, 0.0)
    denom_ballast = np.trapezoid(ballast_chord_sq, y_stations)
    dm_ballast_dy = m_ballast_semi * ballast_chord_sq / denom_ballast
    df_ballast_dy = dm_ballast_dy * load_factor * g

    # Integrate inertia relief shear and moment from tip inward
    shear_wing_inertia = np.array([
        np.trapezoid(df_wing_dy[i:], y_stations[i:])
        for i in range(len(y_stations))
    ])
    moment_wing_inertia = np.array([
        np.trapezoid((y_stations[i:] - y_stations[i]) * df_wing_dy[i:], y_stations[i:])
        for i in range(len(y_stations))
    ])

    shear_ballast_inertia = np.array([
        np.trapezoid(df_ballast_dy[i:], y_stations[i:])
        for i in range(len(y_stations))
    ])
    moment_ballast_inertia = np.array([
        np.trapezoid((y_stations[i:] - y_stations[i]) * df_ballast_dy[i:], y_stations[i:])
        for i in range(len(y_stations))
    ])

    shear_net_ballasted = shear_aero - shear_wing_inertia - shear_ballast_inertia
    moment_net_ballasted = moment_aero - moment_wing_inertia - moment_ballast_inertia

    shear_net_dry = shear_aero - shear_wing_inertia
    moment_net_dry = moment_aero - moment_wing_inertia

    return {
        "y": y_stations,
        "chord": chords_eval,
        "alpha_trim": float(alpha_trim),
        "total_lift_target": float(total_lift_req),
        "total_lift_vlm": float(vlm_res["L"]),
        "semi_wing_lift": float(shear_aero[0]),
        "shear_aero": shear_aero,
        "moment_aero": moment_aero,
        "shear_net_ballasted": shear_net_ballasted,
        "moment_net_ballasted": moment_net_ballasted,
        "shear_net_dry": shear_net_dry,
        "moment_net_dry": moment_net_dry,
        "root_moment_aero": float(moment_aero[0]),
        "root_moment_net_ballasted": float(moment_net_ballasted[0]),
        "root_moment_net_dry": float(moment_net_dry[0]),
        "root_shear_aero": float(shear_aero[0]),
        "root_shear_net_ballasted": float(shear_net_ballasted[0]),
        "root_shear_net_dry": float(shear_net_dry[0]),
        "lift_centroid_y": float(moment_aero[0] / shear_aero[0]),
    }


def _scale_airplane_aspect_ratio(
    airplane: asb.Airplane,
    ar_target: float,
    base_ar: float = 28.446,
    base_s_ref: float = 11.39,
) -> asb.Airplane:
    """Scale the wing aspect ratio at fixed wing area while preserving planform taper and twist."""
    k = np.sqrt(ar_target / base_ar)
    wing_orig = airplane.wings[0]

    xs_le = np.array([xsec.xyz_le[0] for xsec in wing_orig.xsecs])
    ys_le = np.array([xsec.xyz_le[1] for xsec in wing_orig.xsecs])
    chords = np.array([xsec.chord for xsec in wing_orig.xsecs])
    twists = [xsec.twist for xsec in wing_orig.xsecs]
    airfoils = [xsec.airfoil for xsec in wing_orig.xsecs]

    scaled_ys = ys_le * k
    scaled_chords = chords / k

    x_c4 = xs_le + 0.25 * chords
    x_c4_scaled = x_c4[0] + (x_c4 - x_c4[0]) * k
    scaled_xs = x_c4_scaled - 0.25 * scaled_chords

    scaled_zs = 0.15 + scaled_ys * np.tan(np.radians(3.0))
    scaled_zs[-1] = scaled_zs[-2] + 0.40

    xsecs_scaled = [
        asb.WingXSec(
            xyz_le=[scaled_xs[i], scaled_ys[i], scaled_zs[i]],
            chord=scaled_chords[i],
            twist=twists[i],
            airfoil=airfoils[i],
        )
        for i in range(len(scaled_ys))
    ]

    wing_scaled = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=xsecs_scaled,
    )

    return asb.Airplane(
        name=f"Discus-2c-AR{ar_target:.1f}",
        xyz_ref=airplane.xyz_ref,
        wings=[wing_scaled, airplane.wings[1], airplane.wings[2]],
        fuselages=airplane.fuselages,
        s_ref=base_s_ref,
        c_ref=float(wing_scaled.mean_aerodynamic_chord()),
        b_ref=float(airplane.b_ref * k),
    )


def aspect_ratio_trade(
    airplane: asb.Airplane,
    aspect_ratios: np.ndarray = None,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Sweep wing aspect ratio at fixed area, returning best glide and limit structural loads."""
    if aspect_ratios is None:
        aspect_ratios = np.array([20.0, 24.0, 28.45, 32.0, 36.0])
    if speeds_kmh is None:
        speeds_kmh = np.linspace(85, 140, 12)

    spans = []
    macs = []
    max_lds = []
    best_speeds_kmh = []
    m_aeros = []
    m_net_drys = []
    m_net_bals = []

    for ar in aspect_ratios:
        ac = _scale_airplane_aspect_ratio(airplane, ar)
        pol = glide_polar(ac, mass=mass_flight, speeds_kmh=speeds_kmh)
        best_i = int(np.argmax(pol["LD"]))
        loads = wing_structural_loads(
            ac, mass=mass_structural, load_factor=load_factor
        )

        spans.append(float(ac.b_ref))
        macs.append(float(ac.c_ref))
        max_lds.append(float(pol["LD"][best_i]))
        best_speeds_kmh.append(float(pol["speeds_kmh"][best_i]))
        m_aeros.append(float(loads["root_moment_aero"] / 1000))
        m_net_drys.append(float(loads["root_moment_net_dry"] / 1000))
        m_net_bals.append(float(loads["root_moment_net_ballasted"] / 1000))

    return {
        "AR": np.array(aspect_ratios),
        "span": np.array(spans),
        "MAC": np.array(macs),
        "max_LD": np.array(max_lds),
        "best_speed_kmh": np.array(best_speeds_kmh),
        "root_moment_aero_kNm": np.array(m_aeros),
        "root_moment_net_dry_kNm": np.array(m_net_drys),
        "root_moment_net_ballasted_kNm": np.array(m_net_bals),
    }


def _modify_airplane_dihedral(
    airplane: asb.Airplane,
    dihedral_deg: float,
) -> asb.Airplane:
    """Return a copy of the airplane with modified wing dihedral while preserving root translation and winglet geometry."""
    wing_orig = airplane.wings[0]
    z_root = wing_orig.xsecs[0].xyz_le[2]
    ys = np.array([xs.xyz_le[1] for xs in wing_orig.xsecs])

    zs = z_root + ys * np.tand(dihedral_deg)
    delta_winglet = wing_orig.xsecs[-1].xyz_le[2] - wing_orig.xsecs[-2].xyz_le[2]
    zs[-1] = zs[-2] + delta_winglet

    xsecs = [
        asb.WingXSec(
            xyz_le=[wing_orig.xsecs[i].xyz_le[0], ys[i], zs[i]],
            chord=wing_orig.xsecs[i].chord,
            twist=wing_orig.xsecs[i].twist,
            airfoil=wing_orig.xsecs[i].airfoil,
        )
        for i in range(len(wing_orig.xsecs))
    ]
    w = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=xsecs,
    )
    return asb.Airplane(
        name=f"Discus-2c-dihedral-{dihedral_deg:.1f}deg",
        xyz_ref=airplane.xyz_ref,
        wings=[w, airplane.wings[1], airplane.wings[2]],
        fuselages=airplane.fuselages,
        s_ref=airplane.s_ref,
        c_ref=float(w.mean_aerodynamic_chord()),
        b_ref=airplane.b_ref,
    )


def dihedral_trade(
    airplane: asb.Airplane,
    dihedrals_deg: np.ndarray = None,
    mass: float = 417.0,
    speeds_kmh: np.ndarray = None,
    beta_eval_deg: float = 2.0,
) -> dict:
    """Sweep wing dihedral angle, returning best glide ratio and VLM lateral-directional stability derivatives."""
    if dihedrals_deg is None:
        dihedrals_deg = np.array([0.0, 1.5, 3.0, 4.5, 6.0])
    if speeds_kmh is None:
        speeds_kmh = np.linspace(85, 135, 11)

    max_lds = []
    best_speeds_kmh = []
    alphas_trim = []
    cl_betas = []
    cn_betas = []
    cy_betas = []

    dbeta_rad = np.radians(beta_eval_deg)

    for d in dihedrals_deg:
        ac = _modify_airplane_dihedral(airplane, d)
        pol = glide_polar(ac, mass=mass, speeds_kmh=speeds_kmh)
        best_i = int(np.argmax(pol["LD"]))
        max_ld = float(pol["LD"][best_i])
        v_best = float(pol["speeds_kmh"][best_i]) / 3.6
        alpha_best = float(pol["alpha"][best_i])

        op0 = asb.OperatingPoint(velocity=v_best, alpha=alpha_best, beta=0.0)
        op1 = asb.OperatingPoint(velocity=v_best, alpha=alpha_best, beta=beta_eval_deg)
        vlm0 = asb.VortexLatticeMethod(airplane=ac, op_point=op0, verbose=False).run()
        vlm1 = asb.VortexLatticeMethod(airplane=ac, op_point=op1, verbose=False).run()

        cl_b = float((vlm1["Cl"] - vlm0["Cl"]) / dbeta_rad)
        cn_b = float((vlm1["Cn"] - vlm0["Cn"]) / dbeta_rad)
        cy_b = float((vlm1["CY"] - vlm0["CY"]) / dbeta_rad)

        max_lds.append(max_ld)
        best_speeds_kmh.append(float(pol["speeds_kmh"][best_i]))
        alphas_trim.append(alpha_best)
        cl_betas.append(cl_b)
        cn_betas.append(cn_b)
        cy_betas.append(cy_b)

    return {
        "dihedrals_deg": np.array(dihedrals_deg),
        "max_LD": np.array(max_lds),
        "best_speed_kmh": np.array(best_speeds_kmh),
        "alpha_trim_deg": np.array(alphas_trim),
        "Cl_beta": np.array(cl_betas),
        "Cn_beta": np.array(cn_betas),
        "CY_beta": np.array(cy_betas),
    }


def _modify_airplane_sweep(
    airplane: asb.Airplane,
    sweep_deg: float,
) -> asb.Airplane:
    """Return a copy of the airplane with modified wing sweep sheared along x, preserving chords and span."""
    wing_orig = airplane.wings[0]
    sweep_rad = np.radians(sweep_deg)

    xsecs = [
        asb.WingXSec(
            xyz_le=[
                wing_orig.xsecs[i].xyz_le[0] + wing_orig.xsecs[i].xyz_le[1] * np.tan(sweep_rad),
                wing_orig.xsecs[i].xyz_le[1],
                wing_orig.xsecs[i].xyz_le[2],
            ],
            chord=wing_orig.xsecs[i].chord,
            twist=wing_orig.xsecs[i].twist,
            airfoil=wing_orig.xsecs[i].airfoil,
        )
        for i in range(len(wing_orig.xsecs))
    ]
    w = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=xsecs,
    )
    return asb.Airplane(
        name=f"Discus-2c-sweep-{sweep_deg:+.1f}deg",
        xyz_ref=airplane.xyz_ref,
        wings=[w, airplane.wings[1], airplane.wings[2]],
        fuselages=airplane.fuselages,
        s_ref=airplane.s_ref,
        c_ref=float(w.mean_aerodynamic_chord()),
        b_ref=airplane.b_ref,
    )


def sweep_trade(
    airplane: asb.Airplane,
    sweeps_deg: np.ndarray = None,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Sweep wing sweep angle, returning best glide ratio, root bending moments, and root torsion."""
    if sweeps_deg is None:
        sweeps_deg = np.array([-4.0, -2.0, 0.0, 2.0, 4.0])
    if speeds_kmh is None:
        speeds_kmh = np.linspace(85, 135, 11)

    max_lds = []
    best_speeds_kmh = []
    alphas_trim = []
    m_aeros = []
    m_net_drys = []
    m_net_bals = []
    m_torsions = []
    y_cps = []
    x_cps = []

    for sw in sweeps_deg:
        ac = _modify_airplane_sweep(airplane, sw)
        pol = glide_polar(ac, mass=mass_flight, speeds_kmh=speeds_kmh)
        best_i = int(np.argmax(pol["LD"]))

        loads = wing_structural_loads(
            ac, mass=mass_structural, load_factor=load_factor
        )

        op_trim = asb.OperatingPoint(velocity=55.56, alpha=loads["alpha_trim"])
        vlm_sol = asb.VortexLatticeMethod(airplane=ac, op_point=op_trim, verbose=False)
        vlm_sol.run()

        x_c = np.array(vlm_sol.vortex_centers[:, 0])
        y_c = np.array(vlm_sol.vortex_centers[:, 1])
        Fz = np.array(vlm_sol.forces_geometry[:, 2])

        x_root = ac.wings[0].xsecs[0].xyz_le[0]
        is_sb = (x_c < 4.0) & (y_c >= 0)
        torque_y_aero = np.sum((x_c[is_sb] - x_root) * Fz[is_sb])
        lift_total_sb = np.sum(Fz[is_sb])

        max_lds.append(float(pol["LD"][best_i]))
        best_speeds_kmh.append(float(pol["speeds_kmh"][best_i]))
        alphas_trim.append(float(pol["alpha"][best_i]))
        m_aeros.append(float(loads["root_moment_aero"] / 1000))
        m_net_drys.append(float(loads["root_moment_net_dry"] / 1000))
        m_net_bals.append(float(loads["root_moment_net_ballasted"] / 1000))
        m_torsions.append(float(torque_y_aero / 1000))
        y_cps.append(float(loads["lift_centroid_y"]))
        x_cps.append(float(np.sum(x_c[is_sb] * Fz[is_sb]) / lift_total_sb))

    return {
        "sweeps_deg": np.array(sweeps_deg),
        "max_LD": np.array(max_lds),
        "best_speed_kmh": np.array(best_speeds_kmh),
        "alpha_trim_deg": np.array(alphas_trim),
        "root_moment_aero_kNm": np.array(m_aeros),
        "root_moment_net_dry_kNm": np.array(m_net_drys),
        "root_moment_net_ballasted_kNm": np.array(m_net_bals),
        "root_torsion_aero_kNm": np.array(m_torsions),
        "lift_centroid_y_m": np.array(y_cps),
        "lift_centroid_x_m": np.array(x_cps),
    }


def _scale_airplane_ar_dihedral(
    airplane: asb.Airplane,
    ar_target: float,
    dihedral_deg: float,
    base_ar: float = 28.446,
    base_s_ref: float = 11.39,
) -> asb.Airplane:
    """Scale wing aspect ratio and set dihedral while preserving taper and winglet geometry."""
    k = np.sqrt(ar_target / base_ar)
    wing_orig = airplane.wings[0]

    xs_le = np.array([xsec.xyz_le[0] for xsec in wing_orig.xsecs])
    ys_le = np.array([xsec.xyz_le[1] for xsec in wing_orig.xsecs])
    chords = np.array([xsec.chord for xsec in wing_orig.xsecs])
    twists = [xsec.twist for xsec in wing_orig.xsecs]
    airfoils = [xsec.airfoil for xsec in wing_orig.xsecs]

    scaled_ys = ys_le * k
    scaled_chords = chords / k

    x_c4 = xs_le + 0.25 * chords
    x_c4_scaled = x_c4[0] + (x_c4 - x_c4[0]) * k
    scaled_xs = x_c4_scaled - 0.25 * scaled_chords

    z_root = wing_orig.xsecs[0].xyz_le[2]
    scaled_zs = z_root + scaled_ys * np.tand(dihedral_deg)
    delta_winglet = wing_orig.xsecs[-1].xyz_le[2] - wing_orig.xsecs[-2].xyz_le[2]
    scaled_zs[-1] = scaled_zs[-2] + delta_winglet

    xsecs_scaled = [
        asb.WingXSec(
            xyz_le=[scaled_xs[i], scaled_ys[i], scaled_zs[i]],
            chord=scaled_chords[i],
            twist=twists[i],
            airfoil=airfoils[i],
        )
        for i in range(len(scaled_ys))
    ]

    wing_scaled = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=xsecs_scaled,
    )

    return asb.Airplane(
        name=f"Discus-2c-AR{ar_target:.2f}-d{dihedral_deg:.1f}deg",
        xyz_ref=airplane.xyz_ref,
        wings=[wing_scaled, airplane.wings[1], airplane.wings[2]],
        fuselages=airplane.fuselages,
        s_ref=base_s_ref,
        c_ref=float(wing_scaled.mean_aerodynamic_chord()),
        b_ref=float(airplane.b_ref * k),
    )


def ar_dihedral_trade(
    airplane: asb.Airplane,
    configurations: list = None,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate glide performance and limit root bending moments for AR-dihedral combinations."""
    if configurations is None:
        configurations = [
            (28.446, 3.0),
            (28.446, 6.0),
            (28.800, 3.0),
            (28.800, 5.0),
            (29.000, 3.0),
            (29.000, 6.0),
        ]
    if speeds_kmh is None:
        speeds_kmh = np.linspace(95, 125, 7)

    ars = []
    dihedrals = []
    spans = []
    max_lds = []
    best_speeds_kmh = []
    m_root_nets = []
    m_root_aeros = []
    budget_margins = []

    base_loads = wing_structural_loads(
        airplane, mass=mass_structural, load_factor=load_factor
    )
    m_budget = float(base_loads["root_moment_net_ballasted"] / 1000)

    for ar, d in configurations:
        ac = _scale_airplane_ar_dihedral(airplane, ar, d)
        pol = glide_polar(ac, mass=mass_flight, speeds_kmh=speeds_kmh)
        best_i = int(np.argmax(pol["LD"]))
        loads = wing_structural_loads(
            ac, mass=mass_structural, load_factor=load_factor
        )

        m_net = float(loads["root_moment_net_ballasted"] / 1000)
        m_aero = float(loads["root_moment_aero"] / 1000)
        ld_val = float(pol["LD"][best_i])

        ars.append(ar)
        dihedrals.append(d)
        spans.append(float(ac.b_ref))
        max_lds.append(ld_val)
        best_speeds_kmh.append(float(pol["speeds_kmh"][best_i]))
        m_root_nets.append(m_net)
        m_root_aeros.append(m_aero)
        budget_margins.append(m_budget - m_net)

    return {
        "AR": np.array(ars),
        "dihedral_deg": np.array(dihedrals),
        "span_m": np.array(spans),
        "max_LD": np.array(max_lds),
        "best_speed_kmh": np.array(best_speeds_kmh),
        "m_root_net_kNm": np.array(m_root_nets),
        "m_root_aero_kNm": np.array(m_root_aeros),
        "budget_margin_kNm": np.array(budget_margins),
        "m_budget_kNm": m_budget,
    }


def wing_torsion_box_analysis(
    airplane: asb.Airplane,
    sweeps_deg: np.ndarray = None,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    velocity: float = 55.56,
    t_skin: float = 0.0015,
    G_skin: float = 12.0e9,
    spar_chord_frac: float = 0.35,
) -> dict:
    """Analyze wing root torsion from sweep and compare open spar vs closed D-tube structural response."""
    from scipy.interpolate import interp1d

    if sweeps_deg is None:
        sweeps_deg = np.array([0.0, -2.0, -4.0])

    root_chord = float(airplane.wings[0].xsecs[0].chord)
    coords = airplane.wings[0].xsecs[0].airfoil.coordinates
    x_af = np.linspace(0, spar_chord_frac, 100)
    upper = coords[coords[:, 1] >= 0]
    lower = coords[coords[:, 1] <= 0]
    upper = upper[np.argsort(upper[:, 0])]
    lower = lower[np.argsort(lower[:, 0])]
    yu = interp1d(upper[:, 0], upper[:, 1], fill_value="extrapolate")(x_af)
    yl = interp1d(lower[:, 0], lower[:, 1], fill_value="extrapolate")(x_af)
    A_m = float(np.trapezoid(yu - yl, x_af) * (root_chord**2))
    perim_skin = float(
        (
            np.sum(np.sqrt(np.diff(x_af) ** 2 + np.diff(yu) ** 2))
            + np.sum(np.sqrt(np.diff(x_af) ** 2 + np.diff(yl) ** 2))
        )
        * root_chord
    )
    h_web = float((yu[-1] - yl[-1]) * root_chord)

    b_cap = 0.060
    t_cap = 0.0095
    t_web = 0.002
    J_spar = float((1 / 3) * (2 * b_cap * t_cap**3 + h_web * t_web**3))
    GJ_spar = float(
        5.0e9 * (1 / 3) * (2 * b_cap * t_cap**3) + 4.0e9 * (1 / 3) * (h_web * t_web**3)
    )

    oint_ds_t = perim_skin / t_skin + h_web / t_web
    J_dtube = float(4 * A_m**2 / oint_ds_t)
    GJ_dtube = float(G_skin * J_dtube)

    I_cap_lat = float((t_cap * b_cap**3) / 12.0)
    I_w = float(I_cap_lat * (h_web**2) / 2.0)
    lam = float(np.sqrt(GJ_spar / (135e9 * I_w)))
    char_len = float(1.0 / lam)

    x_spar_root = float(
        airplane.wings[0].xsecs[0].xyz_le[0] + spar_chord_frac * root_chord
    )

    t_roots = []
    xcps = []
    ycps = []
    tau_svs = []
    sigma_warps = []
    q_boxes = []
    tau_boxes = []

    for sw in sweeps_deg:
        ac = _modify_airplane_sweep(airplane, sw)
        loads = wing_structural_loads(
            ac, mass=mass_structural, load_factor=load_factor, velocity=velocity
        )
        op_trim = asb.OperatingPoint(velocity=velocity, alpha=loads["alpha_trim"])
        vlm = asb.VortexLatticeMethod(airplane=ac, op_point=op_trim, verbose=False)
        vlm.run()

        x_c = np.array(vlm.vortex_centers[:, 0])
        y_c = np.array(vlm.vortex_centers[:, 1])
        Fz = np.array(vlm.forces_geometry[:, 2])
        is_sb = (x_c < 4.0) & (y_c >= 0)

        L_sb = float(np.sum(Fz[is_sb]))
        xcp = float(np.sum(x_c[is_sb] * Fz[is_sb]) / L_sb)
        ycp = float(np.sum(y_c[is_sb] * Fz[is_sb]) / L_sb)
        t_spar = float(np.sum((x_c[is_sb] - x_spar_root) * Fz[is_sb]))

        tau_sv = abs(t_spar) * t_cap / J_spar
        m_flange = (abs(t_spar) / h_web) * char_len
        sigma_warp = m_flange * (b_cap / 2.0) / I_cap_lat

        q_box = abs(t_spar) / (2.0 * A_m)
        tau_box = q_box / t_skin

        t_roots.append(t_spar)
        xcps.append(xcp)
        ycps.append(ycp)
        tau_svs.append(tau_sv)
        sigma_warps.append(sigma_warp)
        q_boxes.append(q_box)
        tau_boxes.append(tau_box)

    return {
        "sweeps_deg": np.array(sweeps_deg),
        "root_torque_kNm": np.array(t_roots) / 1000.0,
        "x_cp_m": np.array(xcps),
        "y_cp_m": np.array(ycps),
        "tau_sv_spar_MPa": np.array(tau_svs) / 1e6,
        "sigma_warp_spar_MPa": np.array(sigma_warps) / 1e6,
        "q_box_kNm": np.array(q_boxes) / 1000.0,
        "tau_box_MPa": np.array(tau_boxes) / 1e6,
        "GJ_spar": GJ_spar,
        "GJ_dtube": GJ_dtube,
        "stiffness_ratio": GJ_dtube / GJ_spar,
        "A_m_m2": A_m,
    }


def final_design_synthesis(
    airplane: asb.Airplane,
    ar_target: float = 29.0,
    dihedral_deg: float = 6.0,
    sweep_deg: float = 4.0,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
    t_skin: float = 0.0015,
    tau_allowable_MPa: float = 60.0,
) -> dict:
    """Evaluate synthesized final design combining AR, dihedral, sweep, and D-tube torsion box against baseline."""
    if speeds_kmh is None:
        speeds_kmh = np.linspace(95, 125, 7)

    ac_ar_d = _scale_airplane_ar_dihedral(airplane, ar_target=ar_target, dihedral_deg=dihedral_deg)
    ac_final = _modify_airplane_sweep(ac_ar_d, sweep_deg=sweep_deg)
    ac_final.name = f"Discus-2c-Final-AR{ar_target:.1f}-d{dihedral_deg:.1f}-sw{sweep_deg:+.1f}"

    # Glide polars
    pol_base = glide_polar(airplane, mass=mass_flight, speeds_kmh=speeds_kmh)
    pol_final = glide_polar(ac_final, mass=mass_flight, speeds_kmh=speeds_kmh)

    ld_base = float(np.max(pol_base["LD"]))
    ld_final = float(np.max(pol_final["LD"]))
    v_base = float(pol_base["speeds_kmh"][np.argmax(pol_base["LD"])])
    v_final = float(pol_final["speeds_kmh"][np.argmax(pol_final["LD"])])

    # Structural bending loads under +5.3g limit manoeuvre
    loads_base = wing_structural_loads(airplane, mass=mass_structural, load_factor=load_factor)
    loads_final = wing_structural_loads(ac_final, mass=mass_structural, load_factor=load_factor)

    m_net_base = float(loads_base["root_moment_net_ballasted"] / 1000.0)
    m_net_final = float(loads_final["root_moment_net_ballasted"] / 1000.0)
    m_budget = m_net_base
    m_margin = m_budget - m_net_final

    # Wing root torsion and D-tube sizing
    t_res_base = wing_torsion_box_analysis(airplane, sweeps_deg=[0.0], t_skin=t_skin)
    t_res_final = wing_torsion_box_analysis(ac_final, sweeps_deg=[0.0], t_skin=t_skin)

    t_root_base = float(t_res_base["root_torque_kNm"][0])
    t_root_final = float(t_res_final["root_torque_kNm"][0])
    tau_box_base = float(t_res_base["tau_box_MPa"][0])
    tau_box_final = float(t_res_final["tau_box_MPa"][0])
    tau_margin = tau_allowable_MPa - tau_box_final

    return {
        "airplane_final": ac_final,
        "ld_base": ld_base,
        "ld_final": ld_final,
        "delta_ld": ld_final - ld_base,
        "v_base_kmh": v_base,
        "v_final_kmh": v_final,
        "m_budget_kNm": m_budget,
        "m_root_base_kNm": m_net_base,
        "m_root_final_kNm": m_net_final,
        "bending_margin_kNm": m_margin,
        "t_root_base_kNm": t_root_base,
        "t_root_final_kNm": t_root_final,
        "tau_box_base_MPa": tau_box_base,
        "tau_box_final_MPa": tau_box_final,
        "tau_margin_MPa": tau_margin,
        "tau_allowable_MPa": tau_allowable_MPa,
        "stiffness_ratio": float(t_res_final["stiffness_ratio"]),
        "pol_base": pol_base,
        "pol_final": pol_final,
        "loads_base": loads_base,
        "loads_final": loads_final,
    }


def box_wing_reconfiguration(
    airplane: asb.Airplane,
    hb_ratio: float = 0.15,
    area_split: float = 0.5,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate box-wing reconfiguration against baseline in VLM aerodynamics and root bending moments."""
    if speeds_kmh is None:
        speeds_kmh = np.array([85.0, 95.0, 105.0, 115.0, 125.0])

    main_w = airplane.wings[0]
    ys = np.array([xs.xyz_le[1] for xs in main_w.xsecs])
    chords = np.array([xs.chord for xs in main_w.xsecs])
    xs_le = np.array([xs.xyz_le[0] for xs in main_w.xsecs])
    twists = [xs.twist for xs in main_w.xsecs]
    airfoils = [xs.airfoil for xs in main_w.xsecs]

    b_span = float(airplane.b_ref)
    h_box = hb_ratio * b_span

    c_fwd = chords * area_split
    c_aft = chords * (1.0 - area_split)

    rel_xs = xs_le - xs_le[0]

    xsecs_fwd = [
        asb.WingXSec(xyz_le=[rel_xs[i], ys[i], 0.0], chord=c_fwd[i], twist=twists[i], airfoil=airfoils[i])
        for i in range(len(ys))
    ]
    wing_fwd = asb.Wing(name="Forward Wing", symmetric=True, xsecs=xsecs_fwd).translate([2.30, 0.0, 0.0])

    xsecs_aft = [
        asb.WingXSec(xyz_le=[rel_xs[i], ys[i], 0.0], chord=c_aft[i], twist=twists[i], airfoil=airfoils[i])
        for i in range(len(ys))
    ]
    wing_aft = asb.Wing(name="Aft Wing", symmetric=True, xsecs=xsecs_aft).translate([6.00, 0.0, h_box])

    af_plate = asb.Airfoil("hq010")
    endplate = asb.Wing(
        name="Tip Endplate",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[2.30 + rel_xs[-1], ys[-1], 0.0], chord=c_fwd[-1], airfoil=af_plate),
            asb.WingXSec(xyz_le=[6.00 + rel_xs[-1], ys[-1], h_box], chord=c_aft[-1], airfoil=af_plate),
        ],
    )

    box_airplane = asb.Airplane(
        name="Discus-2c-BoxWing",
        xyz_ref=airplane.xyz_ref,
        wings=[wing_fwd, wing_aft, endplate, airplane.wings[2]],
        fuselages=airplane.fuselages,
        s_ref=airplane.s_ref,
        c_ref=float(main_w.mean_aerodynamic_chord()) * area_split,
        b_ref=b_span,
    )

    # 1. Structural loads under +5.3g limit manoeuvre at MTOM
    v_m = 55.56
    target_lift = mass_structural * 9.81 * load_factor

    # Solve baseline
    op_b1 = asb.OperatingPoint(velocity=v_m, alpha=4.0)
    vb1 = asb.VortexLatticeMethod(airplane=airplane, op_point=op_b1, verbose=False).run()
    op_b2 = asb.OperatingPoint(velocity=v_m, alpha=8.0)
    vb2 = asb.VortexLatticeMethod(airplane=airplane, op_point=op_b2, verbose=False).run()
    dL_da_b = (vb2["L"] - vb1["L"]) / 4.0
    a_trim_b = 4.0 + (target_lift - vb1["L"]) / dL_da_b
    sol_b = asb.VortexLatticeMethod(airplane=airplane, op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_b), verbose=False)
    sol_b.run()

    # Solve box-wing
    op_x1 = asb.OperatingPoint(velocity=v_m, alpha=4.0)
    vx1 = asb.VortexLatticeMethod(airplane=box_airplane, op_point=op_x1, verbose=False).run()
    op_x2 = asb.OperatingPoint(velocity=v_m, alpha=8.0)
    vx2 = asb.VortexLatticeMethod(airplane=box_airplane, op_point=op_x2, verbose=False).run()
    dL_da_x = (vx2["L"] - vx1["L"]) / 4.0
    a_trim_x = 4.0 + (target_lift - vx1["L"]) / dL_da_x
    sol_x = asb.VortexLatticeMethod(airplane=box_airplane, op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_x), verbose=False)
    sol_x.run()

    # Root moments
    yb = sol_b.vortex_centers[:, 1]
    xb = sol_b.vortex_centers[:, 0]
    fzb = sol_b.forces_geometry[:, 2]
    sb_b = (yb >= 0) & (xb < 4.0)
    m_root_base = float(np.sum(yb[sb_b] * fzb[sb_b])) / 1000.0

    yx = sol_x.vortex_centers[:, 1]
    xx = sol_x.vortex_centers[:, 0]
    zx = sol_x.vortex_centers[:, 2]
    fzx = sol_x.forces_geometry[:, 2]

    sb_fwd = (yx >= 0) & (xx < 4.0) & (abs(zx) < 1.0)
    sb_aft = (yx >= 0) & (xx >= 4.0) & (zx > 1.5)
    m_root_fwd = float(np.sum(yx[sb_fwd] * fzx[sb_fwd])) / 1000.0
    m_root_aft = float(np.sum(yx[sb_aft] * fzx[sb_aft])) / 1000.0
    m_root_max = max(m_root_fwd, m_root_aft)
    bending_relief_pct = (1.0 - m_root_max / m_root_base) * 100.0

    # 2. VLM induced drag coupling
    v_eval = 27.78
    res_b2 = asb.VortexLatticeMethod(airplane=airplane, op_point=asb.OperatingPoint(velocity=v_eval, alpha=2.0), verbose=False).run()
    res_b6 = asb.VortexLatticeMethod(airplane=airplane, op_point=asb.OperatingPoint(velocity=v_eval, alpha=6.0), verbose=False).run()
    k_base = float((res_b6["CD"] - res_b2["CD"]) / (res_b6["CL"]**2 - res_b2["CL"]**2))

    res_x2 = asb.VortexLatticeMethod(airplane=box_airplane, op_point=asb.OperatingPoint(velocity=v_eval, alpha=2.0), verbose=False).run()
    res_x6 = asb.VortexLatticeMethod(airplane=box_airplane, op_point=asb.OperatingPoint(velocity=v_eval, alpha=6.0), verbose=False).run()
    k_box = float((res_x6["CD"] - res_x2["CD"]) / (res_x6["CL"]**2 - res_x2["CL"]**2))

    ar_val = b_span**2 / airplane.s_ref
    e_base = (1.0 / (np.pi * ar_val)) / k_base
    e_box = (1.0 / (np.pi * ar_val)) / k_box
    induced_ratio = k_box / k_base

    # 3. Glide polar synthesis
    pol_b = glide_polar(airplane, mass=mass_flight, speeds_kmh=speeds_kmh)
    cdi_box = pol_b["CD_induced"] * induced_ratio
    cdp_box = pol_b["CD_profile"] + 0.0010
    cd_box = cdi_box + cdp_box
    ld_box = pol_b["CL"] / cd_box

    ld_base_max = float(np.max(pol_b["LD"]))
    ld_box_max = float(np.max(ld_box))
    v_base_max = float(speeds_kmh[np.argmax(pol_b["LD"])])
    v_box_max = float(speeds_kmh[np.argmax(ld_box)])

    return {
        "box_airplane": box_airplane,
        "m_root_base_kNm": m_root_base,
        "m_root_fwd_kNm": m_root_fwd,
        "m_root_aft_kNm": m_root_aft,
        "m_root_max_kNm": m_root_max,
        "bending_relief_pct": bending_relief_pct,
        "k_base": k_base,
        "k_box": k_box,
        "e_base": e_base,
        "e_box": e_box,
        "induced_drag_reduction_pct": (1.0 - induced_ratio) * 100.0,
        "ld_base_max": ld_base_max,
        "ld_box_max": ld_box_max,
        "delta_ld": ld_box_max - ld_base_max,
        "v_base_max": v_base_max,
        "v_box_max": v_box_max,
        "speeds_kmh": speeds_kmh,
        "ld_base_arr": pol_b["LD"],
        "ld_box_arr": ld_box,
    }


def canard_configuration_analysis(
    airplane: asb.Airplane,
    canard_x_le: float = 0.60,
    canard_z_le: float = 0.10,
    static_margin: float = 0.10,
    mass_flight: float = 417.0,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate canard configuration against baseline Discus-2c in trim, drag, and glide ratio."""
    if speeds_kmh is None:
        speeds_kmh = np.array([75.0, 85.0, 95.0, 105.0, 120.0, 140.0, 160.0, 180.0, 200.0])

    speeds_mps = np.array(speeds_kmh) / 3.6
    weight = mass_flight * 9.81
    s_ref = airplane.s_ref
    b_ref = airplane.b_ref
    main_w = airplane.wings[0]
    htail_w = airplane.wings[1]
    vtail_w = airplane.wings[2]
    fuse_b = airplane.fuselages[0]
    c_mac = float(main_w.mean_aerodynamic_chord())

    # Build canard surface using htail cross-section geometry
    xsecs_canard = [
        asb.WingXSec(
            xyz_le=[canard_x_le + (xs.xyz_le[0] - htail_w.xsecs[0].xyz_le[0]), xs.xyz_le[1], canard_z_le],
            chord=xs.chord,
            twist=0.0,
            airfoil=xs.airfoil,
        )
        for xs in htail_w.xsecs
    ]
    canard_w = asb.Wing(name="Canard", symmetric=True, xsecs=xsecs_canard)

    # Reference condition for stability derivatives
    v_ref = 25.0
    op0 = asb.OperatingPoint(velocity=v_ref, alpha=0.0)
    opa = asb.OperatingPoint(velocity=v_ref, alpha=4.0)

    # 1. Baseline stability and neutral point
    x_cg_b = float(airplane.xyz_ref[0])
    vb0 = asb.VortexLatticeMethod(airplane=airplane, op_point=op0, verbose=False).run()
    vba = asb.VortexLatticeMethod(airplane=airplane, op_point=opa, verbose=False).run()
    CLa_b = (vba["CL"] - vb0["CL"]) / 4.0
    Cma_b = (vba["Cm"] - vb0["Cm"]) / 4.0
    x_np_b = x_cg_b - (Cma_b / CLa_b) * c_mac
    sm_b = (x_np_b - x_cg_b) / c_mac

    # Baseline control derivative (twist = -3 deg on tail, delta = -2 deg from base -1)
    htail_d = asb.Wing(
        name="Horizontal Stabilizer Deflected",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=xs.xyz_le, chord=xs.chord, twist=xs.twist - 2.0, airfoil=xs.airfoil)
            for xs in htail_w.xsecs
        ],
    )
    ap_bd = asb.Airplane(
        xyz_ref=[x_cg_b, 0, airplane.xyz_ref[2]],
        wings=[main_w, htail_d, vtail_w],
        fuselages=[fuse_b],
        s_ref=s_ref,
        c_ref=c_mac,
        b_ref=b_ref,
    )
    vbd = asb.VortexLatticeMethod(airplane=ap_bd, op_point=op0, verbose=False).run()
    CLd_b = (vbd["CL"] - vb0["CL"]) / (-2.0)
    Cmd_b = (vbd["Cm"] - vb0["Cm"]) / (-2.0)

    # 2. Canard stability and neutral point
    ap_c_test = asb.Airplane(
        xyz_ref=[x_cg_b, 0, airplane.xyz_ref[2]],
        wings=[main_w, canard_w, vtail_w],
        fuselages=[fuse_b],
        s_ref=s_ref,
        c_ref=c_mac,
        b_ref=b_ref,
    )
    vc0_test = asb.VortexLatticeMethod(airplane=ap_c_test, op_point=op0, verbose=False).run()
    vca_test = asb.VortexLatticeMethod(airplane=ap_c_test, op_point=opa, verbose=False).run()
    CLa_c = (vca_test["CL"] - vc0_test["CL"]) / 4.0
    Cma_c = (vca_test["Cm"] - vc0_test["Cm"]) / 4.0
    x_np_c = x_cg_b - (Cma_c / CLa_c) * c_mac

    # Canard CG positioned for specified static margin
    x_cg_c = x_np_c - static_margin * c_mac
    canard_airplane = asb.Airplane(
        name="Discus-2c-Canard",
        xyz_ref=[x_cg_c, 0.0, airplane.xyz_ref[2]],
        wings=[main_w, canard_w, vtail_w],
        fuselages=[fuse_b],
        s_ref=s_ref,
        c_ref=c_mac,
        b_ref=b_ref,
    )

    # Canard stability derivatives about its balanced CG
    vc0 = asb.VortexLatticeMethod(airplane=canard_airplane, op_point=op0, verbose=False).run()
    vca = asb.VortexLatticeMethod(airplane=canard_airplane, op_point=opa, verbose=False).run()
    CLa_c_bal = (vca["CL"] - vc0["CL"]) / 4.0
    Cma_c_bal = (vca["Cm"] - vc0["Cm"]) / 4.0

    # Canard control derivative (twist = +4 deg)
    canard_d = asb.Wing(
        name="Canard Deflected",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=xs.xyz_le, chord=xs.chord, twist=xs.twist + 4.0, airfoil=xs.airfoil)
            for xs in canard_w.xsecs
        ],
    )
    ap_cd = asb.Airplane(
        xyz_ref=[x_cg_c, 0, airplane.xyz_ref[2]],
        wings=[main_w, canard_d, vtail_w],
        fuselages=[fuse_b],
        s_ref=s_ref,
        c_ref=c_mac,
        b_ref=b_ref,
    )
    vcd = asb.VortexLatticeMethod(airplane=ap_cd, op_point=op0, verbose=False).run()
    CLd_c = (vcd["CL"] - vc0["CL"]) / 4.0
    Cmd_c = (vcd["Cm"] - vc0["Cm"]) / 4.0

    # 3. Trim linear systems
    A_b = np.array([[CLa_b, CLd_b], [Cma_b, Cmd_b]])
    A_c = np.array([[CLa_c_bal, CLd_c], [Cma_c_bal, Cmd_c]])

    CL_reqs = 2 * weight / (1.225 * s_ref * speeds_mps**2)
    _lin_solve = np.linalg.solve

    trim_alpha_b = []
    trim_delta_b = []
    trim_alpha_c = []
    trim_delta_c = []
    cd_b_arr = []
    cd_c_arr = []
    cdi_b_arr = []
    cdi_c_arr = []
    cdp_b_arr = []
    cdp_c_arr = []
    ld_b_arr = []
    ld_c_arr = []

    for i, v in enumerate(speeds_mps):
        cl_req = CL_reqs[i]

        # Solve baseline trim
        rhs_b = np.array([cl_req - vb0["CL"], -vb0["Cm"]])
        ab, db = _lin_solve(A_b, rhs_b)
        trim_alpha_b.append(float(ab))
        trim_delta_b.append(float(db))

        # Solve canard trim
        rhs_c = np.array([cl_req - vc0["CL"], -vc0["Cm"]])
        ac, dc = _lin_solve(A_c, rhs_c)
        trim_alpha_c.append(float(ac))
        trim_delta_c.append(float(dc))

        # Baseline AeroBuildup evaluation at trimmed state
        ht_twist = htail_w.xsecs[0].twist + db
        ap_b_cur = asb.Airplane(
            xyz_ref=[x_cg_b, 0, airplane.xyz_ref[2]],
            wings=[
                main_w,
                asb.Wing(
                    name="H",
                    symmetric=True,
                    xsecs=[
                        asb.WingXSec(xyz_le=xs.xyz_le, chord=xs.chord, twist=ht_twist, airfoil=xs.airfoil)
                        for xs in htail_w.xsecs
                    ],
                ),
                vtail_w,
            ],
            fuselages=[fuse_b],
            s_ref=s_ref,
            c_ref=c_mac,
            b_ref=b_ref,
        )
        res_b = asb.AeroBuildup(airplane=ap_b_cur, op_point=asb.OperatingPoint(velocity=v, alpha=ab)).run()
        cd_b = float(res_b["CD"][0])
        cdi_b = float(res_b["D_induced"][0] / (0.5 * 1.225 * v**2 * s_ref))
        cl_b = float(res_b["CL"][0])

        # Canard AeroBuildup evaluation at trimmed state
        ap_c_cur = asb.Airplane(
            xyz_ref=[x_cg_c, 0, airplane.xyz_ref[2]],
            wings=[
                main_w,
                asb.Wing(
                    name="C",
                    symmetric=True,
                    xsecs=[
                        asb.WingXSec(xyz_le=xs.xyz_le, chord=xs.chord, twist=dc, airfoil=xs.airfoil)
                        for xs in canard_w.xsecs
                    ],
                ),
                vtail_w,
            ],
            fuselages=[fuse_b],
            s_ref=s_ref,
            c_ref=c_mac,
            b_ref=b_ref,
        )
        res_c = asb.AeroBuildup(airplane=ap_c_cur, op_point=asb.OperatingPoint(velocity=v, alpha=ac)).run()
        cd_c = float(res_c["CD"][0])
        cdi_c = float(res_c["D_induced"][0] / (0.5 * 1.225 * v**2 * s_ref))
        cl_c = float(res_c["CL"][0])

        cd_b_arr.append(cd_b)
        cd_c_arr.append(cd_c)
        cdi_b_arr.append(cdi_b)
        cdi_c_arr.append(cdi_c)
        cdp_b_arr.append(cd_b - cdi_b)
        cdp_c_arr.append(cd_c - cdi_c)
        ld_b_arr.append(cl_b / cd_b)
        ld_c_arr.append(cl_c / cd_c)

    ld_b_arr = np.array(ld_b_arr)
    ld_c_arr = np.array(ld_c_arr)
    cd_b_arr = np.array(cd_b_arr)
    cd_c_arr = np.array(cd_c_arr)
    cdi_b_arr = np.array(cdi_b_arr)
    cdi_c_arr = np.array(cdi_c_arr)

    idx_b_max = int(np.argmax(ld_b_arr))
    idx_c_max = int(np.argmax(ld_c_arr))

    return {
        "canard_airplane": canard_airplane,
        "x_np_base": x_np_b,
        "x_np_canard": x_np_c,
        "delta_x_np": x_np_c - x_np_b,
        "x_cg_base": x_cg_b,
        "x_cg_canard": x_cg_c,
        "delta_x_cg": x_cg_c - x_cg_b,
        "sm_base": sm_b,
        "sm_canard": static_margin,
        "speeds_kmh": speeds_kmh,
        "CL": CL_reqs,
        "alpha_base": np.array(trim_alpha_b),
        "delta_base": np.array(trim_delta_b),
        "alpha_canard": np.array(trim_alpha_c),
        "delta_canard": np.array(trim_delta_c),
        "alpha_canard_local": np.array(trim_alpha_c) + np.array(trim_delta_c),
        "CD_base": cd_b_arr,
        "CD_canard": cd_c_arr,
        "delta_CD": cd_c_arr - cd_b_arr,
        "CDi_base": cdi_b_arr,
        "CDi_canard": cdi_c_arr,
        "LD_base": ld_b_arr,
        "LD_canard": ld_c_arr,
        "ld_base_max": float(ld_b_arr[idx_b_max]),
        "ld_canard_max": float(ld_c_arr[idx_c_max]),
        "delta_ld_max": float(ld_c_arr[idx_c_max] - ld_b_arr[idx_b_max]),
        "v_base_max": float(speeds_kmh[idx_b_max]),
        "v_canard_max": float(speeds_kmh[idx_c_max]),
        "trim_drag_penalty_at_best_glide_counts": float((cd_c_arr[idx_b_max] - cd_b_arr[idx_b_max]) * 1e4),
    }









