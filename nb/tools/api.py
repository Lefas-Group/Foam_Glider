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


def api_signature(path, methods=False):
    import library_explorer as lx
    r = lx.get_methods(path) if methods else lx.get_docstring(path)
    if "error" in r:
        return f"{r['error']}"
    return head(json.dumps(r, indent=2))
