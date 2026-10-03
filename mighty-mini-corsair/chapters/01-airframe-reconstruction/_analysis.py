"""Analysis routines for FT Mighty Mini Corsair airframe reconstruction."""

import aerosandbox.numpy as np


def evaluate_targets(wing, mass_props, target_span=0.737, target_mass=0.270, target_cg_x=0.044,
                     tol_span=0.01, tol_mass=0.05, tol_cg_x=0.10):
    """
    Evaluate reconstructed airframe metrics against published targets and tolerances.
    """
    span = float(wing.span(type="y"))
    mass = float(mass_props.mass)
    cg_x = float(mass_props.x_cg)

    span_err = (span - target_span) / target_span
    mass_err = (mass - target_mass) / target_mass
    cg_err = (cg_x - target_cg_x) / target_cg_x

    max_err = max(abs(span_err), abs(mass_err), abs(cg_err))
    all_passed = (
        abs(span_err) <= tol_span and
        abs(mass_err) <= tol_mass and
        abs(cg_err) <= tol_cg_x
    )

    return {
        "span": span,
        "mass": mass,
        "cg_x": cg_x,
        "span_err": span_err,
        "mass_err": mass_err,
        "cg_err": cg_err,
        "max_err": max_err,
        "all_passed": all_passed,
    }
