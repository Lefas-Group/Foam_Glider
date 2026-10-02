"""Analysis tools for the FT Mighty Mini Mustang MKR2."""

import aerosandbox as asb
import aerosandbox.numpy as np
import numpy as _np


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


def compute_stall_characteristics(
    airplane: asb.Airplane,
    mass_kg: float = 0.2672,
    altitude: float = 0.0,
    tol: float = 1e-4,
    max_iter: int = 25,
) -> dict:
    """
    Compute level-flight stall speed and aerodynamic properties at stall.

    Iterates to match level flight stall speed with Reynolds number effects
    on maximum lift coefficient.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.
    mass_kg : float
        Total flying mass in kg.
    altitude : float
        Flight altitude in meters.
    tol : float
        Convergence tolerance on stall speed in m/s.
    max_iter : int
        Maximum number of iterations.

    Returns
    -------
    dict
        V_stall, V_stall_mph, CL_max, alpha_stall_deg, CD_at_stall,
        Cm_at_stall, wing_loading_g_dm2, weight_N, mass_g, iterations
    """
    W = mass_kg * 9.80665
    rho = float(asb.Atmosphere(altitude=altitude).density())
    S = float(airplane.s_ref)

    V = 8.0
    diff = 1.0
    it = 0
    while diff > tol and it < max_iter:
        it += 1
        alphas = _np.linspace(0, 15, 151)
        op = asb.OperatingPoint(atmosphere=asb.Atmosphere(altitude=altitude), velocity=V, alpha=alphas)
        aero = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        CL = aero["CL"]

        dCL = _np.diff(CL) / _np.diff(alphas)
        stall_idx = _np.where(dCL < 0)[0]
        if len(stall_idx) > 0:
            idx = stall_idx[0]
        else:
            idx = int(_np.argmax(CL))

        cl_max = float(CL[idx])
        alpha_max = float(alphas[idx])
        V_new = float(_np.sqrt(2 * W / (rho * S * cl_max)))
        diff = abs(V_new - V)
        V = V_new

    cd_at_stall = float(aero["CD"][idx])
    cm_at_stall = float(aero["Cm"][idx])

    return {
        "V_stall": V,
        "V_stall_mph": V * 2.23694,
        "V_stall_kmh": V * 3.6,
        "CL_max": cl_max,
        "alpha_stall_deg": alpha_max,
        "CD_at_stall": cd_at_stall,
        "Cm_at_stall": cm_at_stall,
        "wing_loading_g_dm2": (mass_kg * 1e3) / (S * 100.0),
        "wing_loading_lb_ft2": (mass_kg * 2.20462) / (S * 10.7639),
        "weight_N": W,
        "mass_g": mass_kg * 1e3,
        "iterations": it,
    }


def compute_geometry_proportions(airplane: asb.Airplane) -> dict:
    """
    Compute airframe geometry proportions and tail volume coefficients.

    Parameters
    ----------
    airplane : asb.Airplane
        The aircraft model.

    Returns
    -------
    dict
        Geometric dimensions, area ratios, span ratios, moment arms,
        and tail volume coefficients.
    """
    wing = None
    htail = None
    vtail = None
    fuse = airplane.fuselages[0] if len(airplane.fuselages) > 0 else None

    for w in airplane.wings:
        name_lower = w.name.lower()
        if "vert" in name_lower or "fin" in name_lower:
            vtail = w
        elif "horiz" in name_lower or "stab" in name_lower:
            htail = w
        else:
            wing = w

    b_w = float(wing.span())
    b_w_proj = float(wing.span("xy"))
    s_w = float(wing.area())
    ar_w = float(wing.aspect_ratio())
    c_mac_w = float(wing.mean_aerodynamic_chord())
    c_root_w = float(wing.xsecs[0].chord)
    c_tip_w = float(wing.xsecs[-1].chord)
    taper_w = c_tip_w / c_root_w

    # Wing aerodynamic center (approx quarter-chord of MAC)
    y_mac_w = (b_w / 6) * (1 + 2 * taper_w) / (1 + taper_w)
    x_le_root_w = wing.xsecs[0].xyz_le[0]
    x_le_tip_w = wing.xsecs[-1].xyz_le[0]
    x_le_mac_w = x_le_root_w + (x_le_tip_w - x_le_root_w) * (y_mac_w / (b_w / 2))
    x_ac_w = x_le_mac_w + 0.25 * c_mac_w

    # Horizontal tail
    b_h = float(htail.span())
    s_h = float(htail.area())
    ar_h = float(htail.aspect_ratio())
    c_mac_h = float(htail.mean_aerodynamic_chord())
    c_root_h = float(htail.xsecs[0].chord)
    c_tip_h = float(htail.xsecs[-1].chord)
    taper_h = c_tip_h / c_root_h

    y_mac_h = (b_h / 6) * (1 + 2 * taper_h) / (1 + taper_h)
    x_le_root_h = htail.xsecs[0].xyz_le[0]
    x_le_tip_h = htail.xsecs[-1].xyz_le[0]
    x_le_mac_h = x_le_root_h + (x_le_tip_h - x_le_root_h) * (y_mac_h / (b_h / 2))
    x_ac_h = x_le_mac_h + 0.25 * c_mac_h

    l_h = x_ac_h - x_ac_w
    vh = (s_h * l_h) / (s_w * c_mac_w)

    # Vertical tail
    b_v = float(vtail.span())
    s_v = float(vtail.area())
    ar_v = float(vtail.aspect_ratio())
    c_mac_v = float(vtail.mean_aerodynamic_chord())
    c_root_v = float(vtail.xsecs[0].chord)
    c_tip_v = float(vtail.xsecs[-1].chord)
    taper_v = c_tip_v / c_root_v

    z_mac_v = (b_v / 3) * (1 + 2 * taper_v) / (1 + taper_v)
    x_le_root_v = vtail.xsecs[0].xyz_le[0]
    x_le_tip_v = vtail.xsecs[-1].xyz_le[0]
    x_le_mac_v = x_le_root_v + (x_le_tip_v - x_le_root_v) * (z_mac_v / b_v)
    x_ac_v = x_le_mac_v + 0.25 * c_mac_v

    l_v = x_ac_v - x_ac_w
    vv = (s_v * l_v) / (s_w * b_w)

    # Fuselage
    l_fuse = float(fuse.length()) if fuse else 0.0

    return {
        "b_w": b_w,
        "b_w_proj": b_w_proj,
        "s_w": s_w,
        "ar_w": ar_w,
        "c_mac_w": c_mac_w,
        "c_root_w": c_root_w,
        "c_tip_w": c_tip_w,
        "taper_w": taper_w,
        "x_ac_w": x_ac_w,
        "b_h": b_h,
        "s_h": s_h,
        "ar_h": ar_h,
        "c_mac_h": c_mac_h,
        "x_ac_h": x_ac_h,
        "l_h": l_h,
        "vh": vh,
        "sh_sw": s_h / s_w,
        "bh_bw": b_h / b_w,
        "b_v": b_v,
        "s_v": s_v,
        "ar_v": ar_v,
        "c_mac_v": c_mac_v,
        "x_ac_v": x_ac_v,
        "l_v": l_v,
        "vv": vv,
        "sv_sw": s_v / s_w,
        "bv_bw": b_v / b_w,
        "l_fuse": l_fuse,
        "lfuse_bw": l_fuse / b_w if b_w > 0 else 0.0,
    }


