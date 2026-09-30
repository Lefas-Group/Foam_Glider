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





