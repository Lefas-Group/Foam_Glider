"""
read_reference -- the corpus, on demand.

Description in the tool schema, body only when asked. The AeroSandbox book alone
is ~10k lines; loading it eagerly would cost more than every entry it informs.
"""

from ..config import REFERENCES
from ..text import head

BOOK = REFERENCES / "aerosandbox-book"

DOCS = {
    "why": "The failure behind each lint rule. Read before arguing one away.",
    "refactoring": "Proving a _model.py/_analysis.py change moved nothing.",
    "forking": "When a model change earns a new chapter, and how to copy one.",
    "probing": "Scratch-probe mechanics, and timing/benchmark hygiene.",
    "surrogates": "Lookup tables and cached polars: what level to cache at.",
    "quarto": "Render and tooling traps. Read when a render fails.",
    "aerosandbox": "API traps and solver behaviour. Read before writing dynamics.",
}


def names():
    book = sorted(p.stem for p in BOOK.glob("*.qmd")) if BOOK.exists() else []
    return list(DOCS) + [f"book/{b}" for b in book]


def describe():
    lines = [f"  {k:14s} {v}" for k, v in DOCS.items()]
    if BOOK.exists():
        lines.append("  book/<name>    the vendored AeroSandbox book; filenames "
                     "say what each covers:")
        lines.append("      " + ", ".join(sorted(p.stem for p in BOOK.glob("*.qmd"))))
    return "\n".join(lines)


def read_reference(name):
    if name.startswith("book/"):
        p = BOOK / f"{name[5:]}.qmd"
    else:
        p = REFERENCES / f"{name}.md"
    if not p.exists():
        return f"no reference {name!r}. Available:\n{describe()}"
    return head(p.read_text(), 30000)
