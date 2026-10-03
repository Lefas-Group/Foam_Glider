import matplotlib.pyplot as plt


def evaluate_target_errors(airplane, dry_props, auw_props, wing_le_x=0.085):
    """Evaluate reconstructed aircraft parameters against brief target values."""
    area_dm2 = airplane.s_ref * 100
    auw_g = auw_props.mass * 1e3
    dry_g = dry_props.mass * 1e3
    cg_aft_le_mm = (auw_props.x_cg - wing_le_x) * 1e3
    span_mm = airplane.b_ref * 1e3
    length_mm = airplane.fuselages[0].length() * 1e3
    wl = auw_g / area_dm2
    wcl = auw_g / (area_dm2**1.5)

    targets = [
        ("Length", length_mm, 482.0, 2.0, "mm"),
        ("Wing span", span_mm, 610.0, 1.0, "mm"),
        ("Wing area", area_dm2, 6.90, 3.0, "dm2"),
        ("CG aft of LE", cg_aft_le_mm, 38.0, 8.0, "mm"),
        ("Dry weight", dry_g, 156.0, 5.0, "g"),
        ("All-up weight", auw_g, 222.0, 5.0, "g"),
        ("Wing loading", wl, 32.0, 4.0, "g/dm2"),
        ("Wing cubic loading", wcl, 12.2, 6.0, ""),
    ]

    records = []
    worst_err = 0.0
    for name, model_v, target_v, tol_pct, unit in targets:
        err_pct = (model_v - target_v) / target_v * 100
        rel_tol = abs(err_pct) / tol_pct * 100
        status = "PASS" if abs(err_pct) <= tol_pct else "FAIL"
        worst_err = max(worst_err, abs(err_pct))
        records.append(
            {
                "name": name,
                "model": model_v,
                "target": target_v,
                "error_pct": err_pct,
                "tol_pct": tol_pct,
                "rel_tol": rel_tol,
                "unit": unit,
                "status": status,
            }
        )
    return {"records": records, "worst_error": worst_err}


def plot_target_errors(data):
    """Plot relative errors against allowable tolerances for all target metrics."""
    records = data["records"]
    names = [r["name"] for r in records]
    rel_tols = [r["rel_tol"] for r in records]

    fig, ax = plt.subplots(figsize=(7, 3.8))
    y_pos = range(len(names))
    colors = ["#2b7bba" if r <= 100 else "#d95f02" for r in rel_tols]

    bars = ax.barh(y_pos, rel_tols, color=colors, height=0.6)
    ax.axvline(100, color="#d95f02", linestyle="--", linewidth=1.5, label="Tolerance limit (100%)")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("Error relative to allowable tolerance (%)")
    ax.set_xlim(0, 120)
    ax.legend(loc="lower right")
    ax.grid(True, axis="x", alpha=0.3)

    for bar, r in zip(bars, records):
        w = bar.get_width()
        err_str = f"{r['error_pct']:+.2f}% (±{r['tol_pct']:.0f}% tol)"
        ax.text(w + 2, bar.get_y() + bar.get_height() / 2, err_str, va="center", ha="left", fontsize=8)

    plt.tight_layout()
    return fig
