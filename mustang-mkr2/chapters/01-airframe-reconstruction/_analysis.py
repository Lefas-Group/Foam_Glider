import aerosandbox as asb
import aerosandbox.numpy as np
import matplotlib.pyplot as plt


def evaluate_targets():
    """Evaluate reconstructed aircraft against published brief targets."""
    v_stab = [w for w in airplane.wings if w.name == "Vertical Stabilizer"][0]
    length_mm = (v_stab.xsecs[0].xyz_le[0] + v_stab.xsecs[0].chord) * 1e3

    m_wing = [w for w in airplane.wings if w.name == "Main Wing"][0]
    span_mm = m_wing.span(type="y") * 1e3

    area_m2 = m_wing.area()
    area_dm2 = area_m2 * 100.0

    dry_g = dry_mass_props.mass * 1e3
    auw_g = mass_props.mass * 1e3

    wl = auw_g / area_dm2

    w_oz = auw_g / 28.349523
    s_ft2 = area_m2 * 10.76391
    wcl = w_oz / (s_ft2 ** 1.5)

    cg_mm = (mass_props.x_cg - m_wing.xsecs[0].xyz_le[0]) * 1e3

    records = [
        {"name": "Length", "model": length_mm, "target": 482.0, "unit": "mm", "tol": 0.02, "kind": "derived"},
        {"name": "Wing span", "model": span_mm, "target": 622.0, "unit": "mm", "tol": 0.01, "kind": "derived"},
        {"name": "Wing area", "model": area_dm2, "target": 7.4, "unit": "dm2", "tol": 0.03, "kind": "derived"},
        {"name": "Dry weight", "model": dry_g, "target": 156.0, "unit": "g", "tol": 0.06, "kind": "derived"},
        {"name": "Wing loading", "model": wl, "target": 29.9, "unit": "g/dm2", "tol": 0.04, "kind": "derived"},
        {"name": "Wing cubic loading", "model": wcl, "target": 10.9, "unit": "", "tol": 0.06, "kind": "derived"},
        {"name": "Center of gravity", "model": cg_mm, "target": 25.0, "unit": "mm", "tol": 0.08, "kind": "given"},
        {"name": "All-up weight", "model": auw_g, "target": 222.0, "unit": "g", "tol": 0.05, "kind": "given"},
    ]

    for r in records:
        r["error"] = (r["model"] - r["target"]) / r["target"]
        r["rel_err"] = abs(r["error"]) / r["tol"]
        r["passed"] = abs(r["error"]) <= r["tol"]

    return records


def plot_target_errors(records):
    """Plot target discrepancy against allowable tolerance."""
    names = [r["name"] for r in records]
    ratio_pct = [r["rel_err"] * 100 for r in records]

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, ratio_pct, color="#2563eb", alpha=0.85, height=0.6)
    ax.axvline(100, color="#dc2626", linestyle="--", linewidth=1.5, label="Tolerance limit (100%)")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("Discrepancy as percentage of allowable tolerance (%)")
    ax.set_xlim(0, 110)

    for bar, r in zip(bars, records):
        w = bar.get_width()
        ax.text(w + 2, bar.get_y() + bar.get_height() / 2, f"{r['error']*100:+.2f}% (tol ±{r['tol']*100:.0f}%)", va="center", fontsize=8)

    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig, ax
