#!/usr/bin/env python3
"""
library_explorer_server.py
The installed AeroSandbox, over stdio, for a client that speaks MCP.

ONE IMPLEMENTATION, TWO CALLERS. `library_explorer.py` beside this file is the
whole of the logic; `tools/api.py` imports it in-process for the run agent, and
this serves the same five functions to Claude Code. It used to be the other way
round -- the server was the original, in the design-notebook skill, and `nb`
vendored a copy with the transport stripped. That skill is gone and the copy
became the source, so the server is now the thin half.

NOTHING IS RESTATED HERE, and that is the point. The old server carried a
hand-written description and parameter docs per tool, free to drift from the
function underneath; every one of these five already has full type hints and a
docstring, which is all FastMCP needs to build a schema. So the schema IS the
function, and a renamed argument cannot leave a stale description behind.

`mcp.run()` is under `__main__` so that importing this module does nothing:
`preflight`'s import sweep loads every module in `nb` to prove it still parses,
and a server that bound a socket at import time would hang it. (`probe_init.py`
is the one module that sweep skips, for exactly the opposite reason.)
"""

from mcp.server.fastmcp import FastMCP

from . import library_explorer as lx

mcp = FastMCP("library-explorer")

# The BROWSE half -- `list_classes` and `list_functions` -- is here as well as
# the search half. Stripping the transport once orphaned both: `api.py` wired
# `search`, `get_docstring` and `get_methods` and nothing exposed the other
# two, so 46 classes and 291 functions sat unreachable. Registered as a list so
# that cannot happen again by omission.
for _fn in (lx.search, lx.list_classes, lx.list_functions,
            lx.get_docstring, lx.get_methods):
    mcp.tool()(_fn)


def main():
    """Serve on stdio. Launched by `.mcp.json`, not typed by a person."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
