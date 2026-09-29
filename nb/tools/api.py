"""
api_search / api_signature -- what AeroSandbox already has.

Asked before any geometry or aerodynamic calculation gets written, because the
library has areas, spans, aspect ratios, chords, volumes, wetted areas,
stability derivatives and neutral points already.

Imported in-process. The skill reached these over MCP because Claude Code had no
other way in; here the functions are plain callables and the index is built from
the INSTALLED package on first use, so there is nothing to go stale.
"""

import json

from ..text import head


def api_search(query, kind="all", limit=25):
    import library_explorer as lx
    r = lx.search(query, kind=kind, limit=limit)
    if not r.get("results"):
        return f"no match for {query!r}"
    lines = [f"{len(r['results'])} of {r['count']} hits for {query!r}:"]
    lines += [f"  {x['kind']:8s} {x['path']}\n           {x['summary']}"
              for x in r["results"]]
    return head("\n".join(lines))


def api_list(kind, area="", include_numpy_shadows=False):
    """
    The inventory, grouped by area. The other half of `api_search`.

    Search answers "is there something called X?"; this answers "what is there
    at all?", which is the question you have before you know what to search
    for. `library_explorer` has had both since it was an MCP server, and only
    search survived the vendoring -- so for months the tool that exists to stop
    the agent reimplementing `Wing.area()` could only be asked about names it
    was already half-guessing. 46 classes and 291 functions across 35 areas
    were unreachable.

    FLATTENED, not JSON. `api_search` returns lines; this returned nested dicts
    whose braces and quotes were most of the bytes. The same 46 classes read as
    2.2k of text against 11.9k of `json.dumps`.

    WITH NO AREA IT RETURNS THE AREA INDEX, not everything. The full inventory
    is 291 functions of dotted path -- past the 8,000-char truncation, and a
    silently truncated inventory is worse than no inventory: the model reads
    areas A to M and concludes N to Z do not exist, which is exactly the
    reimplementation this tool exists to prevent. An index of 35 areas with
    counts is one short result, and naming one is one more call.

    `include_numpy_shadows` is deliberately not on the tool: it turns on the 48
    `aerosandbox.numpy` names that merely shadow real numpy (sin, dot, inv), an
    API the model already knows. The 39 aerosandbox-original helpers
    (cosspace, softmax, blend, rotation_matrix_3D) are always shown.
    """
    import library_explorer as lx
    if kind == "classes":
        r = lx.list_classes(area)
    elif kind == "functions":
        r = lx.list_functions(area, include_numpy_shadows)
    else:
        return f"kind must be 'classes' or 'functions', not {kind!r}"
    if "error" in r:
        return f"{r['error']}. Areas: {', '.join(r.get('areas', []))}"
    groups = r.get("areas", {})
    if not area:
        rows = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        return head(
            f"{r.get('count', 0)} {kind} in {len(rows)} areas. Name one for "
            f"paths and summaries:\n\n"
            + "\n".join(f"  {g:34} {len(v):3}" for g, v in rows))
    lines = [f"{r.get('count', 0)} {kind} in {area}:"]
    for group in sorted(groups):
        entries = r["areas"][group]
        lines.append(f"\n{group}")
        for e in entries:
            if isinstance(e, str):
                lines.append(f"  {e}")
                continue
            path = e.get("path", "")
            bits = [b for b in (e.get("summary"), ) if b]
            lines.append(f"  {path}" + (f"\n      {bits[0]}" if bits else ""))
            params = e.get("parameters")
            if params:
                lines.append(f"      ({', '.join(params)})")
    return head("\n".join(lines))


def api_signature(path, methods=False):
    import library_explorer as lx
    r = lx.get_methods(path) if methods else lx.get_docstring(path)
    if "error" in r:
        return f"{r['error']}"
    return head(json.dumps(r, indent=2))


# The AeroSandbox the notebooks ACTUALLY use, measured over every committed
# entry, `_model.py` and `_analysis.py` in all four notebooks: 15 classes and
# ~20 methods, against an index of 46 classes and 291 functions. Roughly 5% of
# the library, and stable -- the set has not grown in six days of entries.
#
# It is pregenerated into the prefix rather than looked up, because a lookup
# costs a TURN. `api_signature` returns in microseconds once the index is built,
# which made it look free; it is not, because the model must spend a turn asking
# and then carry the answer in context for every turn after. Flash spent 1.0
# turns per run on `api_signature` and produced 8 NameErrors anyway.
#
# Methods are listed EXPLICITLY, not pulled wholesale: full method lists for
# these classes measure 8,573 tokens for the nine core ones and 19,533 for all
# fifteen, against 2,067 for this. The names below include a few the notebooks
# have not called yet but that `aerosandbox.md` exists to point at -- every row
# of its "instead of / use" table is something that was hand-reimplemented once.
SURFACE = {
    "aerosandbox.geometry.airplane.Airplane": ["draw_three_view"],
    "aerosandbox.geometry.wing.Wing": [
        "area", "span", "aspect_ratio", "mean_aerodynamic_chord",
        "mean_geometric_chord", "translate"],
    "aerosandbox.geometry.wing.WingXSec": [],
    "aerosandbox.geometry.fuselage.Fuselage": [
        "volume", "area_wetted", "length", "fineness_ratio", "translate"],
    "aerosandbox.geometry.fuselage.FuselageXSec": ["xsec_area"],
    "aerosandbox.geometry.airfoil.airfoil.Airfoil": [
        "get_aero_from_neuralfoil", "repanel"],
    "aerosandbox.geometry.airfoil.kulfan_airfoil.KulfanAirfoil": [],
    "aerosandbox.performance.operating_point.OperatingPoint": [],
    "aerosandbox.aerodynamics.aero_3D.aero_buildup.AeroBuildup": [
        "run", "run_with_stability_derivatives"],
    "aerosandbox.optimization.opti.Opti": [
        "variable", "subject_to", "minimize", "maximize", "solve", "value"],
    "aerosandbox.optimization.opti.OptiSol": ["value"],
    "aerosandbox.atmosphere.atmosphere.Atmosphere": [
        "density", "dynamic_viscosity", "speed_of_sound"],
    "aerosandbox.weights.mass_properties.MassProperties": [],
    "aerosandbox.dynamics.point_mass.point_2D.speed_gamma"
    ".DynamicsPointMass2DSpeedGamma": [],
    "aerosandbox.dynamics.rigid_body.rigid_2D.body"
    ".DynamicsRigidBody2DBody": [],
}

HEADER = """# AeroSandbox: the surface this notebook uses

Signatures read from the INSTALLED package, so they are current. This is the
5% of AeroSandbox these notebooks actually call -- it is here so you do not
spend a turn asking for what you were always going to need.

It is NOT the whole library. Anything not below still exists: reach for
`api_search` when you know the concept but not the name, `api_list` to browse
an area, `api_signature` for a full method list. A name that is absent here is
absent from this page only, never from AeroSandbox.
"""


def block():
    """
    The pregenerated API surface, as text for the prefix.

    Regenerate with `python -m nb.tools.api` after an AeroSandbox version bump,
    and COMMIT the result: the prefix has to be byte-identical across runs for
    one implicit cache object to serve them all, so this cannot be built per
    run.
    """
    import library_explorer as lx
    out = [HEADER]
    for path, keep in SURFACE.items():
        r = lx.get_methods(path, docstring_lines=1, include_signature=True)
        if "error" in r:
            continue
        out.append(f"### {r.get('name', path)}")
        doc = (r.get("docstring") or "").strip().splitlines()
        if doc:
            out.append(doc[0][:110])
        if r.get("parameters"):
            out.append("(" + ", ".join(r["parameters"]) + ")")
        for m in (r.get("methods") or []):
            if m.get("name") not in keep:
                continue
            d = (m.get("docstring") or "").strip().replace("\n", " ")[:80]
            out.append(f"  .{m['name']}{m.get('signature') or ''}"
                       + (f"  {d}" if d else ""))
    return "\n".join(out) + "\n"


def main():
    import sys
    from ..config import REFERENCES
    sys.path.insert(0, str(REFERENCES.parent))
    text = block()
    dest = REFERENCES / "aerosandbox-api.md"
    dest.write_text(text)
    print(f"{dest}  {len(text):,} chars  ~{len(text) // 4:,} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
