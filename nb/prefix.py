"""
The cached prefix: system instruction, then everything about this notebook that
does not change during a run.

Whole-notebook, not just the target chapter. All four `index.qmd` come to ~1,900
tokens and all four signature lists to ~1,200 -- cheap, and it makes the prefix
IDENTICAL for every run in the notebook, so one cache object serves them all
until the manifest changes. Targeting one chapter would mean knowing the chapter
before the cache is built, which was the only real argument for a separate
routing call.

`index.qmd` is mandatory context rather than optional: it states what defines
each chapter and the assumptions that live at chapter level, which entry prose
must not repeat.
"""

import ast
import sys

from .config import Notebook, SYSTEM_INSTRUCTION
from . import manifest


def module_summary(path):
    """
    Public names a chapter module defines: functions with their signatures, and
    module-level constants.

    The constants matter as much as the functions. A question about the zoom
    climb is routed by seeing `ZOOM_EFF` and `launch_height()` in one chapter and
    not the others -- without them the only way to find the right chapter is to
    read every `_model.py`, which is what happened before this was added: twenty
    turns of grepping and filesystem probing, and still the wrong chapter.
    """
    if not path.exists() or not path.read_text().strip():
        return [], []
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return [], []
    funcs, consts = [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            doc = (ast.get_docstring(node) or "").strip().split("\n")[0]
            funcs.append(f"    {node.name}({ast.unparse(node.args)})"
                         + (f"\n        {doc}" if doc else ""))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_"):
                    try:
                        v = ast.unparse(node.value)
                    except Exception:
                        v = "..."
                    consts.append(f"    {t.id} = {v[:60]}")
    return funcs, consts


def signatures(path):
    """Just the functions, for `_analysis.py`."""
    return module_summary(path)[0]


def chapter_context(notebook):
    out = []
    for chapter in notebook.chapters():
        d = notebook.chapters_dir / chapter
        out.append(f"\n## chapters/{chapter}\n")
        index = d / "index.qmd"
        if index.exists():
            out.append("### index.qmd — what defines this chapter\n")
            out.append("```")
            out.append(index.read_text().strip())
            out.append("```\n")

        funcs, consts = module_summary(d / "_model.py")
        out.append("### _model.py — the vehicle. These names are in scope in a "
                   "probe of this chapter\n")
        if consts:
            out += consts
        if funcs:
            out.append("")
            out += funcs
        if not funcs and not consts:
            out.append("    (empty)")
        out.append("")

        sigs = signatures(d / "_analysis.py")
        out.append("### _analysis.py — how this chapter measures the vehicle\n")
        if sigs:
            out.append("Pass to `footer(...)` whatever your entry NAMES (rule 13):\n")
            out += sigs
        else:
            out.append("    (empty — nothing promoted yet)")
        out.append("")
    return "\n".join(out)


def build(notebook):
    parts = [
        SYSTEM_INSTRUCTION.read_text().strip(),
        "\n\n# This notebook\n",
        f"`{notebook.root.name}`. Entries live at "
        f"`chapters/NN-name/YYYY-MM-DD-NN-slug.qmd`; the trailing NN orders "
        f"same-day entries. File paths you pass to the file tools are relative "
        f"to `chapters/`.\n",
        "\n# What is already recorded\n",
        "One line per entry: the stem (rule 10 links siblings by stem, never "
        "names them in prose) and the answer it reached. If something you compute "
        "contradicts one of these, that is a correction — say so in YOUR entry, "
        "stating the old value, the new one, and why they differ. Never edit the "
        "earlier entry.\n",
        "```",
        manifest.build(notebook).strip(),
        "```",
        chapter_context(notebook),
    ]
    return "\n".join(parts)


def measure(notebook):
    """
    Billed prompt tokens for the frozen prefix.

    A real call, because count_tokens rejects `tools` on the Gemini API. Below
    4,096 nothing caches and no error is raised, so this is not optional.
    """
    from .session import Session
    from .tools import build as build_tools
    from .tools.mcp_fs import FileSystem
    from .client import config, complete
    from .cache import FLOOR

    text = build(notebook)
    fs = FileSystem(notebook.chapters_dir).start()
    try:
        tools, _ = build_tools(Session(notebook, "measure"), fs)
        base = complete("x", config(max_output_tokens=1)).usage_metadata.prompt_token_count
        full = complete("x", config(tools=tools, system_instruction=text,
                                    max_output_tokens=1)
                        ).usage_metadata.prompt_token_count
        only_tools = complete("x", config(tools=tools, max_output_tokens=1)
                              ).usage_metadata.prompt_token_count - base
    finally:
        fs.stop()
    return {"chars": len(text), "prefix": full, "tools": only_tools,
            "system_and_context": full - only_tools - base,
            "floor": FLOOR, "clears": full >= FLOOR}


def main(argv):
    if not argv:
        print("usage: python -m nb.prefix <notebook> [--measure]")
        return 2
    notebook = Notebook(argv[0])
    if "--measure" in argv:
        m = measure(notebook)
        print(f"  chars               {m['chars']:>7,}")
        print(f"  tool declarations   {m['tools']:>7,}")
        print(f"  system + context    {m['system_and_context']:>7,}")
        print(f"  PREFIX              {m['prefix']:>7,}   floor {m['floor']:,}")
        print(f"\n  {'clears by ' + format(m['prefix'] - m['floor'], ',') if m['clears'] else 'SHORT by ' + format(m['floor'] - m['prefix'], ',')} tokens")
        return 0 if m["clears"] else 1
    print(build(notebook))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
