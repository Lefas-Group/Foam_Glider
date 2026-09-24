"""
Setup shared by both phases: prefix, tools, and a config factory.

There was an explicit cache here, holding the prefix as a `cachedContents`
object. It is gone, because measurement said it was costing roughly twice what
it saved. Passing `cached_content` does not ADD to Gemini's implicit caching --
it replaces it, and the conversation, which is the part that grows, is then
billed at full rate on every turn. Six turns of the same conversation, same
10.4k prefix:

    explicit cache   23.9% hit   $0.4121   cached pinned at the cache size
    implicit only    67.0% hit   $0.2082   cached tracks the conversation

Implicit caching needs nothing declared, stores nothing, and bills no storage.
It also removes a cross-run hazard that mattered under parallel instances: the
explicit key included the manifest, so one run committing invalidated every
sibling's cache outright, where implicit caching merely shortens the matched
prefix from that point.

What it does NOT do is guarantee a hit. `metrics` keeps `cached_tokens` per run
for exactly that reason -- a silent drop in the ratio is the only symptom.
"""

from ..client import config, usage
from .. import prefix as prefix_mod
from ..tools import build as build_tools
from ..tools.mcp_fs import FileSystem


def setup(session, verbose=True):
    """
    (filesystem, tools, make_config).

    The caller must stop the filesystem when done -- it owns a subprocess.
    """
    notebook = session.notebook
    text = prefix_mod.build(notebook)
    fs = FileSystem(notebook.chapters_dir).start()
    tools, handlers = build_tools(session, fs)

    def make_config():
        return config(tools=tools, system_instruction=text)

    return fs, handlers, make_config


# What to show from a tool call, per tool: the argument that says WHICH thing it
# is acting on. `-> read_text_file` twelve times in a row says only that the
# model is reading; `-> read_text_file 03-unswept-c4/_analysis.py` says whether
# it is going in circles. Truncated to a tail, because a path's identity is at
# its end and its prefix is the same on every line.
CALL_ARG = {
    "read_text_file": "path", "write_file": "path", "edit_file": "path",
    "list_directory": "path", "search_files": "pattern",
    "lint": "chapter", "render": "target", "check": "chapter",
    "probe": "question", "bash": "command",
    "api_search": "query", "api_signature": "path",
    "read_reference": "name", "read_figure": "stem",
    "ask_specified": "name",
    "declare_refactor": "function", "request_refactor": "why",
    "open_chapter": "chapter", "declare_input": "name", "open_entry": "title",
}


def spoken_calls(turn, width=44):
    """`name arg` per tool call in a turn, for one telemetry line."""
    out = []
    for part in (turn.parts or []):
        c = part.function_call
        if not c:
            continue
        arg = (dict(c.args or {}).get(CALL_ARG.get(c.name, "")) or "")
        arg = " ".join(str(arg).split())
        if len(arg) > width:
            # A PATH is identified by its end and a sentence by its start, so
            # they truncate from opposite ends. Trimming a probe question from
            # the tail left "…at 3 mm foam thickness?", which says nothing
            # about which question it was.
            arg = ("…" + arg[-(width - 1):] if CALL_ARG.get(c.name) == "path"
                   else arg[:width - 1] + "…")
        out.append(f"{c.name} {arg}".rstrip())
    return out


def report(resp, label=""):
    prompt, cached, out = usage(resp)
    return (f"  {label:9s} {prompt:,} prompt ({cached:,} cached), "
            f"{out:,} out")
