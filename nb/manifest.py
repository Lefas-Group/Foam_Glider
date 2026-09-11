"""
The chapter manifest -- this system's substitute for memory across runs.

Under Claude Code the skill got continuity free: three entries written in one
session and the model still remembered the first while writing the third. Every
run here starts cold, so without this the agent re-derives what it learned last
run and essentially never notices it is contradicting an earlier entry.

One line per entry, carrying the stem (rule 10 links siblings by stem, never
names them in prose) and the hero value (which is what makes a contradiction
visible: an earlier entry reporting 8.4 s for something just computed as 6.1 s).

Read from the RENDERED freeze rather than the source, because the source holds
`{python} f"{res['duration']:.1f} s"` where the freeze holds `3.0 s`. Generated
on every commit; never hand-maintained.
"""

import json
import re
import sys

from .config import Notebook
from . import budgets

TITLE = re.compile(r'^title:\s*"(.+)"\s*$', re.M)
HERO = re.compile(r"\[([^\]]*)\]\{\.hero-value\}")


def _unescape(s):
    """Pandoc escapes punctuation in rendered markdown: `3\\.0 s` -> `3.0 s`."""
    return re.sub(r"\\(.)", r"\1", s).strip()


def _rendered(notebook, chapter, stem):
    p = notebook.freeze / chapter / stem / "execute-results" / "html.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())["result"]["markdown"]
    except (ValueError, KeyError):
        return None


def _title(text):
    m = TITLE.search(text or "")
    return m.group(1) if m else ""


def entry_line(notebook, chapter, path):
    stem = path.stem
    title = _title(path.read_text())
    md = _rendered(notebook, chapter, stem)
    if md is None:
        answer = "(not yet rendered)"
    else:
        # `.hero-pair` carries two; an entry whose answer is a figure or a
        # yes/no carries none, and that is a legitimate state, not a gap.
        heroes = [_unescape(h) for h in HERO.findall(md)]
        answer = " vs ".join(heroes) if heroes else "(no hero)"
    return stem, title, answer


def build(notebook):
    """The manifest, as the text that goes into the cached prefix."""
    out = []
    for chapter in notebook.chapters():
        index = notebook.chapters_dir / chapter / "index.qmd"
        title = _title(index.read_text()) if index.exists() else ""
        ceiling = budgets.entry_ceiling(notebook, chapter)
        note = f"  [entry ceiling {ceiling:.0f} s]" if ceiling else ""
        out.append(f'{chapter} — "{title}"{note}')
        for path in notebook.entries(chapter):
            stem, etitle, answer = entry_line(notebook, chapter, path)
            out.append(f"  {stem}")
            out.append(f"      {etitle}  →  {answer}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv):
    if not argv:
        print("usage: python -m nb.manifest <notebook>")
        return 2
    notebook = Notebook(argv[0])
    text = build(notebook)
    print(text)
    n = sum(len(notebook.entries(c)) for c in notebook.chapters())
    print(f"--- {n} entries, {len(notebook.chapters())} chapters, "
          f"{len(text)} chars", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
