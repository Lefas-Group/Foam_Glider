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

