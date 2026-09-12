"""
create_chapter -- scaffold a new chapter, from the template.

The agent triggers it but does not author it: the template is META, outside the
writable set. What the agent gets afterwards is an ordinary chapter directory
inside `chapters/`, which it then fills through the normal file tools.

A new NOTEBOOK is not offered. That wants a fresh session, which is a process
decision rather than the agent's.
"""

import re
import shutil

from ..config import SCAFFOLD

NAME = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")

# What an undescribed chapter's index carries. Doubles as the marker that nobody
# has claimed the chapter yet -- see `Notebook.claimable_stub`.
PLACEHOLDER = ("<one sentence, then a bullet list: the aero method, the section, "
               "what is left out>")
SLUG = re.compile(r"^(?:\d{2}-)?(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$")


def _number(notebook, claim):
    """
    The number the next chapter gets. Code's decision, not the model's.

    A count (`len(existing) + 1`) collides the moment a chapter is deleted or
    carries `_lint-skip`, so this takes the max. More to the point, the model
    used to supply the number and a wrong guess aborted `nb write` outright --
    after the ask had already been paid for, with no chance to correct it. The
    model owns the slug, which is judgement; the number is bookkeeping.
    """
    if claim:
        return claim[:2]
    used = [int(c[:2]) for c in notebook.chapters() if c[:2].isdigit()]
    return f"{max(used, default=0) + 1:02d}"


def create_chapter(notebook, name, title, defines="", claim=True):
    """
    Create `chapters/<name>/` with index.qmd, _model.qmd, _model.py, _analysis.py.

    `_analysis.py` starts EMPTY by design: chapter-shared helpers arrive by
    promotion from an entry that needed them a second time, never by
    anticipation.

    With `claim`, an untouched scaffold chapter is taken over rather than left
    beside the new one -- see `Notebook.claimable_stub`. Delete-and-recreate
    rather than rename, because `_model.qmd` and `index.qmd` bake the chapter
    path in; recreating reuses the templating instead of patching two files.
    """
    m = SLUG.match(name)
    if not m:
        return name, (f"rejected: {name!r}. Chapter directories are "
                      f"NN-kebab-case, e.g. '05-boom-structure'.")

    stub = notebook.claimable_stub() if claim else None
    name = f"{_number(notebook, stub)}-{m.group('slug')}"
    if not NAME.match(name):
        return name, f"rejected: {name!r} is not NN-kebab-case"

    target = notebook.chapters_dir / name
    if stub:
        shutil.rmtree(notebook.chapters_dir / stub)
        # The stub's index may already have been rendered and frozen. Left
        # behind it is a freeze for a chapter that no longer exists, which
        # nothing ever collects.
        shutil.rmtree(notebook.freeze / stub, ignore_errors=True)
    elif target.exists():
        return name, f"rejected: {target} already exists"

    target.mkdir(parents=True)
    sub = lambda s: s.replace("__CHAPTER__", name).replace("__TITLE__", title) \
        .replace("__WHAT_DEFINES_THE_CHAPTER__", defines or PLACEHOLDER)

    (target / "_model.qmd").write_text(sub((SCAFFOLD / "_model.qmd.tmpl").read_text()))
    (target / "index.qmd").write_text(sub((SCAFFOLD / "index.qmd.tmpl").read_text()))
    (target / "_model.py").write_text((SCAFFOLD / "_model.py.tmpl").read_text())
    (target / "_analysis.py").write_text("")

    what = (f"claimed the empty scaffold chapters/{stub}/ as chapters/{name}/"
            if stub else f"created chapters/{name}/")
    return name, (
            f"{what} with index.qmd, _model.qmd, _model.py and an empty "
            f"_analysis.py.\n\n"
            f"Put the VEHICLE in chapters/{name}/_model.py -- rule 19 requires "
            f"it, and the chapter index renders that file, so it is where a "
            f"reader looks for the aircraft. Where the vehicle is parametric, "
            f"_model.py holds a function taking the design variables and "
            f"returning the Airplane; the entry calls it. Do not restate the "
            f"geometry in the entry cell.\n\n"
            f"State in index.qmd what defines this chapter -- the aero method, "
            f"the section, what is left out. Those chapter-level assumptions "
            f"belong there and must NOT be repeated in entry prose.")
