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
