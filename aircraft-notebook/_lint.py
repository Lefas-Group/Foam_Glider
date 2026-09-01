"""
Format checks for notebook entries.

    uv run python aircraft-notebook/_lint.py [chapter ...]

Defaults to every chapter that has opted in (see OPTED_IN). Exits non-zero if
anything is flagged, so it can gate a commit.

Five rules, each earned by a failure that actually happened in this notebook:

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

5. NO FIXED TRIP COUNT AROUND AN AERO SOLVE. `trim()` was written
   `for _ in range(60)` around a fixed point that settles in 9 to 13, so every
   call spent about twenty seconds re-deriving an answer it already had, at a
   dozen call sites. An AeroBuildup call costs the same whether you ask it for
   one angle of attack or six hundred -- the count of CALLS is the whole budget,
   and a loop is where they hide. Iterate to a tolerance with a max-iteration
   guard that raises; a round number someone picked also hides non-convergence,
   since a loop that never converged returns exactly like one that did.

The leading underscore keeps Quarto from rendering this file.
"""
import ast
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


# Calls that cost a full aero solve -- ~350 ms each on the McEagle, and rising
# with spanwise strip count. Bare `run` catches `AeroBuildup(...).run()` however
# it was spelled, and `opti.solve` is here for the same reason even though the
# failure that earned this rule was aerodynamic.
AERO_CALLS = {"polars", "AeroBuildup", "run", "run_with_stability_derivatives",
              "solve", "trim", "stall", "neutral_point"}


def _calls_aero(node):
    """Does this subtree make a call that costs a solve?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (f.attr if isinstance(f, ast.Attribute) else
                    getattr(f, "id", None)) in AERO_CALLS:
                return True
    return False


def _can_exit_early(body):
    """
    Is there a `break` or `return` belonging to THIS loop?

    Nested loops and nested functions keep their own -- a `break` one level down
    says nothing about whether the outer loop can stop, and counting it would
    wave through exactly the shape this rule exists to catch.
    """
    for stmt in body:
        if isinstance(stmt, (ast.For, ast.While, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, (ast.Break, ast.Return)):
            return True
        for field in ("body", "orelse", "finalbody"):
            if _can_exit_early(getattr(stmt, field, []) or []):
                return True
        for handler in getattr(stmt, "handlers", []):
            if _can_exit_early(handler.body):
                return True
    return False


def fixed_count_solves(source):
    """
    Line numbers of `for ... in range(...)` loops that solve every trip and
    cannot stop early.

    AST rather than regex: the distinction that matters is whether a `break`
    belongs to this loop or a nested one, and no regex can see that. `stall()`
    loops over an array already in memory and calls nothing, so it does not
    trip; `trim()` calls `polars()` every trip and cannot stop, so it does.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []   # a cell that will not parse is not this rule's problem
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and getattr(node.iter.func, "id", None) == "range"
        and _calls_aero(node)
        and not _can_exit_early(node.body))


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

    # Rule 5 reads the shared modules too. The other rules are about how an
    # entry is written, so they only ever looked at .qmd files -- but the loop
    # that earned this rule was in _analysis.py, one tier up, where a single
    # wasted iteration is paid by every entry that calls it.
    for c in chapters:
        for name in ("_model.py", "_analysis.py"):
            f = root / "chapters" / c / name
            if not f.exists():
                continue
            for line in fixed_count_solves(f.read_text()):
                problems.append(
                    (f, f"line {line}: `for … in range(…)` runs a solve every "
                        f"trip and cannot stop early — iterate to a tolerance "
                        f"with a guard that raises"))

    for f in pages:
        text = f.read_text()

        # Rule 5 again, on the entry's own cells. The cells are concatenated to
        # parse, so a line number here would point into that join rather than
        # into the file -- the loop is named by its shape instead, which is
        # enough to find it in an entry.
        cells = "\n".join(
            re.sub(r"^\s*#\|.*$", "", cell, flags=re.M)
            for cell in re.findall(r"```\{python\}(.*?)```", text, re.S))
        if fixed_count_solves(cells):
            problems.append(
                (f, "`for … in range(…)` runs a solve every trip and cannot "
                    "stop early — iterate to a tolerance with a guard that "
                    "raises"))

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
        # Entries are named by date, and the date is the same for every line of
        # a run -- so it is dropped. Shared modules have no date to drop.
        label = "" if where is None else (
            where.name[11:44] if where.name.startswith("2026-")
            else f"{where.parent.name}/{where.name}")
        print(f"  {label + ': ' if label else ''}{msg}")
    print(f"\n{len(found)} problem(s) in {', '.join(chapters)}")
    sys.exit(1 if found else 0)
