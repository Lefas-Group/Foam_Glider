"""
Format checks for notebook entries.

    uv run python aircraft-notebook/_lint.py [chapter ...]

Defaults to every chapter that has opted in (see OPTED_IN). Exits non-zero if
anything is flagged, so it can gate a commit.

Three rules, each earned by a failure that actually happened in this notebook:

1. NO HAND-TYPED NUMBERS IN PROSE. Three separate corrections were needed in one
   session where an entry's prose disagreed with its own rendered output. Every
   result in prose must be an inline expression, `{python} f"{x:.2f}"`, so the
   number is the computation rather than a copy of it.

2. NO REPEATED CODE ACROSS ENTRIES. Machinery that a second entry reaches for
   belongs in the chapter's _analysis.py. Four subtly different neutral points
   were once written in one chapter, one of which took its moment reference from
   the wrong station and put wrong numbers in front of the reader.

3. THE ANSWER COMES BEFORE THE EVIDENCE. An entry is read to find out what was
   learned; the working is there to be checked afterwards.

4. NO SWEEPING A DECISION THAT SHOULD HAVE BEEN ASKED. "Where does the ballast
   go?" was once answered with three static margins because nobody asked which
   one was wanted -- turning a missing input into extra analysis, which is worse
   than either asking or assuming. A design decision gets asked for and recorded
   in a `## Specified` callout, not swept.

The leading underscore keeps Quarto from rendering this file.
"""
import pathlib
import re
import sys
from collections import defaultdict

# Every chapter is checked unless it is named here. Opt-out, not opt-in: a
# chapter added tomorrow is checked the moment it exists, and excluding one is a
# deliberate act someone has to write down. An opt-in list quietly leaves new
# work unchecked until somebody remembers, which is how a checker becomes
# decoration.
SKIP = ["01-aerobuildup-bfg"]   # predates the format; its freeze holds solver runs

# Two decimals or more reads as a result. One decimal is usually a condition --
# 6 m/s, 0.5 deg, 10% -- and flagging those is noise. Measured on this notebook:
# at two decimals the whole thing yields a handful of hits, nearly all real; at
# one decimal it yields dozens, nearly all conditions.
RESULT_NUMBER = re.compile(r"\d+\.\d{2,}")

# Lines that recur legitimately and say nothing about duplicated machinery.
BOILERPLATE = re.compile(
    r"^(plt\.|ax\.grid|ax\.legend|ax\.set_|fig, ax|import |show_source\(|for side in|"
    r"\)|\]|\}|else:|try:|finally:)"
)
BLOCK = 3  # consecutive code lines that count as a repeated block

# A short literal list of numbers bound to a name is how a hedge looks: three
# static margins, five launch heights. A real sensitivity study builds its arms
# from calls, and an analysis sweep uses linspace -- neither trips this.
SWEPT_LITERAL = re.compile(r"^\s*(\w+)\s*=\s*\[\s*([-\d.eE, ]+)\]\s*$", re.M)


def prose_of(text):
    """The entry's prose: no front matter, no code cells, no inline expressions."""
    t = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"`\{python\}[^`]*`", "", t)
    t = re.sub(r"`[^`]*`", "", t)
    return re.sub(r"<!--.*?-->", "", t, flags=re.S)


def code_of(text):
    """Non-trivial, whitespace-normalised code lines from the python cells."""
    out = []
    for cell in re.findall(r"```\{python\}(.*?)```", text, re.S):
        for line in cell.split("\n"):
            s = line.strip()
            if s and not s.startswith("#") and not BOILERPLATE.match(s):
                out.append(re.sub(r"\s+", " ", s))
    return out


def check(chapters):
    root = pathlib.Path(__file__).parent
    entries = [f for c in chapters
               for f in sorted((root / "chapters" / c).glob("2026-*.qmd"))]
    # Chapter indexes get the prose checks too. They are prose about the model
    # like any entry, and an unchecked index is how "5.7% thick" survived in
    # one after the model started saying 5.6%.
    pages = entries + [root / "chapters" / c / "index.qmd" for c in chapters]
    problems = []

    for f in pages:
        text = f.read_text()

        for n in dict.fromkeys(RESULT_NUMBER.findall(prose_of(text))):
            problems.append(
                (f, f"hand-typed number {n!r} in prose — use `{{python}} …`"))

        # A swept design choice with no recorded decision.
        if "## Specified" not in text:
            code = "\n".join(re.findall(r"```\{python\}(.*?)```", text, re.S))
            for name, body in SWEPT_LITERAL.findall(code):
                n = len([v for v in body.split(",") if v.strip()])
                if 3 <= n <= 5:
                    problems.append(
                        (f, f"sweeps {name!r} over {n} values with no recorded "
                            f"decision — should the user have been asked, and the "
                            f"answer put in a `## Specified` callout?"))

        if "**Answer.**" in text:
            last_cell = text.rfind("```{python}")
            if text.index("**Answer.**") > last_cell:
                problems.append(
                    (f, "**Answer.** comes after the last code cell — it should "
                        "come before the evidence"))

    blocks = defaultdict(set)
    for f in entries:
        lines = code_of(f.read_text())
        for i in range(len(lines) - BLOCK + 1):
            blocks[tuple(lines[i:i + BLOCK])].add(f.name)
    for block, where in blocks.items():
        if len(where) >= 2:
            problems.append(
                (None, f"{BLOCK} code lines repeated in {len(where)} entries "
                       f"({', '.join(sorted(n[11:34] for n in where))}) — promote "
                       f"to _analysis.py:\n        " + "\n        ".join(block)))
    return problems


if __name__ == "__main__":
    root = pathlib.Path(__file__).parent
    chapters = sys.argv[1:] or sorted(
        d.name for d in (root / "chapters").iterdir()
        if d.is_dir() and d.name not in SKIP)
    found = check(chapters)
    for where, msg in found:
        print(f"  {where.name[11:44] + ': ' if where else ''}{msg}")
    print(f"\n{len(found)} problem(s) in {', '.join(chapters)}")
    sys.exit(1 if found else 0)
