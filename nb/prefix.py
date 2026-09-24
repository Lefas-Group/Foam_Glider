"""
The cached prefix: system instruction, then everything about this notebook that
does not change during a run.

Whole-notebook, not just the target chapter. All four `index.qmd` come to ~1,900
tokens and all four signature lists to ~1,200 -- cheap, and it makes the prefix
IDENTICAL for every run in the notebook, so one cache object serves them all
until the manifest changes. The chapter IS known before the prefix is built now
-- `--chapter` is required and settled at startup -- which is what let the
chapter's own `_model.py` be appended to it (see `this_chapter`). Scoping the
rest of the prefix to one chapter's lineage is the obvious next step and is not
taken yet: the shared head is 70% of it and caches identically for every run in
the notebook, so the saving is real but small until the manifest grows.

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
    # OSError as well as SyntaxError: under parallel runs the chapter directory
    # may be renamed out from under this read -- claiming a stub is a rename --
    # and an inspection losing its target means "not this one", not a crash.
    try:
        text = path.read_text()
    except OSError:
        return [], []
    if not text.strip():
        return [], []
    try:
        tree = ast.parse(text)
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


def notebook_context(notebook):
    """
    The front page's input callouts -- what is true of the WHOLE aircraft.

    They were in no prompt at all. Measured on `glider-notebook`: the prefix ran
    to 35,555 characters and contained none of "300 mm, fixed tip to tip",
    "Still air" or "Rigid airframe". Every chapter's `index.qmd` was quoted in
    full and the notebook's own was not, so the level that everything inherits
    was the one level the model never saw.

    Nothing else covered it. `_inputs_notice` reports a COUNT, for one chapter.
    `inputs.inherited` reads this page only for a chapter with no parent, which
    no fork ever is. And no chapter index restates a notebook-level item -- also
    measured, zero of six.

    The one surviving trace was the code, badly: chapter 05's `_model.py`
    exposes no top-level constants at all, and the 300 mm span lives as the bare
    literal `0.15` three times inside the builder. So the aircraft's first
    Specified commitment reached the model as an unnamed magic number, with
    nothing to say it was fixed rather than free.

    Callouts only, not the whole page: the rest is the generated lineage
    diagram, which is a picture of the chapters the manifest already lists.
    """
    import lint
    items = lint.notebook_items(notebook.root)
    if not items:
        return ""
    out = ["\n## The aircraft — true of EVERY chapter\n",
           "Stated once, in the notebook's `_inputs.yml`, and inherited by "
           "everything below. Nothing supersedes them: a fork that departs "
           "from one is a different aircraft, and so a different notebook. You "
           "do not restate these in a chapter or an entry, and you do not "
           "change one without `ask_specified`.\n"]
    for kind in ("Specified", "Assumed"):
        rows = [t for k, t in items if k == kind]
        if rows:
            out.append(f"{kind}:")
            out += [f"  - {t}" for t in rows]
            out.append("")
    return "\n".join(out)


def chapter_context(notebook):
    """
    Each chapter, as DATA: what it is, what it forked from, what it declares.

    It used to quote `index.qmd` up to `## The model`, which stopped working
    the moment the items became data. Measured on this notebook: 793 tokens of
    listing configuration, an include directive and two generated cells, under
    a heading reading "what defines this chapter", containing 237 tokens of
    real content and not one specification. The page is for a reader; the model
    wants the register.

    IDS ARE SHOWN, because they are how the model names an item it is changing
    -- `ask_specified(replaces=...)` and `_fork.yml`'s `overwrites:` both take
    one, and a handle you cannot see is a handle you cannot use.
    """
    import re
    import lint
    out = []
    for chapter in notebook.chapters():
        d = notebook.chapters_dir / chapter
        title = ""
        index = d / "index.qmd"
        if index.exists():
            m = re.search(r'^title:\s*"(.+)"\s*$', index.read_text(), re.M)
            title = m.group(1) if m else ""
        out.append(f"\n## chapters/{chapter}" + (f' — "{title}"' if title else ""))
        defines = lint.defines(notebook.root, chapter)
        if defines:
            out.append(f"\n{defines}")
        fork = lint.read_fork(notebook.root, chapter) or {}
        if fork.get("parent"):
            out.append(f"Forked from {fork['parent']}"
                       + (f" — {fork['summary']}" if fork.get("summary") else ""))

        data = lint.read_inputs(notebook.root, chapter)
        declared = lint.declared_items(notebook.root, chapter)
        if declared:
            out.append("\n### Committed to by this chapter. Inherited by every "
                       "entry in it, and never restated in one.\n")
            for key, label in (("specified", "Specified"), ("assumed", "Assumed")):
                rows = data.get(key) or []
                if rows:
                    out.append(f"{label}:")
                    out += [f"    {i}: {t}" for i, t in rows]
            if not data:
                # A chapter still on hand-written callouts -- the frozen corpus.
                for kind, text in declared:
                    out.append(f"    [{kind}] {text}")
            out.append("")
        else:
            out.append("\n    (declares nothing yet)\n")

        funcs, consts = module_summary(d / "_model.py")
        out.append("### _model.py — the vehicle. These names are in scope in a "
                   "probe of this chapter\n")
        if consts:
            out += consts
        if funcs:
            out.append("")
            out += funcs
        if not funcs and not consts:
            # Not just "(empty)": a scaffolded `_model.py` and a deliberately
            # empty one summarise identically, and the first time that happened
            # the model read `(empty)` as a statement of fact and wrote the whole
            # vehicle inline instead. Rule 19 now enforces this, but the prefix
            # is where the model finds out before it costs a lint round.
            out.append("    (empty — scaffolded; the vehicle belongs here)")
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


def this_chapter(notebook, chapter):
    """
    The assigned chapter's `_model.py`, in full. LAST in the prefix.

    It was never here before, and could not be: the prefix is built once,
    before turn 1, and until `--chapter` became mandatory nothing knew which
    chapter the run was in. So the vehicle -- the single thing a question is
    most about -- was the one file the model had to go and fetch. Measured
    across every retained transcript: `_model.py` is 13 of 50 `read_text_file`
    calls, second only to `_analysis.py`, while the brief told it not to go
    looking for what it had already been given. The brief was wrong, and this
    is the half that makes it right.

    It is CHEAP. Mean `_model.py` across this project's chapters is 1,429
    characters, ~357 tokens, and it is cached at a measured 67%.

    APPENDED, never inserted. Everything above it is identical for every run in
    the notebook, so the implicit cache matches the whole shared head and
    diverges only here -- which is the cheapest place for a per-run difference
    to live.
    """
    src = notebook.chapters_dir / chapter / "_model.py"
    try:
        text = src.read_text().strip()
    except OSError:
        return ""
    if not text:
        return ""
    return (f"\n# The vehicle you are working on\n\n"
            f"`chapters/{chapter}/_model.py`, in full. `_model.qmd` execs it "
            f"into every page in the chapter, so every name below is already "
            f"in scope in your entry cell -- it is not a module and importing "
            f"it is rule 29. Do not read this file; it is here.\n\n"
            f"```python\n{text}\n```\n")


def build(notebook, chapter=None):
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
        notebook_context(notebook),
        chapter_context(notebook),
    ]
    if chapter:
        parts.append(this_chapter(notebook, chapter))
    return "\n".join(parts)


def measure(notebook):
    """
    Billed prompt tokens for the frozen prefix.

    A real call, because count_tokens rejects `tools` on the Gemini API.

    The 4,096-token floor it used to check belonged to the EXPLICIT cache, which
    is gone. Implicit caching has the same floor on Gemini 3.x, so the number is
    still the one to beat -- but nothing now depends on clearing it, and falling
    under it costs a worse hit rate rather than no cache at all.
    """
    FLOOR = 4096
    from .session import Session
    from .tools import build as build_tools
    from .tools.mcp_fs import FileSystem
    from .client import config, complete

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
        print("usage: uv run --group nb python -m nb.prefix <notebook> [--measure]")
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
