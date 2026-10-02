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
