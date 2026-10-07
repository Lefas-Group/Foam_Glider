import aerosandbox as asb
import aerosandbox.numpy as np


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
