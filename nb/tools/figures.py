"""
read_figure -- rendered figures, as images.

`verify` exists to catch prose written from the conversation rather than from
the output, and that failure is mostly a FIGURE failure: a caption claiming a
crossover at 6 m/s when the curve crosses at 8 is invisible to a text-only check.

Native rather than MCP. The figures live under `_freeze/`, outside the `chapters/`
allowlist, and the MCP filesystem server has no read-only tier -- adding `_freeze/`
would grant write access to the one directory whose integrity freezediff depends
on. Content the agent may read but not write is a tool, not a file.
"""

import base64


def figure_paths(notebook, chapter, stem=""):
    """Every rendered figure PNG for a chapter, or for one entry within it."""
    root = notebook.freeze / chapter
    if not root.exists():
        return []
    pattern = f"{stem}/figure-html/*.png" if stem else "*/figure-html/*.png"
    return sorted(root.glob(pattern))


def list_figures(notebook, chapter, stem=""):
    paths = figure_paths(notebook, chapter, stem)
    if not paths:
        return f"no rendered figures for {chapter}{'/' + stem if stem else ''}"
    return "\n".join(f"{p.parts[-3]}/{p.name}" for p in paths)


def read_figure(notebook, chapter, stem, name=""):
    """
    One figure as base64 PNG, for passing back as inline image data.

    Returns a dict rather than a string so the caller can build an image Part;
    the loop turns anything non-string into a function_response payload as-is.
    """
    paths = figure_paths(notebook, chapter, stem)
    if name:
        paths = [p for p in paths if p.name == name]
    if not paths:
        return {"error": f"no figure {name or '*'} under {chapter}/{stem}. "
                         f"Available: {list_figures(notebook, chapter, stem)}"}
    p = paths[0]
    return {"name": p.name,
            "mime_type": "image/png",
            "data": base64.b64encode(p.read_bytes()).decode()}
