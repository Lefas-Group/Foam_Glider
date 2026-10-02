import aerosandbox as asb
import aerosandbox.numpy as np
from scipy.optimize import root_scalar


def solve_propulsion_thrust_apc(
    velocity: float,
    v_oc: float = 11.1,
    kv: float = 2300.0,
    r_tot: float = 0.145,
    i0: float = 0.9,
    diameter: float = 6.0 * 0.0254,
    rho: float = 1.225,
) -> dict[str, float]:
    """Compute motor-propeller operating point using calibrated APC 6x4.5E polar.

    Parameters
    ----------
    velocity : float
        Flight speed in m/s.
    v_oc : float
        Battery open-circuit voltage in Volts (11.1 V nominal for 3S).
    kv : float
        Motor velocity constant in rpm/V.
    r_tot : float
        Total electrical loop resistance in Ohms (motor + battery ESR + ESC).
    i0 : float
        Motor no-load current in Amperes.
    diameter : float
        Propeller diameter in meters (6 inches).
    rho : float
        Air density in kg/m^3.

    Returns
    -------
    dict[str, float]
        Dictionary of thrust [N], rpm, advance ratio J, and current [A].
    """
    def ct(J: float) -> float:
        val = 0.12362 * J**3 - 0.29598 * J**2 - 0.06184 * J + 0.18583
        return float(np.maximum(val, 0.0))

    def cp(J: float) -> float:
        val = 0.01608 * J**3 - 0.18765 * J**2 + 0.05471 * J + 0.09082
        return float(np.maximum(val, 0.005))

    def torque_residual(rpm: float) -> float:
        n = rpm / 60.0
        J = velocity / (n * diameter)
        q_prop = cp(J) * rho * (n**2) * (diameter**5) / (2 * np.pi)
        current = (v_oc - (rpm / kv)) / r_tot
        q_motor = (current - i0) / (kv * 2 * np.pi / 60.0)
        return q_motor - q_prop

    rpm_max = v_oc * kv
    sol = root_scalar(torque_residual, bracket=[8000, rpm_max - 20], method="brentq")
    rpm = float(sol.root)
    n = rpm / 60.0
    J = velocity / (n * diameter)
    thrust = float(ct(J) * rho * (n**2) * (diameter**4))
    current = float((v_oc - (rpm / kv)) / r_tot)

    return {
        "thrust": thrust,
        "rpm": rpm,
        "J": J,
        "current": current,
    }


def level_flight_drag(
    airplane: asb.Airplane,
    velocity: float,
    mass: float = 0.254,
    sigma: float = 0.435,
    e0: float = 0.90,
) -> float:
    """Compute level flight aerodynamic drag including Prandtl biplane interference.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    velocity : float
        Flight speed in m/s.
    mass : float
        All-up mass in kg.
    sigma : float
        Prandtl mutual interference factor.
    e0 : float
        Isolated panel Oswald span efficiency.

    Returns
    -------
    float
        Aerodynamic drag in Newtons.
    """
    weight = mass * 9.80665
    rho = 1.225
    q = 0.5 * rho * velocity**2
    s = airplane.s_ref
    cl_req = weight / (q * s)

    op0 = asb.OperatingPoint(velocity=velocity, alpha=-1.0)
    op1 = asb.OperatingPoint(velocity=velocity, alpha=0.0)
    ab0 = asb.AeroBuildup(airplane=airplane, op_point=op0).run()
    ab1 = asb.AeroBuildup(airplane=airplane, op_point=op1).run()
    cl0 = float(np.ravel(ab0["CL"])[0])
    cl1 = float(np.ravel(ab1["CL"])[0])
    cla = cl1 - cl0
    alpha_trim = -1.0 + (cl_req - cl0) / cla

    op_trim = asb.OperatingPoint(velocity=velocity, alpha=alpha_trim)
    res_trim = asb.AeroBuildup(airplane=airplane, op_point=op_trim).run()
    d_profile = float(np.ravel(res_trim["D_profile"])[0])

    b = airplane.b_ref
    di_prandtl = (weight**2) / (q * np.pi * b**2 * e0) * ((1.0 + sigma) / 2.0)
    return d_profile + di_prandtl


def find_top_speed_apc(
    airplane: asb.Airplane,
    mass: float = 0.254,
    v_oc: float = 11.1,
    bracket: tuple[float, float] = (30.0, 50.0),
    sigma: float = 0.435,
) -> dict[str, float]:
    """Find level-flight top speed using calibrated APC polar and biplane drag.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    mass : float
        All-up mass in kg.
    v_oc : float
        Battery open-circuit voltage in Volts.
    bracket : tuple[float, float]
        Airspeed search bracket in m/s.
    sigma : float
        Prandtl mutual interference factor.

    Returns
    -------
    dict[str, float]
        Dictionary of top speed in m/s and km/h, thrust, drag, rpm, current, and J.
    """
    def net_thrust(v: float) -> float:
        d = level_flight_drag(airplane, v, mass=mass, sigma=sigma)
        t = solve_propulsion_thrust_apc(v, v_oc=v_oc)["thrust"]
        return t - d

    sol = root_scalar(net_thrust, bracket=bracket, method="brentq")
    v_top = float(sol.root)
    prop = solve_propulsion_thrust_apc(v_top, v_oc=v_oc)
    d = level_flight_drag(airplane, v_top, mass=mass, sigma=sigma)

    return {
        "v_top": v_top,
        "v_top_kmh": v_top * 3.6,
        "thrust": prop["thrust"],
        "drag": d,
        "rpm": prop["rpm"],
        "current": prop["current"],
        "J": prop["J"],
    }


def find_stall_speed(
    airplane: asb.Airplane,
    mass: float = 0.254,
    sigma: float = 0.435,
    cl_max_isolated: float = 0.922,
) -> dict[str, float]:
    """Compute stall speed accounting for mass and mutual downwash CL reduction.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    mass : float
        All-up mass in kg.
    sigma : float
        Prandtl mutual interference factor.
    cl_max_isolated : float
        Airframe maximum lift coefficient in isolation.

    Returns
    -------
    dict[str, float]
        Dictionary of stall speed in m/s and km/h, CL_max, and CLa ratio.
    """
    weight = mass * 9.80665
    rho = 1.225
    s = airplane.s_ref

    a0 = 2.0 * np.pi
    ar_panel = (airplane.b_ref**2) / (s / 2.0)
    e0 = 0.90
    cla_ratio = (1.0 + a0 / (np.pi * ar_panel * e0)) / (
        1.0 + a0 * (1.0 + sigma) / (np.pi * ar_panel * e0)
    )
    cl_max_bi = cl_max_isolated * cla_ratio
    v_stall = float(np.sqrt(2.0 * weight / (rho * s * cl_max_bi)))

    return {
        "v_stall": v_stall,
        "v_stall_kmh": v_stall * 3.6,
        "cl_max": cl_max_bi,
        "cla_ratio": cla_ratio,
        "cl_max_isolated": cl_max_isolated,
    }


def build_aileron_airplanes(
    delta_a_deg: float = 12.0,
) -> dict[str, asb.Airplane]:
    """Construct monoplane and biplane models with equivalent aileron area.

    Parameters
    ----------
    delta_a_deg : float
        Aileron deflection throw in degrees.

    Returns
    -------
    dict[str, asb.Airplane]
        Dictionary containing 'monoplane', 'biplane_4ail', and 'biplane_2ail'.
    """
    # Monoplane baseline
    b_m = 0.622
    c_r_m = 0.133
    c_t_m = 0.087
    s_m = 0.068485
    sweep_m = 5.0
    dih_m = 2.5

    def chord_m(y: float) -> float:
        return c_r_m - (c_r_m - c_t_m) * (y / (b_m / 2.0))

    y_in_m = 0.50 * (b_m / 2.0)
    y_out_m = 0.95 * (b_m / 2.0)
    x_in_m = y_in_m * np.tan(np.radians(sweep_m))
    x_out_m = y_out_m * np.tan(np.radians(sweep_m))
    x_tip_m = (b_m / 2.0) * np.tan(np.radians(sweep_m))
    z_in_m = y_in_m * np.tan(np.radians(dih_m))
    z_out_m = y_out_m * np.tan(np.radians(dih_m))
    z_tip_m = (b_m / 2.0) * np.tan(np.radians(dih_m))

    wing_mono = asb.Wing(
        name="Monoplane Wing",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.0, 0.0, 0.0], chord=c_r_m, airfoil=asb.Airfoil("naca2404")),
            asb.WingXSec(
                xyz_le=[x_in_m, y_in_m, z_in_m],
                chord=chord_m(y_in_m),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.75)],
            ),
            asb.WingXSec(
                xyz_le=[x_out_m, y_out_m, z_out_m],
                chord=chord_m(y_out_m),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.75)],
            ),
            asb.WingXSec(xyz_le=[x_tip_m, b_m / 2.0, z_tip_m], chord=c_t_m, airfoil=asb.Airfoil("naca2404")),
        ],
    )

    # Empennage and fuselage
    b_htail = 0.213
    c_r_h = 0.060
    c_t_h = 0.037
    x_h_le = 0.28325
    x_tip_h = (b_htail / 2.0) * np.tan(np.radians(8.0))
    htail = asb.Wing(
        name="Horizontal Tail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[x_h_le, 0.0, 0.02], chord=c_r_h, airfoil=asb.Airfoil("naca0008")),
            asb.WingXSec(xyz_le=[x_h_le + x_tip_h, b_htail / 2.0, 0.02], chord=c_t_h, airfoil=asb.Airfoil("naca0008")),
        ],
    )

    b_vtail = 0.088
    c_r_v = 0.065
    c_t_v = 0.032
    x_v_le = x_h_le - 0.005
    x_tip_v = b_vtail * np.tan(np.radians(20.0))
    vtail = asb.Wing(
        name="Vertical Tail",
        symmetric=False,
        xsecs=[
            asb.WingXSec(xyz_le=[x_v_le, 0.0, 0.02], chord=c_r_v, airfoil=asb.Airfoil("naca0008")),
            asb.WingXSec(xyz_le=[x_v_le + x_tip_v, 0.0, 0.02 + b_vtail], chord=c_t_v, airfoil=asb.Airfoil("naca0008")),
        ],
    )

    fuse = asb.Fuselage(
        name="Fuselage",
        xsecs=[
            asb.FuselageXSec(xyz_c=[-0.100, 0.0, 0.000], width=0.020, height=0.020, shape=4),
            asb.FuselageXSec(xyz_c=[-0.070, 0.0, 0.000], width=0.045, height=0.055, shape=4),
            asb.FuselageXSec(xyz_c=[ 0.000, 0.0, 0.010], width=0.048, height=0.075, shape=4),
            asb.FuselageXSec(xyz_c=[ 0.060, 0.0, 0.020], width=0.048, height=0.085, shape=4),
            asb.FuselageXSec(xyz_c=[ 0.150, 0.0, 0.010], width=0.045, height=0.080, shape=4),
            asb.FuselageXSec(xyz_c=[ 0.250, 0.0, 0.010], width=0.035, height=0.060, shape=4),
            asb.FuselageXSec(xyz_c=[ 0.350, 0.0, 0.015], width=0.020, height=0.035, shape=4),
            asb.FuselageXSec(xyz_c=[ 0.382, 0.0, 0.020], width=0.010, height=0.025, shape=4),
        ],
    )

    airplane_mono = asb.Airplane(
        name="FT Mighty Mini Mustang Monoplane",
        xyz_ref=[0.025, 0.0, 0.0],
        wings=[wing_mono, htail, vtail],
        fuselages=[fuse],
        s_ref=s_m,
        c_ref=wing_mono.mean_aerodynamic_chord(),
        b_ref=b_m,
    )

    # Biplane geometries
    b_b = 0.440
    gap_b = 0.095
    s_b = s_m
    taper_b = 0.087 / 0.133
    c_r_b = (s_b / 2.0) / (b_b / 2.0 * (1.0 + taper_b))
    c_t_b = c_r_b * taper_b

    def chord_b(y: float) -> float:
        return c_r_b - (c_r_b - c_t_b) * (y / (b_b / 2.0))

    y_in_b = 0.50 * (b_b / 2.0)
    y_out_b = 0.95 * (b_b / 2.0)
    x_in_b = y_in_b * np.tan(np.radians(5.0))
    x_out_b = y_out_b * np.tan(np.radians(5.0))
    x_tip_b = (b_b / 2.0) * np.tan(np.radians(5.0))

    # 4-aileron biplane (both wings, cf/c = 0.25)
    wing_lower_4ail = asb.Wing(
        name="Lower Wing 4-ail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.0, 0.0, 0.0], chord=c_r_b, airfoil=asb.Airfoil("naca2404")),
            asb.WingXSec(
                xyz_le=[x_in_b, y_in_b, 0.0],
                chord=chord_b(y_in_b),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.75)],
            ),
            asb.WingXSec(
                xyz_le=[x_out_b, y_out_b, 0.0],
                chord=chord_b(y_out_b),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.75)],
            ),
            asb.WingXSec(xyz_le=[x_tip_b, b_b / 2.0, 0.0], chord=c_t_b, airfoil=asb.Airfoil("naca2404")),
        ],
    )

    wing_upper_4ail = asb.Wing(
        name="Upper Wing 4-ail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.0, 0.0, gap_b], chord=c_r_b, airfoil=asb.Airfoil("naca2404")),
            asb.WingXSec(
                xyz_le=[x_in_b, y_in_b, gap_b],
                chord=chord_b(y_in_b),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.75)],
            ),
            asb.WingXSec(
                xyz_le=[x_out_b, y_out_b, gap_b],
                chord=chord_b(y_out_b),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.75)],
            ),
            asb.WingXSec(xyz_le=[x_tip_b, b_b / 2.0, gap_b], chord=c_t_b, airfoil=asb.Airfoil("naca2404")),
        ],
    )

    airplane_bi_4ail = asb.Airplane(
        name="FT Mighty Mini Mustang Biplane 4-Aileron",
        xyz_ref=[0.025, 0.0, 0.0],
        wings=[wing_lower_4ail, wing_upper_4ail, htail, vtail],
        fuselages=[fuse],
        s_ref=s_b,
        c_ref=wing_lower_4ail.mean_aerodynamic_chord(),
        b_ref=b_b,
    )

    # 2-aileron biplane (lower wing only, cf/c = 0.50)
    wing_lower_2ail = asb.Wing(
        name="Lower Wing 2-ail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.0, 0.0, 0.0], chord=c_r_b, airfoil=asb.Airfoil("naca2404")),
            asb.WingXSec(
                xyz_le=[x_in_b, y_in_b, 0.0],
                chord=chord_b(y_in_b),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.50)],
            ),
            asb.WingXSec(
                xyz_le=[x_out_b, y_out_b, 0.0],
                chord=chord_b(y_out_b),
                airfoil=asb.Airfoil("naca2404"),
                control_surfaces=[asb.ControlSurface(name="aileron", symmetric=False, deflection=delta_a_deg, hinge_point=0.50)],
            ),
            asb.WingXSec(xyz_le=[x_tip_b, b_b / 2.0, 0.0], chord=c_t_b, airfoil=asb.Airfoil("naca2404")),
        ],
    )

    wing_upper_noail = asb.Wing(
        name="Upper Wing No-ail",
        symmetric=True,
        xsecs=[
            asb.WingXSec(xyz_le=[0.0, 0.0, gap_b], chord=c_r_b, airfoil=asb.Airfoil("naca2404")),
            asb.WingXSec(xyz_le=[x_tip_b, b_b / 2.0, gap_b], chord=c_t_b, airfoil=asb.Airfoil("naca2404")),
        ],
    )

    airplane_bi_2ail = asb.Airplane(
        name="FT Mighty Mini Mustang Biplane 2-Aileron",
        xyz_ref=[0.025, 0.0, 0.0],
        wings=[wing_lower_2ail, wing_upper_noail, htail, vtail],
        fuselages=[fuse],
        s_ref=s_b,
        c_ref=wing_lower_2ail.mean_aerodynamic_chord(),
        b_ref=b_b,
    )

    return {
        "monoplane": airplane_mono,
        "biplane_4ail": airplane_bi_4ail,
        "biplane_2ail": airplane_bi_2ail,
    }


def evaluate_roll_performance(
    airplane: asb.Airplane,
    velocity: float,
    b_ref: float,
    delta_a_deg: float = 12.0,
) -> dict[str, float]:
    """Compute linear stability derivatives and nonlinear roll trim rate.

    Parameters
    ----------
    airplane : asb.Airplane
        Aircraft model with ailerons deflected.
    velocity : float
        Flight speed in m/s.
    b_ref : float
        Reference wingspan in meters.
    delta_a_deg : float
        Aileron deflection angle in degrees.

    Returns
    -------
    dict[str, float]
        Dictionary of Clp, Cl_da, linear roll rate [deg/s], and nonlinear roll rate [deg/s].
    """
    # 1. Damping at delta_a = 0
    ap_0 = airplane.deepcopy()
    for w in ap_0.wings:
        for xs in w.xsecs:
            if xs.control_surfaces:
                for cs in xs.control_surfaces:
                    cs.deflection = 0.0

    op_trim = asb.OperatingPoint(velocity=velocity, alpha=0.0)
    res_0 = asb.AeroBuildup(airplane=ap_0, op_point=op_trim).run_with_stability_derivatives(p=True)
    clp = float(np.ravel(res_0["Clp"])[0])

    # 2. Control power at delta_a = 1.0 deg
    ap_eps = airplane.deepcopy()
    for w in ap_eps.wings:
        for xs in w.xsecs:
            if xs.control_surfaces:
                for cs in xs.control_surfaces:
                    cs.deflection = 1.0
    res_eps = asb.AeroBuildup(airplane=ap_eps, op_point=op_trim).run()
    cl_eps = float(np.ravel(res_eps["Cl"])[0])
    cl_da = cl_eps / np.radians(1.0)

    # Linear roll rate
    delta_a_rad = np.radians(delta_a_deg)
    pb_2v_lin = - (cl_da * delta_a_rad) / clp
    p_lin_deg = float(np.degrees(pb_2v_lin * (2.0 * velocity / b_ref)))

    # 3. Direct nonlinear roll trim
    def res_p(p_rad: float) -> float:
        op = asb.OperatingPoint(velocity=velocity, alpha=0.0, p=p_rad)
        ab = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        return float(np.ravel(ab["Cl"])[0])

    sol = root_scalar(res_p, bracket=[-80.0, 0.0], method="brentq")
    p_nonlin_rad = float(sol.root)
    p_nonlin_deg = float(np.degrees(p_nonlin_rad))

    return {
        "clp": clp,
        "cl_da": cl_da,
        "pb_2v_lin": pb_2v_lin,
        "p_lin_deg": abs(p_lin_deg),
        "p_nonlin_deg": abs(p_nonlin_deg),
        "p_nonlin_rad": abs(p_nonlin_rad),
    }

