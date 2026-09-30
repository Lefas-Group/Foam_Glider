import aerosandbox as asb
import aerosandbox.numpy as np


def glide_polar(
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


def evaluate_fidelities(
    airplane: asb.Airplane,
    velocity: float,
    alpha: float,
) -> dict:
    """Compare aerodynamic predictions across VLM, AeroBuildup, and LiftingLine."""
    op = asb.OperatingPoint(velocity=velocity, alpha=alpha)
    ab = asb.AeroBuildup(airplane=airplane, op_point=op).run()
    vlm = asb.VortexLatticeMethod(airplane=airplane, op_point=op, verbose=False).run()
    ll = asb.LiftingLine(airplane=airplane, op_point=op, verbose=False).run()

    return {
        "AeroBuildup": {
            "CL": float(ab["CL"][0]),
            "CD": float(ab["CD"][0]),
            "LD": float(ab["CL"][0] / ab["CD"][0]),
        },
        "VLM": {
            "CL": float(vlm["CL"]),
            "CD": float(vlm["CD"]),
            "LD": float(vlm["CL"] / vlm["CD"]),
        },
        "LiftingLine": {
            "CL": float(ll["CL"]),
            "CD": float(ll["CD"]),
            "LD": float(ll["CL"] / ll["CD"]),
        },
    }
