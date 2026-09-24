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
import re
import shutil
import subprocess
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
             "/_freeze/site_libs/\n"
             # Quarto writes a <page>-listing.json beside every page carrying a
             # listing: build output, regenerated on every render, and it churns.
             "**/*-listing.json\n"
             # Per-run working state: probe scripts, logs, run.json, the
             # render lock. This repo's root .gitignore already covers it, so
             # a notebook created HERE was fine by accident -- one created in a
             # sibling directory, which `nb new` exists to support, would have
             # committed a directory per run.
             # CONTENTS, not the directory: a negation cannot re-include a
             # file whose parent directory is excluded.
             "/_scratch/*\n"
             # Except the vendored probe base. Rule 11 requires it and
             # preflight refuses to start without it, so a notebook that does
             # not commit it cannot be run from a fresh clone at all.
             "!/_scratch/_probe_base.py\n")

# Rule 11: vendored, and checked byte-for-byte. The tuple order is
# (canonical in vendor/, destination in the new notebook).
VENDORED = (("notebook.py", "_notebook.py"),
            ("probe_base.py", "_scratch/_probe_base.py"))


def _render(name, title, subject, chapter):
    """Template substitution. Kept blunt on purpose -- these are four files."""
    return (name.replace("<Project>", title)
                .replace("<the aircraft>", subject)
                .replace("NN-name", chapter))


def _slug(text, taken):
    """A short, unique id for a brief item, from its first few words."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"\*\*", " ", text.lower()))
    base = "-".join(words[:3])[:28].strip("-") or "item"
    slug, n = base, 1
    while slug in taken:
        n += 1
        slug = f"{base}-{n}"
    taken.add(slug)
    return slug


def _brief(specs, assumes):
    """The root `_inputs.yml` body, or "" to leave the template placeholders."""
    if not specs and not assumes:
        return ""
    taken = set()
    out = []
    for key, rows in (("specified", specs), ("assumed", assumes)):
        if not rows:
            continue
        out.append(f"{key}:")
        for text in rows:
            text = " ".join(str(text).split())
            out.append(f'  - {_slug(text, taken)}: "{text}"')
    return "\n".join(out) + "\n"


def main(path, title=None, subject=None, chapter="01-first-chapter",
         chapter_title="First chapter", verbose=True,
         specs=(), assumes=()):
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
    # THE TITLE IS SUBSTITUTED INTO FOUR FILES BY BLIND STRING REPLACEMENT, and
    # `_render` is deliberately blunt about it. Nothing downstream catches a bad
    # one: rule 24's placeholder regex looks for `<...>`, so a title carrying a
    # shell comment renders, lints clean and ships. RADICAL-GLIDER did exactly
    # that -- `_quarto.yml` still reads
    #
    #     title: "RADICAL GLIDER # once per aircraft Notebook"
    #
    # from a command whose trailing comment landed inside the quotes. It is the
    # site's heading, the browser tab and the description, and it is wrong in
    # git for ever unless someone notices by eye.
    #
    # Refused rather than sanitised: stripping to the `#` would be a guess at
    # what was meant, and the answer is one keystroke away at the prompt. `"`
    # is here because these are YAML values, and a newline because it is a
    # title.
    bad = [c for c in ('#', '"', '\n', '\r') if c in title]
    if bad or not title.strip() or len(title) > 60:
        why = (f"contains {', '.join(repr(c) for c in bad)}" if bad
               else "is empty" if not title.strip()
               else f"is {len(title)} characters, and 60 is the cap")
        tell(f"  the title {why}: {title!r}")
        tell("  It becomes the site heading, the browser tab and the "
             "description, in four files.")
        tell('  Quote it as one argument:  nb new <dir> "Radical Glider"')
        return 1

    (root / "chapters").mkdir(parents=True)
    (root / "_scratch").mkdir(parents=True)

    for canonical, dest in VENDORED:
        shutil.copy(VENDOR / canonical, root / dest)

    (root / ".gitignore").write_text(GITIGNORE)
    # No probe scaffold: `tools/probe.py` writes its own `_scratch/_nb_probe.py`
    # and imports `_probe_base`, so the `probe.qmd`/`probe.py` pair the skill
    # used was never read by this system. A person who wants to probe by hand
    # writes a file beside `_probe_base.py`, which is what the agent does.
    for tmpl, dest in (("_quarto.yml.tmpl", "_quarto.yml"),
                       ("styles.css.tmpl", "styles.css"),
                       # The site's front page. Without it Quarto serves a
                       # synthesised stub -- not a 404, but nothing that says
                       # what the aircraft is or how the chapters relate.
                       ("book-index.qmd.tmpl", "index.qmd"),
                       # The brief, as data. The front page renders it; nothing
                       # in a run writes it. Its placeholders are what rule 24
                       # sees when nobody has filled the brief in.
                       ("_inputs.root.yml.tmpl", "_inputs.yml")):
        text = _render((SCAFFOLD / tmpl).read_text(), title, subject, chapter)
        # `--spec` / `--assume`, written in place of the placeholders. The
        # prefix is built ONCE at `nb ask`, so a brief left for a hand-edit
        # afterwards is a first run with no notebook level at all -- and rule
        # 24 now watches this file, so the placeholders are a lint failure the
        # moment anything is written.
        if dest == "_inputs.yml":
            body = _brief(specs, assumes)
            if body:
                head = text.split("specified:")[0]
                text = head + body
        (root / dest).write_text(text)

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

    # PROVE IT RENDERS, not merely that it lints. "It lints" says the source
    # satisfies the contract; it says nothing about whether Quarto can execute
    # the front page, find `_notebook.py`, or resolve the sidebar -- and the
    # first notebook created by this command discovered all three inside its
    # first `nb ask`, minutes in and with an API bill attached. Nothing here
    # solves: the chapter model is a bare scaffold and the front page reads
    # source, so it is seconds.
    render = subprocess.run(["uv", "run", "quarto", "render"], cwd=root,
                            capture_output=True, text=True, timeout=600)
    ok = render.returncode == 0
    tell(f"  render    {'ok' if ok else 'FAILED'}")
    if not ok:
        for line in (render.stdout + render.stderr).strip().splitlines()[-12:]:
            tell(f"              {line}")

    if not problems and not bad and ok:
        tell(f"\n  Fill chapters/{chapter}/_model.py with the vehicle, and say in"
              f"\n  its _inputs.yml what defines the chapter. Then:"
              f"\n\n    uv run --group nb python -m nb ask {root.name} \"<question>\"\n")
    return 1 if (problems or bad or not ok) else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
