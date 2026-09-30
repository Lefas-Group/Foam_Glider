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


def box_wing_pitch_stability(
    airplane: asb.Airplane,
    velocity: float = 27.78,
    alpha_eval: float = 2.0,
    elevator_angles_deg: np.ndarray = None,
    elevator_chord_frac: float = 0.25,
) -> dict:
    """Analyze pitch stability (neutral point, static margin) and aft-wing elevator control authority."""
    if elevator_angles_deg is None:
        elevator_angles_deg = np.array([-15.0, -10.0, -5.0, 0.0])

    # 1. Baseline Discus-2c stability
    ap_base = _build_baseline_airplane()
    op_base = asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)
    ab_base = asb.AeroBuildup(airplane=ap_base, op_point=op_base).run_with_stability_derivatives()

    x_cg_base = float(ap_base.xyz_ref[0])
    c_ref_base = float(ap_base.c_ref)
    x_np_base_ab = float(ab_base["x_np"][0])
    sm_base_ab = (x_np_base_ab - x_cg_base) / c_ref_base

    # 2. Box-wing AeroBuildup stability
    op_box = asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)
    ab_box = asb.AeroBuildup(airplane=airplane, op_point=op_box).run_with_stability_derivatives()

    x_cg_box = float(airplane.xyz_ref[0])
    c_ref_box = float(airplane.c_ref)
    x_np_box_ab = float(ab_box["x_np"][0])
    sm_box_ab = (x_np_box_ab - x_cg_box) / c_ref_box
    sm_box_stagger = (x_np_box_ab - x_cg_box) / 3.70

    # 3. Box-wing VLM stability (2-point finite difference: 0 and 4 deg)
    res_vlm0 = asb.VortexLatticeMethod(
        airplane=airplane,
        op_point=asb.OperatingPoint(velocity=velocity, alpha=0.0),
        verbose=False,
    ).run()
    res_vlm4 = asb.VortexLatticeMethod(
        airplane=airplane,
        op_point=asb.OperatingPoint(velocity=velocity, alpha=4.0),
        verbose=False,
    ).run()
    cla_vlm = float((res_vlm4["CL"] - res_vlm0["CL"]) / np.radians(4.0))
    cma_vlm = float((res_vlm4["Cm"] - res_vlm0["Cm"]) / np.radians(4.0))
    x_np_box_vlm = x_cg_box - (cma_vlm / cla_vlm) * c_ref_box
    sm_box_vlm = (x_np_box_vlm - x_cg_box) / c_ref_box

    # 4. Elevator sweep on aft wing
    cms_de = []
    cls_de = []
    cds_de = []
    hinge_point = 1.0 - elevator_chord_frac

    af_root = asb.Airfoil("hq17")
    af_mid = asb.Airfoil("hq2512")
    af_tip = asb.Airfoil("hq2195")
    af_tail = asb.Airfoil("hq010")
    wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
    wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589])
    wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
    wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
    wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]
    c_aft = wing_chords * 0.5
    rel_xs = wing_xs_le - wing_xs_le[0]
    h_box = 0.15 * 18.0

    for de in elevator_angles_deg:
        cs = asb.ControlSurface(name="Elevator", deflection=de, hinge_point=hinge_point)
        xsecs_aft_ctrl = [
            asb.WingXSec(
                xyz_le=[rel_xs[i], wing_ys[i], 0.0],
                chord=c_aft[i],
                twist=wing_twists[i],
                airfoil=wing_airfoils[i],
                control_surfaces=[cs],
            )
            for i in range(len(wing_ys))
        ]
        aft_ctrl = asb.Wing(
            name="Aft Wing", symmetric=True, xsecs=xsecs_aft_ctrl
        ).translate([6.00, 0.0, h_box])

        ap_de = asb.Airplane(
            name="Discus-2c-BoxWing-Elevator",
            xyz_ref=airplane.xyz_ref,
            wings=[airplane.wings[0], aft_ctrl, airplane.wings[2], airplane.wings[3]],
            fuselages=airplane.fuselages,
            s_ref=airplane.s_ref,
            c_ref=airplane.c_ref,
            b_ref=airplane.b_ref,
        )
        ab_de = asb.AeroBuildup(airplane=ap_de, op_point=op_box).run()
        cms_de.append(float(ab_de["Cm"][0]))
        cls_de.append(float(ab_de["CL"][0]))
        cds_de.append(float(ab_de["CD"][0]))

    cms_de = np.array(cms_de)
    cls_de = np.array(cls_de)
    cds_de = np.array(cds_de)
    lds_de = cls_de / cds_de

    dcm_dde = float(np.polyfit(elevator_angles_deg, cms_de, 1)[0])
    delta_e_trim = float(np.interp(0.0, cms_de[::-1], elevator_angles_deg[::-1]))
    cl_trim = float(np.interp(delta_e_trim, elevator_angles_deg, cls_de))
    cd_trim = float(np.interp(delta_e_trim, elevator_angles_deg, cds_de))
    ld_trim = cl_trim / cd_trim

    # 5. Balanced CG check (10% MAC static margin)
    x_cg_bal = x_np_box_ab - 0.10 * c_ref_box
    ap_bal = asb.Airplane(
        name="Discus-2c-BoxWing-Balanced",
        xyz_ref=[x_cg_bal, 0.0, float(airplane.xyz_ref[2])],
        wings=airplane.wings,
        fuselages=airplane.fuselages,
        s_ref=airplane.s_ref,
        c_ref=airplane.c_ref,
        b_ref=airplane.b_ref,
    )
    ab_bal = asb.AeroBuildup(airplane=ap_bal, op_point=op_box).run_with_stability_derivatives()
    cl_bal = float(ab_bal["CL"][0])
    cd_bal = float(ab_bal["CD"][0])
    ld_bal = cl_bal / cd_bal
    cm_bal = float(ab_bal["Cm"][0])

    return {
        "x_cg_base": x_cg_base,
        "c_ref_base": c_ref_base,
        "x_np_base_ab": x_np_base_ab,
        "sm_base_ab": sm_base_ab,
        "x_cg_box": x_cg_box,
        "c_ref_box": c_ref_box,
        "x_np_box_ab": x_np_box_ab,
        "x_np_box_vlm": x_np_box_vlm,
        "sm_box_ab": sm_box_ab,
        "sm_box_vlm": sm_box_vlm,
        "sm_box_stagger": sm_box_stagger,
        "cla_box_ab": float(ab_box["CLa"][0]),
        "cma_box_ab": float(ab_box["Cma"][0]),
        "cla_box_vlm": cla_vlm,
        "cma_box_vlm": cma_vlm,
        "cm_untrimmed": float(ab_box["Cm"][0]),
        "dcm_dde": dcm_dde,
        "delta_e_trim": delta_e_trim,
        "cl_untrimmed": float(ab_box["CL"][0]),
        "cd_untrimmed": float(ab_box["CD"][0]),
        "ld_untrimmed": float(ab_box["CL"][0]) / float(ab_box["CD"][0]),
        "cl_trim": cl_trim,
        "cd_trim": cd_trim,
        "ld_trim": ld_trim,
        "elevator_angles_deg": elevator_angles_deg,
        "cms_de": cms_de,
        "cls_de": cls_de,
        "lds_de": lds_de,
        "x_cg_bal": x_cg_bal,
        "cl_bal": cl_bal,
        "cd_bal": cd_bal,
        "ld_bal": ld_bal,
        "cm_bal": cm_bal,
    }


def box_wing_stagger_gap_trade(
    airplane: asb.Airplane,
    velocity: float = 27.78,
    alpha_eval: float = 2.0,
    staggers: np.ndarray = None,
    gaps: np.ndarray = None,
    elevator_chord_frac: float = 0.25,
) -> dict:
    """Evaluate neutral point, static margin, elevator authority, and trim L/D across stagger and gap."""
    if staggers is None:
        staggers = np.array([3.70, 3.00, 2.50, 2.00, 1.50, 1.00, 0.60, 0.40, 0.20, 0.10, 0.00])
    if gaps is None:
        gaps = np.array([0.50, 1.00, 1.80, 2.70, 3.60])

    af_root = asb.Airfoil("hq17")
    af_mid = asb.Airfoil("hq2512")
    af_tip = asb.Airfoil("hq2195")
    af_tail = asb.Airfoil("hq010")

    wing_ys = np.array([0.0, 2.1, 4.5, 7.5, 8.8, 9.0])
    wing_chords = np.array([0.8093, 0.7646, 0.6653, 0.5015, 0.3128, 0.1589])
    wing_xs_le = np.array([0.0, -0.040, 0.045, 0.250, 0.450, 0.530])
    wing_twists = [0.0, -0.3, -0.8, -1.5, -2.2, -2.5]
    wing_airfoils = [af_root, af_root, af_mid, af_mid, af_tip, af_tip]
    c_fwd = wing_chords * 0.5
    c_aft = wing_chords * 0.5
    rel_xs = wing_xs_le - wing_xs_le[0]
    hinge_point = 1.0 - elevator_chord_frac
    x_cg = float(airplane.xyz_ref[0])

    def _build_variant(stagger_val, h_box_val, de_val=0.0):
        x_fwd_root = 2.30
        x_aft_root = x_fwd_root + stagger_val

        xsecs_fwd = [
            asb.WingXSec(
                xyz_le=[rel_xs[i], wing_ys[i], 0.0],
                chord=c_fwd[i],
                twist=wing_twists[i],
                airfoil=wing_airfoils[i],
            )
            for i in range(len(wing_ys))
        ]
        fwd_w = asb.Wing(name="Forward Wing", symmetric=True, xsecs=xsecs_fwd).translate([x_fwd_root, 0.0, 0.0])

        cs = asb.ControlSurface(name="Elevator", deflection=de_val, hinge_point=hinge_point)
        xsecs_aft = [
            asb.WingXSec(
                xyz_le=[rel_xs[i], wing_ys[i], 0.0],
                chord=c_aft[i],
                twist=wing_twists[i],
                airfoil=wing_airfoils[i],
                control_surfaces=[cs] if de_val != 0.0 else None,
            )
            for i in range(len(wing_ys))
        ]
        aft_w = asb.Wing(name="Aft Wing", symmetric=True, xsecs=xsecs_aft).translate([x_aft_root, 0.0, h_box_val])

        tip_ep = asb.Wing(
            name="Tip Endplate",
            symmetric=True,
            xsecs=[
                asb.WingXSec(xyz_le=[x_fwd_root + rel_xs[-1], wing_ys[-1], 0.0], chord=c_fwd[-1], airfoil=af_tail),
                asb.WingXSec(xyz_le=[x_aft_root + rel_xs[-1], wing_ys[-1], h_box_val], chord=c_aft[-1], airfoil=af_tail),
            ],
        )

        return asb.Airplane(
            name="Discus-2c-BoxWing-Trade",
            xyz_ref=airplane.xyz_ref,
            wings=[fwd_w, aft_w, tip_ep, airplane.wings[3]],
            fuselages=airplane.fuselages,
            s_ref=airplane.s_ref,
            c_ref=float(fwd_w.mean_aerodynamic_chord()),
            b_ref=airplane.b_ref,
        )

    # 1. Stagger trade at nominal gap h_box = 2.70 m
    stagger_res = []
    for s in staggers:
        ap0 = _build_variant(s, 2.70, 0.0)
        c_ref = ap0.c_ref

        # Stability derivatives
        ab1 = asb.AeroBuildup(airplane=ap0, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval - 1.0)).run()
        ab2 = asb.AeroBuildup(airplane=ap0, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval + 1.0)).run()
        cla = (ab2["CL"][0] - ab1["CL"][0]) / np.radians(2.0)
        cma = (ab2["Cm"][0] - ab1["Cm"][0]) / np.radians(2.0)
        x_np = x_cg - (cma / cla) * c_ref
        sm_mac = (x_np - x_cg) / c_ref

        # Untrimmed performance
        ab0 = asb.AeroBuildup(airplane=ap0, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)).run()
        cm0 = float(ab0["Cm"][0])
        cl0 = float(ab0["CL"][0])
        cd0 = float(ab0["CD"][0])
        ld0 = cl0 / cd0

        # Elevator effectiveness
        ap_m10 = _build_variant(s, 2.70, -10.0)
        ab_m10 = asb.AeroBuildup(airplane=ap_m10, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)).run()
        ap_p10 = _build_variant(s, 2.70, 10.0)
        ab_p10 = asb.AeroBuildup(airplane=ap_p10, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)).run()
        dcm_dde = float((ab_p10["Cm"][0] - ab_m10["Cm"][0]) / 20.0)

        if abs(dcm_dde) > 1e-4:
            de_trim = float(-cm0 / dcm_dde)
            if -30.0 <= de_trim <= 30.0:
                ap_tr = _build_variant(s, 2.70, de_trim)
                ab_tr = asb.AeroBuildup(airplane=ap_tr, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)).run()
                cl_tr = float(ab_tr["CL"][0])
                cd_tr = float(ab_tr["CD"][0])
                ld_tr = float(cl_tr / cd_tr)
            else:
                ld_tr = np.nan
                cl_tr = np.nan
                cd_tr = np.nan
        else:
            de_trim = np.nan
            ld_tr = np.nan
            cl_tr = np.nan
            cd_tr = np.nan

        stagger_res.append({
            "stagger": float(s),
            "x_aft": float(2.30 + s),
            "x_np": float(x_np),
            "sm_mac": float(sm_mac),
            "cm0": cm0,
            "dcm_dde": dcm_dde,
            "de_trim": de_trim,
            "ld_untrim": ld0,
            "ld_trim": ld_tr,
            "cl_trim": cl_tr,
            "cd_trim": cd_tr,
        })

    # 2. Gap trade at nominal stagger = 3.70 m
    gap_res = []
    for h in gaps:
        ap_g = _build_variant(3.70, h, 0.0)
        c_ref = ap_g.c_ref
        ab1 = asb.AeroBuildup(airplane=ap_g, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval - 1.0)).run()
        ab2 = asb.AeroBuildup(airplane=ap_g, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval + 1.0)).run()
        cla = (ab2["CL"][0] - ab1["CL"][0]) / np.radians(2.0)
        cma = (ab2["Cm"][0] - ab1["Cm"][0]) / np.radians(2.0)
        x_np = x_cg - (cma / cla) * c_ref
        sm_mac = (x_np - x_cg) / c_ref

        ab_g0 = asb.AeroBuildup(airplane=ap_g, op_point=asb.OperatingPoint(velocity=velocity, alpha=alpha_eval)).run()
        cm0 = float(ab_g0["Cm"][0])
        cl0 = float(ab_g0["CL"][0])
        cd0 = float(ab_g0["CD"][0])

        gap_res.append({
            "h_box": float(h),
            "hb_ratio": float(h / 18.0),
            "x_np": float(x_np),
            "sm_mac": float(sm_mac),
            "cm0": cm0,
            "ld_untrim": float(cl0 / cd0),
        })

    return {
        "x_cg": x_cg,
        "staggers": np.array([r["stagger"] for r in stagger_res]),
        "stagger_res": stagger_res,
        "gaps": np.array([r["h_box"] for r in gap_res]),
        "gap_res": gap_res,
    }


