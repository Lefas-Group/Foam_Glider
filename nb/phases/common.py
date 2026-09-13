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


def setup(session, verbose=True, phase=None):
    """
    (filesystem, tools, make_config).

    The caller must stop the filesystem when done -- it owns a subprocess.
    """
    notebook = session.notebook
    text = prefix_mod.build(notebook)
    fs = FileSystem(notebook.chapters_dir).start()
    tools, handlers = build_tools(session, fs, phase=phase)

    def make_config():
        return config(tools=tools, system_instruction=text)

    return fs, handlers, make_config


def report(resp, label=""):
    prompt, cached, out = usage(resp)
    return (f"  {label:9s} {prompt:,} prompt ({cached:,} cached), "
            f"{out:,} out")
