"""Analysis tools for the FT Mighty Mini Mustang MKR2."""

import aerosandbox.numpy as np


def mass_breakdown(
    wing_style: str = "flat",
    sigma: float = 0.3487,
    m_motor: float = 0.029,
    m_esc: float = 0.018,
    m_servos: float = 0.022,
    m_rx: float = 0.005,
    m_hardware: float = 0.018,
    m_glue: float = 0.016,
) -> dict:
    """
    Compute dry mass breakdown of the FT Mighty Mini Mustang.

    Parameters
    ----------
    wing_style : str
        'flat' for single-layer flat plate foam wing, 'folded' for FT folded airfoil.
    sigma : float
        Areal density of Maker Foam (kg/m^2).
    m_motor : float
        Motor mass (kg).
    m_esc : float
        ESC mass (kg).
    m_servos : float
        Total mass of four 5 g class servos (kg).
    m_rx : float
        Receiver mass (kg).
    m_hardware : float
        Propeller, control horns, pushrods, firewall, fasteners (kg).
    m_glue : float
        Hot melt adhesive used for assembly (kg).

    Returns
    -------
    dict
        Component masses and totals in grams.
    """
    if wing_style == "folded":
        s_wing_foam = 1.8 * 0.0742046
    else:
        s_wing_foam = 0.0742046

    # Component areas from plan
    s_htail_foam = 0.0144
    s_vtail_foam = 0.0072
    s_fuse_foam = 0.0873 + 0.0220 + 0.0150 + 0.0100 + 0.0200  # shell + turtle/canopy + scoop + formers + pod

    s_total_foam = s_wing_foam + s_htail_foam + s_vtail_foam + s_fuse_foam

    m_foam_g = s_total_foam * sigma * 1e3
    m_elec_g = (m_motor + m_esc + m_servos + m_rx) * 1e3
    m_hw_g = m_hardware * 1e3
    m_glue_g = m_glue * 1e3

    m_dry_g = m_foam_g + m_elec_g + m_hw_g + m_glue_g

    return {
        "foam_area_m2": s_total_foam,
        "foam_g": m_foam_g,
        "electronics_g": m_elec_g,
        "hardware_g": m_hw_g,
        "glue_g": m_glue_g,
        "dry_total_g": m_dry_g,
        "delta_g": m_dry_g - 156.0,
    }
