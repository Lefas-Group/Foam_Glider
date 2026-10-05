import aerosandbox.numpy as np
import matplotlib.pyplot as plt


def evaluate_targets(airplane, dry_mass_props, total_mass_props):
    """
    Evaluate reconstructed airframe metrics against brief targets and tolerances.
    """
    all_x = []
    for w in airplane.wings:
        for xsec in w.xsecs:
            all_x.append(xsec.xyz_le[0])
            all_x.append(xsec.xyz_le[0] + xsec.chord)
    for f in airplane.fuselages:
        for xsec in f.xsecs:
            all_x.append(xsec.xyz_c[0])
    length_m = max(all_x) - min(all_x)

    span_m = airplane.wings[0].span(type="y")
    dry_mass_kg = dry_mass_props.mass
    wing_le_x = airplane.wings[0].xsecs[0].xyz_le[0]
    cg_aft_le_m = total_mass_props.x_cg - wing_le_x

    targets = [
        {
            "name": "Wing span",
            "type": "Derived",
            "target": 0.978,
            "unit": "m",
            "tol_pct": 1.0,
            "measured": float(span_m),
            "err_pct": float((span_m - 0.978) / 0.978 * 100),
        },
        {
            "name": "Length",
            "type": "Derived",
            "target": 0.692,
            "unit": "m",
            "tol_pct": 2.0,
            "measured": float(length_m),
            "err_pct": float((length_m - 0.692) / 0.692 * 100),
        },
        {
            "name": "Dry weight",
            "type": "Derived",
            "target": 0.400,
            "unit": "kg",
            "tol_pct": 6.0,
            "measured": float(dry_mass_kg),
            "err_pct": float((dry_mass_kg - 0.400) / 0.400 * 100),
        },
        {
            "name": "CG aft LE",
            "type": "Given",
            "target": 0.051,
            "unit": "m",
            "tol_pct": 8.0,
            "measured": float(cg_aft_le_m),
            "err_pct": float((cg_aft_le_m - 0.051) / 0.051 * 100),
        },
    ]
    for t in targets:
        t["passed"] = abs(t["err_pct"]) <= t["tol_pct"]
    return targets


def plot_target_errors(targets):
    """
    Plot bar chart comparing reconstruction errors against allowable tolerances.
    """
    fig, ax = plt.subplots(figsize=(6.5, 3.0))

    names = [t["name"] for t in targets]
    errs = [t["err_pct"] for t in targets]
    tols = [t["tol_pct"] for t in targets]
    y_pos = np.arange(len(names))

    for i, (y, tol) in enumerate(zip(y_pos, tols)):
        ax.barh(
            y,
            2 * tol,
            left=-tol,
            color="lightgray",
            alpha=0.5,
            edgecolor="gray",
            label="Tolerance band" if i == 0 else "",
        )

    colors = ["#2b6cb0" if abs(e) <= tol else "#c53030" for e, tol in zip(errs, tols)]
    ax.barh(y_pos, errs, height=0.4, color=colors, label="Reconstructed error")

    ax.axvline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.set_xlabel("Error (%)")
    ax.set_xlim(-10, 10)
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig, ax


def plot_photo_comparisons(
    airplane,
    hint_trainer=(40.1, 221.4, 1.7),
    hint_decal=(39.0, 218.2, -0.5),
):
    """
    Draw reconstructed airframe over store photographs to inspect shape match.
    """
    fig, axs = plt.subplots(1, 2, figsize=(11, 5.5))
    note_tr = show_comparison(airplane, "trainer", hint=hint_trainer, ax=axs[0])
    note_dec = show_comparison(airplane, "decal", hint=hint_decal, ax=axs[1])
    axs[0].set_title("Trainer wing (stock)")
    axs[1].set_title("Decal scheme")
    fig.tight_layout()
    return fig, (note_tr, note_dec)

