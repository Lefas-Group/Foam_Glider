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


def canard_comparison(
    airplane: asb.Airplane,
    mass_flight: float = 417.0,
    speeds_kmh: np.ndarray = None,
) -> dict:
    """Evaluate canard configuration against calibrated baseline Discus-2c monoplane."""
    if speeds_kmh is None:
        speeds_kmh = np.array([75.0, 85.0, 95.0, 105.0, 120.0, 140.0, 160.0, 180.0, 200.0])

    speeds_mps = np.array(speeds_kmh) / 3.6
    weight = mass_flight * 9.81
    ap_base = _build_baseline_airplane()
    ap_canard = airplane

    s_ref = airplane.s_ref
    b_ref = airplane.b_ref
    c_mac = airplane.c_ref

    main_w = ap_base.wings[0]
    htail_w = ap_base.wings[1]
    vtail_w = ap_base.wings[2]
    fuse_b = ap_base.fuselages[0]
    canard_w = ap_canard.wings[1]

    v_ref = 25.0
    op0 = asb.OperatingPoint(velocity=v_ref, alpha=0.0)
    opa = asb.OperatingPoint(velocity=v_ref, alpha=4.0)

    # 1. Baseline stability and neutral point
    x_cg_b = float(ap_base.xyz_ref[0])
    vb0 = asb.VortexLatticeMethod(airplane=ap_base, op_point=op0, verbose=False).run()
    vba = asb.VortexLatticeMethod(airplane=ap_base, op_point=opa, verbose=False).run()
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
        xyz_ref=[x_cg_b, 0, ap_base.xyz_ref[2]],
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
    x_cg_c = float(ap_canard.xyz_ref[0])
    vc0 = asb.VortexLatticeMethod(airplane=ap_canard, op_point=op0, verbose=False).run()
    vca = asb.VortexLatticeMethod(airplane=ap_canard, op_point=opa, verbose=False).run()
    CLa_c = (vca["CL"] - vc0["CL"]) / 4.0
    Cma_c = (vca["Cm"] - vc0["Cm"]) / 4.0
    x_np_c = x_cg_c - (Cma_c / CLa_c) * c_mac
    sm_c = (x_np_c - x_cg_c) / c_mac

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
        xyz_ref=[x_cg_c, 0, ap_canard.xyz_ref[2]],
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
    A_c = np.array([[CLa_c, CLd_c], [Cma_c, Cmd_c]])

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
            xyz_ref=[x_cg_b, 0, ap_base.xyz_ref[2]],
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
            xyz_ref=[x_cg_c, 0, ap_canard.xyz_ref[2]],
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
        "baseline_airplane": ap_base,
        "canard_airplane": ap_canard,
        "x_np_base": x_np_b,
        "x_np_canard": x_np_c,
        "delta_x_np": x_np_c - x_np_b,
        "x_cg_base": x_cg_b,
        "x_cg_canard": x_cg_c,
        "delta_x_cg": x_cg_c - x_cg_b,
        "sm_base": sm_b,
        "sm_canard": sm_c,
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
