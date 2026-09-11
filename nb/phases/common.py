"""Setup shared by both phases: prefix, tools, cache, and a config factory."""

from .. import cache as cache_mod
from .. import prefix as prefix_mod
from ..client import config, usage
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
    handle = cache_mod.build(notebook, text, tools, verbose=verbose)

    def make_config():
        # The cache object already carries system_instruction AND tools; passing
        # either alongside it is an error, so the two paths are exclusive.
        if handle:
            return config(cached_content=handle)
        return config(tools=tools, system_instruction=text)

    return fs, handlers, make_config


def report(resp, label=""):
    prompt, cached, out = usage(resp)
    return (f"  {label:9s} {prompt:,} prompt ({cached:,} cached), "
            f"{out:,} out")
