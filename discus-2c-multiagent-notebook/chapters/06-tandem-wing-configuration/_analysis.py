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
    """Compute steady unaccelerated 1-g glide polar across speeds using AeroBuildup."""
    if speeds_kmh is None:
        speeds_kmh = np.linspace(75, 180, 15)
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

    alphas_grid = np.linspace(-2, 10, 41)
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


def tandem_comparison(
    airplane: asb.Airplane,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate tandem-wing configuration against calibrated baseline Discus-2c monoplane."""
    if speeds_kmh is None:
        speeds_kmh = np.linspace(75, 180, 15)

    ap_base = _build_baseline_airplane()
    ap_td = airplane

    # 1. Structural loads: Limit manoeuvre root bending moment (+5.3g at MTOM 565 kg, V = 55.56 m/s)
    v_m = 55.56
    target_lift = mass_structural * 9.81 * load_factor

    # Baseline VLM solve
    vb1 = asb.VortexLatticeMethod(airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_m, alpha=4.0), verbose=False).run()
    vb2 = asb.VortexLatticeMethod(airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_m, alpha=8.0), verbose=False).run()
    dL_da_b = (vb2["L"] - vb1["L"]) / 4.0
    a_trim_b = 4.0 + (target_lift - vb1["L"]) / dL_da_b
    sol_b = asb.VortexLatticeMethod(airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_b), verbose=False)
    sol_b.run()

    yb = sol_b.vortex_centers[:, 1]
    xb = sol_b.vortex_centers[:, 0]
    fzb = sol_b.forces_geometry[:, 2]
    sb_b = (yb >= 0) & (xb < 4.0)
    m_root_base = float(np.sum(yb[sb_b] * fzb[sb_b])) / 1000.0

    # Tandem VLM solve for manoeuvre
    vx1 = asb.VortexLatticeMethod(airplane=ap_td, op_point=asb.OperatingPoint(velocity=v_m, alpha=4.0), verbose=False).run()
    vx2 = asb.VortexLatticeMethod(airplane=ap_td, op_point=asb.OperatingPoint(velocity=v_m, alpha=8.0), verbose=False).run()
    dL_da_x = (vx2["L"] - vx1["L"]) / 4.0
    a_trim_x = 4.0 + (target_lift - vx1["L"]) / dL_da_x
    sol_x = asb.VortexLatticeMethod(airplane=ap_td, op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_x), verbose=False)
    sol_x.run()

    yx = sol_x.vortex_centers[:, 1]
    xx = sol_x.vortex_centers[:, 0]
    fzx = sol_x.forces_geometry[:, 2]

    # Starboard panels of Fore Wing (xc < 2.5) and Aft Wing (xc >= 2.5)
    sb_fwd = (yx >= 0) & (xx < 2.5)
    sb_aft = (yx >= 0) & (xx >= 2.5)

    m_root_fwd = float(np.sum(yx[sb_fwd] * fzx[sb_fwd])) / 1000.0
    m_root_aft = float(np.sum(yx[sb_aft] * fzx[sb_aft])) / 1000.0
    m_root_td_max = max(m_root_fwd, m_root_aft)
    bending_relief_pct = (1.0 - m_root_td_max / m_root_base) * 100.0

    # 2. Pitch trim, static margin, and lift split at cruise (V = 27.78 m/s = 100 km/h, 417 kg)
    v_cruise = 27.78
    op_c1 = asb.OperatingPoint(velocity=v_cruise, alpha=2.0)
    op_c2 = asb.OperatingPoint(velocity=v_cruise, alpha=4.0)
    vc1 = asb.VortexLatticeMethod(airplane=ap_td, op_point=op_c1, verbose=False).run()
    vc2 = asb.VortexLatticeMethod(airplane=ap_td, op_point=op_c2, verbose=False).run()

    dCL_da_c = (vc2["CL"] - vc1["CL"]) / 2.0
    dCm_da_c = (vc2["Cm"] - vc1["Cm"]) / 2.0
    weight_cruise = mass_flight * 9.81
    CL_req_cruise = weight_cruise / (0.5 * 1.225 * v_cruise**2 * ap_td.s_ref)
    alpha_cruise_trim = 2.0 + (CL_req_cruise - vc1["CL"]) / dCL_da_c

    # Evaluate at trimmed cruise
    op_trim = asb.OperatingPoint(velocity=v_cruise, alpha=alpha_cruise_trim)
    sol_trim = asb.VortexLatticeMethod(airplane=ap_td, op_point=op_trim, verbose=False)
    res_trim = sol_trim.run()

    # Panel forces at trim
    fzc = sol_trim.forces_geometry[:, 2]
    xcc = sol_trim.vortex_centers[:, 0]
    lift_fwd_trim = float(np.sum(fzc[xcc < 2.5]))
    lift_aft_trim = float(np.sum(fzc[xcc >= 2.5]))
    total_lift_trim = lift_fwd_trim + lift_aft_trim
    lift_split_fwd_pct = (lift_fwd_trim / total_lift_trim) * 100.0
    lift_split_aft_pct = (lift_aft_trim / total_lift_trim) * 100.0

    c_ref = ap_td.c_ref
    static_margin_pct = float(- (dCm_da_c / dCL_da_c) * 100.0)
    cm_trim = float(res_trim["Cm"])

    # 3. VLM induced drag coupling & tandem interference
    res_b2 = asb.VortexLatticeMethod(airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=2.0), verbose=False).run()
    res_b6 = asb.VortexLatticeMethod(airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=6.0), verbose=False).run()
    k_base = float((res_b6["CD"] - res_b2["CD"]) / (res_b6["CL"]**2 - res_b2["CL"]**2))

    res_x2 = asb.VortexLatticeMethod(airplane=ap_td, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=2.0), verbose=False).run()
    res_x6 = asb.VortexLatticeMethod(airplane=ap_td, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=6.0), verbose=False).run()
    k_td = float((res_x6["CD"] - res_x2["CD"]) / (res_x6["CL"]**2 - res_x2["CL"]**2))

    induced_ratio = k_td / k_base
    ar_base = float(ap_base.b_ref**2 / ap_base.s_ref)
    ar_td = float(ap_td.b_ref**2 / ap_td.s_ref)
    e_base = float((1.0 / (np.pi * ar_base)) / k_base)
    e_td = float((1.0 / (np.pi * ar_td)) / k_td)

    # 4. Glide polar synthesis
    pol_b = _glide_polar(ap_base, mass=mass_flight, speeds_kmh=speeds_kmh)
    pol_td = _glide_polar(ap_td, mass=mass_flight, speeds_kmh=speeds_kmh)

    cdi_td = pol_b["CD_induced"] * induced_ratio
    cdp_td = pol_td["CD_profile"]
    cd_td = cdi_td + cdp_td
    ld_td = pol_b["CL"] / cd_td

    ld_base_max = float(np.max(pol_b["LD"]))
    ld_td_max = float(np.max(ld_td))
    v_base_max = float(speeds_kmh[np.argmax(pol_b["LD"])])
    v_td_max = float(speeds_kmh[np.argmax(ld_td)])
    delta_ld = ld_td_max - ld_base_max

    return {
        "baseline_airplane": ap_base,
        "tandem_airplane": ap_td,
        "m_root_base": m_root_base,
        "m_root_fwd": m_root_fwd,
        "m_root_aft": m_root_aft,
        "m_root_td_max": m_root_td_max,
        "bending_relief_pct": bending_relief_pct,
        "k_base": k_base,
        "k_td": k_td,
        "induced_ratio": induced_ratio,
        "e_base": e_base,
        "e_td": e_td,
        "speeds_kmh": speeds_kmh,
        "ld_base_arr": pol_b["LD"],
        "ld_td_arr": ld_td,
        "cdi_base_arr": pol_b["CD_induced"],
        "cdi_td_arr": cdi_td,
        "cdp_base_arr": pol_b["CD_profile"],
        "cdp_td_arr": cdp_td,
        "ld_base_max": ld_base_max,
        "ld_td_max": ld_td_max,
        "delta_ld": delta_ld,
        "v_base_max": v_base_max,
        "v_td_max": v_td_max,
        "alpha_cruise_trim": float(alpha_cruise_trim),
        "lift_split_fwd_pct": float(lift_split_fwd_pct),
        "lift_split_aft_pct": float(lift_split_aft_pct),
        "static_margin_pct": float(static_margin_pct),
        "cm_trim": float(cm_trim),
    }


def _build_18m_tandem_airplane(decalage_aft: float = -0.98) -> asb.Airplane:
    """Build tandem airplane with full 18 m span on both fore and aft wings, halving chords."""
    af_root = asb.Airfoil("hq17")
    af_mid = asb.Airfoil("hq2512")
    af_tip = asb.Airfoil("hq2195")
    af_tail = asb.Airfoil("hq010")

    wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
    wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589]) * 0.5
    wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
    wing_dihedral_deg = 3.0
    wing_zs_le = wing_ys * np.tand(wing_dihedral_deg)
    wing_zs_le[-1] = wing_zs_le[-2] + 0.40

    wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
    wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]

    x_fwd_root = 1.00
    z_fwd_root = -0.10
    xsecs_fore = [
        asb.WingXSec(
            xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
            chord=wing_chords[i],
            twist=wing_twists[i],
            airfoil=wing_airfoils[i],
        )
        for i in range(len(wing_ys))
    ]
    wf = asb.Wing(name="Fore Wing", symmetric=True, xsecs=xsecs_fore).translate(
        [x_fwd_root, 0.0, z_fwd_root]
    )

    x_aft_root = 4.30
    z_aft_root = 0.35
    xsecs_aft = [
        asb.WingXSec(
            xyz_le=[wing_xs_le[i], wing_ys[i], wing_zs_le[i]],
            chord=wing_chords[i],
            twist=wing_twists[i] + decalage_aft,
            airfoil=wing_airfoils[i],
        )
        for i in range(len(wing_ys))
    ]
    wa = asb.Wing(name="Aft Wing", symmetric=True, xsecs=xsecs_aft).translate(
        [x_aft_root, 0.0, z_aft_root]
    )

    xsecs_vtail = [
        asb.WingXSec(xyz_le=[5.85, 0.0, -0.05], chord=0.85, airfoil=af_tail),
        asb.WingXSec(xyz_le=[6.38, 0.0, 1.25], chord=0.45, airfoil=af_tail),
    ]
    vt = asb.Wing(name="Vertical Stabilizer", symmetric=False, xsecs=xsecs_vtail)

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
    fu = asb.Fuselage(name="Fuselage", xsecs=fuse_xsecs)

    empty_props = asb.MassProperties(
        mass=337.0, x_cg=2.832, y_cg=0.0, z_cg=0.097, Ixx=1760.5, Iyy=189.7, Izz=1934.2
    )
    fl_props = empty_props + asb.MassProperties(mass=80.0, x_cg=1.75, y_cg=0.0, z_cg=0.0)

    return asb.Airplane(
        name="Discus-2c-Tandem-18m",
        xyz_ref=[fl_props.x_cg, fl_props.y_cg, fl_props.z_cg],
        wings=[wf, wa, vt],
        fuselages=[fu],
        s_ref=11.39,
        c_ref=float(wf.mean_aerodynamic_chord()),
        b_ref=18.0,
    )


def tandem_full_span_comparison(
    airplane: asb.Airplane,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate 18 m full-span tandem wing against reduced-span tandem and baseline monoplane."""
    if speeds_kmh is None:
        speeds_kmh = np.linspace(75, 180, 15)

    ap_base = _build_baseline_airplane()
    ap_red = airplane
    ap_18 = _build_18m_tandem_airplane()

    v_m = 55.56
    target_lift = mass_structural * 9.81 * load_factor

    # 1. Manoeuvre bending moments
    def _calc_m_root_tandem(plane, split_x=2.5):
        vx1 = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_m, alpha=4.0), verbose=False
        ).run()
        vx2 = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_m, alpha=8.0), verbose=False
        ).run()
        dL_da = (vx2["L"] - vx1["L"]) / 4.0
        a_trim = 4.0 + (target_lift - vx1["L"]) / dL_da
        sol = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim), verbose=False
        )
        sol.run()
        yx = sol.vortex_centers[:, 1]
        xx = sol.vortex_centers[:, 0]
        fzx = sol.forces_geometry[:, 2]
        sb_fwd = (yx >= 0) & (xx < split_x)
        sb_aft = (yx >= 0) & (xx >= split_x)
        m_fwd = float(np.sum(yx[sb_fwd] * fzx[sb_fwd])) / 1000.0
        m_aft = float(np.sum(yx[sb_aft] * fzx[sb_aft])) / 1000.0
        return m_fwd, m_aft

    vb1 = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_m, alpha=4.0), verbose=False
    ).run()
    vb2 = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_m, alpha=8.0), verbose=False
    ).run()
    dL_da_b = (vb2["L"] - vb1["L"]) / 4.0
    a_trim_b = 4.0 + (target_lift - vb1["L"]) / dL_da_b
    sol_b = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_m, alpha=a_trim_b), verbose=False
    )
    sol_b.run()
    yb = sol_b.vortex_centers[:, 1]
    xb = sol_b.vortex_centers[:, 0]
    fzb = sol_b.forces_geometry[:, 2]
    sb_b = (yb >= 0) & (xb < 4.0)
    m_root_base = float(np.sum(yb[sb_b] * fzb[sb_b])) / 1000.0

    m_fwd_red, m_aft_red = _calc_m_root_tandem(ap_red)
    m_red_max = max(m_fwd_red, m_aft_red)
    relief_red_pct = (1.0 - m_red_max / m_root_base) * 100.0

    m_fwd_18, m_aft_18 = _calc_m_root_tandem(ap_18)
    m_18_max = max(m_fwd_18, m_aft_18)
    relief_18_pct = (1.0 - m_18_max / m_root_base) * 100.0

    # 2. Induced drag factors at cruise (V = 27.78 m/s = 100 km/h)
    v_cruise = 27.78

    def _calc_k(plane):
        r2 = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=2.0), verbose=False
        ).run()
        r6 = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=6.0), verbose=False
        ).run()
        return float((r6["CD"] - r2["CD"]) / (r6["CL"] ** 2 - r2["CL"] ** 2))

    k_base = _calc_k(ap_base)
    k_red = _calc_k(ap_red)
    k_18 = _calc_k(ap_18)

    ir_red = k_red / k_base
    ir_18 = k_18 / k_base

    ar_base = float(ap_base.b_ref ** 2 / ap_base.s_ref)
    ar_red = float(ap_red.b_ref ** 2 / ap_red.s_ref)
    ar_18 = float(ap_18.b_ref ** 2 / ap_18.s_ref)

    e_base = float((1.0 / (np.pi * ar_base)) / k_base)
    e_red = float((1.0 / (np.pi * ar_red)) / k_red)
    e_18 = float((1.0 / (np.pi * ar_18)) / k_18)

    # 3. Glide polars
    pol_b = _glide_polar(ap_base, mass=mass_flight, speeds_kmh=speeds_kmh)
    pol_red = _glide_polar(ap_red, mass=mass_flight, speeds_kmh=speeds_kmh)
    pol_18 = _glide_polar(ap_18, mass=mass_flight, speeds_kmh=speeds_kmh)

    cdi_red = pol_b["CD_induced"] * ir_red
    cdp_red = pol_red["CD_profile"]
    cd_red = cdi_red + cdp_red
    ld_red = pol_b["CL"] / cd_red

    cdi_18 = pol_b["CD_induced"] * ir_18
    cdp_18 = pol_18["CD_profile"]
    cd_18 = cdi_18 + cdp_18
    ld_18 = pol_b["CL"] / cd_18

    ld_base_max = float(np.max(pol_b["LD"]))
    v_base_max = float(speeds_kmh[np.argmax(pol_b["LD"])])

    ld_red_max = float(np.max(ld_red))
    v_red_max = float(speeds_kmh[np.argmax(ld_red)])
    delta_ld_red = ld_red_max - ld_base_max

    ld_18_max = float(np.max(ld_18))
    v_18_max = float(speeds_kmh[np.argmax(ld_18)])
    delta_ld_18 = ld_18_max - ld_base_max

    recovered_ld = ld_18_max - ld_red_max
    recovery_pct = (recovered_ld / (ld_base_max - ld_red_max)) * 100.0

    # 4. Cruise trim and stability for 18m tandem
    op_c1 = asb.OperatingPoint(velocity=v_cruise, alpha=2.0)
    op_c2 = asb.OperatingPoint(velocity=v_cruise, alpha=4.0)
    vc1_18 = asb.VortexLatticeMethod(airplane=ap_18, op_point=op_c1, verbose=False).run()
    vc2_18 = asb.VortexLatticeMethod(airplane=ap_18, op_point=op_c2, verbose=False).run()
    dCL_da_18 = (vc2_18["CL"] - vc1_18["CL"]) / 2.0
    dCm_da_18 = (vc2_18["Cm"] - vc1_18["Cm"]) / 2.0
    weight_cruise = mass_flight * 9.81
    CL_req_cruise = weight_cruise / (0.5 * 1.225 * v_cruise ** 2 * ap_18.s_ref)
    alpha_trim_18 = 2.0 + (CL_req_cruise - vc1_18["CL"]) / dCL_da_18

    sol_trim_18 = asb.VortexLatticeMethod(
        airplane=ap_18, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=alpha_trim_18), verbose=False
    )
    res_trim_18 = sol_trim_18.run()
    fzc_18 = sol_trim_18.forces_geometry[:, 2]
    xc_18 = sol_trim_18.vortex_centers[:, 0]
    l_fwd_18 = float(np.sum(fzc_18[xc_18 < 2.5]))
    l_aft_18 = float(np.sum(fzc_18[xc_18 >= 2.5]))
    l_tot_18 = l_fwd_18 + l_aft_18
    lift_split_fwd_18 = (l_fwd_18 / l_tot_18) * 100.0
    lift_split_aft_18 = (l_aft_18 / l_tot_18) * 100.0

    h_np_18 = -float(dCm_da_18 / dCL_da_18)
    sm_18 = h_np_18 * 100.0
    cm_trim_18 = float(res_trim_18["Cm"])

    return {
        "m_root_base": m_root_base,
        "m_root_fwd_red": m_fwd_red,
        "m_root_aft_red": m_aft_red,
        "m_root_red_max": m_red_max,
        "relief_red_pct": relief_red_pct,
        "m_root_fwd_18": m_fwd_18,
        "m_root_aft_18": m_aft_18,
        "m_root_18_max": m_18_max,
        "relief_18_pct": relief_18_pct,
        "k_base": k_base,
        "k_red": k_red,
        "k_18": k_18,
        "induced_ratio_red": ir_red,
        "induced_ratio_18": ir_18,
        "e_base": e_base,
        "e_red": e_red,
        "e_18": e_18,
        "speeds_kmh": speeds_kmh,
        "ld_base_arr": pol_b["LD"],
        "ld_red_arr": ld_red,
        "ld_18_arr": ld_18,
        "cdi_base_arr": pol_b["CD_induced"],
        "cdi_red_arr": cdi_red,
        "cdi_18_arr": cdi_18,
        "cdp_base_arr": pol_b["CD_profile"],
        "cdp_red_arr": cdp_red,
        "cdp_18_arr": cdp_18,
        "ld_base_max": ld_base_max,
        "v_base_max": v_base_max,
        "ld_red_max": ld_red_max,
        "v_red_max": v_red_max,
        "delta_ld_red": delta_ld_red,
        "ld_18_max": ld_18_max,
        "v_18_max": v_18_max,
        "delta_ld_18": delta_ld_18,
        "recovered_ld": recovered_ld,
        "recovery_pct": recovery_pct,
        "alpha_trim_18": float(alpha_trim_18),
        "lift_split_fwd_18": float(lift_split_fwd_18),
        "lift_split_aft_18": float(lift_split_aft_18),
        "static_margin_18": float(sm_18),
        "cm_trim_18": float(cm_trim_18),
        "ap_18": ap_18,
    }

