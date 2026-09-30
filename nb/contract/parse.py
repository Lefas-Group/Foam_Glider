"""
An entry, and a chapter, as objects -- parsed once instead of forty times.

MEASURED in `lint.py` before this existed: 33 rule functions called `read_text()`
themselves, 21 called `exists()`, and nine parser helpers were invoked between
three and nine times each over the same files. Every rule opened the `.qmd` again
and re-derived what it needed. That is where a large share of 3,000 lines went,
and it is why rules could not be separated from I/O, could not be tested without
a notebook on disk, and could disagree with each other about what "the prose" is.

WHY THIS WRAPS RATHER THAN REPLACES the helpers. Every property below delegates
to the function `lint` already used, unchanged. The point of this phase is to
change WHERE a rule gets its text, not what the text is: the characterization
harness must report zero moved findings, so `Entry.prose` has to be
`body_prose(text)` and nothing cleverer. The helpers travel here properly when
the rules do.

THE LAZY IMPORT IS DELIBERATE. `lint` holds the rules and will import this
module; this module needs `lint`'s parsers. Importing inside the property breaks
the cycle, and it is the idiom the rest of `nb` already uses -- almost every
`import lint` in this package is inside a function for the same reason.

UNREADABLE FILES KEEP THEIR OLD MEANING. Rules wrapped `read_text()` in
`try/except OSError` and skipped the file; a dataclass that read eagerly and
raised would move that decision, and one that substituted `""` would turn "skip
it" into "it declares nothing", which is a finding where there was none. So
`text` is `None` when the file cannot be read, and the translation of a rule's
`except OSError: continue` is `if e.text is None: continue` -- the same
behaviour, said once.
"""

import functools
import pathlib


class Entry:
    """One `.qmd` -- an entry or a chapter index -- read once."""

    def __init__(self, path):
        self.path = pathlib.Path(path)

    def __repr__(self):
        return f"Entry({self.name})"

    # Value identity, so an Entry can sit in a set or a dict key the way the
    # Path it replaced did. Rules group entries by chapter and de-duplicate
    # them; without this, two Entry objects for one file would count twice.
    def __eq__(self, other):
        return isinstance(other, Entry) and self.path == other.path

    def __hash__(self):
        return hash(self.path)

    # PATH-COMPATIBLE ON PURPOSE, and this is what makes the conversion safe.
    #
    # 34 rule functions take a list of `.qmd` paths and call `.read_text()`,
    # `.name`, `.parent` and `str()` on them. Rewriting all 34 in one commit is
    # exactly the kind of change the characterization harness cannot tell from a
    # mistake -- hundreds of edited lines, one of them wrong, findings unchanged
    # in 33 places. So `Entry` answers everything a Path answers, by delegation,
    # and `check()` hands these out instead. Every rule gets parse-once caching
    # without being touched; each one adopts the named views above when it moves
    # into `contract/rules/`, one file at a time, under the harness.
    def __getattr__(self, attr):
        # Only reached for attributes this class does NOT define, so it cannot
        # shadow `text`, `prose` or any cached_property above.
        return getattr(self.path, attr)

    def __fspath__(self):
        return str(self.path)

    def __str__(self):
        return str(self.path)

    # Sorted alongside each other, as the Paths they replace were.
    def __lt__(self, other):
        return str(self.path) < str(getattr(other, "path", other))

    def read_text(self, *args, **kwargs):
        """
        The file, cached -- and RAISING exactly as `Path.read_text` did.

        Rules wrap this in `try/except OSError` and skip the file. Returning ""
        for a missing file would turn "skip it" into "it declares nothing",
        which is a finding where there was none, so the exception is cached and
        re-raised rather than swallowed. `text` is the forgiving view; this is
        the faithful one.
        """
        if isinstance(self._read, Exception):
            raise self._read
        return self._read

    @functools.cached_property
    def _read(self):
        """The bytes, or the OSError that stopped us -- resolved once."""
        try:
            return self.path.read_text()
        except OSError as e:
            return e

    @functools.cached_property
    def text(self):
        """The file, or None if it cannot be read. See the module docstring."""
        got = self._read
        return None if isinstance(got, Exception) else got

    @functools.cached_property
    def is_entry(self):
        """An entry, as opposed to an index or some other page."""
        from .. import lint
        return bool(lint.ENTRY_FILE.match(self.name))

    # ------------------------------------------------------------------ views
    # Each of these is the helper `lint` already called, once per file instead
    # of once per rule. `None` text propagates as the helper's empty answer,
    # which is what a rule that skipped an unreadable file would have produced.

    @functools.cached_property
    def cell_source(self):
        """Every `{python}` cell, concatenated, `#|` options stripped.

        NOT a list of cells, despite what `entry_cells` sounds like -- it is one
        string, which is what every caller wanted: they search it or parse it as
        a module. Named for what it is, because `cells` invited `len(...)` and
        got a character count.
        """
        from .. import lint
        return lint.entry_cells(self.text or "")

    @functools.cached_property
    def prose(self):
        from .. import lint
        return lint.body_prose(self.text or "")

    @functools.cached_property
    def prose_words(self):
        from .. import lint
        return lint.words(self.prose)

    @functools.cached_property
    def callouts(self):
        """(title, body) for each `::: {.callout-*}` block."""
        # MATERIALISED, because `callouts_of` is a generator and this is cached.
        # A cached generator is consumed by whoever reads it first and empty for
        # everyone after -- which is precisely the bug that parsing once instead
        # of forty times would otherwise introduce. `tuple` changes nothing for a
        # caller that iterates, which all of them do.
        from .. import lint
        return tuple(lint.callouts_of(self.text or ""))

    @functools.cached_property
    def tables(self):
        """Every markdown pipe table, as (body_rows, columns)."""
        from .. import lint
        return lint.tables_in(self.text or "")

    @functools.cached_property
    def calls(self):
        from .. import lint
        return lint.entry_calls(self.text or "")

    @functools.cached_property
    def footer(self):
        """(names passed to footer()/show_source(), how many footer() cells)."""
        from .. import lint
        return lint.rendered_by_footer(self.text or "")

    @property
    def rendered_names(self):
        """Just the names half of `footer` -- what rule 13 asks about."""
        return self.footer[0]

    def limits(self, root):
        """(SOLVE_BUDGET, ENTRY_CEILING) as this entry declares them."""
        from .. import lint
        return lint.limits_of(root, self.path)


class Chapter:
    """One `chapters/NN-name/` -- its entries, its index, its two modules."""

    def __init__(self, root, name):
        self.root = pathlib.Path(root)
        self.name = name

    def __repr__(self):
        return f"Chapter({self.name})"

    @property
    def dir(self):
        return self.root / "chapters" / self.name

    @functools.cached_property
    def pages(self):
        """Every `.qmd` in the chapter, entries and index alike, sorted."""
        return tuple(Entry(p) for p in sorted(self.dir.glob("*.qmd")))

    @functools.cached_property
    def entries(self):
        """The entries only -- `index.qmd` and anything unstamped excluded."""
        return tuple(p for p in self.pages if p.is_entry)

    @functools.cached_property
    def index(self):
        """The chapter index, present or not: `Entry.text` is None if absent."""
        return Entry(self.dir / "index.qmd")

    @functools.cached_property
    def model(self):
        return Entry(self.dir / "_model.py")

    @functools.cached_property
    def analysis(self):
        return Entry(self.dir / "_analysis.py")

    @functools.cached_property
    def defs(self):
        from .. import lint
        return lint._defs_of(self.dir)

    @functools.cached_property
    def aero_calls(self):
        from .. import lint
        return lint.aero_calls_of(self.dir)


def chapters(root):
    """Every chapter of a notebook, in order. Mirrors `lint.chapters_of`."""
    from .. import lint
    root = pathlib.Path(root)
    return tuple(Chapter(root, c) for c in lint.chapters_of(root))
