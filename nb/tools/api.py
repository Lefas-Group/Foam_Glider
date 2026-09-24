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
