"""
`nb inputs` -- every Specified and Assumed item the notebook has recorded.

This is the design state of the aircraft: what has been decided, what has been
guessed, and which entry is responsible for each. It exists only as scattered
callouts today -- one entry at a time, readable only by opening the page -- so
nothing answers "what have we assumed about this aircraft" without reading the
whole notebook.

Read from the RENDERED freeze rather than the source, for the same reason the
manifest is: the source holds `{python} f"{sm:.2f}"` where the freeze holds
`0.10`. An item whose value is computed is unreadable in the source.

Costs nothing and asks nothing. It is a read over what the entries already say,
which is why it is worth having before there is any coordinator to hold a
register: the register described in the multi-instance plan is this, plus the
ability to answer back.
"""

import json
import re
import sys

from .config import Notebook

CALLOUT = re.compile(
    r"^::: *\{\.callout-[a-z]+\}\s*\n##\s*(Specified|Assumed)\s*\n(.*?)^:::",
    re.S | re.M)
ITEM = re.compile(r"^\s*\d+\.\s*(.+?)\s*$", re.M)


def _unescape(s):
    """Pandoc escapes punctuation in rendered markdown: `5\\.7%` -> `5.7%`."""
    return re.sub(r"\\(.)", r"\1", s).strip()


def _rendered(notebook, chapter, stem):
    p = notebook.freeze / chapter / stem / "execute-results" / "html.json"
    try:
        return json.loads(p.read_text())["result"]["markdown"]
    except (OSError, ValueError, KeyError):
        return None


def collect(notebook):
    """[(chapter, where, kind, item)] across every entry and chapter index."""
    out = []
    for chapter in notebook.chapters():
        pages = [("index", notebook.chapters_dir / chapter / "index.qmd")]
        pages += [(e.stem, e) for e in notebook.entries(chapter)]
        for stem, path in pages:
            md = _rendered(notebook, chapter, stem)
            if md is None:
                # The chapter index is often unfrozen; its callouts carry no
                # computed values except the solve budget, so the source is a
                # fair fallback there.
                try:
                    md = path.read_text()
                except OSError:
                    continue
            for kind, body in CALLOUT.findall(md):
                for item in ITEM.findall(body):
                    out.append((chapter, stem, kind, _unescape(item)))
    return out


def main(argv):
    if not argv:
        print("usage: python -m nb.inputs <notebook>")
        return 2
    notebook = Notebook(argv[0])
    rows = collect(notebook)
    if not rows:
        print("  nothing recorded yet")
        return 0

    chapter = None
    for c, where, kind, item in rows:
        if c != chapter:
            chapter = c
            print(f"\n{c}")
        label = "SPECIFIED" if kind == "Specified" else "assumed  "
        print(f"  {label}  {item}")
        print(f"             {where}")
    n_spec = sum(1 for r in rows if r[2] == "Specified")
    print(f"\n  {n_spec} specified, {len(rows) - n_spec} assumed, "
          f"across {len(set(r[0] for r in rows))} chapter(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
