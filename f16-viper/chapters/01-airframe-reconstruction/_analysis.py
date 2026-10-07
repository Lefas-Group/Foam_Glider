##### Imports

import aerosandbox as asb
import aerosandbox.numpy as np

##### Target verification

def evaluate_airframe_targets(airplane, mass_props, wing_break_le_x):
    """
    Evaluate reconstructed airframe metrics against published brief targets.
    Returns dictionary with target values, reconstructed values, errors, and pass status.
    """
    span_val = float(airplane.wings[0].span(include_centerline_distance=True))
    length_val = float(airplane.fuselages[0].length())
    mass_val = float(mass_props.mass)
    cg_val = float(mass_props.x_cg - wing_break_le_x)

    targets = {
        "Wing span": {
            "target": 0.914,
            "tol_pct": 1.0,
            "value": span_val,
            "unit": "m",
            "scale": 1000.0,
            "unit_disp": "mm",
            "err_pct": (span_val - 0.914) / 0.914 * 100.0,
        },
        "Length": {
            "target": 1.295,
            "tol_pct": 2.0,
            "value": length_val,
            "unit": "m",
            "scale": 1000.0,
            "unit_disp": "mm",
            "err_pct": (length_val - 1.295) / 1.295 * 100.0,
        },
        "Dry weight": {
            "target": 1.361,
            "tol_pct": 6.0,
            "value": mass_val,
            "unit": "kg",
            "scale": 1000.0,
            "unit_disp": "g",
            "err_pct": (mass_val - 1.361) / 1.361 * 100.0,
        },
        "CG aft LE": {
            "target": 0.0315,
            "tol_pct": (0.0065 / 0.0315) * 100.0,  # [25, 38] mm -> 31.5 +/- 6.5 mm = +/-20.6%
            "value": cg_val,
            "unit": "m",
            "scale": 1000.0,
            "unit_disp": "mm",
            "err_pct": (cg_val - 0.0315) / 0.0315 * 100.0,
            "min_val": 0.025,
            "max_val": 0.038,
        },
    }

    for k, v in targets.items():
        v["passed"] = abs(v["err_pct"]) <= v["tol_pct"]

    return targets
