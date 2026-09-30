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

TITLE = re.compile(r'^title:\s*"(.+)"\s*$', re.M)
HERO = re.compile(r"\[([^\]]*)\]\{\.hero-value\}")
# The fallback when there is no hero: the entry's own first answer sentence,
# read off the RENDERED markdown so its numbers are already substituted.
#
# NOT the first `.key` value, which was the first attempt and was wrong. A
# heroless entry is not reliably one whose answer is a number that merely went
# unmarked -- it is just as often one whose answer is qualitative, and then the
# first marked value belongs to the reasoning rather than the conclusion.
# Measured on this notebook: "What airspeed does it trim at when ballasted to
# the required CG?" answers "It cannot trim at any airspeed", and its first
# `.key` is `cm_0` = -0.043 -- a pitching-moment coefficient offered where an
# airspeed was asked for. A wrong number in the answer column is worse than no
# number, because `(no hero)` at least says nothing.
#
# The sentence cannot have that failure: it is what the entry itself concluded.
ANSWER = re.compile(r"\*\*Answer\.\*\*\s*(.+?)(?:\n\n|\Z)", re.S)


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


def _answer_sentence(md, cap=110):
    """
    The first sentence of an entry's `**Answer.**`, flattened to one line.

    Link text is kept and link targets dropped -- a stem in the middle of the
    manifest's answer column is noise, and the entry it names is already a line
    away. Truncated on a sentence boundary where there is one, because the first
    sentence is the conclusion and the rest is the reasoning.
    """
    m = ANSWER.search(md or "")
    if not m:
        return ""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1))   # links -> text
    text = re.sub(r"\[([^\]]*)\]\{[^}]*\}", r"\1", text)         # spans -> text
    text = _unescape(" ".join(text.split()))
    text = re.sub(r"[*`]", "", text)
    if len(text) <= cap:
        return text
    cut = text[:cap]
    stop = cut.rfind(". ")
    return (cut[:stop + 1] if stop > 40 else cut.rstrip() + "…")


def entry_line(notebook, chapter, path):
    stem = path.stem
    title = _title(path.read_text())
    md = _rendered(notebook, chapter, stem)
    if md is None:
        answer = "(not yet rendered)"
    else:
        # `.hero-pair` carries two; an entry whose answer is a figure or a
        # yes/no carries none, and that is a legitimate state, not a gap.
        #
        # But it is not a reason to publish NOTHING. Measured 2026-09-29: a run
        # needing the 50 g mass budget was given
        # `Does it meet the 50 g mass budget with ballast fitted?  →  (no hero)`
        # -- the question without the answer -- and spent eight turns reading
        # the page to recover a number this line could have carried. That is the
        # opposite of what the manifest is for, and it is the stretch that
        # tripped the stuck detector.
        #
        # So fall back to the entry's own opening answer sentence. `(no hero)`
        # remains only when there is no `**Answer.**` to read either.
        heroes = [_unescape(h) for h in HERO.findall(md)]
        if heroes:
            answer = " vs ".join(heroes)
        else:
            answer = _answer_sentence(md) or "(no hero)"
    return stem, title, answer


def build(notebook):
    """The manifest, as the text that goes into the cached prefix."""
    out = []
    for chapter in notebook.chapters():
        index = notebook.chapters_dir / chapter / "index.qmd"
        title = _title(index.read_text()) if index.exists() else ""
        # No chapter-level ceiling any more: budgets are per entry, and the
        # one in force is granted at the prompt and stated in the write brief.
        # Dropping it also shortens the cached prefix, which is free headroom.
        out.append(f'{chapter} — "{title}"')
        for path in notebook.entries(chapter):
            stem, etitle, answer = entry_line(notebook, chapter, path)
            out.append(f"  {stem}")
            out.append(f"      {etitle}  →  {answer}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv):
    if not argv:
        print("usage: uv run --group nb python -m nb.manifest <notebook>")
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
