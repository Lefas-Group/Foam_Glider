"""
The lint contract: what makes an entry well-formed, checked without running it.

Pure by intent -- a notebook root in, findings out. Nothing here renders, shells
out or touches git; that is `nb/build/`.

    findings = check(root, chapters_of(root))      # [(rule, where, message)]
    uv run --group nb python -m nb.contract <notebook-dir> [chapter ...]

  contract.py   which rules exist, their reasons, and the registry
  shared.py     the parsers, regexes and budget readers
  rules.py      the 44 checks, one function each
  parse.py      Entry and Chapter, over the parsers

THERE WAS A `nb/lint.py` IN FRONT OF THIS. It began as the whole checker, 3,300
lines of rules interleaved with the parsers they read with. Splitting it left a
164-line facade holding `check()`, `main()` and 29 re-exports -- kept so that
twelve callers would not have to change in the same commit that moved the code.
They have changed now: each imports the layer it actually depends on, which is
the thing the facade hid.
"""

import pathlib

# EXACTLY WHAT `check` AND `main` USE, and nothing for anyone else. The facade
# this replaced re-exported 29 names so that twelve callers could keep saying
# `lint.X`; each of them now imports the layer it depends on, and the only
# things reached through this package are `check` and `main`.
from .contract import run as run_registered
from .shared import ENTRY_FILE, _label, aero_calls_of, chapters_of


def check(root, chapters):
    # `Entry`, not `Path`. It answers everything a Path answers and caches the
    # read and every parse of it, so the rules that call `.read_text()` and the
    # helpers invoked repeatedly over one file now do that work once per file for
    # the whole run. See `contract/parse.Entry`.
    from .parse import Entry
    entries = [Entry(f) for c in chapters
               for f in sorted((root / "chapters" / c).glob("*.qmd"))
               if ENTRY_FILE.match(f.name)]
    # Chapter indexes get the prose checks too. They are prose about the model
    # like any entry, and an unchecked index is how "5.7% thick" survived in
    # one after the model started saying 5.6%.
    pages = entries + [Entry(root / "chapters" / c / "index.qmd") for c in chapters
                       if (root / "chapters" / c / "index.qmd").exists()]

    # Derived per chapter: two chapters model different aircraft with different
    # helpers, and one chapter's `trim` says nothing about another's.
    aero = {c: aero_calls_of(root / "chapters" / c) for c in chapters}

    # EVERY CHECK, AND NOTHING ELSE. This function was 214 lines, of which ten
    # rules were written inline because they had nowhere else to live; the rest
    # was a list of twenty-four dispatch calls saying rule numbers that `RULES`
    # already declared. Both are gone: a check declares its own rule with
    # `@register`, and this assembles the context they ask for by name.
    problems = run_registered(root=root, chapters=chapters, entries=entries,
                              pages=pages, aero=aero)

    # Normalised so every caller sees one shape. `_tag` already produced
    # triples; a check returning `(where, msg)` pairs is padded with `None`.
    return [p if len(p) == 3 else (None, p[0], p[1]) for p in problems]


def main(argv):
    if not argv:
        print(__doc__.strip().split("\n\n")[1].strip())
        return 2
    root = pathlib.Path(argv[0]).resolve()
    if not (root / "chapters").is_dir():
        print(f"  {root} is not a notebook (no chapters/ directory)")
        return 2

    chapters = argv[1:] or chapters_of(root)
    found = check(root, chapters)
    for _rule, where, msg in found:
        label = "" if where is None else (
            _label(where.name) if ENTRY_FILE.match(where.name)
            else f"{where.parent.name}/{where.name}")
        print(f"  {label + ': ' if label else ''}{msg}")
    # Warnings are reported and do not fail. Only rule 17's lower tier uses
    # this: wall clock swings with machine load, so a message about it is worth
    # printing and not worth failing a render over.
    blocking = [p for p in found if "(warning)" not in p[2]]
    warned = len(found) - len(blocking)
    tail = f", {warned} warning(s)" if warned else ""
    print(f"\n{len(blocking)} problem(s){tail} in {', '.join(chapters)}")
    return 1 if blocking else 0


# LAST, and for its side effect: importing the module runs the `@register`
# decorators, which is what puts the 44 checks in the registry. After `check`
# so that a partially-initialised package cannot bite -- `rules` reaches into
# `.contract` and `.shared`, never back into this file.
from . import rules as _rules  # noqa: E402,F401
