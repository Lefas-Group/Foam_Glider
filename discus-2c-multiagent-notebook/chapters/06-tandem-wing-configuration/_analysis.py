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


def _build_scaled_tandem_airplane(
    b_target: float,
    decalage_aft: float = -0.98,
) -> asb.Airplane:
    """Build tandem airplane with span b_target on both wings, preserving total area 11.39 m^2."""
    scale_span = b_target / 18.0
    scale_chord = 18.0 / b_target

    af_root = asb.Airfoil("hq17")
    af_mid = asb.Airfoil("hq2512")
    af_tip = asb.Airfoil("hq2195")
    af_tail = asb.Airfoil("hq010")

    base_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
    base_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589]) * 0.5
    base_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
    wing_dihedral_deg = 3.0

    wing_ys = base_ys * scale_span
    wing_chords = base_chords * scale_chord
    x_c4 = base_xs_le + 0.25 * base_chords
    x_c4_scaled = x_c4[0] + (x_c4 - x_c4[0]) * scale_span
    wing_xs_le = x_c4_scaled - 0.25 * wing_chords

    wing_zs_le = wing_ys * np.tand(wing_dihedral_deg)
    wing_zs_le[-1] = wing_zs_le[-2] + 0.40

    wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
    wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]

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
        [1.00, 0.0, -0.10]
    )

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
        [4.30, 0.0, 0.35]
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
        name=f"Discus-2c-Tandem-{b_target:.1f}m",
        xyz_ref=[fl_props.x_cg, fl_props.y_cg, fl_props.z_cg],
        wings=[wf, wa, vt],
        fuselages=[fu],
        s_ref=11.39,
        c_ref=float(wf.mean_aerodynamic_chord()),
        b_ref=b_target,
    )


def tandem_aspect_ratio_trade(
    airplane: asb.Airplane = None,
    spans: np.ndarray = None,
    mass_flight: float = 417.0,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Sweep tandem wing aspect ratio up to the baseline root bending budget."""
    if spans is None:
        spans = np.array([18.0, 23.0, 28.0, 32.86])
    if speeds_kmh is None:
        speeds_kmh = np.linspace(75, 165, 10)

    ap_base = _build_baseline_airplane()
    v_m = 55.56
    target_lift = mass_structural * 9.81 * load_factor

    # 1. Baseline root bending moment under manoeuvre (+5.3g)
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

    # Baseline cruise induced drag factor
    v_cruise = 27.78
    r2_b = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=2.0), verbose=False
    ).run()
    r6_b = asb.VortexLatticeMethod(
        airplane=ap_base, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=6.0), verbose=False
    ).run()
    k_base = float((r6_b["CD"] - r2_b["CD"]) / (r6_b["CL"] ** 2 - r2_b["CL"] ** 2))

    pol_b = _glide_polar(ap_base, mass=mass_flight, speeds_kmh=speeds_kmh)
    ld_base_max = float(np.max(pol_b["LD"]))
    v_base_max = float(speeds_kmh[np.argmax(pol_b["LD"])])

    # 2. Evaluate each span
    m_root_arr = []
    m_fwd_arr = []
    m_aft_arr = []
    k_arr = []
    ir_arr = []
    ld_max_arr = []
    v_max_arr = []
    ar_ref_arr = []
    ar_wing_arr = []
    relief_arr = []
    cdp_best_arr = []
    cdi_best_arr = []

    for b in spans:
        plane = _build_scaled_tandem_airplane(b)
        ar_ref = float(b**2 / 11.39)
        ar_wing = float(b**2 / 5.695)
        ar_ref_arr.append(ar_ref)
        ar_wing_arr.append(ar_wing)

        # Manoeuvre bending
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
        mf = float(np.sum(yx[(yx >= 0) & (xx < 2.5)] * fzx[(yx >= 0) & (xx < 2.5)])) / 1000.0
        ma = float(np.sum(yx[(yx >= 0) & (xx >= 2.5)] * fzx[(yx >= 0) & (xx >= 2.5)])) / 1000.0
        m_pk = max(mf, ma)
        m_fwd_arr.append(mf)
        m_aft_arr.append(ma)
        m_root_arr.append(m_pk)
        relief_arr.append((1.0 - m_pk / m_root_base) * 100.0)

        # Cruise induced drag factor
        r2 = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=2.0), verbose=False
        ).run()
        r6 = asb.VortexLatticeMethod(
            airplane=plane, op_point=asb.OperatingPoint(velocity=v_cruise, alpha=6.0), verbose=False
        ).run()
        k_val = float((r6["CD"] - r2["CD"]) / (r6["CL"] ** 2 - r2["CL"] ** 2))
        ir_val = k_val / k_base
        k_arr.append(k_val)
        ir_arr.append(ir_val)

        # Glide polar
        pol_cur = _glide_polar(plane, mass=mass_flight, speeds_kmh=speeds_kmh)
        cdi_cur = pol_b["CD_induced"] * ir_val
        cdp_cur = pol_cur["CD_profile"]
        cd_cur = cdi_cur + cdp_cur
        ld_cur = pol_b["CL"] / cd_cur
        best_idx = int(np.argmax(ld_cur))
        ld_max_arr.append(float(ld_cur[best_idx]))
        v_max_arr.append(float(speeds_kmh[best_idx]))
        cdp_best_arr.append(float(cdp_cur[best_idx]))
        cdi_best_arr.append(float(cdi_cur[best_idx]))

    m_root_arr = np.array(m_root_arr)
    spans = np.array(spans)
    ar_ref_arr = np.array(ar_ref_arr)
    ar_wing_arr = np.array(ar_wing_arr)
    ld_max_arr = np.array(ld_max_arr)
    v_max_arr = np.array(v_max_arr)
    relief_arr = np.array(relief_arr)

    # Break-even span and AR where M_root == m_root_base
    b_limit = float(np.interp(m_root_base, m_root_arr, spans))
    ar_limit = float(b_limit**2 / 11.39)
    ar_wing_limit = float(b_limit**2 / 5.695)
    ld_limit = float(np.interp(b_limit, spans, ld_max_arr))
    delta_ld_limit = ld_limit - ld_base_max
    beats_baseline = bool(ld_limit > ld_base_max)

    return {
        "spans": spans,
        "ar_ref": ar_ref_arr,
        "ar_wing": ar_wing_arr,
        "m_root_base": m_root_base,
        "k_base": k_base,
        "ld_base_max": ld_base_max,
        "v_base_max": v_base_max,
        "m_root_arr": m_root_arr,
        "m_fwd_arr": np.array(m_fwd_arr),
        "m_aft_arr": np.array(m_aft_arr),
        "relief_arr": relief_arr,
        "k_arr": np.array(k_arr),
        "ir_arr": np.array(ir_arr),
        "ld_max_arr": ld_max_arr,
        "v_max_arr": v_max_arr,
        "cdp_best_arr": np.array(cdp_best_arr),
        "cdi_best_arr": np.array(cdi_best_arr),
        "b_limit": b_limit,
        "ar_limit": ar_limit,
        "ar_wing_limit": ar_wing_limit,
        "ld_limit": ld_limit,
        "delta_ld_limit": delta_ld_limit,
        "beats_baseline": beats_baseline,
        "speeds_kmh": speeds_kmh,
    }


def tandem_aeroelastic_analysis(
    b_target: float = 32.86,
    mass_structural: float = 565.0,
    load_factor: float = 5.3,
    velocity_manoeuvre: float = 55.56,
    v_ne: float = 77.78,
    t_skin: float = 0.0015,
    G_skin: float = 12.0e9,
    tau_allow: float = 60.0e6,
    spar_chord_frac: float = 0.35,
    e_frac: float = 0.10,
    a0: float = 2.0 * np.pi,
) -> dict:
    """Analyze wing torsional stiffness, stress margin, and aeroelastic divergence for high-AR tandem wing."""
    from scipy.interpolate import interp1d
    import scipy.linalg

    scale_span = b_target / 18.0
    scale_chord = 18.0 / b_target

    base_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
    base_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589]) * 0.5
    wing_ys = base_ys * scale_span
    wing_chords = base_chords * scale_chord
    semi_span = b_target / 2.0

    s_wing = float(np.trapezoid(wing_chords, wing_ys) * 2.0)
    c_mean = s_wing / b_target

    rho = 1.225
    q_m = 0.5 * rho * velocity_manoeuvre**2
    q_ne = 0.5 * rho * v_ne**2

    af_root = asb.Airfoil("hq17")
    af_mid = asb.Airfoil("hq2512")
    af_tip = asb.Airfoil("hq2195")

    cm_root = float(af_root.get_aero_from_neuralfoil(alpha=0.0, Re=1e6)["CM"][0])
    cm_mid = float(af_mid.get_aero_from_neuralfoil(alpha=0.0, Re=5e5)["CM"][0])
    cm_tip = float(af_tip.get_aero_from_neuralfoil(alpha=0.0, Re=2e5)["CM"][0])
    cm_stations = np.array([cm_root, cm_root, cm_mid, cm_mid, cm_tip, cm_tip])

    # Discretize along span
    ys = np.linspace(0, semi_span, 100)
    chords = np.interp(ys, wing_ys, wing_chords)
    cms = np.interp(ys, wing_ys, cm_stations)

    # Torque from intrinsic pitching moment
    m_running = q_m * (chords**2) * np.abs(cms)
    t_root = float(np.trapezoid(m_running, ys))
    t_y = np.array([np.trapezoid(m_running[i:], ys[i:]) for i in range(len(ys))])

    # D-tube geometry (HQ-17 profile scaled to chord)
    coords = af_root.coordinates
    x_af = np.linspace(0, spar_chord_frac, 100)
    upper = coords[coords[:, 1] >= 0]
    lower = coords[coords[:, 1] <= 0]
    upper = upper[np.argsort(upper[:, 0])]
    lower = lower[np.argsort(lower[:, 0])]
    yu = interp1d(upper[:, 0], upper[:, 1], fill_value="extrapolate")(x_af)
    yl = interp1d(lower[:, 0], lower[:, 1], fill_value="extrapolate")(x_af)

    A_m_nd = float(np.trapezoid(yu - yl, x_af))
    perim_skin_nd = float(
        np.sum(np.sqrt(np.diff(x_af) ** 2 + np.diff(yu) ** 2))
        + np.sum(np.sqrt(np.diff(x_af) ** 2 + np.diff(yl) ** 2))
    )
    h_web_nd = float(yu[-1] - yl[-1])
    t_web = 0.002

    k_J = 4.0 * (A_m_nd**2) / (perim_skin_nd / t_skin + h_web_nd / t_web)
    J_fine = k_J * (chords**3)
    GJ_fine = G_skin * J_fine
    GJ_root = float(GJ_fine[0])
    GJ_avg = float(np.mean(GJ_fine))

    c_root = float(chords[0])
    A_m_root = A_m_nd * (c_root**2)
    q_flow_root = t_root / (2.0 * A_m_root)
    tau_root = q_flow_root / t_skin
    margin_stress = tau_allow / tau_root

    theta_rad = np.zeros_like(ys)
    for i in range(1, len(ys)):
        theta_rad[i] = np.trapezoid(t_y[: i + 1] / GJ_fine[: i + 1], ys[: i + 1])
    tip_twist_deg = float(np.degrees(theta_rad[-1]))

    # Strip theory divergence criterion: q_div = GJ / (e * a0 * c^2 * b)
    q_div_strip = float(GJ_avg / (e_frac * a0 * (c_mean**2) * b_target))
    v_div_strip = float(np.sqrt(2.0 * q_div_strip / rho))

    # Tapered beam continuous eigenvalue
    n_nodes = 100
    dy = semi_span / (n_nodes - 1)
    K = np.zeros((n_nodes, n_nodes))
    for i in range(1, n_nodes - 1):
        GJ_p = 0.5 * (GJ_fine[i] + GJ_fine[i + 1])
        GJ_m = 0.5 * (GJ_fine[i] + GJ_fine[i - 1])
        K[i, i - 1] = -GJ_m / dy**2
        K[i, i] = (GJ_p + GJ_m) / dy**2
        K[i, i + 1] = -GJ_p / dy**2
    K[-1, -2] = -GJ_fine[-1] / dy**2
    K[-1, -1] = GJ_fine[-1] / dy**2

    A_mat = np.diag(chords**2 * e_frac * a0)
    A_mat[0, 0] = 0.0
    A_mat[-1, -1] = 0.0

    eigvals = scipy.linalg.eigvals(K[1:, 1:], A_mat[1:, 1:])
    eigvals_real = np.real(eigvals[np.isreal(eigvals) & (np.real(eigvals) > 0)])
    q_div_beam = float(np.min(eigvals_real))
    v_div_beam = float(np.sqrt(2.0 * q_div_beam / rho))

    v_req = 1.20 * v_ne
    q_req = 0.5 * rho * v_req**2
    reinforce_factor_strip = q_req / q_div_strip
    reinforce_factor_beam = q_req / q_div_beam

    return {
        "b_target": b_target,
        "semi_span": semi_span,
        "s_wing": s_wing,
        "c_root": c_root,
        "c_mean": c_mean,
        "c_tip": float(chords[-1]),
        "t_root_Nm": t_root,
        "A_m_root_m2": A_m_root,
        "GJ_root": GJ_root,
        "GJ_avg": GJ_avg,
        "tau_root_MPa": tau_root / 1e6,
        "margin_stress": margin_stress,
        "tip_twist_deg": tip_twist_deg,
        "q_div_strip_Pa": q_div_strip,
        "v_div_strip_ms": v_div_strip,
        "v_div_strip_kmh": v_div_strip * 3.6,
        "q_div_beam_Pa": q_div_beam,
        "v_div_beam_ms": v_div_beam,
        "v_div_beam_kmh": v_div_beam * 3.6,
        "v_ne_ms": v_ne,
        "v_ne_kmh": v_ne * 3.6,
        "q_ne_Pa": q_ne,
        "speed_ratio_strip": v_div_strip / v_ne,
        "speed_ratio_beam": v_div_beam / v_ne,
        "reinforce_factor_strip": reinforce_factor_strip,
        "reinforce_factor_beam": reinforce_factor_beam,
        "ys": ys,
        "chords": chords,
        "GJ": GJ_fine,
        "t_y": t_y,
        "theta_deg": np.degrees(theta_rad),
    }


