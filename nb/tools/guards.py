"""
What the agent may not write, and why refusing beats predicting.

Editing a chapter's `_model.py` when the chapter already has entries is a
REFACTOR, not an entry: every sibling execs that file through `_model.qmd`, and
Quarto's freeze tracks the page rather than its includes, so their committed
output silently stops matching the code that produces it. `check.py` exists to
prove a refactor moved nothing -- it deletes the freeze, re-renders and diffs --
and for a seven-entry chapter that is tens of minutes of re-solving.

That cost is worth approving BEFORE it is paid, which makes it one of the two
stops that survive the gate's removal. The problem is that the agent cannot
predict it will touch `_model.py` until it is writing, and asking it to predict
yields the quality of `render_cost_s: 0.0`.

So do not predict -- refuse at the boundary. The agent then either adapts and
writes the entry without touching the vehicle, or declares that it genuinely
needs the refactor, and the run stops with the price attached. The stop happens
because the agent was refused, not because anything guessed.

`_analysis.py` is deliberately NOT guarded here. Adding a function is additive
and safe -- rule 2 promotion explicitly leaves sibling entries untouched -- and
telling an add from a body change needs the post-edit content, which `edit_file`
does not hand over. It is caught after the fact instead, by comparing function
bodies before and after the loop and running `check` if any moved.
"""

import ast


def _guarded(notebook, chapter, path):
    """Is `path` this chapter's `_model.py`, in a chapter that has entries?"""
    if not str(path).endswith("_model.py"):
        return False
    return bool(notebook.entries(chapter)) if chapter else False


def wrap_writes(handlers, session):
    """Refuse `_model.py` writes in an established chapter, unless allowed."""
    notebook = session.notebook

    def guard(name, inner):
        def call(**kw):
            path = kw.get("path", "")
            chapter = str(path).strip("/").split("/")[0] if path else None
            if (not getattr(session, "allow_refactor", False)
                    and _guarded(notebook, chapter, path)):
                n = len(notebook.entries(chapter))
                return {"error":
                        f"refused: chapters/{chapter}/_model.py already has "
                        f"{n} entr{'y' if n == 1 else 'ies'} built on it, so "
                        f"changing it is a refactor, not an entry. Every one of "
                        f"them would have to be re-solved to prove the answers "
                        f"did not move. Either write this entry against the "
                        f"vehicle as it is, or call request_refactor to say why "
                        f"it must change -- that stops the run for approval."}
            return inner(**kw)
        return call

    return {n: (guard(n, h) if n in ("edit_file", "write_file") else h)
            for n, h in handlers.items()}


def bodies(path):
    """{name: source} for every top-level function, or {} if unreadable."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return {}
    return {n.name: ast.unparse(n) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def changed_bodies(before, after):
    """Names present in both whose source moved -- an edit, not an addition."""
    return sorted(n for n in before if n in after and before[n] != after[n])
