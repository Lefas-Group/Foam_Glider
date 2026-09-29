"""
read_reference -- the corpus, on demand.

Description in the tool schema, body only when asked. The AeroSandbox book alone
is ~10k lines; loading it eagerly would cost more than every entry it informs.
"""

from ..config import REFERENCES
from ..text import head

BOOK = REFERENCES / "aerosandbox-book"

DOCS = {
    # Each line has to name the SITUATION, not the subject. "Read before writing
    # dynamics" did not fire for a run computing stability derivatives, which
    # then spent four probes rediscovering a return type this page states
    # outright. A description the model has to classify itself into is one it
    # will classify itself out of.
    "refactoring": "Which of _model.py and _analysis.py you may edit, and how "
                   "to prove a change to either moved no answer.",
    "forking": "When a model change earns a new chapter, and how to copy one.",
    "probing": "Scratch-probe mechanics, timing hygiene, and when to stop "
               "probing and read instead.",
    "surrogates": "Lookup tables and cached polars: what level to cache at.",
    "quarto": "Render and tooling traps. Read when a render fails, or before "
              "writing a figure or table you have not written here before.",
    # `aerosandbox` and `aerosandbox-api` are deliberately NOT here: both are in
    # the prefix now (see nb/prefix.py PREFIX_DOCS), so offering them would buy
    # a turn to re-read what the model already has in front of it. That turn was
    # the point of moving them -- 0.8 read_reference calls per run on flash.
    # The files stay in this directory; only the tool's enum drops them.
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
