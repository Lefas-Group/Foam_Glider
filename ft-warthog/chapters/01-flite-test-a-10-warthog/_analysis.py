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

def compute_max_level_speed(airplane, mass_props, propeller_diameter=9.0*0.0254, propeller_pitch=4.5*0.0254, kv=1180.0, voltage=14.8, altitude=0.0):
    """
    Compute maximum level flight speed where thrust available equals level drag.
    """
    atmos = asb.Atmosphere(altitude=altitude)
    rho = float(atmos.density())
    W = float(mass_props.mass * 9.81)
    
    def level_drag(V):
        alphas = np.linspace(-3.0, 8.0, 31)
        op = asb.OperatingPoint(atmosphere=atmos, velocity=V, alpha=alphas)
        aero = asb.AeroBuildup(airplane=airplane, op_point=op).run()
        L = np.array(aero["L"])
        alpha_trim = float(np.interp(W, L, alphas))
        op_trim = asb.OperatingPoint(atmosphere=atmos, velocity=V, alpha=alpha_trim)
        aero_trim = asb.AeroBuildup(airplane=airplane, op_point=op_trim).run()
        return float(aero_trim["D"][0]), alpha_trim, float(aero_trim["CL"][0]), float(aero_trim["CD"][0])
    
    def prop_coefs(J):
        J_c = np.clip(J, 0.0, 0.65)
        CT = np.maximum(0.098 - 0.045 * J_c - 0.215 * J_c**2, 0.0)
        CP = np.maximum(0.043 + 0.015 * J_c - 0.085 * J_c**2, 0.01)
        return CT, CP

    def powertrain_thrust(V):
        def torque_diff(rpm):
            n = rpm / 60.0
            J = V / (n * propeller_diameter)
            CT, CP = prop_coefs(J)
            Q_prop = (CP / (2 * np.pi)) * rho * (n**2) * (propeller_diameter**5)
            E = rpm / kv
            I = np.maximum((voltage - E) / 0.08, 0.0)
            Q_mot = np.maximum((I - 0.8) * 60 / (kv * 2 * np.pi), 0.0)
            return Q_mot - Q_prop

        sol = so.root_scalar(torque_diff, bracket=[5000, 18000], method='brentq')
        rpm = sol.root
        n = rpm / 60.0
        J = V / (n * propeller_diameter)
        CT, CP = prop_coefs(J)
        T_total = 2 * CT * rho * (n**2) * (propeller_diameter**4)
        I_total = 2 * np.maximum((voltage - rpm / kv) / 0.08, 0.0)
        P_shaft = 2 * CP * rho * (n**3) * (propeller_diameter**5)
        return T_total, rpm, I_total, P_shaft
    
    def res_fn(V):
        D, _, _, _ = level_drag(V)
        T, _, _, _ = powertrain_thrust(V)
        return T - D
    
    sol = so.root_scalar(res_fn, bracket=[15.0, 38.0], method='brentq')
    V_max = float(sol.root)
    D_max, alpha_max, cl_max, cd_max = level_drag(V_max)
    T_max, rpm_max, current_max, p_shaft_max = powertrain_thrust(V_max)
    
    V_curve = np.linspace(8.5, 33.0, 35)
    D_curve = []
    T_curve = []
    alpha_curve = []
    for v in V_curve:
        d, a, _, _ = level_drag(v)
        t, _, _, _ = powertrain_thrust(v)
        D_curve.append(d)
        T_curve.append(t)
        alpha_curve.append(a)
        
    return {
        "V_max": V_max,
        "thrust_drag_max": D_max,
        "alpha_max": alpha_max,
        "cl_max": cl_max,
        "cd_max": cd_max,
        "rpm_max": rpm_max,
        "current_max": current_max,
        "p_elec_max": current_max * voltage,
        "p_shaft_max": p_shaft_max,
        "voltage": voltage,
        "V_curve": V_curve,
        "D_curve": np.array(D_curve),
        "T_curve": np.array(T_curve),
        "alpha_curve": np.array(alpha_curve),
    }

def plot_speed_thrust_drag(speed_data, axs=None):
    """
    Plot thrust available versus level drag and power required across airspeeds.
    """
    if axs is None:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.5))
    else:
        fig = axs[0].get_figure()
        ax1, ax2 = axs
    
    V_c = speed_data["V_curve"]
    D_c = speed_data["D_curve"]
    T_c = speed_data["T_curve"]
    
    v_max = speed_data["V_max"]
    td_max = speed_data["thrust_drag_max"]
    
    # Panel 1: Thrust and Drag vs Airspeed
    ax1.plot(V_c, T_c, "b-", lw=2, label="Thrust available $T$")
    ax1.plot(V_c, D_c, "r-", lw=2, label="Level drag $D$")
    ax1.plot(v_max, td_max, "ko", markersize=6, label=f"$V_{{\\max}} = {v_max:.1f}$ m/s")
    ax1.axvline(v_max, color="k", linestyle=":", alpha=0.5)
    ax1.set_xlabel("Airspeed $V$ [m/s]")
    ax1.set_ylabel("Force [N]")
    ax1.set_title("Thrust and Drag Balance")
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="upper right", frameon=False)
    
    # Panel 2: Power Required
    P_req = D_c * V_c
    ax2.plot(V_c, P_req, "g-", lw=2, label="Thrust power $P = D \\cdot V$")
    ax2.plot(v_max, td_max * v_max, "ro", markersize=6, label=f"$P = {td_max*v_max:.0f}$ W")
    ax2.set_xlabel("Airspeed $V$ [m/s]")
    ax2.set_ylabel("Power [W]")
    ax2.set_title("Thrust Power Required")
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(loc="upper left", frameon=False)
    
    fig.tight_layout()
    return fig


