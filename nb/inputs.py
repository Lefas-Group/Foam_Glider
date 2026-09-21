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

# Every heading these callouts have gone by. The notebook front page says
# INITIAL -- it is what everything inherits; a chapter or entry says NEW -- it
# lists only what that page introduced; and the two frozen notebooks still say
# Specified/Assumed. All three are read, and the kind is normalised, because a
# parser that knew one vocabulary would silently return nothing for the others
# and the inheritance gate would offer an empty list.
CALLOUT = re.compile(
    r"^::: *\{\.callout-[a-z]+\}\s*\n##\s*"
    r"(?:New |Initial )?(specifications?|user specifications|assumptions|"
    r"Specified|Assumed)\s*\n(.*?)^:::",
    re.S | re.M | re.I)
ITEM = re.compile(r"^\s*\d+\.\s*(.+?)\s*$", re.M)


def _kind(heading):
    """`Specified` or `Assumed`, whichever vocabulary said it."""
    return "Assumed" if "assum" in heading.lower() else "Specified"


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
                    out.append((chapter, stem, _kind(kind), _unescape(item)))
    return out


def declared(notebook, chapter):
    """
    (specified, assumed) counts for ONE chapter's index.

    The chapter's own declarations, not its entries': what the chapter was
    given and what it guessed, which is the set an entry inherits rather than
    restates (`system_instruction.md`, "assumptions sit at the level they
    belong to"). Zero for a chapter whose index declares nothing -- two of the
    thirteen written so far, both predating the callouts.
    """
    index = notebook.chapters_dir / chapter / "index.qmd"
    try:
        md = index.read_text()
    except OSError:
        return 0, 0
    spec = asm = 0
    for kind, body in CALLOUT.findall(md):
        n = len(ITEM.findall(body))
        if _kind(kind) == "Specified":
            spec += n
        else:
            asm += n
    return spec, asm


def ancestry(notebook, chapter):
    """
    `[parent, grandparent, ...]` from the `_fork.yml` chain. Empty for a root.

    Cycles are impossible by construction -- `create_chapter` only ever names
    an EARLIER chapter -- but a hand-edited file could make one, and a lint run
    that hangs is worse than one that is wrong. So the walk is bounded by the
    number of chapters.
    """
    out, seen, cur = [], {chapter}, chapter
    for _ in range(len(notebook.chapters())):
        f = notebook.chapters_dir / cur / "_fork.yml"
        try:
            m = re.search(r"^parent:\s*(.+?)\s*$", f.read_text(), re.M)
        except OSError:
            break
        if not m:
            break
        cur = m.group(1).strip()
        if cur in seen or not (notebook.chapters_dir / cur).is_dir():
            break
        seen.add(cur)
        out.append(cur)
    return out


def inherited(notebook, chapter):
    """
    [(kind, item, from_chapter)] a new chapter would carry forward.

    COMPUTED, not asked. With the parent named in `_fork.yml` the candidate set
    is a lookup -- no model judgement and no turn. What cannot be computed is
    whether the fork BREAKS an item: forking 5 mm to 3 mm inherits "tail
    dimensions remain 100x30 mm", and that may or may not survive. So this
    produces the list and the human strikes what the fork invalidates, which is
    a review rather than an open question.

    A chapter with no parent inherits from the NOTEBOOK instead -- the front
    page states what the aircraft is, and a new aircraft in an existing notebook
    is where the most is open, not the least.
    """
    out = []
    chain = ancestry(notebook, chapter)
    if chain:
        for c in chain:
            for kind, item in _declared_items(notebook, c):
                if not any(i == item for _, i, _ in out):
                    out.append((kind, item, c))
        return out
    index = notebook.root / "index.qmd"
    try:
        md = index.read_text()
    except OSError:
        return out
    for kind, body in CALLOUT.findall(md):
        for item in ITEM.findall(body):
            out.append((_kind(kind), _unescape(item), notebook.root.name))
    return out


def _declared_items(notebook, chapter):
    """[(kind, item)] from one chapter's index."""
    try:
        md = (notebook.chapters_dir / chapter / "index.qmd").read_text()
    except OSError:
        return []
    return [(_kind(kind), _unescape(i)) for kind, body in CALLOUT.findall(md)
            for i in ITEM.findall(body)]


def main(argv):
    if not argv:
        print("usage: uv run --group nb python -m nb inputs <notebook>")
        return 2
    notebook = Notebook(argv[0])
    rows = collect(notebook)
    if not rows:
        print("  nothing recorded yet")
        return 0

    # Grouped by LINEAGE, not by page. A flat list of every callout is what
    # the pages already are; the question this answers is "what have we decided
    # about this aircraft", and the answer has a shape -- each chapter adds to
    # what its parent already held.
    #
    # There is no "true of every chapter" section, and the reason is a fact
    # about the notebook rather than a limitation here: the same decision is
    # worded differently in each index ("Span 300 mm, fixed tip to tip" against
    # "**Span**: 300 mm, fixed tip to tip"), so the intersection is empty and
    # matching them loosely would be a guess printed as a fact. Wording them
    # identically where they ARE identical is what would make that section
    # possible.
    chapter = None
    for c, where, kind, item in rows:
        if c != chapter:
            chapter = c
            parent = ancestry(notebook, c)
            lineage = f"  (from {parent[0]})" if parent else ""
            print(f"\n{c}{lineage}")
        label = "SPECIFIED" if kind == "Specified" else "assumed  "
        print(f"  {label}  {item}")
        print(f"             {where}")
    n_spec = sum(1 for r in rows if r[2] == "Specified")
    print(f"\n  {n_spec} specified, {len(rows) - n_spec} assumed, "
          f"across {len(set(r[0] for r in rows))} chapter(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
