import aerosandbox as asb
import aerosandbox.numpy as np
from scipy.optimize import root_scalar


def find_trim_speed(
    airplane: asb.Airplane,
    mass: float = 0.222,
    alpha: float = 2.0,
    bracket: tuple[float, float] = (5.0, 35.0),
) -> float:
    """Find level flight speed where lift equals weight at a given angle of attack.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    mass : float
        All-up mass in kg.
    alpha : float
        Angle of attack in degrees.
    bracket : tuple[float, float]
        Airspeed search bracket in m/s.

    Returns
    -------
    float
        Trim velocity in m/s.
    """
    weight = mass * 9.80665

    def lift_residual(v: float) -> float:
        op = asb.OperatingPoint(velocity=v, alpha=alpha)
        res = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        return float(np.ravel(res["L"])[0]) - weight

    sol = root_scalar(lift_residual, bracket=bracket, method="brentq")
    return float(sol.root)


def evaluate_stability(
    airplane: asb.Airplane,
    velocity: float,
    alpha: float = 2.0,
) -> dict[str, float]:
    """Evaluate longitudinal stability derivatives, neutral point, and static margin.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    velocity : float
        Flight speed in m/s.
    alpha : float
        Angle of attack in degrees.

    Returns
    -------
    dict[str, float]
        Dictionary of CL, CD, CLa, Cma, x_np, and static_margin.
    """
    op = asb.OperatingPoint(velocity=velocity, alpha=alpha)
    ab = asb.AeroBuildup(airplane=airplane, op_point=op)
    res = ab.run_with_stability_derivatives(alpha=True, beta=False, p=False, q=False, r=False)

    x_np = float(np.ravel(res["x_np"])[0])
    x_cg = airplane.xyz_ref[0]
    c_ref = airplane.c_ref
    sm = (x_np - x_cg) / c_ref

    return {
        "CL": float(np.ravel(res["CL"])[0]),
        "CD": float(np.ravel(res["CD"])[0]),
        "CLa": float(np.ravel(res["CLa"])[0]),
        "Cma": float(np.ravel(res["Cma"])[0]),
        "x_np": x_np,
        "static_margin": sm,
    }


def level_flight_drag(
    airplane: asb.Airplane,
    velocity: float,
    mass: float = 0.222,
) -> float:
    """Compute level flight aerodynamic drag where lift equals weight.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    velocity : float
        Flight speed in m/s.
    mass : float
        All-up mass in kg.

    Returns
    -------
    float
        Aerodynamic drag in Newtons.
    """
    weight = mass * 9.80665

    def lift_residual(a: float) -> float:
        op = asb.OperatingPoint(velocity=velocity, alpha=a)
        res = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        return float(np.ravel(res["L"])[0]) - weight

    sol = root_scalar(lift_residual, bracket=[-6.0, 10.0], method="brentq")
    op = asb.OperatingPoint(velocity=velocity, alpha=sol.root)
    res = asb.AeroBuildup(airplane=airplane, op_point=op).run()
    return float(np.ravel(res["D"])[0])


def solve_propulsion_thrust(
    velocity: float,
    v_oc: float = 11.1,
    kv: float = 2300.0,
    r_tot: float = 0.145,
    i0: float = 0.9,
    diameter: float = 6.0 * 0.0254,
    rho: float = 1.225,
) -> dict[str, float]:
    """Compute coupled motor-propeller operating point and thrust.

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
        return float(np.maximum(0.108 - 0.045 * J - 0.115 * J**2, 0.0))

    def cp(J: float) -> float:
        return float(np.maximum(0.058 - 0.012 * J - 0.065 * J**2, 0.005))

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


def find_top_speed(
    airplane: asb.Airplane,
    mass: float = 0.222,
    v_oc: float = 11.1,
    bracket: tuple[float, float] = (30.0, 50.0),
) -> dict[str, float]:
    """Find level-flight top speed where available thrust equals aerodynamic drag.

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

    Returns
    -------
    dict[str, float]
        Dictionary of top speed in m/s and km/h, thrust, drag, rpm, and current.
    """
    def net_thrust(v: float) -> float:
        d = level_flight_drag(airplane, v, mass=mass)
        t = solve_propulsion_thrust(v, v_oc=v_oc)["thrust"]
        return t - d

    sol = root_scalar(net_thrust, bracket=bracket, method="brentq")
    v_top = float(sol.root)
    prop = solve_propulsion_thrust(v_top, v_oc=v_oc)
    d = level_flight_drag(airplane, v_top, mass=mass)

    return {
        "v_top": v_top,
        "v_top_kmh": v_top * 3.6,
        "thrust": prop["thrust"],
        "drag": d,
        "rpm": prop["rpm"],
        "current": prop["current"],
    }

