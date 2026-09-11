"""
create_chapter -- scaffold a new chapter, from the template.

The agent triggers it but does not author it: the template is META, outside the
writable set. What the agent gets afterwards is an ordinary chapter directory
inside `chapters/`, which it then fills through the normal file tools.

A new NOTEBOOK is not offered. That wants a fresh session, which is a process
decision rather than the agent's.
"""

import re

from ..config import SCAFFOLD

NAME = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


def create_chapter(notebook, name, title, defines=""):
    """
    Create `chapters/<name>/` with index.qmd, _model.qmd, _model.py, _analysis.py.

    `_analysis.py` starts EMPTY by design: chapter-shared helpers arrive by
    promotion from an entry that needed them a second time, never by
    anticipation.
    """
    if not NAME.match(name):
        return (f"rejected: {name!r}. Chapter directories are NN-kebab-case, "
                f"numbered in creation order, e.g. '05-boom-structure'.")

    target = notebook.chapters_dir / name
    if target.exists():
        return f"rejected: {target} already exists"

    existing = notebook.chapters()
    expected = f"{len(existing) + 1:02d}"
    if not name.startswith(expected):
        return (f"rejected: {name!r}. The next chapter is {expected}-... "
                f"(existing: {', '.join(existing)})")

    target.mkdir(parents=True)
    sub = lambda s: s.replace("__CHAPTER__", name).replace("__TITLE__", title) \
        .replace("__WHAT_DEFINES_THE_CHAPTER__",
                 defines or "<one sentence, then a bullet list: the aero method, "
                            "the section, what is left out>")

    (target / "_model.qmd").write_text(sub((SCAFFOLD / "_model.qmd.tmpl").read_text()))
    (target / "index.qmd").write_text(sub((SCAFFOLD / "index.qmd.tmpl").read_text()))
    (target / "_model.py").write_text((SCAFFOLD / "_model.py.tmpl").read_text())
    (target / "_analysis.py").write_text("")

    return (f"created chapters/{name}/ with index.qmd, _model.qmd, _model.py and "
            f"an empty _analysis.py. Fill _model.py with the vehicle, and state "
            f"in index.qmd what defines this chapter -- the aero method, the "
            f"section, what is left out. Those chapter-level assumptions belong "
            f"there and must NOT be repeated in entry prose.")
