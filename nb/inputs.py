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
def declared(notebook, chapter):
    """
    (specified, assumed) counts for ONE chapter.

    Delegated to `lint.declared_items`, which knows both sources: a chapter
    with `_inputs.yml` is read from it, one without from its index callouts.
    This used to carry its own regex over the markdown, and the day the items
    moved into a data file that copy would have returned zero -- silently, for
    the notice that is the only reason `ask_specified` fires at all.
    """
    import lint
    items = lint.declared_items(notebook.root, chapter)
    spec = sum(1 for k, _ in items if k == "Specified")
    return spec, len(items) - spec


# Words too common to mean anything on their own. A name is matched on what is
# distinctive in it, so "static margin" finds "center of gravity (or static
# margin): 10%" and "wing" alone finds nothing useful.
_NOISE = {"the", "a", "an", "of", "for", "and", "or", "in", "at", "to",
          "value", "used", "per", "its"}


def _words(text):
    """Significant words, case-folded, punctuation gone."""
    return {w for w in re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split()
            if len(w) > 2 and w not in _NOISE}


def committed(notebook, chapter):
    """
    [(kind, text, where)] -- everything this chapter is already committed to.

    BOTH TIERS, which is the whole point. `_inputs.yml` holds what is true of
    every entry and `where` is the chapter; an entry's own callout holds what
    that question introduced and `where` is its stem. Only the first was ever
    read back, so an `ask_specified` answer -- which lands in the second --
    was invisible to the next run, and the same quantity got asked twice.

    Chapter items first, because they are the standing commitments; entries
    after, in order, because a later one revising an earlier one is the
    notebook's whole shape.
    """
    import lint
    # `where` IS THE HANDLE: the `_inputs.yml` id for a chapter item, the stem
    # for an entry's. Both consumers want the same thing -- where this was
    # recorded and what to name it by -- and for a chapter item the id is also
    # part of the item's IDENTITY, because the format is `- <id>: <text>` and
    # the text never repeats the name. `- dihedral: 20 degrees determines the
    # cross-angle` says nothing about dihedral except in its id, so matching on
    # text alone let "dihedral angle" be asked again.
    ids = {t: i for i, t in lint.input_ids(notebook.root, chapter).items()}
    out = [(k, t, ids.get(t, chapter))
           for k, t in lint.declared_items(notebook.root, chapter)]
    standing = [_words(t) | _words(w) for _, t, w in out]
    # An entry that introduced an item the chapter later took into its
    # `_inputs.yml` still carries its own callout -- correctly, because that
    # callout says what THAT entry introduced. Listing both says the same
    # commitment twice, so the restatement is dropped: the chapter's wording is
    # the standing one. Same subset test as `settled` below, which is the only
    # notion of "these are the same quantity" this file has.
    for kind, text, where in lint.entry_items(notebook.root, chapter):
        words = _words(text)
        if any(w and w <= words for w in standing):
            continue
        out.append((kind, text, where))
    return out


def settled(notebook, chapter, name):
    """
    The committed item this question is about, or None.

    A QUANTITY IS SETTLED WHEN EVERY DISTINCTIVE WORD OF ITS NAME IS ALREADY IN
    THE REGISTER. "static margin" matches "center of gravity (or static
    margin): 10%", which is the case this was written for -- asked on one entry
    and asked again, verbatim, two entries later.

    Deliberately a subset test and not a similarity score. It fires when the
    thing being asked about is named in something already agreed, which is
    exactly when the user would be answering the same question twice; anything
    looser starts refusing genuinely new inputs, and a refusal the model cannot
    understand is worse than a duplicate.
    """
    want = _words(name)
    if not want:
        return None
    for kind, text, where in committed(notebook, chapter):
        if kind == "Specified" and want <= (_words(text) | _words(where)):
            return kind, text, where
    return None


def ancestry(notebook, chapter, parent=None):
    """
    `[parent, grandparent, ...]` from the `_fork.yml` chain. Empty for a root.

    `parent` SEEDS the walk, for a chapter that does not exist yet. That is the
    case the inheritance review is for and the case it never handled: it runs
    before `create_chapter`, so `chapters/<chapter>/_fork.yml` is not there,
    the walk returned empty, and every new chapter -- fork or not -- was
    offered the notebook's brief instead of its parent's declarations. The
    fallback was doing the work of the lookup, silently and always.

    Cycles are impossible by construction -- `create_chapter` only ever names
    an EARLIER chapter -- but a hand-edited file could make one, and a lint run
    that hangs is worse than one that is wrong. So the walk is bounded by the
    number of chapters.
    """
    out, seen, cur = [], {chapter}, chapter
    if parent and parent != chapter and (notebook.chapters_dir / parent).is_dir():
        out.append(parent)
        seen.add(parent)
        cur = parent
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


def inherited(notebook, chapter, parent=None):
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

    Returns (kept, dropped). `dropped` is [(kind, item, from, overwritten_by)] --
    items an ancestor declared and a LATER ancestor replaced. They used to be in
    the list: chapter 06 was offered "Foam thickness: 3 mm" (04) beside "Foam
    5 mm, 174.4 g/m² sheet throughout" (01) as thirteen peers, along with
    "Fuselage neglected" that 02 had contradicted by adding one. The union was
    doing the work of an override because nothing recorded which item replaced
    which. `_fork.yml`'s `overwrites:` records it now, so the override is
    mechanical and the dropped set is reported rather than silently missing.
    """
    out, dropped = [], []
    chain = ancestry(notebook, chapter, parent)
    if chain:
        import lint
        gone = lint.departures(notebook.root, notebook.chapters())
        ids = {c: lint.input_ids(notebook.root, c) for c in chain}
        for c in chain:
            for kind, item in _declared_items(notebook, c):
                if any(i == item for _, i, _ in out):
                    continue
                item_id = next((i for i, t in ids[c].items() if t == item), None)
                by = gone.get((c, item_id)) if item_id else None
                # Only an ancestor's supersession counts. A chapter outside this
                # lineage replacing one of its own ancestors' items says nothing
                # about what THIS fork carries.
                if by and by in chain:
                    dropped.append((kind, item, c, by))
                    continue
                out.append((kind, item, c))
        return out, dropped
    import lint
    for kind, item in lint.notebook_items(notebook.root):
        out.append((kind, item, notebook.root.name))
    return out, dropped


def _declared_items(notebook, chapter):
    """[(kind, item)] from one chapter, via lint's dual-source reader."""
    import lint
    return lint.declared_items(notebook.root, chapter)
