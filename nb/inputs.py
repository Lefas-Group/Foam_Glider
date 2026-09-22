"""
What the notebook has already been given, and what it has guessed.

A LIBRARY, not a command. `nb inputs` printed this as a report, grouped by
lineage -- and it was a read over callouts that are already on every page, for
a register that does not exist yet. What earns its place is the lookup:

  * `declared()` is what `probe._inputs_notice` puts to the model after its
    first probe, which is what made `ask_specified` fire at all -- it was 3 of
    8 runs before;
  * `inherited()` is the candidate set a NEW chapter carries forward, reviewed
    at the new-chapter stop.

Read from the chapter INDEXES, whose callouts hold what the chapter was given
rather than what one entry computed. The entry-level read went with the
command: the source holds `{python} f"{sm:.2f}"` where only the freeze holds
`0.10`, and nothing needed it.
"""

import re

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
