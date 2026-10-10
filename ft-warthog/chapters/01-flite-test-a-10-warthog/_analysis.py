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
