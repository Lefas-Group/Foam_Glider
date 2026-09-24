"""
What the agent may not change without asking, and why asking beats predicting.

Editing a function that a chapter's siblings already call is a REFACTOR, not an
entry: every one of them execs the shared modules through `_model.qmd`, and
Quarto's freeze tracks the page rather than its includes, so their committed
output silently stops matching the code that produces it. `check.py` exists to
prove a refactor moved nothing -- it moves the freeze aside, re-renders and
diffs -- and for a seven-entry chapter that is minutes of re-solving.

ASK BEFORE PAYING, WHICH IS THE WHOLE POINT. The gate after the loop used to be
the only one: it ran `check` (56-173 s, measured) and THEN showed the user the
diff and asked whether to accept. That is the permission question asked after
the thing it authorises has been paid for. Now the question comes at the moment
the body moves -- before the entry is built, before anything is re-solved -- and
the post-loop gate keeps its own job, which is a different question: not "may
this change happen" but "here is what it did to the answers".

IT COVERS BOTH FILES, which it did not before, and the asymmetry was the bug.
`_model.py` was guarded by a blanket refusal on any write once the chapter had
entries; `_analysis.py` was not guarded at all, because "telling an add from a
body change needs the post-edit content, which `edit_file` does not hand over".
Measured across every retained transcript: the `_model.py` guard has NEVER
fired -- three writes ever, all to chapters with zero entries, where writing is
correct -- and all three real refactors were in `_analysis.py`. The file that
asked permission never needed to; the file that needed to never asked.

The post-edit content is available one line later. So the write goes through,
the bodies are compared against the snapshot taken before the model's first
turn, and a CHANGED body is what triggers the question -- an ADDED function
triggers nothing, which is what rule 2 promotion is and is why the blanket
refusal was wrong in the other direction too.

A refusal RESTORES the file from the text read immediately before the write, so
"no" leaves the chapter exactly as it was. Rolling back from the startup
snapshot would have clobbered every legitimate addition made since.
"""

import ast
import pathlib


SHARED = ("_model.py", "_analysis.py")


def _refactor(session, path):
    """
    (names, siblings) for bodies this write CHANGED, or (None, 0).

    Compared against `session.before_bodies`, snapshotted before the model's
    first turn -- so it is the chapter as it was COMMITTED, not as the run has
    left it. Names present in both whose source moved; anything added is not a
    refactor and is not reported.
    """
    f = pathlib.Path(path)
    if f.name not in SHARED or not session.siblings:
        return None, 0
    before = session.before_bodies.get(f.name, {})
    moved = changed_bodies(before, bodies(session.notebook.chapters_dir / path))
    return (moved or None), session.siblings


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
    # NO RUN-STATE CHECK HERE ANY MORE. It used to refuse every write until
    # `open_chapter` had run, because until then nothing knew which chapter the
    # run was in or had claimed it. `--chapter` is required now and both happen
    # before the first token, so the chapter is known for the whole life of the
    # process and this is a pure path check -- no ordering, no state, nothing
    # that can be in the wrong sequence.
    parts = [p for p in str(path).strip("/").split("/") if p]
    if len(parts) != 2:
        return False, (f"writes go inside a chapter, as `<chapter>/<file>`. "
                       f"{path!r} is not one")
    chapter, name = parts
    if chapter != session.chapter:
        return False, (f"this run is in chapters/{session.chapter}, and "
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
    """Refuse a write outside the chapter's own files, and stop to ask before
    one that changes a function the chapter's siblings already call."""
    notebook = session.notebook

    def guard(name, inner):
        def call(**kw):
            path = kw.get("path", "")
            ok, why = _allowed(session, path)
            if not ok:
                return {"error": f"refused: {why}"}
            # READ BEFORE WRITING, so a refusal can put it back exactly. Only
            # for the two shared files; an entry is never rolled back.
            f = notebook.chapters_dir / str(path).strip("/")
            watched = f.name in SHARED
            restore = f.read_text() if watched and f.exists() else None

            out = inner(**kw)
            if isinstance(out, dict) and out.get("error"):
                return out

            if watched and not session.allow_refactor:
                moved, siblings = _refactor(session, path)
                if moved:
                    from .interact import approve_refactor
                    refused = approve_refactor(session, f.name, moved, siblings)
                    if refused:
                        if restore is not None:
                            f.write_text(restore)
                        return {"error": refused}
                    # Approved once, for the rest of the run: the user has
                    # agreed to re-prove this chapter, and asking again for the
                    # second function of the same fix would be asking the same
                    # question twice.
                    session.allow_refactor = True
            # Every successful write, counted. `lint_chapter` compares this
            # against the count at its last call, so it can say "nothing has
            # changed" instead of re-deriving the same answer: runs spend 2-5
            # lint calls in 8-16 turns, and the transcript shows consecutive
            # calls with no edit between them.
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
