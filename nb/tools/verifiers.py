"""
lint / render / check -- the deterministic half, wrapped as tools.

These are the vendored scripts, called rather than reimplemented. `lint.check()`
returns structured tuples so it is called directly; `check.main()` only prints,
so its stdout is captured the same way check.py captures lint's.
"""

import contextlib
import io
import subprocess

from ..config import Notebook
from ..text import tail
from ..log import say


def _problems(root, chapters):
    """
    (blocking, warnings) as message strings.

    There is no rule number anywhere in lint's output -- the message string IS
    the unit, and `"(warning)"` is an in-string marker rather than a field, so
    severity is split exactly the way check.py splits it.
    """
    import lint
    blocking, warnings = [], []
    for where, msg in lint.check(root, chapters):
        label = "" if where is None else f"{where.name}: "
        (warnings if "(warning)" in msg else blocking).append(f"{label}{msg}")
    return blocking, warnings


def lint_chapter(notebook, chapter):
    """
    Lint one chapter. Scoped to the chapter, not the entry, because rule 2
    (repeated code) and rule 10 (sibling links) are cross-entry by nature.
    """
    blocking, warnings = _problems(notebook.root, [chapter])
    if not blocking and not warnings:
        return "lint clean."
    out = []
    if blocking:
        out.append(f"{len(blocking)} blocking problem(s) -- fix all of these:")
        out += [f"  {p}" for p in blocking]
    if warnings:
        out.append(f"{len(warnings)} warning(s), not blocking:")
        out += [f"  {w}" for w in warnings]
    return tail("\n".join(out))


def is_clean(notebook, chapter):
    """True when nothing blocking remains. The mandatory step after the loop."""
    blocking, _ = _problems(notebook.root, [chapter])
    return not blocking, blocking


def render(notebook, target=""):
    """
    `quarto render`. Target may be a chapter or a single entry path; empty
    renders the whole notebook.

    Quarto's freeze tracks the page, not its includes, so this alone will happily
    serve a cached result for an entry whose `_model.py` changed underneath it.
    That is what `check` is for.
    """
    path = notebook.root if not target else notebook.root / target
    # Deadlined: a wedged Jupyter kernel used to hang here forever, the same
    # shape as the socket that hung a run for four hours. lint.render_quarto
    # sizes the deadline from what will actually execute and names the page it
    # died on.
    import lint
    # Announced before it starts, so `nb watch` knows how long silence here is
    # allowed to last. Without it the watcher falls back to a flat 120 s and
    # would cry wolf over an honest 200 s render.
    # From the SAME path render_quarto will deadline on. Computed from the root
    # here once, it announced a project-sized number for a one-page render --
    # 90 s against the 60 s actually enforced, which is worse than saying
    # nothing, since `nb watch` sizes its staleness warning on this line.
    deadline = lint.render_deadline(notebook.root, path)
    todo = [q for q in lint.unfrozen(
                notebook.root,
                sorted(d.name for d in (notebook.root / "chapters").iterdir()
                       if d.is_dir()))
            if path == notebook.root or q == path or path in q.parents]
    say(f"  render    deadline {deadline:.0f} s ({len(todo)} page(s) to execute)")
    r = lint.render_quarto(path, notebook.root, cwd=notebook.root)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        return tail(f"render ok.\n{out}", 2000)
    return tail(f"render FAILED (exit {r.returncode}):\n{out}")


def check(notebook, chapter="", force_all=False, no_render=False):
    """
    The full gate: lint, discard the invalidated freezes, render, lint again,
    then diff the rendered values and figures against git.

    Deleting the freeze is not optional -- freeze tracks the page and not its
    includes, so without it a fresh render is compared against a cache hit and
    the match is an artefact. There is no flag to skip it.
    """
    import check as check_mod
    argv = [str(notebook.root)]
    if chapter:
        argv.append(chapter)
    if no_render:
        argv.append("--no-render")
    if force_all:
        argv.append("--all")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = check_mod.main(argv)
    return tail(f"check exit={code}\n{buf.getvalue()}")
