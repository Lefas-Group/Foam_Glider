"""
`nb new` -- scaffold a notebook, then prove it.

Creating a notebook is a deliberate act: a second notebook is a second aircraft,
and `references/forking.md` treats that as a decision, not a convenience. So this
is a command you run rather than something the agent can reach -- there is no
`new_notebook` route, and `create_chapter` is not a tool either.

What makes it worth a command rather than a documented procedure is the failure
mode. `_notebook.py` and `_scratch/_probe_base.py` are VENDORED into every
notebook -- Quarto execs them at render time, so a notebook must render without
`nb` installed -- and lint rule 11 requires them byte-identical to the copies in
`vendor/`. Copied by hand, a stray edit or a truncated paste is silent until the
first lint run. Copied here, they cannot drift, and the command lints and
preflights before it returns.
"""

import pathlib
import shutil
import sys

from ..config import SCAFFOLD, VENDOR, Notebook
from ..tools.scaffold import NAME as CHAPTER_NAME
from ..tools.scaffold import create_chapter
from ..log import say, tell

# `_freeze/chapters/` is deliberately NOT here -- committing it is what lets a
# fresh clone render without re-solving. Everything else Quarto writes is a build
# artefact: the first notebook to get a project render put 22 of them into
# history, including a 180 KB icon font.
GITIGNORE = ("/.quarto/\n"
             "**/*.quarto_ipynb\n"
             "/_site/\n"
             "/_freeze/site_libs/\n")

# Rule 11: vendored, and checked byte-for-byte. The tuple order is
# (canonical in vendor/, destination in the new notebook).
VENDORED = (("notebook.py", "_notebook.py"),
            ("probe_base.py", "_scratch/_probe_base.py"))


def _render(name, title, subject, chapter):
    """Template substitution. Kept blunt on purpose -- these are four files."""
    return (name.replace("<Project>", title)
                .replace("<the aircraft>", subject)
                .replace("NN-name", chapter))


def main(path, title=None, subject=None, chapter="01-first-chapter",
         chapter_title="First chapter", verbose=True):
    root = pathlib.Path(path).resolve()
    if root.exists() and any(root.iterdir()):
        tell(f"  {root} exists and is not empty")
        return 1
    if not CHAPTER_NAME.match(chapter):
        tell(f"  {chapter!r} is not NN-kebab-case, e.g. '01-first-chapter'")
        return 1
    # The first chapter of a new notebook is 01 by construction. Normalise here
    # rather than let create_chapter renumber later -- the name is substituted
    # into _quarto.yml and the probe scaffold below, before it is created.
    chapter = "01-" + chapter[3:]

    title = title or root.name.replace("-", " ").title()
    subject = subject or "the aircraft"

    (root / "chapters").mkdir(parents=True)
    (root / "_scratch").mkdir(parents=True)

    for canonical, dest in VENDORED:
        shutil.copy(VENDOR / canonical, root / dest)

    (root / ".gitignore").write_text(GITIGNORE)
    for tmpl, dest in (("_quarto.yml.tmpl", "_quarto.yml"),
                       ("styles.css.tmpl", "styles.css"),
                       ("probe.qmd.tmpl", "_scratch/probe.qmd"),
                       ("probe.py.tmpl", "_scratch/probe.py")):
        (root / dest).write_text(
            _render((SCAFFOLD / tmpl).read_text(), title, subject, chapter))

    notebook = Notebook(root)
    # claim=False: there is nothing to claim in a notebook this command just
    # made, and the chapter name here is the caller's, not a model's guess.
    # No `defines`: the placeholder create_chapter substitutes instead is also
    # the marker that says this chapter is still claimable.
    chapter, msg = create_chapter(notebook, chapter, chapter_title, claim=False)
    if msg.startswith("rejected"):
        tell(f"  {msg}")
        return 1

    if verbose:
        tell(f"  created   {root}")
        tell(f"  vendored  {', '.join(d for _, d in VENDORED)}  (rule 11)")
        tell(f"  chapter   chapters/{chapter}/")

    # Prove it rather than claim it. A notebook that does not lint is a notebook
    # whose first `nb ask` fails at preflight, several minutes later.
    import lint
    problems = [m for _, m in lint.check(root, [chapter]) if "(warning)" not in m]
    tell(f"  lint      {'clean' if not problems else f'{len(problems)} problem(s)'}")
    for m in problems:
        tell(f"              {m}")

    from ..preflight import check as preflight
    bad = [b for b in preflight(root) if "GEMINI_API_KEY" not in b]
    tell(f"  preflight {'ok' if not bad else 'FAILED'}")
    for b in bad:
        tell(f"              {b}")

    if not problems and not bad:
        tell(f"\n  Fill chapters/{chapter}/_model.py with the vehicle, and say in"
              f"\n  its index.qmd what defines the chapter. Then:"
              f"\n\n    uv run --group nb python -m nb ask {root.name} \"<question>\"\n")
    return 1 if (problems or bad) else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
