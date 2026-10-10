import matplotlib.pyplot as plt
import aerosandbox.numpy as np

def evaluate_targets(airplane, mass_props, wing_x_le):
    """
    Evaluate model geometry and mass properties against brief targets.
    """
    target_span = 1.537
    target_cg = 0.064
    
    actual_span = float(airplane.wings[0].span(type="y"))
    actual_cg = float(mass_props.x_cg - wing_x_le)
    
    span_err_pct = (actual_span - target_span) / target_span * 100
    cg_err_pct = (actual_cg - target_cg) / target_cg * 100
    
    return {
        "Wingspan [m]": {"target": target_span, "actual": actual_span, "err_pct": span_err_pct},
        "CG aft LE [m]": {"target": target_cg, "actual": actual_cg, "err_pct": cg_err_pct},
    }

def plot_target_errors(target_results, ax=None):
    """
    Plot bar chart of percentage error against targets.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 3))
    
    names = list(target_results.keys())
    errors = [target_results[k]["err_pct"] for k in names]
    
    bars = ax.barh(names, errors, color=["#2b5c8f" if abs(e) < 5 else "#d95f02" for e in errors], height=0.4)
    ax.axvline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.set_xlabel("Relative error (%)")
    ax.set_xlim(-5, 5)
    
    for bar, err in zip(bars, errors):
        offset = 0.2 if err >= 0 else -0.2
        ha = "left" if err >= 0 else "right"
        ax.text(err + offset, bar.get_y() + bar.get_height() / 2, f"{err:+.2f}%", va="center", ha=ha, fontsize=9)
    
    ax.grid(True, linestyle=":", alpha=0.5, axis="x")
    return ax

import aerosandbox as asb
import scipy.optimize as so

def compute_stall_characteristics(airplane, mass_props, altitude=0.0):
    """
    Compute stall speed and polar in unaccelerated level flight (L = W).
    """
    atmos = asb.Atmosphere(altitude=altitude)
    rho = float(atmos.density())
    W = float(mass_props.mass * 9.81)
    S = float(airplane.s_ref) if airplane.s_ref is not None else float(airplane.wings[0].area())
    
    def find_cl_max(V):
        alphas = np.linspace(8.0, 13.0, 51)
        op = asb.OperatingPoint(atmosphere=atmos, velocity=V, alpha=alphas)
        aero = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        cls = np.array(aero["CL"])
        i_max = int(np.argmax(cls))
        return float(cls[i_max]), float(alphas[i_max])
    
    def res_fn(V):
        cl_max, _ = find_cl_max(V)
        return V - np.sqrt(2 * W / (rho * S * cl_max))
    
    sol = so.root_scalar(res_fn, bracket=[5.0, 15.0], method="brentq")
    V_stall = float(sol.root)
    cl_max, alpha_stall = find_cl_max(V_stall)
    
    mac = float(airplane.c_ref) if airplane.c_ref is not None else float(airplane.wings[0].mean_aerodynamic_chord())
    op_stall = asb.OperatingPoint(atmosphere=atmos, velocity=V_stall, alpha=alpha_stall)
    reynolds_stall = float(op_stall.reynolds(mac))
    
    alphas_sweep = np.linspace(0.0, 16.0, 65)
    op_sweep = asb.OperatingPoint(atmosphere=atmos, velocity=V_stall, alpha=alphas_sweep)
    aero_sweep = asb.AeroBuildup(airplane=airplane, op_point=op_sweep).run()
    
    return {
        "V_stall": V_stall,
        "cl_max": cl_max,
        "alpha_stall": alpha_stall,
        "reynolds": reynolds_stall,
        "W": W,
        "rho": rho,
        "S": S,
        "mass": float(mass_props.mass),
        "wing_loading_N_m2": W / S,
        "wing_loading_kg_m2": float(mass_props.mass) / S,
        "alphas": alphas_sweep,
        "CL": np.array(aero_sweep["CL"]),
        "CD": np.array(aero_sweep["CD"]),
        "Cm": np.array(aero_sweep["Cm"]),
    }

def plot_stall_polar(stall_data, axs=None):
    """
    Plot lift curve and drag/moment curves at stall speed.
    """
    if axs is None:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5))
    else:
        fig = axs[0].get_figure()
        ax1, ax2 = axs
    
    alphas = stall_data["alphas"]
    CL = stall_data["CL"]
    CD = stall_data["CD"]
    Cm = stall_data["Cm"]
    
    a_st = stall_data["alpha_stall"]
    cl_max = stall_data["cl_max"]
    
    # Panel 1: Lift curve
    ax1.plot(alphas, CL, "b-", lw=2, label="$C_L$")
    ax1.plot(a_st, cl_max, "ro", markersize=6, label=f"$C_{{L,\\max}} = {cl_max:.3f}$")
    ax1.axvline(a_st, color="r", linestyle=":", alpha=0.5)
    ax1.axhline(cl_max, color="r", linestyle=":", alpha=0.5)
    ax1.set_xlabel(r"Angle of attack $\alpha$ [deg]")
    ax1.set_ylabel(r"Lift coefficient $C_L$")
    ax1.set_title("Lift Curve")
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="upper left", frameon=False)
    
    # Panel 2: Drag and Pitching Moment
    ax2.plot(alphas, CD, "g-", lw=2, label="$C_D$")
    ax2.plot(alphas, Cm, "m--", lw=2, label="$C_m$ (ref CG)")
    ax2.axvline(a_st, color="r", linestyle=":", alpha=0.5, label=f"Stall ({a_st:.1f}°)")
    ax2.set_xlabel(r"Angle of attack $\alpha$ [deg]")
    ax2.set_ylabel("Coefficients $C_D, C_m$")
    ax2.set_title("Drag & Moment Curves")
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="lower left", frameon=False)
    
    fig.tight_layout()
    return fig

