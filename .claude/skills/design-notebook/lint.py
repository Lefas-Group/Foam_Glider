"""
Format checks for notebook entries. One copy, shared by every notebook.

    uv run python <skill>/lint.py <notebook-dir> [chapter ...]

Defaults to every chapter except those a notebook opts out of. Exits non-zero if
anything is flagged, so it can gate a commit.

This lives in the skill rather than in each notebook because it is a CHECKER: it
runs at authoring time, reads the notebook and writes nothing. Nothing it does
ends up in the rendered site, so a notebook does not need it present to render.
`_notebook.py` is the opposite -- exec'd into every page at render time, with its
output baked into the published HTML -- which is why that one stays vendored in
each notebook and this one does not.

**A notebook carries no lint configuration.** Everything that once looked
notebook-specific is either derived or declared where it belongs: the helpers
that cost an aero solve are derived from each chapter's own call graph, a
sibling entry is matched generically, and a chapter opts out with a `_lint-skip`
file whose contents say why. A freshly scaffolded notebook has none of these,
and lints correctly with nothing added.

Eleven rules, each earned by a failure that actually happened:

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

6. PROSE FITS IN 100 WORDS. Everything the reader must read as prose -- the
   answer, any warning, an assembly section -- across the whole entry. Entries
   drift long one clause at a time, and the fix is always the same: the sentence
   that explains why a number is what it is belongs in the figure or the code
   comment, not in the answer. Only `## Specified`, `## Assumed` and figure
   captions are excluded, each having its own budget below. A `callout-warning`
   counts: moving a paragraph into a coloured box does not make it shorter.

7. A FIGURE CAPTION FITS IN 50 WORDS. It says what is plotted, not what to
   conclude; a caption that needs more than fifty words is carrying an argument
   that belongs in the prose.

8. A SPECIFIED OR ASSUMED ITEM FITS IN 10 WORDS. These are a numbered list of
   inputs, not a discussion of them. One entry recorded a static margin with
   three lines of justification, which reads as hedging a decision that was
   actually made.

9. ONE PROSE SECTION, NOT SEVERAL. An entry has a single run of prose -- the
   answer -- and everything else is a callout, a figure or code. A second
   headed block (`**Assembly.**`, `**Method.**`, a `##` heading) reads as its
   own little essay with its own budget, which is how an entry that is inside
   100 words in each part ends up long overall. If a procedure or a caveat is
   worth keeping, it belongs inside the answer or inside a callout.

10. A REFERENCE TO ANOTHER ENTRY IS A LINK. "the previous entry", "the glide
    entry" as bare prose is the same defect as a hand-typed number: it points at
    something that can be retitled, reordered or deleted, and nothing notices.
    A markdown link to the `.qmd` is checked by Quarto at render, and the
    notebook's whole structure is later entries revising earlier ones -- so
    those references are the structure, not decoration.

11. `_notebook.py` MATCHES THE SKILL'S COPY. It is vendored into each notebook
    because it runs at render time, so a shared one would make a notebook
    unrenderable without the skill and would hide edits from Quarto's freeze.
    Vendoring costs propagation; this rule buys it back, so an improvement to
    footer() or the plot style surfaces in every notebook that has not taken it.

A value written as an inline expression counts as one word, so tightening prose
is never at odds with computing the numbers in it.
"""
import ast
import pathlib
import re
import sys
from collections import defaultdict

# An entry is a date-prefixed .qmd. Matched by shape rather than by a literal
# year: the first version of this globbed "2026-*.qmd", which would have stopped
# checking every new entry on 1 January without failing or saying anything.
ENTRY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}-")

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

# Library calls that cost a full aero solve -- ~350 ms each on a small glider,
# and rising with spanwise strip count. A chapter's own helpers are DERIVED from
# these rather than listed (see aero_calls_of): a hand-written list is wrong the
# first time a helper is renamed, and the one written for this notebook was
# wrong immediately, claiming a mass calculation cost a solve. Bare `run`
# catches `AeroBuildup(...).run()` however it was spelled, and `solve` is here
# for the same reason even though the failure that earned this rule was
# aerodynamic.
AERO_PRIMITIVES = {"AeroBuildup", "run", "run_with_stability_derivatives", "solve"}

# Any "the <word> entry" is a reference to a sibling. Matched generically rather
# than against a list of topic words: an enumerated list silently misses the
# first entry about something new, which is the failure this rule exists to
# prevent. Only self-reference is exempt -- it points at nothing that can drift.
ENTRY_REFERENCE = re.compile(r"\bthe\s+(\w+)\s+entry\b", re.I)
ENTRY_SELF = {"this", "that", "the", "a", "an", "each", "every", "same",
              "whole", "current", "present", "other"}

# Word budgets. Prose is the whole entry's readable text; the two callouts and
# the figure captions are excluded because they are indexes rather than reading.
MAX_PROSE, MAX_FIG_CAP, MAX_CALLOUT_ITEM = 100, 50, 10


def chapters_of(root):
    """
    Chapters to check: all of them, minus any holding a `_lint-skip` file.

    Opt-out, not opt-in -- a chapter added tomorrow is checked the moment it
    exists, and excluding one is a deliberate act someone writes down. The
    marker's CONTENTS are the reason, and it lives in the chapter it describes,
    so deleting the chapter deletes its exemption. A central list of names
    outlives the chapter it names and then silently exempts whatever is created
    with that name next.

    A notebook therefore carries no lint configuration at all: a freshly
    scaffolded one has nothing to exempt, so no such file exists.
    """
    return sorted(d.name for d in (root / "chapters").iterdir()
                  if d.is_dir() and not (d / "_lint-skip").exists())


def aero_calls_of(chapter):
    """
    Every name in this chapter that costs an aero solve, derived not declared.

    Seeded with the library primitives, then a fixed point over the chapter's
    own `_model.py` and `_analysis.py`: a local function is expensive if it
    calls something already known to be. So `trim` counts because it calls
    `polars`, and `ballast_for` does not, because nothing it reaches solves
    anything.

    Derived rather than configured because the alternative was measurably
    wrong: the hand-written list for this notebook named `ballast_for` as an
    aero call within minutes of being written, and would have gone on being
    wrong every time a helper was renamed.
    """
    defs = {}
    for name in ("_model.py", "_analysis.py"):
        f = chapter / name
        if not f.exists():
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs[node.name] = {
                    (c.func.attr if isinstance(c.func, ast.Attribute)
                     else getattr(c.func, "id", None))
                    for c in ast.walk(node) if isinstance(c, ast.Call)}

    expensive = set(AERO_PRIMITIVES)
    changed = True
    while changed:                      # fixed point: helpers calling helpers
        changed = False
        for name, called in defs.items():
            if name not in expensive and (called & expensive):
                expensive.add(name)
                changed = True
    return expensive


def words(text):
    """
    Word count, with an inline expression counting as one word.

    A computed value is one thing the reader takes in, however long its format
    string -- so `{python} f"{x*1e3:.2f}"` mm is two words, not six. Counting the
    source verbatim would penalise exactly the habit rule 1 exists to enforce.
    """
    t = re.sub(r"`\{python\}[^`]*`", "N", text)
    t = re.sub(r"\(@[\w-]+\)|@[\w-]+", "", t)        # cross-references
    t = re.sub(r"\]\{\.[\w\s.-]+\}|\[", "", t)       # span syntax, not content
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)  # links: keep the label
    t = re.sub(r"^\s*#\|.*$", "", t, flags=re.M)     # cell options
    t = re.sub(r"[*_`#>]|^\s*\d+\.\s*|^\s*[-+]\s+", " ", t, flags=re.M)
    return len(t.split())


def callouts_of(text):
    """(title, body) for each ::: callout block, however it is fenced."""
    for m in re.finditer(r"^:{3,}\s*\{\.callout-\w+\}\s*\n(.*?)^:{3,}\s*$",
                         text, re.S | re.M):
        body = m.group(1)
        head = re.match(r"\s*##\s*(.+)", body)
        yield (head.group(1).strip() if head else ""),\
              re.sub(r"^\s*##.*$", "", body, count=1, flags=re.M)


def body_prose(text):
    """
    Everything the reader reads straight through, across the whole entry.

    Only `## Specified` and `## Assumed` are removed -- they are an index of
    inputs with their own per-item budget. A `callout-warning` stays in: it is
    addressed to the reader in sentences, and putting a caveat in a coloured box
    does not make it shorter. Hero blocks stay in too; a headline is words.
    """
    t = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    # Drop only the two input callouts, by title, leaving warnings in place.
    t = re.sub(
        r"^:{3,}\s*\{\.callout-\w+\}\s*\n\s*##\s*(?:Specified|Assumed)\b"
        r".*?^:{3,}\s*$", "", t, flags=re.S | re.M)
    t = re.sub(r"```\{python\}.*?```", "", t, flags=re.S)
    t = re.sub(r"\{\{<[^>]*>\}\}", "", t)
    return re.sub(r"^:{3,}.*$", "", t, flags=re.M)   # callout and hero fences


def _calls_aero(node, aero_calls):
    """Does this subtree make a call that costs a solve?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if (f.attr if isinstance(f, ast.Attribute) else
                    getattr(f, "id", None)) in aero_calls:
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


def fixed_count_solves(source, aero_calls):
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
        and _calls_aero(node, aero_calls)
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


def _notebook_drift(root):
    """
    Rule 11: the notebook's `_notebook.py` matches the skill's canonical copy.

    `_notebook.py` is VENDORED into each notebook rather than shared from here,
    unlike this file. It is exec'd into every page at render time and its output
    is baked into the published HTML, so sharing it would make a notebook
    unrenderable without the skill installed, and would put a render-affecting
    file outside the Quarto project -- where freeze cannot see edits to it, which
    is the failure mode that has already served stale pages here three times.

    Vendoring costs propagation, so this is what buys it back: an improvement to
    footer() or the plot style shows up as a problem in every notebook that has
    not taken it. Byte equality is the right test because nothing in the file is
    project-specific; any difference is either an un-propagated improvement or an
    accident, and both want a person to decide which.
    """
    canonical = pathlib.Path(__file__).parent / "notebook.py"
    local = root / "_notebook.py"
    if not canonical.exists():
        return []                       # skill is the thing that is broken
    if not local.exists():
        return [(local, f"missing — copy it from {canonical}")]

    want, got = canonical.read_text().splitlines(), local.read_text().splitlines()
    if want == got:
        return []
    n = next((i for i, (a, b) in enumerate(zip(want, got), 1) if a != b),
             min(len(want), len(got)) + 1)
    return [(local, f"differs from {canonical} (first at line {n}) — copy the "
                    f"skill's version down, or promote the local change up so "
                    f"every notebook gets it")]


def check(root, chapters):
    entries = [f for c in chapters
               for f in sorted((root / "chapters" / c).glob("*.qmd"))
               if ENTRY_FILE.match(f.name)]
    # Chapter indexes get the prose checks too. They are prose about the model
    # like any entry, and an unchecked index is how "5.7% thick" survived in
    # one after the model started saying 5.6%.
    pages = entries + [root / "chapters" / c / "index.qmd" for c in chapters
                       if (root / "chapters" / c / "index.qmd").exists()]
    problems = []

    # Derived per chapter: two chapters model different aircraft with different
    # helpers, and one chapter's `trim` says nothing about another's.
    aero = {c: aero_calls_of(root / "chapters" / c) for c in chapters}

    problems += _notebook_drift(root)

    # Rule 5 reads the shared modules too. The other rules are about how an
    # entry is written, so they only ever looked at .qmd files -- but the loop
    # that earned this rule was in _analysis.py, one tier up, where a single
    # wasted iteration is paid by every entry that calls it.
    for c in chapters:
        for name in ("_model.py", "_analysis.py"):
            f = root / "chapters" / c / name
            if not f.exists():
                continue
            for line in fixed_count_solves(f.read_text(), aero[c]):
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
        if fixed_count_solves(cells, aero[f.parent.name]):
            problems.append(
                (f, "`for … in range(…)` runs a solve every trip and cannot "
                    "stop early — iterate to a tolerance with a guard that "
                    "raises"))

        for n in dict.fromkeys(RESULT_NUMBER.findall(prose_of(text))):
            problems.append(
                (f, f"hand-typed number {n!r} in prose — use `{{python}} …`"))

        # The three word budgets.
        n = words(body_prose(text))
        if n > MAX_PROSE:
            problems.append(
                (f, f"{n} words of prose, over the {MAX_PROSE}-word budget — "
                    f"answer, warnings and any other running text, added up; "
                    f"only Specified/Assumed and figure captions are excluded"))

        # Rule 9: one prose section. Every callout is stripped from the RAW text
        # first -- body_prose() has already discarded the ::: fences, so
        # stripping there would find nothing and count each callout's own title
        # as a top-level section. A warning keeps its internal bold lead-ins;
        # what is counted is blocks sitting alongside the answer as peers.
        top = re.sub(r"^:{3,}\s*\{\.callout-\w+\}.*?^:{3,}\s*$", "", text,
                     flags=re.S | re.M)
        top = re.sub(r"```\{python\}.*?```", "", top, flags=re.S)
        top = re.sub(r"^:{3,}.*$", "", top, flags=re.M)
        leads = (re.findall(r"^\*\*([^*]+?\.)\*\*", top, re.M)
                 + re.findall(r"^(#{2,}\s+.+)$", top, re.M))
        if len(leads) > 1:
            problems.append(
                (f, f"{len(leads)} prose sections ({', '.join(l.strip()[:24] for l in leads)})"
                    f" — an entry has one: the answer. Fold the rest into it, or "
                    f"into a callout"))

        # Rule 10: a sibling entry named in prose, not linked. Link *labels* are
        # stripped first, so "[the ballast entry](….qmd)" is the fix rather than
        # a permanent offence.
        unlinked = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", prose_of(text))
        for ref in dict.fromkeys(
                m.group(0) for m in ENTRY_REFERENCE.finditer(unlinked)
                if m.group(1).lower() not in ENTRY_SELF):
            problems.append(
                (f, f"{ref!r} in prose — link it: [{ref}](YYYY-MM-DD-….qmd). A bare "
                    f"reference drifts when the target is retitled or removed"))

        for cap in re.findall(r"^\s*#\|\s*fig-cap:\s*(.+)$", text, re.M):
            n = words(cap.strip().strip('"'))
            if n > MAX_FIG_CAP:
                problems.append(
                    (f, f"figure caption is {n} words, over {MAX_FIG_CAP} — say "
                        f"what is plotted, not what to conclude from it"))

        for title, body in callouts_of(text):
            if title not in ("Specified", "Assumed"):
                continue
            for item in re.findall(r"^\s*\d+\.\s+(.*(?:\n(?!\s*\d+\.).*)*)",
                                   body, re.M):
                n = words(item)
                if n > MAX_CALLOUT_ITEM:
                    problems.append(
                        (f, f"{title} item is {n} words, over "
                            f"{MAX_CALLOUT_ITEM} — record the input, not the "
                            f"argument for it: {' '.join(item.split())[:56]}…"))

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
                       f"({', '.join(sorted(_label(n)[:23] for n in where))}) — promote "
                       f"to _analysis.py:\n        " + "\n        ".join(block)))
    return problems


def _label(name):
    """An entry's name without its date, which is the same for every line."""
    return ENTRY_FILE.sub("", name)


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
    for where, msg in found:
        label = "" if where is None else (
            _label(where.name) if ENTRY_FILE.match(where.name)
            else f"{where.parent.name}/{where.name}")
        print(f"  {label + ': ' if label else ''}{msg}")
    print(f"\n{len(found)} problem(s) in {', '.join(chapters)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
