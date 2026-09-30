import aerosandbox as asb
import aerosandbox.numpy as np


def _build_baseline_airplane() -> asb.Airplane:
    """Reconstruct calibrated baseline 18m Discus-2c monoplane."""
    af_root = asb.Airfoil("hq17")
    af_mid = asb.Airfoil("hq2512")
    af_tip = asb.Airfoil("hq2195")
    af_tail = asb.Airfoil("hq010")

    wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
    wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589])
    wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
    wing_dihedral_deg = 3.0
    wing_zs_le = wing_ys * np.tand(wing_dihedral_deg)
    wing_zs_le[-1] = wing_zs_le[-2] + 0.40

    wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
    wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]

    xsecs_wing = [
        asb.WingXSec(
            xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
            chord=wing_chords[i],
            twist=wing_twists[i],
            airfoil=wing_airfoils[i],
        )
        for i in range(len(wing_ys))
    ]

    main_wing = asb.Wing(
        name="Main Wing",
        symmetric=True,
        xsecs=xsecs_wing,
    ).translate([2.30, 0.0, 0.15])

    xsecs_htail = [
        asb.WingXSec(xyz_le=[6.35, 0.0, 1.25], chord=0.48, twist=-1.0, airfoil=af_tail),
        asb.WingXSec(xyz_le=[6.42, 1.2, 1.25], chord=0.32, twist=-1.0, airfoil=af_tail),
    ]
    htail = asb.Wing(name="Horizontal Stabilizer", symmetric=True, xsecs=xsecs_htail)

    xsecs_vtail = [
        asb.WingXSec(xyz_le=[5.85, 0.0, -0.05], chord=0.85, airfoil=af_tail),
        asb.WingXSec(xyz_le=[6.38, 0.0, 1.25], chord=0.45, airfoil=af_tail),
    ]
    vtail = asb.Wing(name="Vertical Stabilizer", symmetric=False, xsecs=xsecs_vtail)

    fuse_xsecs = [
        asb.FuselageXSec(xyz_c=[0.0, 0.0, 0.0], width=0.02, height=0.02),
        asb.FuselageXSec(xyz_c=[0.5, 0.0, 0.02], width=0.45, height=0.55),
        asb.FuselageXSec(xyz_c=[1.1, 0.0, 0.05], width=0.62, height=0.78),
        asb.FuselageXSec(xyz_c=[1.8, 0.0, 0.04], width=0.60, height=0.75),
        asb.FuselageXSec(xyz_c=[2.4, 0.0, 0.00], width=0.50, height=0.65),
        asb.FuselageXSec(xyz_c=[3.2, 0.0, -0.02], width=0.36, height=0.48),
        asb.FuselageXSec(xyz_c=[4.5, 0.0, -0.04], width=0.20, height=0.28),
        asb.FuselageXSec(xyz_c=[5.8, 0.0, -0.05], width=0.14, height=0.22),
        asb.FuselageXSec(xyz_c=[6.81, 0.0, -0.05], width=0.04, height=0.15),
    ]
    fuse = asb.Fuselage(name="Fuselage", xsecs=fuse_xsecs)

    empty_mass_props = asb.MassProperties(
        mass=337.0, x_cg=2.832, y_cg=0.0, z_cg=0.097, Ixx=1760.5, Iyy=189.7, Izz=1934.2
    )
    pilot_props = asb.MassProperties(mass=80.0, x_cg=1.75, y_cg=0.0, z_cg=0.0)
    flight_props = empty_mass_props + pilot_props

    return asb.Airplane(
        name="Discus-2c-Baseline",
        xyz_ref=[flight_props.x_cg, flight_props.y_cg, flight_props.z_cg],
        wings=[main_wing, htail, vtail],
        fuselages=[fuse],
        s_ref=11.39,
        c_ref=float(main_wing.mean_aerodynamic_chord()),
        b_ref=18.0,
    )


def _glide_polar(
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
        cdi_t = float(
            np.interp(alpha_t, alphas_grid, aero["D_induced"] / (0.5 * rho * V**2 * s_ref))
        )
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


def box_wing_comparison(
    airplane: asb.Airplane,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate box-wing configuration against calibrated baseline Discus-2c monoplane."""
    if speeds_kmh is None:
        speeds_kmh = np.array([85.0, 95.0, 105.0, 115.0, 125.0])

    ap_base = _build_baseline_airplane()
    ap_box = airplane

    # 1. Structural loads under +5.3g limit manoeuvre at MTOM
    v_m = 55.56
    target_lift = mass_structural * 9.81 * load_factor

    # Solve baseline
    op_b1 = asb.OperatingPoint(velocity=v_m, alpha=4.0)
    vb1 = asb.VortexLatticeMethod(airplane=ap_base, op_point=op_b1, verbose=False).run()
    op_b2 = asb.OperatingPoint(velocity=v_m, alpha=8.0)
    vb2 = asb.VortexLatticeMethod(airplane=ap_base, op_point=op_b2, verbose=False).run()
    dL_da_b = (vb2["L"] - vb1["L"]) / 4.0
    a_trim_b = 4.0 + (target_lift - vb1["L"]) / dL_da_b
    sol_b = asb.VortexLatticeMethod(
        airplane=ap_base,
        op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_b),
        verbose=False,
    )
    sol_b.run()

    # Solve box-wing
    op_x1 = asb.OperatingPoint(velocity=v_m, alpha=4.0)
    vx1 = asb.VortexLatticeMethod(airplane=ap_box, op_point=op_x1, verbose=False).run()
    op_x2 = asb.OperatingPoint(velocity=v_m, alpha=8.0)
    vx2 = asb.VortexLatticeMethod(airplane=ap_box, op_point=op_x2, verbose=False).run()
    dL_da_x = (vx2["L"] - vx1["L"]) / 4.0
    a_trim_x = 4.0 + (target_lift - vx1["L"]) / dL_da_x
    sol_x = asb.VortexLatticeMethod(
        airplane=ap_box,
        op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_x),
        verbose=False,
    )
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
    res_b2 = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_eval, alpha=2.0), verbose=False
    ).run()
    res_b6 = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_eval, alpha=6.0), verbose=False
    ).run()
    k_base = float((res_b6["CD"] - res_b2["CD"]) / (res_b6["CL"] ** 2 - res_b2["CL"] ** 2))

    res_x2 = asb.VortexLatticeMethod(
        airplane=ap_box, op_point=asb.OperatingPoint(velocity=v_eval, alpha=2.0), verbose=False
    ).run()
    res_x6 = asb.VortexLatticeMethod(
        airplane=ap_box, op_point=asb.OperatingPoint(velocity=v_eval, alpha=6.0), verbose=False
    ).run()
    k_box = float((res_x6["CD"] - res_x2["CD"]) / (res_x6["CL"] ** 2 - res_x2["CL"] ** 2))

    b_span = float(airplane.b_ref)
    ar_val = b_span**2 / airplane.s_ref
    e_base = (1.0 / (np.pi * ar_val)) / k_base
    e_box = (1.0 / (np.pi * ar_val)) / k_box
    induced_ratio = k_box / k_base

    # 3. Glide polar synthesis
    pol_b = _glide_polar(ap_base, mass=mass_flight, speeds_kmh=speeds_kmh)
    cdi_box = pol_b["CD_induced"] * induced_ratio
    cdp_box = pol_b["CD_profile"] + 0.0010
    cd_box = cdi_box + cdp_box
    ld_box = pol_b["CL"] / cd_box

    ld_base_max = float(np.max(pol_b["LD"]))
    ld_box_max = float(np.max(ld_box))
    v_base_max = float(speeds_kmh[np.argmax(pol_b["LD"])])
    v_box_max = float(speeds_kmh[np.argmax(ld_box)])

    return {
        "baseline_airplane": ap_base,
        "box_airplane": ap_box,
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
