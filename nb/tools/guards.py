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


# The only files a run may write. Everything else is scratch, and scratch goes
# to `probe`, which runs in the run directory and writes nothing into the
# notebook.
#
# Measured, on the first X-Wing entry: fourteen turns writing `test.py`,
# `test2.py` and `test3.py` into `chapters/` and running them through `bash` to
# find out what `draw_three_view()` returns -- then a cleanup `rm` that silently
# removed nothing, because `bash` runs in the repo root and those paths meant
# something else there. The stuck detector never fired and could not: a
# successful `write_file` is progress by its definition, so every throwaway file
# reset the counter.
#
# A path allowlist rather than gating the TOOL on run state. The tool stays
# declared and the handler refuses, which is cache-safe -- tools render at
# prefix position 0, so removing one mid-conversation invalidates the cached
# prefix from that point. Refusing costs nothing there.
WRITABLE = ("_model.py", "_analysis.py", "_inputs.yml", "_fork.yml",
            "index.qmd", "_model.qmd")


def _allowed(session, path):
    """(ok, why not) for a write to `path`, which is relative to chapters/."""
    import lint
    notebook = session.notebook
    # NOTHING IS WRITTEN BEFORE THE CHAPTER IS SETTLED. `open_chapter` is where
    # the `--chapter` pin is enforced, where a new chapter stops for approval,
    # where the lock is claimed and where the shared modules are snapshotted
    # for the refactor gate -- so a write that arrives before it has bypassed
    # all four, and the snapshot in particular would then include the model's
    # own edits and report that nothing moved.
    if not session.chapter_open:
        return False, ("no chapter is open. Call `open_chapter` first -- it "
                       "settles which aircraft this is about, claims the "
                       "chapter so two runs cannot edit it at once, and stops "
                       "for the user's approval if it is a new one. Until it "
                       "has run there is nowhere for this to go")
    parts = [p for p in str(path).strip("/").split("/") if p]
    if len(parts) != 2:
        return False, (f"writes go inside a chapter, as `<chapter>/<file>`. "
                       f"{path!r} is not one")
    chapter, name = parts
    if chapter != session.chapter:
        return False, (f"this run opened chapters/{session.chapter}, and "
                       f"{path!r} is not in it. One question, one chapter: a "
                       f"write into another is either a refactor of somebody "
                       f"else's work or a misroute, and both want a different "
                       f"ask")
    if name in WRITABLE or lint.ENTRY_FILE.match(name):
        return True, ""
    return False, (
        f"{name!r} is not a file this notebook keeps. A chapter holds "
        f"{', '.join(WRITABLE)} and its dated entries, and nothing else.\n"
        f"If you are trying something out, that is `probe`: it runs your Python "
        f"in the run directory with the chapter already loaded, prints what you "
        f"ask it to, and writes nothing here. Scratch files in the source tree "
        f"get committed or forgotten, and one run left three of each.")


def wrap_writes(handlers, session):
    """Refuse a write outside the chapter's own files, or to `_model.py` in an
    established chapter."""
    notebook = session.notebook

    def guard(name, inner):
        def call(**kw):
            path = kw.get("path", "")
            chapter = str(path).strip("/").split("/")[0] if path else None
            ok, why = _allowed(session, path)
            if not ok:
                return {"error": f"refused: {why}"}
            if not session.allow_refactor and _guarded(notebook, chapter, path):
                n = len(notebook.entries(chapter))
                return {"error":
                        f"refused: chapters/{chapter}/_model.py already has "
                        f"{n} entr{'y' if n == 1 else 'ies'} built on it, so "
                        f"changing it is a refactor, not an entry. Every one of "
                        f"them would have to be re-solved to prove the answers "
                        f"did not move. Either write this entry against the "
                        f"vehicle as it is, or call request_refactor to say why "
                        f"it must change -- that stops the run for approval."}
            # Every successful write, counted. `lint_chapter` compares this
            # against the count at its last call, so it can say "nothing has
            # changed" instead of re-deriving the same answer: write runs spend
            # 2-5 lint calls in 8-16 turns, and the transcript shows
            # consecutive calls with no edit between them.
            out = inner(**kw)
            if not (isinstance(out, dict) and out.get("error")):
                session.writes = getattr(session, "writes", 0) + 1
            return out
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
