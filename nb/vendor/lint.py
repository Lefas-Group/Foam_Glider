"""
Format checks for notebook entries. One copy, shared by every notebook.

    uv run python nb/vendor/lint.py <notebook-dir> [chapter ...]

Defaults to every chapter except those a notebook opts out of. Exits non-zero if
anything is flagged, so it can gate a commit.

This lives in `nb/vendor/` rather than in each notebook because it is a CHECKER:
it runs at authoring time, reads the notebook and writes nothing. Nothing it does
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

Thirty-nine rules, each earned by a failure that actually happened. `RULES`
below is the registry -- the numbers, one line each -- and `WHY` beside it is
the failure that earned each one. This docstring used to carry a THIRD copy of
the list, which said "Eighteen rules", stopped at 38, and had disagreed with
`RULES` for months: nothing compared them, because a docstring is not something
a check can hold to anything.

`preflight` compares `RULES` against the list in `system_instruction.md`, which
is the model's copy and is hand-written on purpose -- its wording is tuned for
drafting rather than for diagnosis. That check is what keeps the two in step.

Two details the list cannot carry. A value written as an inline expression counts
as ONE word, so tightening prose is never at odds with computing the numbers in
it. And rules 12 and 15 read the rendered freeze, so they are silent when there
is none -- an unrendered notebook is not thereby clean.
"""
import ast
import json
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
# The four an entry declares in its first cell, printed by footer(). Named
# once because three rules need the same list: rule 2 must not read them as a
# repeated block, rule 18 must refuse them in a callout, and the transcription
# check must not read them as citations.
# The footer line `notebook.footer()` prints, parsed in exactly one place.
# Three things read it -- rule 17 below, `write._render_cost`, and
# `freezediff`'s per-render mask -- and they had three regexes between them,
# which is three chances to miss a wording change.
#
# MEASURED is what varies between two renders of the same page; SOLVES is kept
# out of it because masking the whole line once hid a real 18 -> 2, and the
# limits are kept because a changed ceiling IS worth reporting.
# BOTH spellings. The line used to read "Executed in N s" and every freeze
# written before the rename still says so -- permanently, for the two frozen
# corpus notebooks. Matching only the new wording made rule 17 find nothing and
# skip its check on six entries, so a frozen notebook silently LOST six
# problems: a rule that stops applying looks exactly like a notebook that got
# better. `nb.corpus` is what caught it.
RUNTIME_SECONDS = re.compile(r"(?:Executed|Rendered) in ([\d.]+) s")
RUNTIME_SOLVES = re.compile(r"· (\d+) aero solve")

BUDGET_NAMES = {"ENTRY_CEILING", "SOLVE_BUDGET", "PROBE_POOL", "PROBE_SPENT"}

RESULT_NUMBER = re.compile(r"\d+\.\d{2,}")

# Rule 27. Every top-level name `_notebook.py` binds -- its imports, its helpers
# and its state. READ FROM THE FILE rather than typed out here: the two live in
# the same directory, and a hand-copied list would be wrong the first time
# someone adds a helper, in the silent direction (no rule, no warning). Falls
# back to the names that actually broke a render if the file cannot be parsed,
# so the rule degrades rather than vanishing.
def _machinery_names():
    try:
        tree = ast.parse((pathlib.Path(__file__).parent / "notebook.py").read_text())
    except (OSError, SyntaxError):
        return {"time", "pathlib", "aero_cost", "footer", "_T0"}
    names = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.FunctionDef):
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    # `_T0` is set by _model.qmd, not by _notebook.py, but footer() reads it
    # and an entry can clobber it.
    return names | {"_T0"}


MACHINERY = _machinery_names()

# Lines that recur legitimately and say nothing about duplicated machinery.
#
# `footer(` is here because rule 13 REQUIRES one in every entry: a line the rules
# demand everywhere can never be "promoted to _analysis.py", so flagging it as
# duplication puts two rules in direct contradiction. That surfaced the moment
# deleting a table moved a footer cell up against two lines of plot styling and
# completed a three-line block.
#
# `from ` is here for the same reason, found the same way. `import ` was already
# exempt but `from _analysis import optimize_glider` was not -- so an entry that
# promoted a helper EXACTLY as rule 2 demands was then flagged for the call site
# promotion creates. Measured: eight turns of lint/edit thrash on one entry,
# with the model reasoning "wait, but in my previous attempt, lint did pass".
# A rule must not punish its own remedy.
#
# Axis cosmetics are here for the older reason: every figure hides the same
# spines and sets the same labels, and that says nothing about shared machinery.
# ENTRY_CEILING and SOLVE_BUDGET are here because RULE 28 REQUIRES THEM in every
# entry. Without the exemption rule 2 would flag the two identical lines rule 28
# mandates the moment a third shared line followed -- one rule punishing another
# rule's remedy, which is the failure mode this contract keeps rediscovering.
BOILERPLATE = re.compile(
    r"^(plt\.|ax\d?\.|fig, ax|fig\.|import |from |show_source\(|footer\(|"
    r"for s(ide)? in|\)|\]|\}|else:|try:|finally:|"
    r"ENTRY_CEILING\s*=|SOLVE_BUDGET\s*=|PROBE_POOL\s*=|PROBE_SPENT\s*=)"
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

# Rule 25. Measured across 32 written entries: the most inline expressions any
# one sentence carries is FIVE, and the distribution falls away hard -- 42
# sentences with one, 27 with two, 20 with three, 5 with four, 4 with five, and
# nothing above. Six is therefore a threshold no honest sentence has ever
# reached, and the sentence that earned this rule carried fifteen.
MAX_INLINE_PER_SENTENCE = 5

# Rule 26. Measured across 35 written entries: 34 are a single sentence ending
# in "?", the median is 8 words and the longest legitimate one is 18. The single
# exception is the same entry on all three counts -- two sentences, 26 words, no
# question mark -- because the ask was pasted in verbatim with the chapter's
# constraints still attached. 18 is the cap because it flags that entry and
# nothing else; aim for the median.
MAX_TITLE_WORDS = 18
ENTRY_TITLE = re.compile(r'^title:\s*"(.+)"\s*$', re.M)
SENTENCE = re.compile(r"(?<=[.!?])\s+")
INLINE = re.compile(r"`\{python\}")


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


def _defs_of(chapter):
    """
    {name: (filename, {names it calls})} for the chapter's shared modules.

    One AST pass, two consumers: aero_calls_of() runs its fixed point over the
    call sets, and rule 13 filters by filename to find what `_analysis.py`
    defines. Keeping "what does this chapter define" in one place means the two
    cannot drift apart.
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
        # TOP LEVEL ONLY -- `tree.body`, not `ast.walk`. A function nested
        # inside another is an implementation detail of its parent, not chapter
        # API: nothing outside can call it and no entry can import it. Walking
        # the whole tree made rules 21 and 22 demand that `_dynamics` and
        # `_hit_ground`, defined inside `simulate_launch` and passed to
        # `solve_ivp` by reference, be called or deleted. A run spent seven
        # turns on that, worked out the cause ("the ast module visits all the
        # FunctionDef nodes, even nested ones") and renamed them anyway.
        #
        # Calls are still collected with `ast.walk(node)`, so what a nested
        # helper reaches still counts towards its parent -- `aero_calls_of`'s
        # fixed point and rule 13 both depend on that and are unaffected.
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs[node.name] = (name, {
                    (c.func.attr if isinstance(c.func, ast.Attribute)
                     else getattr(c.func, "id", None))
                    for c in ast.walk(node) if isinstance(c, ast.Call)})
    return defs


def entry_calls(text):
    """
    Every function name an entry calls, from its cells AND its inline expressions.

    The inline half is not optional: a value quoted only in prose, as
    `{python} f"{trim(ap)['alpha']:.1f}"`, is a call that appears in no cell, and
    an entry whose only use of a helper is in its answer sentence is exactly the
    shape that would otherwise slip through unrendered.
    """
    sources = re.findall(r"```\{python\}(.*?)```", text, re.S)
    called = set()
    for src in sources:
        src = re.sub(r"^\s*#\|.*$", "", src, flags=re.M)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        called |= {(c.func.attr if isinstance(c.func, ast.Attribute)
                    else getattr(c.func, "id", None))
                   for c in ast.walk(tree) if isinstance(c, ast.Call)}
    for expr in re.findall(r"`\{python\}([^`]*)`", text):
        try:
            tree = ast.parse(expr.strip(), mode="eval")
        except SyntaxError:
            continue
        called |= {(c.func.attr if isinstance(c.func, ast.Attribute)
                    else getattr(c.func, "id", None))
                   for c in ast.walk(tree) if isinstance(c, ast.Call)}
    return called


def rendered_by_footer(text):
    """
    (names passed to footer()/show_source(), how many footer() cells there are).

    Bare names only: both take live function objects, so `getattr(m, "f")` or a
    comprehension is not something anyone writes there.
    """
    names, footers = set(), 0
    for src in re.findall(r"```\{python\}(.*?)```", text, re.S):
        src = re.sub(r"^\s*#\|.*$", "", src, flags=re.M)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for c in ast.walk(tree):
            if not isinstance(c, ast.Call):
                continue
            fn = getattr(c.func, "id", None)
            if fn in ("footer", "show_source"):
                if fn == "footer":
                    footers += 1
                names |= {a.id for a in c.args if isinstance(a, ast.Name)}
    return names, footers


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
    defs = {n: called for n, (_, called) in _defs_of(chapter).items()}
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

    Only the two INPUT callouts are removed -- they are an index of inputs with
    their own per-item budget. Two vocabularies are recognised because the
    corpus holds two: `Specified`/`Assumed` in the notebooks written before the
    headings were renamed, and `New user specifications`/`New assumptions`
    after. The frozen notebooks keep theirs, so a checker that reads only the
    new names would stop stripping their callouts and charge every word of
    them to rule 6. A `callout-warning` stays in: it is
    addressed to the reader in sentences, and putting a caveat in a coloured box
    does not make it shorter. Hero blocks stay in too; a headline is words.
    """
    t = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    # Drop only the two input callouts, by title, leaving warnings in place.
    t = re.sub(
        r"^:{3,}\s*\{\.callout-\w+\}\s*\n\s*##\s*(?:" + INPUT_CALLOUTS + r")\b"
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


# Rule 1, second half. `prose_of` strips inline expressions before the rule sees
# the text, so a number typed INSIDE one is invisible to it -- which is exactly
# what a run reached for when it wanted to cite an earlier chapter's answer and
# wrote `{python} 0.401`. An expression that reads nothing and calls nothing is
# not a computation; it is a hand-typed number wearing the syntax of one.
#
# Name, Attribute or Call is the test for "reaches something": f"{sink:.3f}"
# carries a Name and passes, f"{0.401:.3f}" and a bare 0.401 do not. Measured
# across all three notebooks -- 618 inline expressions, one hit.
INLINE_BODY = re.compile(r"`\{python\}([^`]*)`")


def _computes_nothing(expr):
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return False            # not ours to report; rule 1 is not a parser
    return not any(isinstance(n, (ast.Name, ast.Attribute, ast.Call))
                   for n in ast.walk(tree))


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
    Rule 11: the notebook's `_notebook.py` matches the canonical copy.

    `_notebook.py` is VENDORED into each notebook rather than shared from here,
    unlike this file. It is exec'd into every page at render time and its output
    is baked into the published HTML, so sharing it would make a notebook
    unrenderable without `nb` installed, and would put a render-affecting
    file outside the Quarto project -- where freeze cannot see edits to it, which
    is the failure mode that has already served stale pages here three times.

    Vendoring costs propagation, so this is what buys it back: an improvement to
    footer() or the plot style shows up as a problem in every notebook that has
    not taken it. Byte equality is the right test because nothing in the file is
    project-specific; any difference is either an un-propagated improvement or an
    accident, and both want a person to decide which.
    """
    # Both vendored files, not just _notebook.py. _probe_base.py is vendored the
    # same way and went unchecked, so an improvement to it sat in one notebook
    # while the scaffold that creates the next one still held the old text --
    # drift invisible precisely because nothing compared them.
    problems = []
    for canonical_name, local_name in (("notebook.py", "_notebook.py"),
                                       ("probe_base.py", "_scratch/_probe_base.py")):
        problems += _one_drift(pathlib.Path(__file__).parent / canonical_name,
                               root / local_name)
    return problems


def _one_drift(canonical, local):
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
                    f"canonical version down, or promote the local change up so "
                    f"every notebook gets it")]


# `<quantity>`, `<value>`, `<why, if it fits>` -- and the chapter-defines
# placeholder that also marks a stub as claimable. Angle-bracketed lowercase
# prose is not something a real index writes, and nothing in the eight real
# indexes matches it.
# 120, not 60. `create_chapter`'s own placeholder is 82 characters -- "<one sentence,
# then a bullet list: the aero method, the section, what is left out>" -- so the
# marker that decides whether a chapter is still claimable was the one placeholder
# this could not see. The cap exists to avoid matching an inequality in prose;
# 120 still does, because prose does not run a hundred characters between < and >
# without a newline.
PLACEHOLDER = re.compile(r"<[a-z][^>\n]{2,120}>")


def _shadowed_machinery(root, chapters, entries):
    """
    Rule 27. An entry may not rebind a name `_notebook.py` owns.

    `_model.qmd` EXECS `_notebook.py` into the page's own globals rather than
    importing it -- every chapter names its model `_model`, so real imports
    would collide in sys.modules -- which means `footer.__globals__` IS the
    entry's namespace. An entry writing `time = h / opt_sink` leaves footer()
    reading a float, and the render dies with

        AttributeError: 'float' object has no attribute 'perf_counter'

    pointing at `_notebook.py:450`: a file rule 11 pins byte-identical and the
    author of the entry therefore cannot fix. Expensive (the solves are already
    paid for), late (render, not lint) and aimed at the wrong file. This says it
    at lint time instead, for nothing. `_notebook.py` also binds private aliases
    so that a miss here degrades rather than crashes; the two are deliberately
    independent.

    TOP-LEVEL BINDINGS ONLY, and that is the whole subtlety. An earlier version
    used ast.walk and flagged `time = np.linspace(0, t_final, N)` inside a
    function in 2026-08-07-03-can-we-rewrite-the-trajectory -- a local, which
    shadows nothing. Walking the tree finds binding sites that cannot possibly
    reach the page namespace.

    Imports are not assignments: `_model.py` legitimately says
    `import aerosandbox as asb`, rebinding `asb` to the same object, and a rule
    that fought the scaffold it ships with would be turned off within a day.

    Chapter files are in scope with entries, because `_model.qmd` execs
    `_model.py` and `_analysis.py` into that same namespace.

    Calibrated before it was written: zero hits across 166 cells in every entry
    of all three notebooks, and zero across 18 chapter .py files.
    """
    out = []
    for f, src in ([(e, entry_cells(e.read_text())) for e in entries] +
                   [(p, p.read_text())
                    for c in chapters
                    for p in (root / "chapters" / c).glob("_*.py")]):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue                      # rule 5 owns unparseable cells
        for node in tree.body:            # top level only -- see the docstring
            targets = (node.targets if isinstance(node, ast.Assign) else
                       [node.target]
                       if isinstance(node, (ast.AnnAssign, ast.AugAssign,
                                            ast.For)) else [])
            for t in targets:
                for name in ast.walk(t):
                    if isinstance(name, ast.Name) and name.id in MACHINERY:
                        out.append((f, f"rebinds `{name.id}`, which "
                                       f"_notebook.py still uses after your "
                                       f"code runs — the traceback would land "
                                       f"in a vendored file you cannot edit; "
                                       f"rename it"))
    return out


def _title_is_a_question(entries):
    """
    Rule 26. The title is the question this entry answers, phrased as one.

    The schema used to demand the ask VERBATIM, which is right when someone asks
    a question and wrong when they state a brief: "optimise a glider for trimmed
    glide. It is constructed of foam 5mm thick density 174.4g/m^2, with a fixed
    300mm span and a sensibly sized, fixed tail" became a title, a sidebar entry
    and a 70-character filename. Worse, every constraint in it belongs to the
    CHAPTER -- so the title was restating what index.qmd already says, which is
    the duplication rule 24's test exists to prevent one tier up.

    Three checks, because the failure showed up on all three and each catches a
    different kind of clunky: a statement rather than a question, two thoughts
    rather than one, and length.

    Rephrasing is now allowed, so the verbatim ask has to survive somewhere it
    cannot be edited: `write.py` records it in the commit body whenever the
    title differs from what was asked.
    """
    out = []
    for f in entries:
        m = ENTRY_TITLE.search(f.read_text())
        if not m:
            continue
        title = m.group(1).strip()
        n = len(title.split())
        if n > MAX_TITLE_WORDS:
            out.append((f, f"title is {n} words, over {MAX_TITLE_WORDS} — it is "
                           f"the question THIS entry answers, not the brief. "
                           f"Constraints that hold for the whole chapter belong "
                           f"in its index.qmd"))
        if len([x for x in SENTENCE.split(title) if x.strip()]) > 1:
            out.append((f, "title is more than one sentence — one question, one "
                           "entry, one title"))
        if not title.endswith("?"):
            out.append((f, "title is not a question — phrase it as the question "
                           "the entry answers, ending in '?'"))
    return out


def _prose_enumeration(pages):
    """
    Rule 25. A list of computed values is a table, not a sentence.

    The escape hatch rule 15 used to leave open. Six optimisation variables
    against their bounds had no legal table under the old 3x4 cap, so the entry
    wrote them into running prose instead: fifteen numbers in one sentence,
    which is exactly the grid-to-be-searched rule 15 exists to prevent, only
    without the alignment to make it scannable. Rule 15 now reaches 6x4 so the
    table is available; this makes the prose form a violation rather than a free
    fallback, which is what stops the pair contradicting each other.

    Counted in the SOURCE, on inline expressions rather than rendered digits, so
    it works before anything has been rendered and cannot be fooled by a number
    that happens to appear in a word.

    If the entry already spends its one visual (rule 14) on a figure, the
    resolution is to decide which of the two carries the answer -- which is what
    rule 14 asks for anyway. An entry that needs both is usually two questions.
    """
    out = []
    for f in pages:
        text = re.sub(r"```.*?```", "", f.read_text(), flags=re.S)
        for sent in SENTENCE.split(text):
            n = len(INLINE.findall(sent))
            if n > MAX_INLINE_PER_SENTENCE:
                out.append((f, f"one sentence carries {n} computed values — "
                               f"past {MAX_INLINE_PER_SENTENCE} it is a table, "
                               f"not a sentence; rule 15 allows 6×4"))
    return out


def _unfinished_index(root, chapters, entries):
    """
    Rule 24. A chapter that has an entry has an index someone finished.

    The scaffold ships `1. **<quantity>: <value>** — <why, if it fits>.` inside
    both callouts, and `create_chapter` substitutes only the prose line, so a
    chapter gets described and its callouts stay as template text -- which then
    renders into the published site verbatim. Nothing caught it: rule 8 counts
    those words and passes at eight, and rule 1 sees no digits.

    Exempt while the chapter has no entries, exactly like rule 19: a freshly
    scaffolded chapter is unfinished on purpose, and becomes a defect only once
    something has been written into it.

    This also catches a chapter that acquired entries while still carrying the
    `claimable_stub` placeholder -- the same failure one tier up.
    """
    out = []
    for c in chapters:
        if not any(e.parent.name == c for e in entries):
            continue
        # BOTH FILES. The placeholder moved to `_inputs.yml` with the items and
        # with `defines:`, and this went on reading only the page -- so a
        # chapter could keep `<one sentence, then a bullet list…>` for ever and
        # nothing said so. The index is still checked because its own scaffold
        # placeholders (a title, a listing field) land there.
        for name in ("_inputs.yml", "index.qmd"):
            where = root / "chapters" / c / name
            try:
                text = where.read_text()
            except OSError:
                continue
            # COMMENTS STRIPPED FIRST. `_inputs.yml`'s own header explains the
            # format with `- <id>: <text>`, and both look exactly like a
            # scaffold placeholder to this regex -- so every chapter would
            # fail rule 24 for ever, on the instructions telling it how not to.
            text = "\n".join(l for l in text.splitlines()
                             if not l.lstrip().startswith("#"))
            hits = PLACEHOLDER.findall(text)
            if hits:
                out.append((where, f"still carries scaffold placeholders "
                                   f"({', '.join(sorted(set(hits))[:3])}) — say "
                                   f"what is true of EVERY entry in this "
                                   f"chapter, or delete the line"))
    # AND THE NOTEBOOK'S OWN BRIEF, on a different trigger from the chapter
    # one: not "this chapter has an entry" but "this notebook has an entry".
    # A placeholder brief before the first entry is a notebook nobody has
    # started; after it, it is a top level that lies -- and it lied silently,
    # because a fresh notebook lints clean with `- <id>: "**<what>**: <value>."`
    # still in it and nothing watched the root at all.
    #
    # `nb new --spec/--assume` is the way to fill it, so it is filled before
    # the first run rather than after the model has been shown the placeholder
    # as fact. The prefix is built ONCE, at `nb ask`.
    if entries:
        where = root / "_inputs.yml"
        try:
            text = "\n".join(l for l in where.read_text().splitlines()
                             if not l.lstrip().startswith("#"))
        except OSError:
            text = ""
        hits = PLACEHOLDER.findall(text)
        if hits:
            out.append((where, f"the notebook's BRIEF still carries scaffold "
                               f"placeholders ({', '.join(sorted(set(hits))[:3])})"
                               f" — say what is true of the whole aircraft, or "
                               f"delete the line. It is rendered on the front "
                               f"page and inherited by every chapter"))
    return out


def _loud_solves(root, chapters, entries):
    """
    Rule 23. A `solve()` says whether it prints.

    IPOPT writes a sixty-line convergence table on every call, and an entry that
    publishes one has buried its answer under the working -- which the scope
    rules already forbid in prose and nothing enforced in code. Measured: two
    consecutive entries did it, both with the table ahead of the hero value.

    The notebooks had already solved this by CONVENTION and nothing held them to
    it. The mature chapters thread a parameter -- `def optimise(..., verbose=
    False)` then `opti.solve(verbose=verbose)` -- across seventeen call sites,
    and only the chapter written after that convention stopped being copied says
    a bare `opti.solve()`.

    So the rule is that the choice is MADE, not which way it goes.
    `verbose=verbose` stays legal, and deliberately: it is what lets a probe turn
    the table back on while diagnosing, where it is genuinely wanted. Requiring
    `False` would take that away to fix a problem entries have and probes do not.

    Scoped like rule 5, over the shared modules as well as the entry cells: the
    solve is usually two files from the page. In the entry that earned this, the
    cell called `optimize_glider()` and the `solve` was in `_analysis.py`, so an
    entry-only rule would have found nothing at all.
    """
    out = []
    for c in chapters:
        chapter = root / "chapters" / c
        pages = [(chapter / n, None) for n in ("_model.py", "_analysis.py")]
        pages += [(e, "cells") for e in entries if e.parent.name == c]
        for f, kind in pages:
            if not f.exists():
                continue
            src = entry_cells(f.read_text()) if kind else f.read_text()
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "solve"):
                    continue
                if any(k.arg == "verbose" for k in node.keywords):
                    continue
                where = f"line {node.lineno}: " if not kind else ""
                out.append((f, f"{where}solve() does not say whether it prints "
                               f"— IPOPT writes a convergence table by default "
                               f"and an entry must not publish one. Take a "
                               f"`verbose=False` parameter and pass it through, "
                               f"so a probe can still turn it on"))
    return out


def _empty_model(root, chapters, entries):
    """
    Rule 19. A chapter that has an entry has a vehicle in `_model.py`.

    The chapter index renders `_model.py` in full, so it is where a reader looks
    for the aircraft. An entry that defines the vehicle in its own cell puts it
    somewhere the chapter cannot show it and the next entry cannot reuse it --
    and nothing else catches that. Rule 2 keys repeated blocks to a SET of entry
    filenames and fires at two, so on a chapter's first entry it is structurally
    incapable of firing: a sixty-line inline vehicle lints perfectly clean, and
    did.

    A chapter with no entries is exempt, which is what keeps a freshly
    scaffolded chapter clean until something is written into it.
    """
    out = []
    for c in chapters:
        if not any(e.parent.name == c for e in entries):
            continue
        f = root / "chapters" / c / "_model.py"
        if not f.exists():
            out.append((f, "missing — the chapter's vehicle lives here"))
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue        # the render will say so, and say it better
        if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef))
               and not n.name.startswith("_")
               or isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and not t.id.startswith("_")
                       for t in n.targets)
               for n in tree.body):
            continue
        out.append((f, "defines nothing — the vehicle belongs here, not in the "
                       "entry cell. A parametric vehicle is a function taking "
                       "the design variables and returning the Airplane"))
    return out


def entry_cells(text):
    """An entry's `{python}` cells, concatenated, with `#|` options stripped."""
    return "\n".join(
        re.sub(r"^\s*#\|.*$", "", cell, flags=re.M)
        for cell in re.findall(r"```\{python\}(.*?)```", text, re.S))


def _shared_hygiene(root, chapters, entries):
    """
    Rules 20, 21 and 22 -- where a chapter's helpers live, and which are API.

    `_analysis.py` exists to force CONSISTENCY between entries: one
    implementation, so entries cannot drift apart. Measured, that is working --
    of twelve helpers that exist in more than one chapter (forks copy the file),
    eleven are byte-identical, and the one difference is the fork's declared
    purpose. The failure it prevents is on record: four subtly different neutral
    points in one chapter, one of them taking its moment reference from the
    wrong station.

    It also saves tokens, but only on REUSE: a signature sits in the cached
    prefix forever, against one avoided read of a sibling entry. So the rules
    pull in both directions on purpose -- 20 promotes what must not diverge, 21
    removes what nothing calls, 22 keeps what is merely internal out of the
    prefix and out of `api()`.

    ALL THREE ARE WARNINGS, and 21 and 22 for a different reason than 20. They
    describe the chapter's accumulated state, not the entry being written: an
    established chapter carries 27 of them, and blocking on those would make
    every run in it start by refactoring `_analysis.py` -- work nobody asked
    for, on code the run did not touch, which is itself the refactor that needs
    proving. They are for a human doing a cleanup pass, or for the run that
    happens to be editing that function anyway. Rule 20 is a warning for the
    narrower reason that its false-positive rate is not yet measured.
    """
    out = []
    for c in chapters:
        chapter = root / "chapters" / c
        mine = [e for e in entries if e.parent.name == c]
        defs = _defs_of(chapter)
        shared = {n: called for n, (f, called) in defs.items()
                  if f == "_analysis.py"}
        model_names = {n for n, (f, _) in defs.items() if f == "_model.py"}
        expensive = aero_calls_of(chapter)
        f_analysis = chapter / "_analysis.py"

        # Who calls what, from the entries.
        called_by_entries = {n: sum(1 for e in mine
                                    if re.search(rf"\b{re.escape(n)}\s*\(", e.read_text()))
                             for n in shared}
        # Every definition in the chapter, not just `_analysis.py`: a helper
        # called only from `_model.py` is still called.
        called_internally = {
            n: any(n in called for m, (_, called) in defs.items() if m != n)
            for n in shared}

        # Rule 20. An entry-local function that reaches the vehicle is chapter
        # machinery: it is a measurement of the aircraft, and two entries
        # measuring the same thing differently is the failure `_analysis.py`
        # exists to prevent. A function that only formats an already-computed
        # value diverges harmlessly and stays where it is. WARNING while the
        # false-positive rate is unknown -- a genuinely one-off measurement
        # trips it, and forcing that into the prefix forever is its own cost.
        for e in mine:
            try:
                tree = ast.parse(entry_cells(e.read_text()))
            except SyntaxError:
                continue
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                reached = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                hits = reached & (model_names | set(shared) | expensive)
                if hits:
                    out.append((e, f"(warning) `{node.name}()` is defined in the "
                                   f"entry but reaches the vehicle "
                                   f"({', '.join(sorted(hits)[:3])}) — a "
                                   f"measurement of the aircraft belongs in "
                                   f"_analysis.py, where a sibling cannot "
                                   f"reimplement it differently"))

        if not f_analysis.exists():
            continue

        for n in sorted(shared):
            # Rule 21. Nothing reaches it: not an entry, not another helper.
            # Dead here is worse than dead elsewhere -- someone calls the stale
            # one and the chapter has two answers again.
            if not called_by_entries[n] and not called_internally[n]:
                out.append((f_analysis, f"(warning) `{n}()` is called by no "
                                        f"entry and no other helper — delete "
                                        f"it, or call it"))
            # Rule 22. Internal-only, but public: it costs a line of the cached
            # prefix and a line of `api()` on every run, and an entry that does
            # not call it does not need to know it exists.
            elif not called_by_entries[n] and not n.startswith("_"):
                out.append((f_analysis, f"(warning) `{n}()` is only called by "
                                        f"other _analysis.py functions — rename "
                                        f"it `_{n}` so it stays out of the "
                                        f"prefix and out of api()"))
    return out


def tables_in(md):
    """
    Every markdown pipe table in `md`, as (body_rows, columns).

    A table is a header line, a `|---|` separator, then body rows. Counting the
    body only, and the columns from the header, is what the size rule is stated
    in: "6x4, excluding the header".
    """
    lines = [l.strip() for l in md.splitlines()]
    found, i = [], 0
    while i < len(lines) - 1:
        if (lines[i].startswith("|")
                and re.fullmatch(r"\|[\s:|-]+\|", lines[i + 1] or "")):
            cols = lines[i].strip("|").count("|") + 1
            body = i + 2
            while body < len(lines) and lines[body].startswith("|"):
                body += 1
            found.append((body - i - 2, cols))
            i = body
        else:
            i += 1
    return found


# What makes a figure a DRAWING of the aircraft rather than a plot of its
# behaviour. Named functions, not a guess: these are what aerosandbox offers and
# what every three-view in these notebooks is made with.
DRAWING = re.compile(r"\b(draw_three_view|draw_wireframe|\.draw\s*\()")


def _visuals_and_tables(root, chapters, entries):
    """
    Rules 14 and 15: how many visuals an entry shows, and how big a table may be.

    BOTH now read the RENDERED output, for the reason rule 15 always did: a
    table produced by `print()` or `display(Markdown(...))` inside a cell is not
    parseable as a table anywhere in the source. Rule 14 counted `fig-`/`tbl-`
    cell labels, and the two entries that prompted this change carry neither --
    one emits its table through `display(Markdown(md))` with no label, the other
    captions it inline as `{#tbl-plans}`, which is not a cell option. Both were
    invisible, so "one visual per entry" was unenforced for exactly the form the
    model had started choosing.

    Counting figures by label and tables by what rendered cannot double-count:
    a figure reaches the freeze as an image, never as pipe-markdown.

    No freeze means the source is counted instead, exactly as rule 12 -- and
    rule 12 is what keeps the freeze honest.
    """
    found = []
    for f in entries:
        text = f.read_text()
        figures = re.findall(r"^\s*#\|\s*label:\s*(fig-[\w-]+)", text, re.M)

        # Hand-written tables in the .qmd, plus whatever the page rendered.
        seen = tables_in(re.sub(r"```.*?```", "", text, flags=re.S))
        frozen = (root / "_freeze" / "chapters" / f.parent.name / f.stem
                  / "execute-results" / "html.json")
        if frozen.exists():
            try:
                md = json.loads(frozen.read_text())["result"]["markdown"]
                # ECHOED SOURCE IS NOT A TABLE. A cell without `echo: false`
                # puts its own text in the output, so an entry building a
                # markdown table in an f-string had that f-string counted as a
                # second table -- `{c_root:.1f}` and all. Measured on one entry
                # of 77; it made the rendered count 2 for a page showing 1.
                seen += tables_in(re.sub(r"^```.*?^```", "", md, flags=re.S | re.M))
            except (ValueError, KeyError, TypeError):
                pass

        # The cap is ONE, raised to two when one of the figures is a drawing of
        # the aircraft rather than a second plot. A schematic and a plot are
        # different claims -- "what does it look like" and "how does it behave"
        # -- and the old cap made the second displace the first, which is how
        # three chapters ended up with no picture of the aeroplane at all.
        # Lint cannot judge "schematic", but it can see which function drew it.
        drawn = bool(DRAWING.search(text))
        cap = 2 if drawn and figures else 1
        n = len(figures) + len(seen)
        if n > cap:
            what = ", ".join(figures + [f"{r}×{c} table" for r, c in seen])
            found.append((f, (
                f"{n} visuals ({what}) — a table counts as a figure, and an "
                f"entry shows one" + (" (two, when one is a drawing of the "
                f"aircraft)" if drawn else "") + f". Delete whichever is not "
                f"carrying the answer")))
        for rows, cols in seen:
            # 6x4, raised from 3x4-or-4x3. The tighter cap was written against a
            # table DECORATING a finding -- the failure behind rule 14 was 72
            # numbers printed under a plot showing the same quantities. It also
            # caught the case where the table IS the finding: six optimisation
            # variables against their bounds is 6x4 at minimum, there was no
            # legal table for it, and the entry fell back to prose -- which has
            # no row limit, so it became a fifteen-number run-on sentence. That
            # is the grid-to-be-searched this rule exists to prevent, minus the
            # alignment. Rule 25 now closes that escape; this opens the door the
            # answer should have gone through. Measured: every table in 32
            # written entries is 3x3 or 4x3, so nothing existing needed it.
            if not (rows <= 6 and cols <= 4):
                found.append((f, (
                    f"table is {rows}×{cols} — at most 6×4 excluding the "
                    f"header; past that it is a data dump, not evidence")))
    return found


def _stale_freeze(root, chapters):
    """
    A chapter's shared module edited without re-rendering.

    Freeze tracks the page, not its includes, so editing `_model.py` leaves
    every entry serving values the current model does not produce -- silently.
    That has happened here once: a ply count changed, nothing re-executed, and
    an entry went on rendering a duration the model no longer gave. It surfaced
    only because that entry happened to carry an assert.

    Detected through git rather than a stored hash: if a shared module is dirty
    while the chapter's freeze is not, the freeze predates it. Self-clearing,
    because footer()'s runtime line means a real re-render always rewrites the
    freeze. mtimes were rejected -- `_freeze/` is committed so a clone renders
    without solving, and git writes files at checkout in arbitrary order, so a
    clean clone would fail at random and train you to ignore the rule.
    """
    import subprocess
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode:                      # not a git repo; nothing to compare
        return []
    dirty = {line[3:].strip().strip('"') for line in out.stdout.splitlines()}

    found = []
    for c in chapters:
        frozen = list((root / "_freeze" / "chapters" / c).glob(
            "*/execute-results/html.json")) if (
            root / "_freeze" / "chapters" / c).exists() else []
        if not frozen:
            continue                        # no freeze serves nothing stale
        touched = sorted(
            # `_inputs.yml` and `_fork.yml` joined the list when the chapter
            # index stopped carrying its callouts and started RENDERING them:
            # `chapter_inputs()` and `chapter_lineage()` read those two files,
            # so editing one changes the page exactly as editing `_model.qmd`
            # does, and Quarto's freeze tracks neither.
            n for n in ("_model.py", "_analysis.py", "_model.qmd",
                        "_inputs.yml", "_fork.yml")
            if any(p.endswith(f"chapters/{c}/{n}") for p in dirty))
        if touched and not any(f"_freeze/chapters/{c}/" in p for p in dirty):
            found.append((
                root / "chapters" / c / touched[0],
                f"modified, but the freeze is not — {len(frozen)} frozen "
                f"page(s) are serving values the current model may not produce. "
                f"NOT YOURS TO FIX — the write phase re-proves the chapter "
                f"itself, after lint passes and the entry builds, and will show you any "
                f"answer that moved. Do not run a checker by hand: it re-"
                f"renders the notebook, costs two to three minutes a call, and "
                f"changes nothing the run was not going to do anyway."))
    return found


def _bound(source, name):
    """
    (was it bound?, to what) for a module-level name in `source`.

    Two-valued because binding None is a real answer -- "deliberately unbounded"
    -- and must not read the same as having said nothing, which is what takes
    the default. Conflating them is how an opt-out and an oversight would become
    indistinguishable to the rules below.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return True, ast.literal_eval(node.value)
            except ValueError:
                return True, None       # bound, but not to a readable literal
    return False, None


def _defaults(root):
    """The notebook's own DEFAULT_* values, read from its `_notebook.py`."""
    nb = root / "_notebook.py"
    src = nb.read_text() if nb.exists() else ""
    _, budget = _bound(src, "DEFAULT_SOLVE_BUDGET")
    _, ceiling = _bound(src, "DEFAULT_ENTRY_CEILING")
    return budget, ceiling


def limits_of(root, entry):
    """
    (solve budget, entry ceiling) declared by an ENTRY, falling back to the
    notebook defaults.

    Budgets moved from the chapter to the entry because the entry is the unit of
    work AND the unit the user is asked about: the render ceiling is granted at
    the prompt, so it belongs in the page that spends it. The chapter-level
    `_budget.py` is gone -- its own header records why it had to exist, a fork
    that "silently inherited SOLVE_BUDGET = None" from its parent. Nothing is
    inherited now, because nothing is chapter-scoped.

    No new runtime machinery was needed: `_notebook.py` is EXEC'd into the page
    namespace and `_budgeted_solve` re-reads `_active_budget()` on every call,
    so a binding in the entry's own cell is already in force for every later
    solve. Measured before this was written -- an entry binding
    SOLVE_BUDGET = 0.001 reported it from solve_budget() and had its solve
    refused by ipopt.

    Returns the literal `None` where an entry bound None, so rule 28 can tell
    that apart from having said nothing, which takes the default.
    """
    d_budget, d_ceiling = _defaults(root)
    try:
        src = entry_cells(entry.read_text())
    except OSError:
        return d_budget, d_ceiling
    found_b, budget = _bound(src, "SOLVE_BUDGET")
    found_c, ceiling = _bound(src, "ENTRY_CEILING")
    return (budget if found_b else d_budget,
            ceiling if found_c else d_ceiling)


# How long a render may take, derived from what it will actually execute.
#
# THE GRANT GOVERNS. The user is asked for a render budget at the prompt, the
# entry declares it as ENTRY_CEILING, and it is the whole of the executing cost
# here -- no multiplier. The earlier 4x slack made that promise false: a granted
# 20 s produced a 995 s deadline, of which only 80 s came from the grant.
#
# The trade is real and is the reason the slack existed: the same solve measured
# 533.9 s against a 145 s baseline purely from machine load, 3.7x, so a busy
# laptop can now kill honest work. The recovery is a bigger number at the
# prompt, which is the only knob and is meant to be.
#
# FLOOR is quarto's own startup and pandoc, which happen whether or not anything
# executes: one frozen page measured 11.4 s and 11.6 s, and an UNFROZEN index --
# which execs _notebook.py, _model.py and _analysis.py, importing aerosandbox --
# measured 11.2 s, indistinguishable. So an index costs the floor and little
# else, where it used to be charged a 200 s entry default. 35 s is ~3x the
# measurement; erring high on a fixed cost is cheap, and it keeps the grant
# visible as a separate term rather than buried in a multiplier.
RENDER_FLOOR = 35.0         # startup + pandoc, once
RENDER_PER_PAGE = 5.0       # pandoc per page in the target
RENDER_INDEX = 15.0         # a page that executes definitions but never a solve


def unfrozen(root, chapters):
    """
    Pages with no freeze at all.

    NOT the same as "what a render will execute" -- see `will_execute`, which
    is what every deadline and every progress line should be counting. This
    answers only the narrower question `check` asks after it has deleted the
    freezes it invalidated.
    """
    out = []
    for c in chapters:
        d = root / "chapters" / c
        if not d.is_dir():
            continue
        for page in sorted(d.glob("*.qmd")):
            if page.name.startswith("_"):
                continue            # includes, not pages
            f = (root / "_freeze" / "chapters" / c / page.stem
                 / "execute-results" / "html.json")
            if not f.exists():
                out.append(page)
                continue
            # A freeze OLDER than the page it froze is stale, and Quarto
            # re-executes it. Checking only for absence sized a project render
            # at "nothing to execute" right after seven entries were edited,
            # and the render was killed at 200 s having re-run all of them.
            # Same fault as the one this function's docstring already records:
            # answering "is there a freeze" when the question is "will this
            # page run".
            try:
                if page.stat().st_mtime > f.stat().st_mtime:
                    out.append(page)
            except OSError:
                out.append(page)
    return out


def _root_index_stale(root):
    """
    The notebook's front page, if a PROJECT render would execute it, else None.

    It is not under `chapters/`, so every function that sizes a render walked
    straight past it -- `will_execute`, `unfrozen`, `render_deadline` and
    `pages_of` all enumerate `chapters/*/*.qmd`. That was harmless while the
    page was incidental. It stopped being harmless when the lineage diagram
    started counting entries: the front page now re-renders on every commit,
    and `render_deadline(root, "index.qmd")` returned RENDER_FLOOR alone while
    the announce line said "0 pages", for a render that certainly executes one.

    Same staleness test `unfrozen` applies to an entry: no freeze, or a freeze
    older than the page. The page also depends on every chapter's `_fork.yml`
    and entry COUNT, which no mtime can see -- that is rule 40's job, and this
    is only about sizing the render.
    """
    page = root / "index.qmd"
    if not page.exists():
        return None
    f = root / "_freeze" / "index" / "execute-results" / "html.json"
    try:
        if f.exists() and page.stat().st_mtime <= f.stat().st_mtime:
            return None
    except OSError:
        pass
    return page


def will_execute(root, target=None):
    """
    The pages `quarto render <target>` will actually RUN, freeze included.

    Quarto honours `freeze` on a PROJECT render only. Name a target -- a
    chapter directory or a single `.qmd` -- and every page under it executes,
    whatever `_freeze/` holds.

    Measured on 2026-09-18, this notebook, nothing else running:

        quarto render chapters/01-foam-glider   5 kernels, 110 s, twice running
        quarto render                           0 kernels, every page cached

    with `unfrozen()` reporting an empty list throughout. Everything that sized
    itself on the freeze was therefore sizing a targeted render at zero work:
    the write phase announced "0 page(s) to execute" and then killed its own
    render on a 40 s deadline, on a chapter whose pages needed minutes. That
    reads exactly like a wedged kernel, and was handed to the model as a bug in
    an entry that built perfectly well.
    """
    root = pathlib.Path(root)
    target = root if target is None else pathlib.Path(target)
    chapters = sorted(d.name for d in (root / "chapters").iterdir() if d.is_dir())
    pages = [q for c in chapters
             for q in sorted((root / "chapters" / c).glob("*.qmd"))
             if not q.name.startswith("_")]
    # The front page belongs to no chapter and was in nobody's count. It is a
    # page a render executes like any other -- and since the lineage diagram
    # started counting entries, one that re-renders on every commit.
    index = root / "index.qmd"
    if target.is_file():
        return [q for q in pages + [index] if q == target]
    if target != root:
        return [q for q in pages if target in q.parents]
    # The one case where the freeze counts.
    frozen = set(pages) - set(unfrozen(root, chapters))
    out = [q for q in pages if q not in frozen]
    stale = _root_index_stale(root)
    return ([stale] + out) if stale else out


def render_deadline(root, target=None):
    """
    Seconds a `quarto render` of `target` may take before it is killed.

    Scoped to the TARGET, which is what makes the grant mean anything. It used
    to size every render from the whole project: rendering one entry was
    charged for all 11 pages and for a chapter index it was not rendering, so
    the number had nothing to do with the page being built.

    `target` is a path -- the notebook root, a chapter directory, or one .qmd --
    or None for the whole project. What executes under it comes from
    `will_execute`, which knows the thing this function used to get wrong: the
    freeze only spares a page on a PROJECT render.

    An entry contributes the ENTRY_CEILING it declares, which is the number the
    user granted at the prompt. Anything else that executes -- an index -- takes
    RENDER_INDEX, because it defines and prints rather than solving.
    """
    root = pathlib.Path(root)
    target = root if target is None else pathlib.Path(target)
    # ALL chapters, not chapters_of(): a `_lint-skip` marker exempts a chapter
    # from being CHECKED, and quarto renders it regardless. Sizing the deadline
    # from the linted set would have left a project render of this notebook with
    # a budget for 10 of its 31 pages.
    chapters = sorted(d.name for d in (root / "chapters").iterdir() if d.is_dir())
    pages = [q for c in chapters
             for q in sorted((root / "chapters" / c).glob("*.qmd"))
             if not q.name.startswith("_")]
    # The front page, on the two targets that reach it. Without this a targeted
    # render of index.qmd was budgeted RENDER_FLOOR and nothing else, and a
    # project render was charged for every page except the one that is now
    # rebuilt on every commit.
    pages = pages + [root / "index.qmd"]
    if target.is_file():
        pages = [q for q in pages if q == target]
    elif target != root:
        pages = [q for q in pages if target in q.parents]

    executing = set(will_execute(root, target))
    total = RENDER_FLOOR + RENDER_PER_PAGE * len(pages)
    for page in pages:
        if page not in executing:
            continue
        if ENTRY_FILE.match(page.name):
            _, ceiling = limits_of(root, page)
            total += ceiling if ceiling else (_defaults(root)[1] or 200.0)
        else:
            total += RENDER_INDEX
    return total


def render_quarto(target, root, cwd=None):
    """
    `quarto render <target>`, killed if it stops making progress.

    Returns the CompletedProcess. On a timeout it returns a stand-in with
    returncode 124 and a message naming the page Quarto was on, because the
    three call sites all want the same thing and a bare TimeoutExpired says only
    that time ran out.

    Naming the page is the whole point. It is the property `budgets.py` asks of
    every layer -- the inner limit should fire first, "because it knows why it
    killed the probe and says so" -- and Quarto prints `[n/N] path` as it goes,
    which `TimeoutExpired.stdout` preserves.
    """
    import subprocess
    deadline = render_deadline(root, target)
    try:
        # stdin=DEVNULL: a render is the longest child this system spawns, and
        # an inherited terminal stdin is how a background run gets SIGTTIN'd
        # into a stop that looks exactly like a wedge. See `tools/probe.py`.
        return subprocess.run(["quarto", "render", str(target)],
                              capture_output=True, text=True, cwd=cwd,
                              stdin=subprocess.DEVNULL, timeout=deadline)
    except subprocess.TimeoutExpired as t:
        blob = ((t.stdout or b"").decode() if isinstance(t.stdout, bytes)
                else (t.stdout or ""))
        # Quarto's `[n/N] path` progress lines are the best answer, but it
        # BLOCK-BUFFERS to a pipe, so a killed render usually leaves stdout
        # empty -- measured. The work list is the fallback and is often exact:
        # a render with one page to execute can only have been stuck on it.
        #
        # SCOPED TO THE TARGET, and from the same call the deadline came from.
        # Project-wide `unfrozen` named pages the render was never going to
        # touch: one killed render reported "3 page(s) awaiting execution"
        # against a deadline sized for one, which is not a near miss but two
        # different questions printed as one answer.
        todo = will_execute(root, target)
        n = len(todo)
        seen = re.findall(r"\[\d+/\d+\][^\n]*", blob)
        if seen:
            where = f", on {seen[-1].strip()}"
        elif n == 1:
            where = f", on {todo[0].parent.name}/{todo[0].name}"
        elif todo:
            where = (f", somewhere in {n} page(s) awaiting execution: "
                     + ", ".join(q.name for q in todo[:3])
                     + (" …" if n > 3 else ""))
        else:
            where = ""
        return subprocess.CompletedProcess(
            t.cmd, 124, blob,
            f"render killed after {deadline:.0f} s{where}\n"
            f"  ({RENDER_FLOOR:.0f} s floor + {RENDER_PER_PAGE:.0f} s/page "
            f"+ the ENTRY_CEILING each of {n} executing page(s) declares)\n"
            f"  Nothing was advancing. The ceiling is what was granted at the "
            f"prompt and it governs directly -- ask for more there if the work "
            f"is genuinely this expensive.")


def _budget_rules(root, chapters, entries):
    """
    Rules 16, 17, 18 and 28 -- what an entry may spend, declared by the entry.

    These were chapter-scoped, read from an optional `_budget.py`. That file is
    gone: budgets belong to the entry, which is both the unit of work and the
    unit the user is asked about, since the render ceiling is granted at the
    prompt before the run starts.

    28 BLOCKS and is the load-bearing one, because the ceiling is no longer
    advisory -- `render_deadline()` derives an actual subprocess timeout from
    it. An entry that declares nothing would be bounded by the notebook default
    silently; an entry that declares None would have no bound at all, which is
    the state that let a render hang unnoticed.

    17 still WARNS below the ceiling, for the reason it always did: the same
    solve here measured 533.9 s against a 145 s baseline purely from load, so a
    hard block on wall clock would fail on a busy machine and pass on an idle
    one. It blocks only PAST the ceiling, where load cannot be the explanation.
    """
    problems = []
    for e in entries:
        budget, ceiling = limits_of(root, e)
        src = entry_cells(e.read_text())
        found_b, _ = _bound(src, "SOLVE_BUDGET")
        found_c, _ = _bound(src, "ENTRY_CEILING")

        # 28: both declared, neither None.
        for name, found, value in (("SOLVE_BUDGET", found_b, budget),
                                   ("ENTRY_CEILING", found_c, ceiling)):
            if not found:
                problems.append(
                    (e, f"declares no {name} — every entry states what it may "
                        f"spend, in its own first cell; the render ceiling is "
                        f"the one granted at the prompt"))
            elif value is None:
                problems.append(
                    (e, f"binds {name} = None — unbounded is no longer an "
                        f"option: the ceiling is what bounds the render, and "
                        f"a render with no bound is one that can hang"))

        # 28, second half: a solve cannot outlive the render containing it.
        # Declaring SOLVE_BUDGET = 60 under ENTRY_CEILING = 20 is not a slack
        # setting, it is two numbers that cannot both hold -- the render is
        # killed at 20 s and the solve budget never binds anything. Seen the
        # first time an entry was written against a granted ceiling, so the
        # combination is one the brief invites by calling SOLVE_BUDGET "yours".
        if (budget is not None and ceiling is not None
                and found_b and found_c and budget > ceiling):
            problems.append(
                (e, f"declares SOLVE_BUDGET = {budget:.0f} s under an "
                    f"ENTRY_CEILING of {ceiling:.0f} s — one solve cannot "
                    f"outlive the render that contains it. Lower the solve "
                    f"budget, or ask for a bigger ceiling with ask_specified; "
                    f"do not raise ENTRY_CEILING yourself, it was granted"))

        # 18, inverted. Budgets used to be REQUIRED in the Specified callout,
        # on the reasoning that a granted number is a Specified input. True, but
        # it crowded out the thing the callout exists for: an entry whose only
        # Specified items were two budgets recorded nothing about its own
        # design. `footer()` prints them now, from the declarations themselves,
        # so the page still shows them and the callout is free again.
        spec = "".join(body for title, body in callouts_of(e.read_text())
                       if title in ("Specified", "New user specifications"))
        named = sorted(n for n in BUDGET_NAMES if n in spec)
        if named:
            problems.append(
                (e, f"declares {', '.join(named)} in the `## Specified` callout "
                    f"— footer() prints the budgets now, so that callout is for "
                    f"what the DESIGN was committed to. Delete the budget "
                    f"item(s); if nothing else was specified, say `None.`"))

        # 17: what the frozen page actually cost.
        if ceiling is None:
            continue
        hj = (root / "_freeze" / "chapters" / e.parent.name / e.stem
              / "execute-results" / "html.json")
        if not hj.exists():
            continue
        m = RUNTIME_SECONDS.search(
            json.loads(hj.read_text()).get("result", {}).get("markdown", ""))
        if not m:
            continue
        spent = float(m.group(1))
        if spent > ceiling:
            problems.append(
                (e, f"took {spent:.0f} s, past its ENTRY_CEILING of "
                    f"{ceiling:.0f} s — make it cheaper, or ask for more"))
        elif spent > ceiling / 2:
            problems.append(
                (e, f"(warning) took {spent:.0f} s, over half the "
                    f"{ceiling:.0f} s ceiling"))

    # 16: the budget is negotiated once, not overridden per call site.
    for c in chapters:
        f = root / "chapters" / c / "_analysis.py"
        if not f.exists():
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "solve"):
                continue
            local = sorted(k.arg for k in node.keywords
                           if k.arg in ("max_runtime", "behavior_on_failure"))
            if local:
                problems.append(
                    (f, f"solve() on line {node.lineno} passes "
                        f"{', '.join(local)} — that silently overrides the "
                        f"entry's SOLVE_BUDGET. Raise the budget in the entry "
                        f"instead, where it is on the record"))

    # 18, the other half: a CHAPTER INDEX does not declare a budget. The
    # scaffold template already says so -- "Budgets do NOT go here: each entry
    # declares its own" -- but three indexes inherited the line from the
    # chapter-budget era, and it is not merely stale. The index RENDERS the
    # number, so changing the budget in force rewrites the index's output,
    # which `check` reports as a changed value and the refactor gate then holds
    # an unrelated entry for. That happened: `index: +4. Solve budget 60 s`.
    for c in chapters:
        index = root / "chapters" / c / "index.qmd"
        if not index.exists():
            continue
        try:
            text = index.read_text()
        except OSError:
            continue
        hit = next((n for n in ("solve_budget(", "SOLVE_BUDGET", "ENTRY_CEILING")
                    if n in text), None)
        if hit:
            problems.append(
                (index, f"declares a budget (`{hit}`) — budgets belong to the "
                        f"ENTRY, which states its own in its first cell and its "
                        f"own Specified callout (rules 18 and 28). An index "
                        f"that renders one also makes every budget change look "
                        f"like a changed answer to `check`"))
    return problems

# The chapter-local modules `_model.qmd` EXECS into the page namespace. They are
# not importable and never were: `execute-dir: project` puts the cwd at the
# notebook root, so `chapters/NN-name/` is not on sys.path.
EXECD = ("_model", "_analysis", "_notebook")


def _composition(root, chapters, entries):
    """
    Rules 29 and 30 -- the two halves of how a chapter composes.

    Rule 29 is an ERROR, unlike its neighbours here, because the page does not
    BUILD: `from _analysis import optimize_glider_unswept_c4` cost a whole run,
    dying at the render with ModuleNotFoundError after lint had passed clean.
    The names are already in scope; importing them is the mistake a fresh
    chapter invites, because there is no sibling to copy the convention from.

    Rule 30 guards the justification rule 19 rests on -- "the vehicle goes in
    `_model.py` because the chapter index renders that file, so it is where a
    reader looks for the aircraft". The scaffold ships that block; a model that
    rewrites index.qmd with `write_file` rather than editing it drops the block
    and nothing noticed, leaving a chapter whose aircraft appears nowhere.

    Calibrated across every chapter of all three notebooks before being
    written: rule 29 matched the two lines from that failed run and nothing
    else, rule 30 matched that run's index and nothing else.
    """
    out = []
    for c in chapters:
        chapter = root / "chapters" / c
        sources = [(e, entry_cells(e.read_text())) for e in entries
                   if e.parent.name == c]
        for py in sorted(chapter.glob("*.py")):
            try:
                sources.append((py, py.read_text()))
            except OSError:
                continue
        for where, src in sources:
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue            # rule 29 is not the one that reports this
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    hit = node.module if node.module in EXECD else None
                elif isinstance(node, ast.Import):
                    hit = next((a.name for a in node.names if a.name in EXECD),
                               None)
                else:
                    continue
                if hit:
                    out.append((where, (
                        f"imports `{hit}` — it is not a module. _model.qmd "
                        f"execs _model.py and _analysis.py into the page "
                        f"namespace, so their names are ALREADY in scope; the "
                        f"import raises ModuleNotFoundError at render. Delete "
                        f"the line and call the name directly")))

        # Rule 30. Two loose marks rather than one exact path: every index in
        # the corpus builds the path with an f-string over a loop variable
        # (`f"chapters/{c}/{_f}"`, with the loop named `_f`, `name` or `code`
        # in different chapters), so the literal `chapters/NN-name/_model.py`
        # appears in none of them. Naming the file AND its own chapter
        # directory is what they all share -- checked against all 12 indexes
        # across the three notebooks, where only the failing one misses both.
        index = chapter / "index.qmd"
        if not any(e.parent.name == c for e in entries) or not index.exists():
            continue                # same exemption as rules 19 and 24
        text = index.read_text()
        if "_model.py" not in text or f"chapters/{c}" not in text:
            out.append((index, (
                "does not render its own _model.py — the scaffold's `## The "
                "model` block is gone. Rule 19 puts the vehicle in _model.py "
                "BECAUSE the index shows it; without the block the aircraft "
                "appears nowhere a reader looks. Restore the block (edit the "
                "index, never write_file over it)")))
    return out


# Quarto escapes decimals in the markdown it freezes -- 0.36 is stored as
# `0\.36`. Missing that is not a small thing: the first version of the check
# below matched NOTHING and read as "every citation in the notebook has already
# drifted", which was wrong and alarming in the wrong direction.
FROZEN_NUMBER = re.compile(r"\d+\.\d+")


def _rendered_numbers(root, chapter):
    """Every decimal number a chapter's frozen output actually shows."""
    out = set()
    d = root / "_freeze" / "chapters" / chapter
    for f in d.rglob("html.json") if d.exists() else []:
        try:
            md = json.loads(f.read_text()).get("result", {}).get("markdown", "")
        except (OSError, ValueError):
            continue
        out |= set(FROZEN_NUMBER.findall(md.replace("\\.", ".")))
    return out


def _transcribed(root, chapters, entries):
    """
    A number hand-typed into an entry that another chapter also publishes.

    A WARNING, because it still misses more than it catches. Measured on this
    corpus after the own-chapter filter below: one true positive
    (`old_sink = 0.36`, taken from 01-foam-glider and rendered as an authority
    in a comparison table, which every other rule passes), no false positives,
    and two misses in the same entry -- `old_mass` and `old_c_root`, both
    transcribed and then REFORMATTED, kg to g and to fewer decimals, which no
    string match can see. Precision is good; recall is the half that cannot be
    fixed without `cite()`.

    That precision is why it is a warning and why the remedy is a link rather
    than a correction: the system deliberately has no `cite()` yet, so a
    transcription is allowed. What is not allowed is one whose source cannot be
    found, because nothing here can tell you when it goes stale.
    """
    out = []
    published = {c: _rendered_numbers(root, c) for c in chapters}
    for e in entries:
        mine = e.parent.name
        try:
            tree = ast.parse(entry_cells(e.read_text()))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            v = node.value
            if not (isinstance(v, ast.Constant) and isinstance(v.value, float)):
                continue
            literal = repr(v.value)
            if not RESULT_NUMBER.fullmatch(literal):
                continue        # one decimal is a condition, not a result
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not names or set(names) & BUDGET_NAMES:
                continue        # rule 28 requires these to be literal
            # A value the chapter's OWN model or analysis already contains is
            # a design constant of this vehicle, not a citation -- 0.15 is the
            # half span, written into every `xyz_le`, and it was matching every
            # chapter that publishes a span. This drops both false positives on
            # record (`c_root_bound`, `b_half`) and keeps the true one
            # (`old_sink = 0.36`, which appears nowhere in its own chapter).
            own = ""
            for f in ("_model.py", "_analysis.py"):
                try:
                    own += (root / "chapters" / mine / f).read_text()
                except OSError:
                    pass
            if literal in own:
                continue
            source = [c for c in chapters
                      if c != mine and literal in published.get(c, ())]
            if source:
                out.append((e, (
                    f"(warning) `{names[0]} = {literal}` is hand-typed, and "
                    f"{', '.join(source[:2])} publishes the same value — if it "
                    f"came from there, name that entry in prose and link it "
                    f"(rule 10). Nothing can tell you when a transcribed number "
                    f"goes stale, so the link is the only trail back")))
    return out


# Two chapters this alike are a fork, not a coincidence: measured on this
# notebook, 03 and 04 are 97% identical and 02 and 03 are 94%, while unrelated
# chapters sit near 66%. The threshold only has to separate those.
FORK_SIMILARITY = 0.85

# The two input callouts, under both names they have gone by. The rename to
# "New ..." came with the rule that a page lists only what IT introduced --
# what it inherits is stated once, one level up.
INPUT_TITLES = ("Specified", "Assumed",
                "New user specifications", "New assumptions",
                "Initial user specifications", "Initial assumptions")
INPUT_CALLOUTS = "|".join(INPUT_TITLES)

# What `forking.md` asks a forked file's header to carry. Checked by substring
# because the header is prose -- the point is that a reader can answer "what
# was this taken from, and what was meant to change", not that it match a form.


def _code_only(src):
    """
    Source with comments and formatting normalised away.

    Similarity has to be measured on CODE. Measured on raw text, adding the
    nine-line fork header rule 31 demands dropped 03-unswept-c4's similarity to
    its parent from 94% to under the threshold -- so satisfying the rule made
    the rule stop seeing the fork, and would let any fork evade it by carrying
    a long enough comment. `ast.unparse` drops comments and normalises spacing,
    which is exactly the difference that should not count.
    """
    try:
        return ast.unparse(ast.parse(src))
    except (SyntaxError, ValueError):
        return src


def model_kinship(root, chapters):
    """
    Every pair of chapters whose `_model.py` is close enough to be a copy.

    Reported rather than judged: rule 31 asks a fork to declare itself, this
    says what the notebook actually looks like. The number that matters is not
    any one pair but the shape -- four chapters holding four copies of one
    vehicle means a fix to the shared physics is four edits, and nothing will
    tell you if you make three.
    """
    import difflib
    src = {}
    for c in chapters:
        try:
            src[c] = _code_only((root / "chapters" / c / "_model.py").read_text())
        except OSError:
            continue
    out = []
    names = sorted(src)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = difflib.SequenceMatcher(None, src[a], src[b]).ratio()
            if r >= FORK_SIMILARITY:
                out.append((a, b, r))
    return sorted(out, key=lambda t: -t[2])


def _empty_callouts(root, chapters, entries):
    """
    Rule 32. A callout whose whole content is "None." should not be there.

    Cheap to write and cheap to read past, which is why it accumulated: every
    entry carried a `## Specified` and an `## Assumed` heading, and on a page
    that specified nothing and assumed nothing both said "None." -- eight lines
    of furniture around two words, printed above the answer. A reader scanning
    for what was assumed had to read the box to learn there was nothing in it.

    Absence is already unambiguous: an entry with no Assumed callout assumed
    nothing, exactly as an entry with no figure has no figure.
    """
    # Entries AND chapter indexes. The scaffold ships both callouts in an
    # index, so a chapter that genuinely assumes nothing is the case most
    # likely to end up with a box saying so.
    pages = list(entries) + [root / "chapters" / c / "index.qmd"
                             for c in chapters
                             if (root / "chapters" / c / "index.qmd").exists()]
    out = []
    for e in pages:
        try:
            text = e.read_text()
        except OSError:
            continue
        for title, body in callouts_of(text):
            if title not in INPUT_TITLES:
                continue
            words = re.sub(r"[^a-z0-9]+", " ", body.lower()).split()
            if words in ([], ["none"]):
                out.append((e, f"has an empty `## {title}` callout — delete it. "
                                f"Nothing was {title.lower()}, and a box saying "
                                f"so costs a heading and four lines to carry "
                                f"one word"))
    return out


CITE_CALL = re.compile(
    r"""cite\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']([^)]*)\)""")
HERO_PAIR = re.compile(
    r"\[([^\]]+)\]\{\.hero-value\}[^\[]*\[([^\]]*)\]\{\.hero-label\}")


def _sidebar_lists_chapters(root, chapters):
    """
    Rule 38. Every chapter is named in the sidebar.

    The sidebar names each chapter rather than using `- auto: "chapters"`. That
    drops a redundant "Chapters" heading wrapping the whole notebook, and the
    price is a list somebody has to maintain -- `create_chapter` does, but a
    chapter created any other way, or a rename, leaves a chapter that renders
    perfectly and appears in no navigation. Nothing else would ever say so:
    the page is there, the links work, and only a reader looking for it notices.
    """
    cfg = root / "_quarto.yml"
    if not cfg.exists():
        return []
    text = cfg.read_text()
    if re.search(r'^\s*-\s*auto:\s*["\']?chapters["\']?\s*$', text, re.M):
        return []          # the wrapper form: nothing to maintain, nothing to check
    listed = set(re.findall(r'-\s*auto:\s*["\']chapters/([^"\']+)["\']', text))
    return [(cfg, f"chapter {c!r} is in no sidebar entry — it renders and links "
                  f"correctly and appears in no navigation, which only a reader "
                  f"looking for it would notice")
            for c in chapters if c not in listed]


def _citation_targets(root, chapters, entries):
    """
    Rule 37. A `cite()` names an entry that exists and publishes a hero value.

    `cite()` reads the cited page's freeze at RENDER time, so a wrong chapter or
    a mistyped stem is a ValueError several minutes into a run -- after the
    solves, which is the expensive place to learn it. Every part of it is
    checkable from source in milliseconds.

    A missing freeze is NOT a finding here: an entry written in the same run as
    the one it cites has not been rendered yet, and `check` discards freezes on
    purpose. What must hold is that the target EXISTS and, if it has been
    rendered, that it published something to quote.
    """
    out = []
    for f in entries:
        for chapter, stem, rest in CITE_CALL.findall(f.read_text()):
            target = root / "chapters" / chapter / f"{stem}.qmd"
            if not target.exists():
                out.append((f, f"cites {chapter}/{stem}, which does not exist — "
                               f"a citation resolves at render, so a typo here "
                               f"costs a whole run"))
                continue
            if target.resolve() == f.resolve():
                out.append((f, "cites itself — quote the value directly"))
                continue
            frozen = (root / "_freeze" / "chapters" / chapter / stem
                      / "execute-results" / "html.json")
            if not frozen.exists():
                continue
            heroes = HERO_PAIR.findall(frozen.read_text())
            if not heroes:
                out.append((f, f"cites {chapter}/{stem}, which publishes no hero "
                               f"value — there is no single answer there to "
                               f"quote"))
            elif len(heroes) > 1 and "label" not in rest:
                out.append((f, f"cites {chapter}/{stem}, which publishes "
                               f"{len(heroes)} values — pass label= to say which. "
                               f"Caught here because at render it is a "
                               f"ValueError after the solves, and the first "
                               f"version of cite() quietly returned the first"))
    return out


def _chapter_index_blocks(root, chapters):
    """
    Rule 35. A chapter index keeps the two blocks that orient a reader.

    Both are scaffolded, both are DERIVED, and both are lost the same way rule
    30's block was lost -- a model rewriting index.qmd with `write_file` rather
    than editing it. What is left then still renders and still reads fine, which
    is exactly why nothing notices.

      * the entry listing: without it you land on a chapter index with nothing
        to click, and navigation falls back to the sidebar;
      * the lineage cell: the parent is recorded only in `_model.py`'s fork
        header, inside a collapsed source callout no reader opens.

    Silent on a chapter with no entries: a listing of nothing is furniture, the
    same judgement rule 32 makes about an empty callout.
    """
    out = []
    for c in chapters:
        index = root / "chapters" / c / "index.qmd"
        if not index.exists():
            continue
        if not list((root / "chapters" / c).glob("20*.qmd")):
            continue
        text = index.read_text()
        if "id: entries" not in text or "{#entries}" not in text:
            out.append((index, "has no entry listing — a reader landing here "
                               "has nothing to click. The scaffold ships the "
                               "`listing:` block and a `::: {#entries}` div"))
        # THE CALL, not a comment. This pinned the banner's exact wording twice
        # and failed all six chapters both times -- once when the cell learned
        # to read every chapter's `_fork.yml` rather than its own, once when it
        # moved into `_notebook.py`. A comment is prose and will be reworded;
        # `chapter_lineage(` is the thing that has to be on the page.
        if "chapter_lineage(" not in text:
            out.append((index, "does not print its lineage — the parent chapter "
                               "is recorded only in `_fork.yml`, which no reader "
                               "opens. The scaffold ships the one-line cell: "
                               "`chapter_lineage(\"<chapter>\")`"))
    return out


def _book_index(root, chapters):
    """
    Rule 34. The notebook has a front page, and it still draws itself.

    Quarto synthesises an `_site/index.html` when a website has no root page, so
    the absence is not a 404 -- it is a site whose front door says nothing about
    what the aircraft is or how the chapters relate. Three notebooks were built
    without one and nobody noticed, because nothing was broken.

    The generated-block check is the same guard rule 30 makes for a chapter
    index, for the same reason and against the same failure: the scaffold ships
    a cell that draws the chapter graph FROM the chapters, and a model that
    rewrites the page with `write_file` rather than editing it replaces a
    derived diagram with a hand-drawn one that is correct exactly once.

    Only when the notebook has chapters -- a graph of nothing is not a finding.
    """
    if not chapters:
        return []
    index = root / "index.qmd"
    if not index.exists():
        return [(index, "the notebook has no front page — every chapter is "
                        "reachable only from the sidebar, and nothing says how "
                        "they relate. `nb new` scaffolds one")]
    if "GENERATED FROM THE CHAPTERS" not in index.read_text():
        return [(index, "the chapter graph is not the generated one — the nodes "
                        "and the arrow labels both come from each "
                        "`_fork.yml`, so it cannot disagree with the chapters. "
                        "A hand-drawn diagram is correct once")]
    return []


def _index_ordering(root, chapters):
    """
    Rule 33. A chapter index declares `order:` matching its directory number.

    The sidebar is built by `- auto: "chapters"`. With no `order:` in a
    chapter's index, Quarto does not sort the sections at all -- it emits them
    in readdir order, which on APFS is a hash of the directory names. Measured
    on this notebook: the directories are 01..06 and the sidebar read
    03, 01, 06, 04, 02, 05, matching `ls -f` exactly.

    Two things follow, and the second is worse than the mess:

      * the `NN-` prefixes that encode the whole design lineage are invisible;
      * `page-navigation: true` walks the chapters in that same hash order, so
        "read straight through" takes you 03 -> 01 -> 06.

    And it is UNSTABLE: the hash changes as names are added, so a seventh
    chapter can reshuffle the six above it.

    The title was numbered too, and is not any more. That half was insurance
    against a mis-sorted sidebar -- "a Quarto change or a stray file" -- and the
    sidebar has since been sorted by `order:` and labelled by breadcrumbs on
    every entry page. The number was being paid for in the narrowest column on
    the page, which is also the one the titles have to fit.

    `create_chapter` writes both, so this rule exists for the case rule 30 was
    written for -- a model that rewrites index.qmd with `write_file` instead of
    editing it drops whatever the scaffold put there, and nothing notices.
    """
    out = []
    for c in chapters:
        index = root / "chapters" / c / "index.qmd"
        if not index.exists() or not c[:2].isdigit():
            continue
        text = index.read_text()
        n = int(c[:2])
        m = re.search(r"^order:\s*(\d+)\s*$", text, re.M)
        if not m:
            out.append((index, f"declares no `order:` — without it Quarto does "
                               f"not sort the sidebar at all, it uses readdir "
                               f"order. Add `order: {n}` under the title"))
        elif int(m.group(1)) != n:
            out.append((index, f"declares `order: {m.group(1)}` but is chapter "
                               f"{n} — the sidebar would disagree with the "
                               f"directory names"))
    return out


# An index carries its input callouts and nothing else with a heading. It used
# to carry "Questions asked here" and "The model" too, above a listing and a
# code dump that are perfectly legible without being announced -- a heading
# whose section is one div is a label for something the reader can already see.
INDEX_SECTIONS = INPUT_TITLES


def _root_index_freeze(root, chapters, entries):
    """
    Rule 40. The front page draws a tick per entry, so its freeze goes stale
    whenever one is added -- and rule 12 cannot say so.

    Rule 12 fires on a dirty `_model.py` against THAT chapter's freeze. The
    root `index.qmd` belongs to no chapter, so nothing watches it. That was
    survivable while the page only read `_fork.yml`, which changes when a
    chapter is created, because `create_chapter` deletes the freeze itself.
    Counting ENTRIES made every run a run that changes what the page shows.

    `write.py` re-renders it before each commit. This is the check that the
    re-render happened -- the same relationship rule 12 has with `check.py`:
    one does the work, the other refuses to believe it was done.

    No freeze means no finding, exactly as rule 12: a notebook that has never
    been rendered is not thereby wrong.
    """
    index = root / "index.qmd"
    frozen = root / "_freeze" / "index" / "execute-results" / "html.json"
    if not index.exists() or not frozen.exists() or not entries:
        return []
    # The brief too: the front page RENDERS `_inputs.yml` now, so editing it
    # moves the page exactly as adding an entry does.
    watched = list(entries)
    brief = root / "_inputs.yml"
    if brief.exists():
        watched.append(brief)
    newest = max(e.stat().st_mtime for e in watched)
    if newest > frozen.stat().st_mtime:
        return [(index, "the front page counts every chapter's entries, and an "
                        "entry is newer than the freeze it was drawn from — so "
                        "the lineage diagram is showing a tick count that is "
                        "out of date. Re-render it: `quarto render index.qmd`")]
    return []


def _index_shape(root, chapters, entries):
    """
    Rule 39. An index RENDERS its input callouts and does not also write them.

    The callouts are data now (`_inputs.yml`) and the page carries
    `chapter_inputs("<chapter>")`, which prints New user specifications, New
    assumptions and Superseded from it. Two things can go wrong, and both are
    the failure rule 30 names -- a model rewriting the page with `write_file`
    and putting back what looks like it belongs:

      * the call goes missing, and the chapter silently declares nothing;
      * the callouts come back as hand-written markdown beside the generated
        ones, and every item is on the page twice. That is not hypothetical:
        it is what the first version of the supersession marker did, measured
        at all 7 items across the two affected chapters.

    A chapter with no `_inputs.yml` is held to the OLD rule instead -- order,
    no stray `##`, no lead-in prose. Both frozen corpus notebooks are in that
    state and are not worth migrating, which is the same judgement rules 33-35
    already make about them.
    """
    out = []
    for c in chapters:
        if not any(e.parent.name == c for e in entries):
            continue
        index = root / "chapters" / c / "index.qmd"
        try:
            text = index.read_text()
        except OSError:
            continue

        if read_inputs(root, c):
            if "chapter_inputs(" not in text:
                out.append((index, (
                    "has an `_inputs.yml` but never renders it — the chapter's "
                    "specifications and assumptions appear nowhere on its page. "
                    "The scaffold ships the one-line cell: "
                    "`chapter_inputs(\"" + c + "\")`")))
            for title, _ in callouts_of(text):
                if title in INPUT_TITLES:
                    out.append((index, (
                        f"writes a `## {title}` callout by hand AND renders "
                        f"`_inputs.yml`, so every item is on the page twice. "
                        f"The list lives in `_inputs.yml`; delete the markup")))
                    break
            continue

        heads = re.findall(r"^##\s+(.+?)\s*$", text, re.M)
        seen = [h for h in heads if h in INDEX_SECTIONS]
        want = [s for s in INDEX_SECTIONS if s in seen]
        if seen != want:
            out.append((index, (
                f"sections run {' → '.join(seen)}; the order is "
                f"{' → '.join(want)} — what was given before what was guessed")))
        for h in heads:
            if h not in INDEX_SECTIONS:
                out.append((index, (
                    f"has a `## {h}` heading. An index carries its input "
                    f"callouts and nothing else: a listing and a code block "
                    f"are legible without being announced, and a heading over "
                    f"one div is a label for what the reader can already see")))
        for body in re.findall(
                r"^:{3,}\s*\{\.callout-\w+\}\s*\n\s*##\s*(?:" + INPUT_CALLOUTS
                + r")[^\n]*\n(.*?)^:{3,}\s*$", text, re.S | re.M):
            lead = [l for l in body.strip().splitlines()
                    if l.strip() and not re.match(r"^\s*\d+\.", l)]
            if lead and not lead[0].startswith(" "):
                out.append((index, (
                    f"says {lead[0].strip()[:40]!r} above its numbered items. "
                    f"The callout IS the list; anything before it is a "
                    f"sentence introducing three lines")))
    return out


def _input_item_budget(root, chapters, entries):
    """
    Rule 8, for a chapter that keeps its items in `_inputs.yml`.

    The budget used to be counted in `check()`, over callouts found in the page
    source. Generated callouts are not in the source, so an index's items
    stopped being counted at all the moment they moved -- a rule going quiet
    because its input moved is the failure `nb.corpus` exists to catch.
    """
    out = []
    pairs = [(root / "_inputs.yml", notebook_items(root))]
    pairs += [(root / "chapters" / c / "_inputs.yml", declared_items(root, c))
              for c in chapters
              if any(e.parent.name == c for e in entries) and read_inputs(root, c)]
    for where, items in pairs:
        for kind, text in items:
            n = words(text)
            if n > MAX_CALLOUT_ITEM:
                out.append((where, (
                    f"{kind} item is {n} words, over {MAX_CALLOUT_ITEM} — "
                    f"record the input, not the argument for it: "
                    f"{' '.join(text.split())[:56]}…")))
    return out


def read_fork(root, chapter):
    """
    `chapters/<c>/_fork.yml` as a dict, or None. Flat by design.

    Deliberately not a YAML parse, for the reason `_categories.yml` is not one:
    lint imports nothing outside the stdlib, so the vendored checker runs
    standalone. The shape is therefore held flat enough for one regex --
    `key: value` lines and a `changes:` list of `- item` -- which is also the
    shape a human edits, and a human edits this every time a fork is refined.

    A file BESIDE the model rather than a comment inside it. Two reasons, and
    neither is the one-off retrofit. `index.qmd` was the other candidate and
    loses to rule 30: agents rewrite that page with `write_file` and drop what
    was scaffolded into it, which is why three rules already exist. And a
    header inside `_model.py` would make every future correction dirty the
    model under rule 12 and re-prove the whole chapter -- the record most
    likely to need editing would be the most expensive to edit, which is how a
    record stops being edited and starts being wrong.
    """
    f = root / "chapters" / chapter / "_fork.yml"
    try:
        text = f.read_text()
    except OSError:
        return None
    # ANY key whose value is empty opens a list -- `changes:` and `supersedes:`
    # today. It used to be `changes` by name, which meant adding a second list
    # was a parser change rather than a file change.
    out, lists, current = {}, {}, None
    for line in text.splitlines():
        if re.match(r"^\s*#", line) or not line.strip():
            continue
        item = re.match(r"^\s*-\s*(.+?)\s*$", line)
        if item and current:
            lists[current].append(item.group(1).strip().strip('"').strip("'"))
            continue
        kv = re.match(r"^(\w+):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip().strip('"').strip("'")
            if val:
                out[key] = val
                current = None
            else:
                current = key
                lists.setdefault(key, [])
            continue
        # A CONTINUATION: indented, no dash, no key. One change is often a
        # sentence and a file nobody can wrap is a file nobody edits, so a
        # wrapped item joins the one above it rather than being dropped --
        # which is what the first draft of this parser did, silently, to the
        # second half of every wrapped line.
        if current and lists.get(current) and line.startswith(" "):
            lists[current][-1] += " " + line.strip()
    # EVERY list, not a hand-listed two. `changes:` and `supersedes:` were
    # named explicitly here, so adding `replaces:`/`drops:` returned a parser
    # that read them and then threw them away -- silently, because an empty
    # list and an unread one look identical to every caller.
    out.update(lists)
    out.setdefault("changes", [])
    return out


# An `overwrites:` entry: `<chapter>/<their id>`, with an OPTIONAL reason. It
# was a `replaces:`/`drops:` pair whose value named the replacing id, and that
# was a fiction -- one overwritten assumption is often replaced by several new
# items, so the 1:1 link had to pick one arbitrarily. What replaced it is the
# chapter's own `_inputs.yml`, entire.
DEPARTURE = re.compile(
    r"^\s*([0-9]{2}-[a-z0-9-]+)/([a-z0-9][a-z0-9-]*)\s*(?::\s*(.*?))?\s*$")


def read_inputs(root, chapter):
    """
    `chapters/<c>/_inputs.yml` as {"specified": [(id, text)], "assumed": [...]}.

    The chapter's standing commitments, as DATA. They used to be a numbered
    markdown list inside a callout in `index.qmd`, which made them readable
    only by regex and, worse, UNMARKABLE: when a later chapter replaced one,
    nothing could say so on the page that declared it, because a Quarto cell
    cannot annotate markup already written. The generated line that worked
    around it put every item on the page twice -- measured on this notebook,
    both affected chapters had all of their items doubled.

    Same shape as `_fork.yml`'s `supersedes:` on purpose -- `key:` then
    `- <id>: <text>` -- so there is one format to learn and one parser to be
    wrong in. `_notebook.py` carries its own copy for the page to render from,
    for the reason rule 11 exists: a notebook must render without `nb`.
    """
    return parse_inputs(root / "chapters" / chapter / "_inputs.yml")


def parse_inputs(path):
    """
    A flat `key:` / `- id: text` file, plus `key: value` scalars.

    Scalars carry `defines:` -- the aero method, the section, what is left out.
    That used to be prose in `index.qmd` and was removed from the page for good
    reason (measured across six chapters it restated the fork in half of them
    and the front page in the other half), which left it with nowhere to live:
    `defines` is a required argument of `open_chapter` for a new one, and was
    being written into a placeholder that no longer existed. It is not rendered.
    Its readers are the PREFIX, which needs it to route a question to the right
    chapter, and `claimable_stub`, which needs its placeholder to tell a
    scaffolded chapter from a claimed one.
    """
    out, current = {}, None
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        row = INPUT_ROW.match(line)
        if row and current is not None:
            out[current].append((row.group(1),
                                 row.group(2).strip().strip('"').strip("'")))
            continue
        kv = re.match(r"^(\w+):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val:
                out[key] = val.strip('"').strip("'")
                current = None
            else:
                current = key
                out.setdefault(current, [])
            continue
        current = None
    return out


# `- <id>: <text>`. The id is a slug so a colon inside the TEXT -- "**Tail: H
# 100x30 mm**" -- cannot be mistaken for the separator.
INPUT_ROW = re.compile(r"^\s*-\s*([a-z0-9][a-z0-9-]*)\s*:\s*(.+?)\s*$")


def declared_items(root, chapter):
    """
    [(kind, text)] a chapter declares. `_inputs.yml` if it has one.

    DUAL SOURCE, deliberately. `aircraft-notebook` and
    `optimised-glider-notebook` are frozen corpus with hand-written callouts,
    and unfreezing the front door of a notebook nobody opens is not worth a
    migration. A chapter with `_inputs.yml` is read from it; one without is
    read the old way and nothing complains.
    """
    data = read_inputs(root, chapter)
    if data:
        return [("Specified" if k == "specified" else "Assumed", t)
                for k in ("specified", "assumed")
                for _, t in (data.get(k) or [])]
    try:
        text = (root / "chapters" / chapter / "index.qmd").read_text()
    except OSError:
        return []
    out = []
    for title, body in callouts_of(text):
        if title not in INPUT_TITLES:
            continue
        kind = "Assumed" if "assum" in title.lower() else "Specified"
        for item in re.findall(r"^\s*\d+\.\s+(.*(?:\n(?!\s*\d+\.).*)*)",
                               body, re.M):
            out.append((kind, " ".join(item.split())))
    return out


def input_ids(root, chapter):
    """{id: text} for a chapter with `_inputs.yml`, else {}."""
    data = read_inputs(root, chapter)
    return {i: t for k in ("specified", "assumed") for i, t in data.get(k, [])}


def notebook_items(root):
    """[(kind, text)] from the notebook's brief -- `_inputs.yml` at its root."""
    data = parse_inputs(root / "_inputs.yml")
    return [("Specified" if k == "specified" else "Assumed", t)
            for k in ("specified", "assumed") for _, t in (data.get(k) or [])]


def defines(root, chapter):
    """The one line saying what this chapter is, for routing. Not rendered."""
    return read_inputs(root, chapter).get("defines", "")


def departures(root, chapters):
    """
    {(chapter, item id): the chapter that departed from it}.

    Read from `replaces:` and `drops:` in each chapter's `_fork.yml` -- which
    record what THAT chapter changed, on the page that changed it. It used to
    be a `supersedes:` block meaning the same thing read the other way round,
    and reading it forward put a `Superseded` stamp on the page that DECLARED
    the item. That says the chapter is stale, when `forking.md`'s whole
    criterion for keeping it is that "the old answer stays valid under its own
    stated assumptions" -- and on this notebook it emptied two chapters of
    their callouts, because every one of their items had been departed from.

    Nothing renders from this. Its one reader is the inheritance review, which
    needs to know that an item an ancestor declared was replaced further down
    the chain before it offers it to a new fork.
    """
    out = {}
    for c in chapters:
        fork = read_fork(root, c) or {}
        for raw in (fork.get("overwrites") or []):
            m = DEPARTURE.match(raw)
            if m:
                out[(m.group(1), m.group(2))] = c
    return out


def _plausible_parent(root, chapter, parent):
    """
    A declared parent must exist and be EARLIER. It need not be the most
    similar chapter, and that is the loosening this function exists for.

    `_fork.yml` records where a design came from; code similarity is only how
    an UNDECLARED one is detected. The two coincide when a model was copied and
    diverge when it was rewritten -- 05-fully-optimized is 84% similar to its
    parent, below the fork threshold, so nothing demanded a declaration, and
    without one the lineage diagram showed two unconnected trees and the
    notebook read as two projects.

    So similarity still DEMANDS a declaration from a copy. It no longer
    contradicts one that is offered.
    """
    if not (root / "chapters" / parent).is_dir():
        return False
    return parent < chapter


def _fork_provenance(root, chapters, entries):
    """
    Rule 31. A copied `_model.py` declares its parent, in `_fork.yml`.

    `forking.md` has specified this since before the rule existed -- "the header
    of the copy names its parent chapter, the commit it was taken at, and every
    deliberate difference... `diff` between the two files is then the review, and
    an empty `diff` on the file that was NOT meant to change is a positive check
    rather than an absence of information."

    That was a comment, and exactly one field of it was machine-readable. The
    parent was parsed by a regex written out twice -- the book index and the
    chapter index, independently, both truncating at 2000 bytes -- and the
    DIFFERENCES, which are the thing a fork actually is, were prose nothing
    checked. So the lineage arrows could not be labelled, and a later edit to a
    forked model left the header describing a fork that no longer existed.

    One check, with four parts:

      31   a fork has a `_fork.yml` naming its parent, the commit, the
           parent's entry count at the fork, a summary and what it changed
    A THIRD was designed and did not survive calibration: comparing the
    declared list against a real `git diff` of the two models. Measured both
    ways on the four forks here. Against `_code_only` the model collapses to
    ten logical lines, so every geometry change lands in one hunk and two
    separate undeclared edits did not move the count. Against raw lines,
    reflow dominates -- a correct fork declaring 2 changes shows 9 hunks --
    and the same two edits again moved nothing. A threshold loose enough to
    clear 9-vs-2 catches nothing worth catching. The failure it was for, a
    forked model edited without updating its record, stays uncaught; that is
    worth knowing rather than papering over with a rule that fires at random.

    Blocking, because it is cheap at the moment of forking and expensive to
    reconstruct later -- the commit it was taken at is the part that rots first.
    """
    out = []
    import difflib
    models, code = {}, {}
    for c in chapters:
        f = root / "chapters" / c / "_model.py"
        try:
            models[c] = f.read_text()
        except OSError:
            continue
        code[c] = _code_only(models[c])
    for c, text in models.items():
        if not any(e.parent.name == c for e in entries):
            continue            # same exemption as rules 19, 24 and 30
        # Only EARLIER chapters are candidate parents. Chapters are numbered in
        # creation order, so similarity is symmetric but forking is not: without
        # this the rule told 02-fuselage-model it was a fork of 03-unswept-c4,
        # which was copied FROM it. A parent owes no provenance.
        kin = [(o, difflib.SequenceMatcher(None, other, code[c]).ratio())
               for o, other in code.items() if o < c]
        close = sorted((r, o) for o, r in kin if r >= FORK_SIMILARITY)
        if not close:
            continue
        ratio, parent = close[-1]
        fork = read_fork(root, c)
        where = root / "chapters" / c / "_fork.yml"
        if not fork or not fork.get("parent"):
            out.append((where, (
                f"chapters/{c}/_model.py is {ratio:.0%} identical to "
                f"chapters/{parent}/_model.py and no _fork.yml says so. Write "
                f"one beside it: `parent: {parent}`, `at: <commit>`, and a "
                f"`changes:` list with one line per deliberate difference, so "
                f"that `diff` between the two files is the review")))
            continue
        if not _plausible_parent(root, c, fork["parent"]):
            out.append((where, (
                f"names parent {fork['parent']!r}, which is not an earlier "
                f"chapter of this notebook. A parent is where the design came "
                f"from, and a design cannot come from a chapter that does not "
                f"exist or was written afterwards")))
            continue
        if not fork.get("at"):
            out.append((where, (
                "names a parent but no commit. `at:` is what makes `git show "
                "<at>:chapters/<parent>/_model.py` the baseline the changes "
                "are read against, and it is the part that rots first")))
        if not fork.get("at_entry"):
            out.append((where, (
                "names a parent but no `at_entry:` — how many entries the "
                "parent had written when this was taken. It cannot be "
                "reconstructed later: filename dates are day-granular and a "
                "chapter can gain several in a day. `create_chapter` counts it "
                "at the moment of the fork, which is the only moment it is "
                "known exactly")))
        # A PLACEHOLDER IS NOT AN ANSWER. `create_chapter` writes
        # `summary: "TODO: ..."` and one `TODO:` change, as the scaffold for
        # the model to replace -- and the keys being present satisfied every
        # test here, so a forked chapter could commit with its TODO intact and
        # the lineage diagram on the front page would render, as the box label
        # for that chapter, the words "TODO: what the design BECAME". Rule 24
        # is the same check for `index.qmd`'s placeholders; this is the one
        # scaffolded file that had none.
        summary = fork.get("summary") or ""
        if not summary or summary.upper().startswith("TODO"):
            out.append((where, (
                "names a parent but no `summary:` — a few words for the arrow "
                "on the lineage diagram, which carries the text because the "
                "nodes do not, and which renders this string verbatim on the "
                "front page. Write what the design BECAME, not `from → to`: "
                "the arrow already carries the from by pointing out of it")))
        changes = [x for x in (fork.get("changes") or [])
                   if not x.upper().startswith("TODO")]
        if not changes:
            out.append((where, (
                f"lists no changes, but chapters/{c}/_model.py is "
                f"{100 - ratio * 100:.0f}% different from its parent. One line "
                f"per deliberate difference — the differences ARE the chapter")))
    # Departures are checked on EVERY chapter, not only ones the similarity
    # test flagged: a fork that rewrote its model rather than copying it -- 05,
    # at 35% -- can still depart from an ancestor's declaration.
    out += _departure_targets(root, chapters)
    return out


def _departure_targets(root, chapters):
    """
    Rule 31, second half. Every `overwrites:` entry names something real.

    The id either exists or it does not, which is the point of having ids. A
    typo, a renamed chapter, or an item deleted out from under the link all
    produce a departure that silently stops resolving -- and the symptom is
    invisible, because the row simply does not appear in the callout it was
    meant to appear in.
    """
    out = []
    known = set(chapters)
    for c in chapters:
        fork = read_fork(root, c) or {}
        where = root / "chapters" / c / "_fork.yml"
        for raw in (fork.get("overwrites") or []):
            m = DEPARTURE.match(raw)
            if not m:
                # NAMING THE NOTEBOOK gets its own message, because the fix is
                # not to correct the row. A first chapter has no parent, so the
                # inheritance review used to offer the notebook's BRIEF for
                # striking, and a strike wrote `<notebook>/<id>` here --
                # resolving to no chapter and no id, silently. The gate no
                # longer takes those strikes; this is the backstop, and it says
                # why rather than asking for a better id.
                if str(raw).partition("/")[0].strip() == root.name:
                    out.append((where, (
                        f"overwrites: {raw!r} names the NOTEBOOK. The brief in "
                        f"{root.name}/_inputs.yml is true of the whole "
                        f"aircraft and is never overwritten -- a design that "
                        f"departs from it is a different aircraft, and so a "
                        f"different notebook, not a fork. Drop the row; if the "
                        f"departure is real, this chapter belongs elsewhere")))
                    continue
                out.append((where, (
                    f"overwrites: {raw!r} is not `<chapter>/<id>`, with an "
                    f"optional reason after a colon")))
                continue
            parent, item_id, _ = m.groups()
            if parent not in known:
                out.append((where, (
                    f"overwrites {parent!r}, which is not a chapter of this "
                    f"notebook")))
                continue
            if parent >= c:
                out.append((where, (
                    f"overwrites {parent!r}, which is not EARLIER than {c}. A "
                    f"chapter can only overwrite a declaration that already "
                    f"existed when it was written")))
                continue
            theirs = input_ids(root, parent)
            if item_id not in theirs:
                out.append((where, (
                    f"overwrites {parent}/{item_id!r}, which is not an id in "
                    f"chapters/{parent}/_inputs.yml"
                    + (" — its ids are: " + ", ".join(sorted(theirs))
                       if theirs else " — it has no _inputs.yml"))))
    return out


# =============================================================================
# WHICH RULES EXIST. The single source of truth for the rule NUMBERS, and the
# only thing that stops the model's copy of the list drifting from the checks.
#
# It is not a dispatch table and does not pretend to be: one function covers
# several rules (`_budget_rules` is 16, 17, 18 and 28) and rules 1-10 are inline
# in `check()` below, so a number-to-function map would be a fiction. What
# drifted was never the wiring -- it was the LIST. `system_instruction.md` said
# "The 32 rules lint checks" while this file enforced 40, so rules 33, 35, 37
# and 39 were blocking, were tripped by edits the write brief explicitly asks
# for, and had never been shown to the model. README said 38; the `lint` tool
# declaration said 26. Four copies, three wrong.
#
# `preflight` now refuses to start when the instruction's numbers are not
# exactly these, so adding a rule is two edits that cannot be done singly.
#
# 36 IS ABSENT ON PURPOSE. It checked `_categories.yml`, and the categories
# system was retired; the number is not reused, because rule numbers appear in
# commit messages, in `corpus.py`'s recorded counts and in the references.
# THE FAILURE BEHIND EACH RULE. One home, beside the numbers.
#
# It used to be `references/why.md`, a model-facing document reachable through
# `read_reference`. Two things were wrong with that. It was never once read --
# zero calls across every retained transcript, because a model that trips a rule
# reads the message and fixes it rather than going to argue with the rule. And
# it had drifted to covering 20 of 39, with the missing 19 being exactly the
# ones added after it was written, while its own tool description promised "the
# failure behind each lint rule".
#
# So it is here, where the numbers are, and it is for a PERSON -- deciding
# whether a rule still earns its place, or why one fires on something that looks
# fine. The model's channel is the violation message, which names its own fix.
#
# A RULE MISSING HERE IS NOT NECESSARILY UNEXPLAINED: seventeen of them carry
# their reason in the docstring of the check that enforces it, which opens
# `Rule N.` -- that is the better home when the reason is about the MECHANICS of
# detecting it rather than about the failure. `unexplained()` below reports the
# ones in neither place, so the gap is a number rather than an impression. It is
# six: 20, 21, 22, 28, 29, 30.
WHY = {
    1: "Three corrections were needed in one session where an entry's prose "
       "disagreed with its own rendered output. An inline expression makes the "
       "number BE the computation rather than a copy of it. Two decimals reads "
       "as a result; one decimal is usually a condition (6 m/s, 0.5 deg) and "
       "flagging those is noise.",
    2: "Four subtly different neutral points were written in one chapter, one "
       "of which took its moment reference from the wrong station and put "
       "wrong numbers in front of the reader.",
    3: "An entry is read to find out what was learned; the working is there to "
       "be checked afterwards.",
    4: "'Where does the ballast go?' was answered with three static margins "
       "because nobody asked which was wanted -- turning a missing input into "
       "extra analysis, which is worse than either asking or assuming. The "
       "failure looks like diligence, which is why the rule needs its reason.",
    5: "`trim()` was written `for _ in range(60)` around a fixed point that "
       "settles in 9 to 13, so every call spent ~20 s re-deriving an answer it "
       "already had, at a dozen call sites. A round number also hides "
       "non-convergence: a loop that never converged returns exactly like one "
       "that did.",
    6: "Entries drift long one clause at a time, and the fix is always the "
       "same -- the sentence explaining WHY a number is what it is belongs in "
       "the figure caption or a code comment. A `callout-warning` counts "
       "against the budget: moving a paragraph into a coloured box does not "
       "make it shorter.",
    7: "Same failure as rule 6, in the one place prose is allowed to explain "
       "itself.",
    8: "One entry recorded a static margin with three lines of justification, "
       "which reads as hedging a decision that was actually made.",
    9: "A second headed block reads as its own little essay with its own "
       "budget, which is how an entry inside 100 words in each part ends up "
       "long overall.",
    10: "'The previous entry' in bare prose is the same defect as a hand-typed "
        "number: it points at something that can be retitled, reordered or "
        "deleted, and nothing notices. Later entries revising earlier ones IS "
        "the notebook's structure, so those references are structure, not "
        "decoration.",
    11: "See `_notebook_drift`. Vendoring costs propagation; this rule buys it "
        "back.",
    12: "Freeze tracks the page, not its includes, so editing `_model.py` "
        "leaves every entry serving values the current model does not produce, "
        "silently. A fuselage ply count changed, nothing re-executed, and an "
        "entry went on rendering a duration the model no longer gave -- it "
        "surfaced only because that entry happened to carry an `assert`.",
    13: "Moving code into `_analysis.py` must not move the method out of "
        "sight; the notebook exists to be reviewed. Only what the entry NAMES, "
        "never the transitive closure -- that would reproduce the whole file in "
        "every entry, and make splitting a function break entries whose "
        "conclusions never changed.",
    14: "Three entries printed a grid directly beneath a plot showing the same "
        "quantities; one was 72 numbers under a figure plotting four of its "
        "eight columns. See `_visuals_and_tables` for the two-visual "
        "loosening.",
    15: "Past 6x4 a table stops being something a reader takes in and becomes "
        "a grid to be searched. Raised from 3x4: six optimisation variables "
        "against their bounds had no legal form, and the entry wrote fifteen "
        "numbers into one sentence instead -- the same grid, minus the "
        "alignment. Rule 25 closes that escape.",
    16: "A local `max_runtime=` at one of five call sites re-opens the hole "
        "silently and nothing downstream shows it. OPT-OUT, and the first "
        "version had this backwards -- it applied only to chapters that bound "
        "SOLVE_BUDGET, so a new chapter that never bound it ran unprotected, "
        "and forgetting is the failure the mechanism exists to catch. A guard "
        "you skip by inaction is not a guard.",
    17: "One entry reached 599 s and nothing anywhere said so; the cost of a "
        "notebook was invisible until `footer()` started recording it. Blocks "
        "past a ceiling the USER set and only warns below it, because wall "
        "clock is not reproducible -- the same solve measured 533.9 s against a "
        "145 s baseline purely from machine load.",
    18: "A chapter was forked from another and silently inherited "
        "`SOLVE_BUDGET = None`, carried in a file nobody re-reads, with a "
        "comment -- 'its pages are already frozen' -- that was untrue of a "
        "chapter with no pages at all. A budget is a decision about what the "
        "work may cost, so it belongs where every other brief is.",
    25: "The other half of 15. Prose had no row limit, so when a table was "
        "illegal the values went into a run-on sentence and read worse than "
        "the table would have. Across 32 entries the most any sentence carried "
        "was five, falling away hard above three; the sentence that earned "
        "this rule carried fifteen.",
    26: "The schema demanded the ask VERBATIM, which is right for a question "
        "and wrong for a brief: a 70-character filename, a sidebar entry and a "
        "title that restated what index.qmd already said. Measured across 35 "
        "entries: 34 are one sentence ending in '?', median eight words, "
        "longest legitimate eighteen.",
}

def unexplained():
    """
    Rule numbers with no recorded reason, in `WHY` or in a check's docstring.

    A rule nobody wrote a reason for is a rule nobody can argue with, which is
    how a contract accumulates lines that fire on things that look fine. This
    counts them instead of leaving it to impression -- it was an impression for
    a long time, and the impression was that `references/why.md` covered them
    all. It covered 20 of 39.
    """
    import ast
    import re
    try:
        src = pathlib.Path(__file__).read_text()
    except OSError:
        return []
    documented = set(WHY)
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.FunctionDef):
            m = re.match(r"\s*Rules? ([0-9, and]+)[.:]", ast.get_docstring(n) or "")
            if m:
                documented |= {int(x) for x in re.findall(r"\d+", m.group(1))}
    return sorted(set(RULES) - documented)


RULES = {
    1: "no hand-typed number in prose",
    2: "no 3 consecutive code lines repeated across entries",
    3: "`**Answer.**` comes before the last code cell",
    4: "no sweeping a decision that should have been asked",
    5: "no `for … in range(…)` around an aero solve",
    6: "prose within the word budget",
    7: "figure caption within the word budget",
    8: "each Specified / Assumed item within the word budget",
    9: "one prose section",
    10: "a sibling entry is linked, never named in bare prose",
    11: "`_notebook.py` and `_probe_base.py` byte-match the canonical copies",
    12: "the freeze is not older than the model that froze it",
    13: "every `_analysis.py` function the entry calls is passed to `footer(…)`",
    14: "one visual per entry (two, if one draws the aircraft)",
    15: "a table is at most 6x4",
    16: "a budgeted chapter does not override SOLVE_BUDGET at a call site",
    17: "a frozen entry stays under the ENTRY_CEILING it declares",
    18: "budgets are declared in the entry's first cell",
    19: "a chapter with an entry defines its vehicle in `_model.py`",
    20: "(warning) an entry-local function reaching the vehicle belongs in _analysis.py",
    21: "(warning) an `_analysis.py` function nothing calls is dead",
    22: "(warning) an `_analysis.py` function called only internally is private",
    23: "every `solve()` passes `verbose` explicitly",
    24: "no unfilled scaffold placeholder, in a chapter index or the brief",
    25: "no sentence enumerates more than five computed values",
    26: "the title is ONE question, at most 18 words",
    27: "never assign to a name `_notebook.py` owns",
    28: "every entry declares ENTRY_CEILING and SOLVE_BUDGET",
    29: "never import `_model`, `_analysis` or `_notebook`",
    30: "a chapter index renders its own `_model.py`",
    31: "a forked `_model.py` names its parent chapter, commit and differences; "
        "every `overwrites:` row names a real item",
    32: "no empty callout",
    33: "a chapter index declares `order:` matching its directory number",
    34: "the notebook has a front page, and its generated block is intact",
    35: "a chapter index keeps its entry listing and its lineage cell",
    37: "`cite()` names an entry that exists and publishes a hero value",
    38: "every chapter is named in the sidebar",
    39: "an index carries its input callouts, in order, and nothing else",
    40: "the front page's freeze is not older than the entries it counts",
}


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
    problems += _empty_model(root, chapters, entries)
    problems += _shared_hygiene(root, chapters, entries)
    problems += _loud_solves(root, chapters, entries)
    problems += _unfinished_index(root, chapters, entries)
    problems += _prose_enumeration(pages)
    problems += _title_is_a_question(entries)
    problems += _shadowed_machinery(root, chapters, entries)
    problems += _stale_freeze(root, chapters)
    problems += _budget_rules(root, chapters, entries)
    problems += _visuals_and_tables(root, chapters, entries)
    problems += _composition(root, chapters, entries)
    problems += _transcribed(root, chapters, entries)
    problems += _fork_provenance(root, chapters, entries)
    problems += _empty_callouts(root, chapters, entries)
    problems += _index_ordering(root, chapters)
    problems += _index_shape(root, chapters, entries)
    problems += _input_item_budget(root, chapters, entries)
    problems += _root_index_freeze(root, chapters, entries)
    problems += _book_index(root, chapters)
    problems += _chapter_index_blocks(root, chapters)
    problems += _citation_targets(root, chapters, entries)
    problems += _sidebar_lists_chapters(root, chapters)

    # Rule 13. Scoped to `_analysis.py`: `_model.py` is rendered in full by the
    # chapter index, and `_notebook.py` is deliberately invisible, so requiring
    # either would be noise. An entry renders only what it NAMES -- an entry
    # calling optimise() passes `optimise`, not the private builder optimise
    # happens to use, or the transitive closure would reproduce the whole file
    # in every entry and splitting a function would break the rule in entries
    # whose conclusions never changed.
    for c in chapters:
        shared = {n for n, (f, _) in _defs_of(root / "chapters" / c).items()
                  if f == "_analysis.py" and not n.startswith("_")}
        for f in [e for e in entries if e.parent.name == c]:
            text = f.read_text()
            rendered, n_footers = rendered_by_footer(text)
            missing = sorted((entry_calls(text) & shared) - rendered)
            if missing:
                problems.append((f, (
                    f"calls {', '.join(m + '()' for m in missing)} from "
                    f"_analysis.py but does not render "
                    f"{'them' if len(missing) > 1 else 'it'} — the footer cell "
                    f"passes the shared functions the entry called: "
                    f"footer({', '.join(sorted(rendered | set(missing)))})")))
            if n_footers == 0:
                problems.append((f, (
                    "no footer(…) cell — every entry ends with one; it renders "
                    "the method and what the entry cost to run, which freeze "
                    "records nowhere else")))
            elif n_footers > 1:
                problems.append((f, f"{n_footers} footer(…) cells — an entry "
                                    f"ends with one"))

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

        for expr in dict.fromkeys(e for e in INLINE_BODY.findall(text)
                                  if _computes_nothing(e)):
            problems.append(
                (f, f"`{{python}} {expr.strip()}` computes nothing — it reads no "
                    f"variable and calls no function, so the number was typed "
                    f"by hand and rule 1 applies. Compute it, or if it belongs "
                    f"to an earlier chapter, say so in prose and link the entry"))

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
        #
        # ENTRIES ONLY, which the message has always said: "an entry has one:
        # the answer". A chapter index is a different kind of page and has
        # legitimate structure -- the entry listing, and the collapsed model
        # source -- so holding it to one section said nothing true about it. It
        # only ever passed because it happened to carry exactly one heading;
        # adding the listing collided with a rule that was not aimed at it.
        # Index quality has its own rules: 24, 30, 32, 33, 34 and 35.
        if f.name != "index.qmd":
            top = re.sub(r"^:{3,}\s*\{\.callout-\w+\}.*?^:{3,}\s*$", "", text,
                         flags=re.S | re.M)
            top = re.sub(r"```\{python\}.*?```", "", top, flags=re.S)
            top = re.sub(r"^:{3,}.*$", "", top, flags=re.M)
            leads = (re.findall(r"^\*\*([^*]+?\.)\*\*", top, re.M)
                     + re.findall(r"^(#{2,}\s+.+)$", top, re.M))
            if len(leads) > 1:
                problems.append(
                    (f, f"{len(leads)} prose sections "
                        f"({', '.join(l.strip()[:24] for l in leads)})"
                        f" — an entry has one: the answer. Fold the rest into "
                        f"it, or into a callout"))

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
            if title not in INPUT_TITLES:
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

    # WITHIN a chapter, not across the notebook. The remedy this rule names --
    # promote to `_analysis.py` -- only exists inside one chapter, because every
    # chapter has its own. Comparing across them produced a finding whose advice
    # could not be followed: two chapters drawing the same three-view, told to
    # share a file that does not exist. Rule 20 is what watches for a helper
    # that ought to be shared more widely, and it is a warning for that reason.
    by_chapter = defaultdict(list)
    for f in entries:
        by_chapter[f.parent.name].append(f)
    for chapter, group in by_chapter.items():
        blocks = defaultdict(set)
        for f in group:
            lines = code_of(f.read_text())
            for i in range(len(lines) - BLOCK + 1):
                blocks[tuple(lines[i:i + BLOCK])].add(f.name)
        for block, where in blocks.items():
            if len(where) >= 2:
                problems.append(
                    (None, f"{BLOCK} code lines repeated in {len(where)} entries "
                           f"of {chapter} "
                           f"({', '.join(sorted(_label(n)[:23] for n in where))}) — promote "
                           f"to {chapter}/_analysis.py:\n        "
                           + "\n        ".join(block)))
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
    # Warnings are reported and do not fail. Only rule 17's lower tier uses
    # this: wall clock swings with machine load, so a message about it is worth
    # printing and not worth failing a render over.
    blocking = [p for p in found if "(warning)" not in p[1]]
    warned = len(found) - len(blocking)
    tail = f", {warned} warning(s)" if warned else ""
    print(f"\n{len(blocking)} problem(s){tail} in {', '.join(chapters)}")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
