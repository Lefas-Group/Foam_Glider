import aerosandbox as asb
import aerosandbox.numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import root_scalar


def check_reconstruction(airplane, mass_props, cg_aft_le):
    """
    Evaluate reconstructed aircraft dimensions against published specifications.

    Returns dict of target dicts with actual values, tolerances, and error ratios.
    """
    targets = {
        "Wingspan": {
            "target": 0.914,
            "actual": float(airplane.wings[0].span(include_centerline_distance=True)),
            "tol": 0.005,
            "unit": "m",
        },
        "Length": {
            "target": 1.295,
            "actual": float(airplane.fuselages[0].length()),
            "tol": 0.010,
            "unit": "m",
        },
        "Dry mass": {
            "target": 1.361,
            "actual": float(mass_props.mass),
            "tol": 0.050,
            "unit": "kg",
        },
        "CG aft LE": {
            "target": 0.0317,
            "actual": float(cg_aft_le),
            "tol": 0.0063,
            "unit": "m",
        },
    }
    for k, v in targets.items():
        v["abs_err"] = abs(v["actual"] - v["target"])
        v["rel_err"] = v["abs_err"] / v["target"]
        v["tol_frac"] = v["abs_err"] / v["tol"]
    return targets


def compute_stall_speed(airplane, mass, altitude=0.0):
    """
    Compute self-consistent aerodynamic stall speed and CL_max for a given aircraft and mass.
    """
    atm = asb.Atmosphere(altitude=altitude)
    rho = float(atm.density())
    g = 9.80665
    W = mass * g
    wing_area = airplane.s_ref

    def residual(V_guess):
        alphas = np.linspace(10.0, 18.0, 81)
        op = asb.OperatingPoint(velocity=V_guess, alpha=alphas, atmosphere=atm)
        res = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        cl_max = np.max(res["CL"])
        lift_max = 0.5 * rho * V_guess**2 * wing_area * cl_max
        return lift_max - W

    res = root_scalar(residual, bracket=[8.0, 18.0], xtol=1e-4)
    v_stall = res.root

    alphas = np.linspace(10.0, 18.0, 81)
    op = asb.OperatingPoint(velocity=v_stall, alpha=alphas, atmosphere=atm)
    res = asb.AeroBuildup(airplane=airplane, op_point=op).run()
    idx = np.argmax(res["CL"])

    return {
        "V_stall": float(v_stall),
        "CL_max": float(res["CL"][idx]),
        "alpha_stall_deg": float(alphas[idx]),
        "wing_loading": float(W / wing_area),
        "mass": float(mass),
        "weight": float(W),
    }


def build_aero_surrogate(airplane, v_range=(5.0, 30.0), alpha_range=(-2.0, 20.0), n_v=26, n_a=23):
    """
    Build 2D regular-grid interpolators for CL and CD over airspeed and angle of attack.
    """
    V_vals = np.linspace(v_range[0], v_range[1], n_v)
    a_vals = np.linspace(alpha_range[0], alpha_range[1], n_a)
    V_m, a_m = np.meshgrid(V_vals, a_vals)
    op = asb.OperatingPoint(velocity=V_m.flatten(), alpha=a_m.flatten())
    res = asb.AeroBuildup(airplane=airplane, op_point=op).run()

    CL_g = res["CL"].reshape(V_m.shape)
    CD_g = res["CD"].reshape(V_m.shape)

    cl_fn = RegularGridInterpolator((a_vals, V_vals), CL_g, bounds_error=False, fill_value=None)
    cd_fn = RegularGridInterpolator((a_vals, V_vals), CD_g, bounds_error=False, fill_value=None)
    return cl_fn, cd_fn


def simulate_hand_launch(cl_fn, cd_fn, airplane, mass, V0, gamma0_deg=0.0, alpha_deg=10.0,
                         T_static=22.0, V_exit=90.0, h0=1.7, dt=0.02, t_final=2.5):
    """
    Simulate 2D point-mass hand launch trajectory under gravity, aero, and EDF thrust.
    """
    g = 9.80665
    W = mass * g
    wing_area = airplane.s_ref
    rho = 1.225

    t = 0.0
    V = V0
    gamma = np.radians(gamma0_deg)
    alpha = np.radians(alpha_deg)
    x = 0.0
    z = h0

    t_hist, x_hist, z_hist, V_hist, gamma_hist = [t], [x], [z], [V], [gamma]

    while t < t_final and z > 0:
        T = max(0.0, T_static * (1.0 - V / V_exit))
        a_deg = np.degrees(alpha)
        cl_val = float(cl_fn([[a_deg, V]])[0])
        cd_val = float(cd_fn([[a_deg, V]])[0])

        q = 0.5 * rho * V**2
        L = q * wing_area * cl_val
        D = q * wing_area * cd_val

        dV_dt = (T * np.cos(alpha) - D - W * np.sin(gamma)) / mass
        dgamma_dt = (L + T * np.sin(alpha) - W * np.cos(gamma)) / (mass * V)

        V += dV_dt * dt
        gamma += dgamma_dt * dt
        x += V * np.cos(gamma) * dt
        z += V * np.sin(gamma) * dt
        t += dt

        t_hist.append(t)
        x_hist.append(x)
        z_hist.append(z)
        V_hist.append(V)
        gamma_hist.append(gamma)

    return {
        "t": np.array(t_hist),
        "x": np.array(x_hist),
        "z": np.array(z_hist),
        "V": np.array(V_hist),
        "gamma": np.array(gamma_hist),
        "z_min": min(z_hist),
        "crashed": z <= 0,
    }


def find_min_throw_speed(cl_fn, cd_fn, airplane, mass, gamma0_deg=0.0, alpha_deg=10.0,
                         T_static=22.0, V_exit=90.0, h0=1.7, z_min_threshold=0.0, dt=0.02):
    """
    Find minimum throw speed V0 to avoid ground impact during launch.
    """
    v_low = 3.0
    v_high = 20.0
    for _ in range(16):
        v_mid = 0.5 * (v_low + v_high)
        res = simulate_hand_launch(cl_fn, cd_fn, airplane, mass, v_mid,
                                   gamma0_deg=gamma0_deg, alpha_deg=alpha_deg,
                                   T_static=T_static, V_exit=V_exit, h0=h0, dt=dt)
        if res["z_min"] < z_min_threshold or res["crashed"]:
            v_low = v_mid
        else:
            v_high = v_mid
    return v_high

