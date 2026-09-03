#!/usr/bin/env python3
"""
library_explorer_server.py
MCP server exposing the installed AeroSandbox for discovery.

The question this exists to answer is "does aerosandbox already have this?",
asked before any geometry or aero code gets written. It is answered by walking
the INSTALLED package, so the inventory is always the version actually imported
by the notebook. Nothing here is curated by hand, and there are no generated
data files to go stale.

Tools:
- search:         find something by name or docstring, across functions,
                  classes AND methods. The entry point when you know what you
                  want but not where it lives.
- list_classes:   every class, grouped by area
- list_functions: every function, grouped by area
- get_docstring:  docstring + signature for any dotted path
- get_methods:    every method of a class
"""

import contextlib
import importlib
import inspect
import os
import pkgutil
import sys
from typing import Dict, List, Optional

import numpy as _real_numpy

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("library-explorer")

PACKAGE = "aerosandbox"

# `library` and `tools` are split one level deeper: they are large and
# heterogeneous (library/weights holds 46 transport-aircraft weight
# correlations, library/aerodynamics another 45), so a single "library" bucket
# would hide the distinction that decides whether an entry is relevant at all.
# Everything else groups at the top level. Structural rather than curated, so a
# new aerosandbox release re-groups itself with no mapping to maintain.
_SPLIT_DEEPER = {"library", "tools"}


def _area(path: str) -> str:
    """The group a dotted path belongs to, derived from the path itself."""
    parts = path.split(".")
    if len(parts) < 2:
        return "?"
    if parts[1] in _SPLIT_DEEPER and len(parts) > 2:
        return f"{parts[1]}/{parts[2]}"
    return parts[1]


def _summary(obj) -> str:
    """First line of the docstring, or ''."""
    doc = inspect.getdoc(obj) or ""
    return doc.strip().split("\n")[0].strip()


def _unwrap(obj):
    """
    The underlying function of a property, staticmethod or classmethod.

    A bare inspect.isfunction() sees none of these three, which would drop
    Fuselage.area_wetted and most of the geometry API from the index -- exactly
    the things worth finding.
    """
    if isinstance(obj, property):
        return obj.fget
    return getattr(obj, "__func__", obj)


# ============================================================================
# The index
# ============================================================================

_INDEX: Optional[dict] = None


def _build_index() -> dict:
    """
    Walk the installed aerosandbox once and record what it defines.

    Entities are keyed by `obj.__module__`, not by the module they were found
    in. aerosandbox re-exports heavily -- `aerosandbox.Wing` is really
    `aerosandbox.geometry.wing.Wing` -- so keying on the DEFINING module dedupes
    the re-exports and yields one canonical dotted path per entity.
    """
    package = importlib.import_module(PACKAGE)
    root = os.path.dirname(package.__file__)

    modules, failed = [], []

    # Imports must not write to stdout. This server speaks JSON-RPC over stdio,
    # so a single stray print from an imported module corrupts the stream and
    # takes down the transport rather than just the answer. aerosandbox is clean
    # today (measured: 0 chars), but that is a property of its current __init__
    # files, not a promise -- so redirect rather than trust.
    with contextlib.redirect_stdout(sys.stderr):
        for mi in pkgutil.walk_packages([root], f"{PACKAGE}."):
            try:
                modules.append(importlib.import_module(mi.name))
            except BaseException as e:
                # BaseException, not Exception: some optional-dependency import
                # failures do not subclass Exception, and one of those escaping
                # would take the whole index down. Three modules fail today
                # (plotly x2, sympy_interactive); they are reported, not hidden,
                # because a silently absent module looks like a missing feature.
                failed.append({"module": mi.name, "error": type(e).__name__})

    classes: Dict[str, type] = {}
    functions: Dict[str, object] = {}

    for m in modules:
        for name, obj in vars(m).items():
            if name.startswith("_"):
                continue
            mod = getattr(obj, "__module__", "") or ""
            if not mod.startswith(PACKAGE):
                continue
            path = f"{mod}.{getattr(obj, '__qualname__', name)}"
            if inspect.isclass(obj):
                classes[path] = obj
            elif inspect.isfunction(obj):
                functions[path] = obj

    # Methods are indexed for search only -- they are not listed by
    # list_functions (that is what get_methods is for). Without them, a search
    # for "neutral point" finds nothing at all, because the call that computes
    # it is AeroBuildup.run_with_stability_derivatives.
    methods: Dict[str, object] = {}
    for cpath, cls in classes.items():
        for name, raw in vars(cls).items():
            if name.startswith("_"):
                continue
            fn = _unwrap(raw)
            if inspect.isfunction(fn):
                methods[f"{cpath}.{name}"] = fn

    return {
        "classes": classes,
        "functions": functions,
        "methods": methods,
        "failed": failed,
        "n_modules": len(modules),
    }


def _index() -> dict:
    """The index, built once per server process and cached.

    The installed package cannot change under a running process, so a rebuild
    could only ever return the same answer. Built lazily on first use: startup
    stays instant and the ~2.6 s walk is paid by whichever call comes first.
    """
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def _is_numpy_shadow(path: str, obj) -> bool:
    """
    True for aerosandbox.numpy functions that reimplement a real numpy name.

    aerosandbox.numpy holds two different kinds of thing. 48 of its 87 functions
    shadow numpy (`sin`, `dot`, `inv`) as CasADi-safe versions of an API the
    caller already knows -- used via `import aerosandbox.numpy as np`, never
    browsed, so listing them is pure noise. The other 39 are original and
    discoverable only by listing: cosspace, sinspace, softmax, blend, sind,
    rotation_matrix_3D, integrate_discrete_intervals, is_casadi_type.

    Membership of dir(numpy) draws that line by computation, so it needs no
    hand-maintained list and follows both libraries as they change. Shadowed
    functions stay fully resolvable by path through get_docstring.
    """
    return path.split(".")[1] == "numpy" and path.split(".")[-1] in dir(_real_numpy)


# ============================================================================
# Shared helpers for the path-resolving tools
# ============================================================================

def get_object_from_path(full_path: str):
    """Import and return the object at a dotted path."""
    parts = full_path.split(".")
    for i in range(len(parts), 0, -1):
        module_path = ".".join(parts[:i])
        attr_path = parts[i:]
        try:
            obj = importlib.import_module(module_path)
            for attr in attr_path:
                obj = getattr(obj, attr)
            return obj
        except (ImportError, ModuleNotFoundError, AttributeError):
            continue
    raise ImportError(f"Could not resolve path: {full_path}")


def get_signature_string(obj) -> Optional[str]:
    """Signature as a string, or None if it has none."""
    try:
        return str(inspect.signature(obj))
    except (ValueError, TypeError):
        return None


def get_docstring_summary(obj, max_lines: Optional[int] = None) -> str:
    """Docstring, optionally trimmed to the first `max_lines` lines."""
    docstring = inspect.getdoc(obj)
    if not docstring:
        return ""
    if max_lines is None or max_lines == 0:
        return docstring
    return "\n".join(docstring.split("\n")[:max_lines])


def get_class_parameters(cls) -> List[str]:
    """Constructor parameter names, excluding self."""
    try:
        sig = inspect.signature(getattr(cls, "__init__"))
        return [p for p in sig.parameters if p != "self"]
    except (ValueError, TypeError, AttributeError):
        return []


def _grouped(paths, entry_fn) -> dict:
    """Group entries by area, areas and entries both sorted."""
    out: Dict[str, list] = {}
    for p in sorted(paths):
        out.setdefault(_area(p), []).append(entry_fn(p))
    return dict(sorted(out.items()))


# ============================================================================
# Tools
# ============================================================================

@mcp.tool()
def search(query: str, kind: str = "all", limit: int = 40) -> dict:
    """
    Find an aerosandbox function, class or method by name or docstring.

    Start here when you know what you want but not where it lives. Unlike the
    listings, this searches FULL docstrings and includes methods, so it finds
    things whose name gives no clue: search("neutral") returns
    AeroBuildup.run_with_stability_derivatives, which is what computes x_np.

    Matching is lexical, not semantic: a multi-word query requires ALL its words
    to appear somewhere in the path or docstring, in any order. A query that
    returns nothing means those words are absent from aerosandbox's docstrings
    -- it is not proof the capability is missing. Try a single distinctive word,
    or browse with list_classes / list_functions.

    Args:
        query: one or more words, case-insensitive
        kind: "all" (default), "function", "class" or "method"
        limit: maximum results

    Returns:
        Matches with path, kind and summary; name matches ranked first.
    """
    idx = _index()
    tokens = query.lower().split()
    if not tokens:
        return {"error": "empty query"}

    pools = {"function": idx["functions"], "class": idx["classes"], "method": idx["methods"]}
    if kind != "all":
        if kind not in pools:
            return {"error": f"kind must be one of all, function, class, method (got {kind!r})"}
        pools = {kind: pools[kind]}

    hits = []
    for k, pool in pools.items():
        for path, obj in pool.items():
            name = path.split(".")[-1].lower()
            doc = (inspect.getdoc(obj) or "").lower()
            haystack = f"{path.lower()} {doc}"
            if not all(t in haystack for t in tokens):
                continue
            # Rank: all tokens in the bare name beats a path match beats a
            # docstring-only match, so an exact name lands at the top.
            if all(t in name for t in tokens):
                rank = 0
            elif all(t in path.lower() for t in tokens):
                rank = 1
            else:
                rank = 2
            hits.append((rank, path, {"path": path, "kind": k, "summary": _summary(obj)}))

    hits.sort(key=lambda h: (h[0], h[1]))
    results = [h[2] for h in hits[:limit]]
    out = {"query": query, "count": len(hits), "results": results}
    if len(hits) > limit:
        out["truncated"] = f"showing {limit} of {len(hits)}; narrow the query or raise limit"
    return out


@mcp.tool()
def list_classes(area: str = "") -> dict:
    """
    Every class defined in the installed aerosandbox, grouped by area.

    The whole set is small enough to read in one call, so there is no need to
    filter unless you want to. Use get_methods on anything interesting.

    Args:
        area: optional group to restrict to, e.g. "geometry", "aerodynamics",
              "dynamics", "weights". Omit for everything.

    Returns:
        Classes by area: path, summary and constructor parameters.
    """
    idx = _index()
    paths = [p for p in idx["classes"] if not area or _area(p) == area]
    if area and not paths:
        return {"error": f"no area {area!r}", "areas": sorted({_area(p) for p in idx["classes"]})}

    def entry(p):
        cls = idx["classes"][p]
        return {"path": p, "summary": _summary(cls), "parameters": get_class_parameters(cls)}

    return {"count": len(paths), "areas": _grouped(paths, entry)}


@mcp.tool()
def list_functions(area: str = "", include_numpy_shadows: bool = False) -> dict:
    """
    Every module-level function in the installed aerosandbox, grouped by area.

    With no arguments: the complete inventory, names only, so it stays readable
    in one call. Name an `area` to get one-line summaries for that group.
    Signatures are never included -- they run to hundreds of characters; call
    get_docstring once you have a name.

    Methods are not listed here: use get_methods on a class, or search().

    By default this omits the 48 aerosandbox.numpy functions that merely shadow
    real numpy names (sin, dot, inv -- CasADi-safe versions of an API you
    already know). The 39 aerosandbox-original numpy helpers (cosspace, softmax,
    blend, sind, rotation_matrix_3D...) are always shown.

    Args:
        area: optional group, e.g. "geometry", "aerodynamics", "numpy",
              "library/weights", "tools/pretty_plots"
        include_numpy_shadows: also list the numpy-shadowing functions

    Returns:
        Functions by area; summaries included when `area` is given.
    """
    idx = _index()
    fns = idx["functions"]
    paths = [
        p for p in fns
        if (include_numpy_shadows or not _is_numpy_shadow(p, fns[p]))
        and (not area or _area(p) == area)
    ]
    if area and not paths:
        return {"error": f"no area {area!r}", "areas": sorted({_area(p) for p in fns})}

    entry = (lambda p: {"path": p, "summary": _summary(fns[p])}) if area else (lambda p: p)

    out = {"count": len(paths), "areas": _grouped(paths, entry)}
    if not area:
        out["note"] = "names only; call list_functions(area=...) for summaries"
    if idx["failed"]:
        out["import_failures"] = idx["failed"]
    return out


@mcp.tool()
def get_docstring(full_path: str, max_lines: int = 0, include_signature: bool = True) -> dict:
    """
    Get the docstring and signature of an aerosandbox class, function, or method.

    Args:
        full_path: Full dotted path (e.g., "aerosandbox.geometry.wing.Wing" or
                   "aerosandbox.Atmosphere.density")
        max_lines: Number of docstring lines to return (0 = full docstring,
                   positive = first N lines)
        include_signature: Whether to include the function/method signature

    Returns:
        Dictionary with path, name, signature (optional), and docstring
    """
    try:
        obj = get_object_from_path(full_path)
    except (ImportError, AttributeError) as e:
        return {"error": f"Could not resolve '{full_path}': {e}"}

    result = {"path": full_path, "name": full_path.split(".")[-1]}

    if include_signature:
        sig = get_signature_string(obj)
        if sig:
            result["signature"] = sig

    docstring = get_docstring_summary(obj, max_lines if max_lines != 0 else None)
    result["docstring"] = docstring if docstring else None
    return result


@mcp.tool()
def get_methods(
    full_path: str,
    docstring_lines: int = 2,
    include_signature: bool = True,
    include_private: bool = False,
) -> dict:
    """
    Get all methods and parameters from an aerosandbox class.

    Args:
        full_path: Full dotted path to the class (e.g., "aerosandbox.geometry.wing.Wing")
        docstring_lines: Number of docstring lines per method (0 = full, positive = first N)
        include_signature: Whether to include method signatures
        include_private: Whether to include private methods (starting with _)

    Returns:
        Dictionary with path, name, docstring, parameters, and methods list
    """
    try:
        cls = get_object_from_path(full_path)
    except (ImportError, AttributeError) as e:
        return {"error": f"Could not resolve '{full_path}': {e}"}

    if not inspect.isclass(cls):
        return {"error": f"'{full_path}' is not a class"}

    result = {"path": full_path, "name": full_path.split(".")[-1]}

    class_doc = get_docstring_summary(cls, docstring_lines if docstring_lines != 0 else None)
    result["docstring"] = class_doc if class_doc else None
    result["parameters"] = get_class_parameters(cls)

    methods = {}
    for name, obj in inspect.getmembers(cls):
        if not include_private and name.startswith("_"):
            continue
        if inspect.ismethod(obj) or inspect.isfunction(obj):
            methods[name] = obj

    methods_list = []
    for name in sorted(methods):
        info = {"name": name}
        if include_signature:
            sig = get_signature_string(methods[name])
            if sig:
                info["signature"] = sig
        if docstring_lines != 0:
            doc = get_docstring_summary(
                methods[name], docstring_lines if docstring_lines > 0 else None
            )
            info["docstring"] = doc if doc else None
        methods_list.append(info)

    result["methods"] = methods_list
    return result


# ============================================================================
# Main
# ============================================================================

def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
