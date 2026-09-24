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


def own(notebook, chapter, entries_before=None):
    """
    [(kind, text, handle)] this chapter declares ITSELF, both tiers.

    `_inputs.yml` holds what is true of every entry here and the handle is its
    id; an entry's callout holds what that question introduced and the handle
    is its stem. Only the first was ever read back, so an `ask_specified`
    answer -- which lands in the second -- was invisible to the next run, and
    the same quantity got asked twice.

    `entries_before` takes only the first N entries, for an ancestor seen
    through a fork: see `_lineage`.
    """
    import lint
    # THE HANDLE IS ALSO PART OF THE IDENTITY for a chapter item, because the
    # format is `- <id>: <text>` and the text never repeats the name.
    # `- dihedral: 20 degrees determines the cross-angle` says nothing about
    # dihedral except in its id, so matching on text alone let "dihedral angle"
    # be asked again.
    ids = {t: i for i, t in lint.input_ids(notebook.root, chapter).items()}
    out = [(k, t, ids.get(t, chapter))
           for k, t in lint.declared_items(notebook.root, chapter)]
    standing = [_words(t) | _words(w) for _, t, w in out]

    rows = lint.entry_items(notebook.root, chapter)
    if entries_before is not None:
        keep = {e.stem for e in notebook.entries(chapter)[:entries_before]}
        rows = [r for r in rows if r[2] in keep]
    # An entry that introduced an item the chapter later took into its
    # `_inputs.yml` still carries its own callout -- correctly, because that
    # callout says what THAT entry introduced. Listing both says the same
    # commitment twice, so the restatement is dropped: the chapter's wording is
    # the standing one. Same subset test as `settled` below, which is the only
    # notion of "these are the same quantity" this file has.
    for kind, text, where in rows:
        words = _words(text)
        if any(w and w <= words for w in standing):
            continue
        out.append((kind, text, where))
    return out


def _lineage(notebook, chapter, parent=None):
    """
    [(ancestor, entries_at_the_fork)] nearest first, or [] for a root.

    THE CUTOFF IS THE POINT OF IT. `_fork.yml` records `at_entry:` -- how many
    entries the parent had written when the copy was taken -- and that is
    exactly what decides which of the parent's assumptions this chapter was
    built on. An entry written in the parent AFTERWARDS was never part of what
    this chapter inherited: nobody reviewed it at the fork, and the human who
    approved the inheritance approved the set that existed then.

    It compounds down a chain: C sees B's entries up to C's `at_entry`, and A's
    up to B's. Each step carries its own cutoff, which is the one its own
    `_fork.yml` recorded.

    `parent` seeds the walk for a chapter that does not exist yet, which is
    what the fork-time review needs -- there is no `_fork.yml` to read until
    `create_chapter` has run.
    """
    import lint
    out, seen, cur = [], {chapter}, chapter
    if parent and parent != chapter and (notebook.chapters_dir / parent).is_dir():
        out.append((parent, None))     # not forked yet: everything it has
        seen.add(parent)
        cur = parent
    for _ in range(len(notebook.chapters())):
        fork = lint.read_fork(notebook.root, cur) or {}
        nxt = (fork.get("parent") or "").strip()
        if not nxt or nxt in seen or not (notebook.chapters_dir / nxt).is_dir():
            break
        try:
            at = int(fork.get("at_entry") or 0) or None
        except (TypeError, ValueError):
            at = None
        seen.add(nxt)
        out.append((nxt, at))
        cur = nxt
    return out


def _ancestral(notebook, chapter, parent=None):
    """
    (carried, dropped) from this chapter's ancestors. The one walk both
    `committed` and `inherited` project from.

    `carried` is [(kind, text, ancestor, handle)]: the ancestor is what the
    review groups by, and the handle is the id or entry stem WITHIN it. Both
    are needed and neither substitutes -- `<ancestor>/<handle>` is exactly the
    `overwrites:` syntax, and the handle alone is what carries an item's
    identity when its text does not (`- dihedral: 20 degrees…` names dihedral
    only in its id).
    """
    import lint
    chain = _lineage(notebook, chapter, parent)
    gone = lint.departures(notebook.root, notebook.chapters())
    # THIS CHAPTER'S OWN OVERWRITES COUNT. The test was against the ancestors
    # alone -- written when this only ever ran for a chapter that did not exist
    # yet and so could not have overwritten anything. Used for a chapter that
    # DOES exist, an item it had already struck came straight back.
    breakers = {c for c, _ in chain} | {chapter}
    carried, dropped = [], []
    for c, at in chain:
        ids = lint.input_ids(notebook.root, c)
        for kind, text, handle in own(notebook, c, entries_before=at):
            if any(t == text for _, t, _, _ in carried):
                continue
            item_id = next((i for i, t in ids.items() if t == text), None)
            by = gone.get((c, item_id)) if item_id else None
            if by and by in breakers:
                dropped.append((kind, text, c, by))
                continue
            carried.append((kind, text, c, handle))
    return carried, dropped


def committed(notebook, chapter):
    """
    [(kind, text, where)] -- everything in force for an entry written here.

    THE CHAPTER'S OWN, AND ITS ANCESTORS'. A fork COPIES its parent's
    `_model.py`, so every assumption the parent's entries made while building
    that vehicle comes across in the most literal way there is -- and this used
    to read the current chapter alone, so the first entry in a fresh fork was
    shown nothing at all. Measured on 02-wings-at-rear: it inherits eight items
    and `committed` reported zero.

    An ancestor's item keeps `<ancestor>/<handle>` as its `where`, so the
    register SHOWS provenance rather than asserting the item as this chapter's
    own -- and that string is the one `overwrites:` takes. The distinction is
    what makes including an ancestor's ENTRY-level assumptions safe: "velocity:
    5 m/s (from 01-first-chapter)" is a fact about where to look, not a claim
    that every entry here assumes it. Promoting the same item into this
    chapter's `_inputs.yml` WOULD be that claim, and would be false for roughly
    half of them.
    """
    out = list(own(notebook, chapter))
    # NOT the notebook's brief, which `inherited` falls back to for a chapter
    # with no ancestor. It is true of every chapter equally, the prefix quotes
    # it under its own heading, and a root chapter picking it up here while a
    # forked one did not would make the register mean two different things
    # depending on where you stood.
    have = [_words(t) | _words(w) for _, t, w in out]
    for kind, text, anc, handle in _ancestral(notebook, chapter)[0]:
        words = _words(text) | _words(handle)
        if any(w and w <= words for w in have):
            continue          # this chapter restates it; its wording wins
        out.append((kind, text, f"{anc}/{handle}"))
    return out


def short(handle, chapter=""):
    """
    A handle as it reads in a listing: an id whole, an entry as its date.

    An id IS the thing `replaces=` and `overwrites:` take, so truncating it
    makes it useless -- `foam-thick` is not a handle. An entry stem is 70
    characters of slug whose front is a date, and the date is what places it
    against the entries the prefix already lists.
    """
    import lint
    if handle == chapter:
        return ""
    anc, _, tail = handle.rpartition("/")
    tail = f"{anc}/{tail[:10]}" if anc and lint.ENTRY_FILE.match(tail) else (
        handle[:10] if lint.ENTRY_FILE.match(handle) else handle)
    return tail


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
    (kept, dropped) -- what this chapter carries from its ANCESTORS.

    COMPUTED, not asked. With the parent named in `_fork.yml` the candidate set
    is a lookup -- no model judgement and no turn. What cannot be computed is
    whether the fork BREAKS an item: forking 5 mm to 3 mm inherits "tail
    dimensions remain 100x30 mm", and that may or may not survive. So this
    produces the list and the human strikes what the fork invalidates, which is
    a review rather than an open question.

    BOTH TIERS, through `own`. It read `_inputs.yml` alone, which is half of
    what a fork actually carries: measured on the fork that moved the X-Wing's
    wings to the rear, it was offered two items and inherited eight, and the
    one it explicitly broke ("Wing position: x=0.25 m, placed near
    mid-fuselage") was not among the two. The human could not strike what they
    were never shown.

    Each ancestor is seen AS OF THE FORK, via `_lineage`'s cutoff: an entry
    written in the parent afterwards was never part of what this chapter was
    built on.

    A chapter with no ancestor inherits from the NOTEBOOK instead -- the front
    page states what the aircraft is, and a new aircraft in an existing
    notebook is where the most is open, not the least.

    `dropped` is [(kind, item, from, overwritten_by)] -- items an ancestor
    declared that a LATER chapter replaced. They used to be in the list:
    chapter 06 was offered "Foam thickness: 3 mm" (04) beside "Foam 5 mm,
    174.4 g/m2 sheet throughout" (01) as thirteen peers. `_fork.yml`'s
    `overwrites:` records the override now, so it is mechanical and the dropped
    set is reported rather than silently missing.
    """
    import lint
    if not _lineage(notebook, chapter, parent):
        return [(k, t, notebook.root.name)
                for k, t in lint.notebook_items(notebook.root)], []
    carried, dropped = _ancestral(notebook, chapter, parent)
    return [(k, t, c) for k, t, c, _h in carried], dropped
