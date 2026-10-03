"""
What the rules read with: the regexes, the budgets, and the parsers.

Every one of these was a module-level name in `lint.py`, interleaved with the
rules that use them -- which is a large part of why that file reached 3,300
lines and why a rule could not be moved without deciding where its constants
went. They are separated here so the rules can be, and so the parse layer has
somewhere to be that is not "beside the checks".

PARSERS, NOT POLICY. Nothing here decides that anything is wrong: these turn a
`.qmd` or a chapter directory into text, cells, prose, tables, callouts, calls
and declared budgets, and the rules in `rules.py` judge what comes out.
`contract/parse.py` wraps them as `Entry` and `Chapter`, which is how a rule
should reach them; the functions stay public because `lint` re-exports several
and `build/freezediff.py` imports three by name.
"""

import ast
import functools
import json
import pathlib
import re


# An entry is a date-prefixed .qmd. Matched by shape rather than by a literal
# year: the first version of this globbed "2026-*.qmd", which would have stopped
# checking every new entry on 1 January without failing or saying anything.
ENTRY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}-")



def is_entry(handle):
    """
    Is this handle an ENTRY stem rather than an `_inputs.yml` id?

    THE HANDLE ALREADY SAYS SO, which is the point. An id is a slug an author
    chose; an entry stem starts with its date. Three readers were each deciding
    this their own way -- `inputs.short` by matching `ENTRY_FILE`,
    `inputs.own_entry` by re-reading `input_ids` off disk to see which tier a
    row came from, and `_notebook.py` by a private `_STEM` copy. The middle one
    was the worst: a second file read to learn something already encoded in the
    string it was holding.

    An `<ancestor>/<handle>` pair is judged on its last segment, which is the
    part that names the declaration.
    """
    return bool(ENTRY_FILE.match(handle.rpartition("/")[2]))


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


# THE CANONICAL `_notebook.py`, which rules 11 and 27 both read. One constant,
# because they used to derive it separately from `__file__` and the two would
# have disagreed the moment either moved -- as both just did, out of `vendor/`
# and into `nb/`, leaving `vendored/` holding the only file the word fits.
# THE SEED `nb new` COPIES DOWN, which rule 11 holds each notebook's own copy
# to. In `nb/scaffold/`, with the seven templates it is written beside -- it was
# `nb/vendored/notebook.py`, from when four modules that were never copied
# anywhere shared that directory with it.
#
# FROM `config.SCAFFOLD`, which is the one place that knows where the package
# keeps its seeds. FOUR TIMES in this refactor a path was derived from
# `__file__` and silently changed meaning when its file moved: rule 11 stopped
# reporting drift, `unexplained()` would have reported seventeen false gaps,
# `api._furniture` raised FileNotFoundError on every api_search miss, and rule
# 27 read the seed's names for every notebook. Counting directory levels by hand
# is what they have in common, and `parents[1]` here was the last of them.
#
# `config` imports nothing of ours at module level -- only `os` and `pathlib` --
# so this cannot cycle, and `Notebook`'s own reach into `contract` is a lazy
# import inside a method.
from ..config import SCAFFOLD as _SCAFFOLD

SCAFFOLD_NOTEBOOK = _SCAFFOLD / "_notebook.py"



# Rule 27. Every top-level name `_notebook.py` binds -- its imports, its helpers
# and its state. READ FROM THE FILE rather than typed out here: a hand-copied
# list would be wrong the first time someone adds a helper, in the silent
# direction (no rule, no warning). Falls back to the names that actually broke a
# render if the file cannot be parsed, so the rule degrades rather than
# vanishing.
#
# PER NOTEBOOK, and that is a fix. It was `MACHINERY = _machinery_names()`,
# evaluated once at import from the SEED copy and then used for every notebook
# -- so the two notebooks whose `_notebook.py` has drifted were checked against
# a list of names their own file does not bind. Rule 27 exists to stop an entry
# clobbering a name its own render depends on, which is a question about the
# notebook in front of it.
#
# Cached per root, because rule 27 asks this once per entry and the answer is
# one parse of one file.
@functools.lru_cache(maxsize=None)
def machinery_names(root):
    """Top-level names bound by THIS notebook's `_notebook.py`."""
    try:
        tree = ast.parse((pathlib.Path(root) / "_notebook.py").read_text())
    except (OSError, SyntaxError):
        return frozenset({"time", "pathlib", "aero_cost", "footer", "_T0"})
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
    return frozenset(names | {"_T0"})


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



def _passed_names(tree):
    """
    Bare identifiers handed to a call as arguments -- `f(helper)`, not `f()`.

    A PARAMETERISED CHAPTER USES ITS HELPERS THIS WAY. `optimize_geometry_for_
    sink_rate(get_airplane_plate, alpha_max=5.75)` calls the optimiser and
    *passes* the vehicle, so `get_airplane_plate` is an `ast.Name` argument and
    never an `ast.Call`. Counting calls alone therefore reported the most used
    function in the chapter as dead: `get_airplane_plate()` was flagged with
    three entries depending on it, and chapter 04 carried four more of exactly
    the same shape.

    `rendered_by_footer` already reads bare names out of `footer(...)` for the
    same reason -- "both take live function objects". This is that allowance,
    applied to every call rather than to one.
    """
    out = set()
    for c in ast.walk(tree):
        if not isinstance(c, ast.Call):
            continue
        for a in list(c.args) + [k.value for k in c.keywords]:
            if isinstance(a, ast.Name):
                out.add(a.id)
    return out



def entry_calls(text):
    """
    Every function name an entry calls, from its cells AND its inline
    expressions -- plus every bare name it PASSES to a call.

    The inline half is not optional: a value quoted only in prose, as
    `{python} f"{trim(ap)['alpha']:.1f}"`, is a call that appears in no cell, and
    an entry whose only use of a helper is in its answer sentence is exactly the
    shape that would otherwise slip through unrendered.

    The passed-name half is not optional either, for the reason `_passed_names`
    gives: a helper handed to another function is used, and a rule that cannot
    see that calls the chapter's workhorse dead.
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
        called |= _passed_names(tree)
    for expr in re.findall(r"`\{python\}([^`]*)`", text):
        try:
            tree = ast.parse(expr.strip(), mode="eval")
        except SyntaxError:
            continue
        called |= {(c.func.attr if isinstance(c.func, ast.Attribute)
                    else getattr(c.func, "id", None))
                   for c in ast.walk(tree) if isinstance(c, ast.Call)}
        called |= _passed_names(tree)
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



def _one_drift(seed, local):
    """
    The notebook's copy against the seed `nb new` wrote it from.

    THE REMEDY IS TWO-WAY, and the message says both because neither is
    obviously right. The notebook's copy is the one that RENDERS, so a local
    change may be the improvement; the seed is what the next notebook starts
    from, so a difference left alone is an improvement the next notebook will
    not get. It used to say "so every notebook gets it" -- true when four
    notebooks were kept in step, and now an argument about a set of size one.
    """
    if not seed.exists():
        return []                       # the scaffold is the thing that is broken
    if not local.exists():
        return [(local, f"missing — copy it from {seed}")]

    want, got = seed.read_text().splitlines(), local.read_text().splitlines()
    if want == got:
        return []
    n = next((i for i, (a, b) in enumerate(zip(want, got), 1) if a != b),
             min(len(want), len(got)) + 1)
    return [(local, f"differs from {seed} (first at line {n}) — the copy here "
                    f"is the one that renders, so decide which is right: take "
                    f"the seed's version down, or lift this change up into it")]



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



def entry_cells(text):
    """An entry's `{python}` cells, concatenated, with `#|` options stripped."""
    return "\n".join(
        re.sub(r"^\s*#\|.*$", "", cell, flags=re.M)
        for cell in re.findall(r"```\{python\}(.*?)```", text, re.S))


# WHERE A CHAPTER'S HELPERS LIVE, and which of them are API. Rules 20, 21 and 22,
# which were one function called `_shared_hygiene`.
#
# `_analysis.py` exists to force CONSISTENCY between entries: one implementation,
# so entries cannot drift apart. Measured, that is working -- of twelve helpers
# that exist in more than one chapter (forks copy the file), eleven are
# byte-identical, and the one difference is the fork's declared purpose. The
# failure it prevents is on record: four subtly different neutral points in one
# chapter, one of them taking its moment reference from the wrong station.
#
# It also saves tokens, but only on REUSE: a signature sits in the cached prefix
# forever, against one avoided read of a sibling entry. So the rules pull in both
# directions on purpose -- 20 promotes what must not diverge, 21 removes what
# nothing calls, 22 keeps what is merely internal out of the prefix and out of
# `api()`.
#
# ALL THREE ARE WARNINGS, and 21 and 22 for a different reason than 20. They
# describe the chapter's accumulated state, not the entry being written: an
# established chapter carries 27 of them, and blocking on those would make every
# run in it start by refactoring `_analysis.py` -- work nobody asked for, on code
# the run did not touch, which is itself the refactor that needs proving. They are
# for a human doing a cleanup pass, or for the run that happens to be editing
# that function anyway. Rule 20 is a warning for the narrower reason that its
# false-positive rate is not yet measured.


def _helper_usage(root, chapter_name, entries):
    r"""
    Who in a chapter calls what: the shared reading rules 20, 21 and 22 need.

    `entry_calls`, NOT a `\bname\s*\(` regex. The regex needed a literal
    open-paren after the name, so it saw `helper()` and missed
    `optimise(helper)` -- and a parameterised chapter passes its vehicle far more
    often than it calls it. That reported `get_airplane_plate()` dead while three
    entries depended on it, and four more in chapter 04 the same way. One
    definition of "used", shared with the render-scope closure in build/verify.py,
    instead of two that disagree.
    """
    chapter = root / "chapters" / chapter_name
    mine = [e for e in entries if e.parent.name == chapter_name]
    defs = _defs_of(chapter)
    shared = {n: called for n, (f, called) in defs.items()
              if f == "_analysis.py"}
    used = [entry_calls(e.read_text()) for e in mine]
    return {
        "chapter": chapter,
        "analysis": chapter / "_analysis.py",
        "mine": mine,
        "shared": shared,
        "model_names": {n for n, (f, _) in defs.items() if f == "_model.py"},
        "expensive": aero_calls_of(chapter),
        "by_entries": {n: sum(1 for u in used if n in u) for n in shared},
        # Every definition in the chapter, not just `_analysis.py`: a helper
        # called only from `_model.py` is still called.
        "internally": {
            n: any(n in called for m, (_, called) in defs.items() if m != n)
            for n in shared},
    }



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


# Rules 14 and 15 were one function because they share the hard part: working
# out what an entry actually SHOWS. Both read the rendered output, for the reason
# rule 15 always did -- a table produced by `print()` or
# `display(Markdown(...))` inside a cell is not parseable as a table anywhere in
# the source. Rule 14 counted `fig-`/`tbl-` cell labels, and the two entries that
# prompted that change carry neither: one emits its table through
# `display(Markdown(md))` with no label, the other captions it inline as
# `{#tbl-plans}`, which is not a cell option. Both were invisible, so "one visual
# per entry" was unenforced for exactly the form the model had started choosing.
#
# So the shared work is a helper and the two rules are two rules. Counting
# figures by label and tables by what rendered cannot double-count: a figure
# reaches the freeze as an image, never as pipe-markdown.


def _visuals_of(root, entry):
    """
    (figure labels, tables as (rows, cols), whether the aircraft is drawn).

    No freeze means the source is counted instead, exactly as rule 12 -- and
    rule 12 is what keeps the freeze honest.
    """
    text = entry.read_text()
    figures = re.findall(r"^\s*#\|\s*label:\s*(fig-[\w-]+)", text, re.M)

    # Hand-written tables in the .qmd, plus whatever the page rendered.
    seen = tables_in(re.sub(r"```.*?```", "", text, flags=re.S))
    frozen = (root / "_freeze" / "chapters" / entry.parent.name / entry.stem
              / "execute-results" / "html.json")
    if frozen.exists():
        try:
            md = json.loads(frozen.read_text())["result"]["markdown"]
            # ECHOED SOURCE IS NOT A TABLE. A cell without `echo: false` puts
            # its own text in the output, so an entry building a markdown table
            # in an f-string had that f-string counted as a second table --
            # `{c_root:.1f}` and all. Measured on one entry of 77; it made the
            # rendered count 2 for a page showing 1.
            seen += tables_in(re.sub(r"^```.*?^```", "", md, flags=re.S | re.M))
        except (ValueError, KeyError, TypeError):
            pass
    return figures, seen, bool(DRAWING.search(text))



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


# The chapter-local modules `_model.qmd` EXECS into the page namespace. They are
# not importable and never were: `execute-dir: project` puts the cwd at the
# notebook root, so `chapters/NN-name/` is not on sys.path.
EXECD = ("_model", "_analysis", "_notebook")



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



CITE_CALL = re.compile(
    r"""cite\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']([^)]*)\)""")

HERO_PAIR = re.compile(
    r"\[([^\]]+)\]\{\.hero-value\}[^\[]*\[([^\]]*)\]\{\.hero-label\}")



HERO_SOURCE = re.compile(
    r"\[([^\]]*)\]\{\.hero-value\}", re.S)      # source side, before rendering



# An index carries its input callouts and nothing else with a heading. It used
# to carry "Questions asked here" and "The model" too, above a listing and a
# code dump that are perfectly legible without being announced -- a heading
# whose section is one div is a label for something the reader can already see.
INDEX_SECTIONS = INPUT_TITLES



def read_fork(root, chapter):
    """
    `chapters/<c>/_fork.yml` as a dict, or None. Flat by design.

    Deliberately not a YAML parse, for the reason `_categories.yml` is not one:
    lint imports nothing outside the stdlib, so the checker runs
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
    `defines` is a required argument of `fork_chapter` and of `nb new`, and was
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



def entry_items(root, chapter):
    """
    [(kind, text, stem)] the chapter's ENTRIES declare, in order.

    The other half of the register, and it was read by nothing. `_inputs.yml`
    holds what is true of every entry; an entry's own callout holds what THAT
    question introduced -- and an `ask_specified` answer lands in the second,
    where the next run cannot see it.

    Measured: the X-Wing chapter asked the user for a static margin, recorded
    "center of gravity (or static margin): 10%" in its entry, and two entries
    later asked for the same quantity again and recorded it a second time under
    a different name. The register a run was shown held one item, from
    `_inputs.yml`; the three its own entries had declared were invisible.

    Reads the callouts rather than a data file because that is where an entry
    puts them, by design: rule 39 keeps a CHAPTER's items out of markdown and
    an ENTRY's items in it.
    """
    out = []
    for e in sorted((root / "chapters" / chapter).glob("*.qmd")):
        if not ENTRY_FILE.match(e.name):
            continue
        try:
            text = e.read_text()
        except OSError:
            continue
        for title, body in callouts_of(text):
            if title not in INPUT_TITLES:
                continue
            kind = "Assumed" if "assum" in title.lower() else "Specified"
            for item in re.findall(r"^\s*\d+\.\s+(.*(?:\n(?!\s*\d+\.).*)*)",
                                   body, re.M):
                out.append((kind, " ".join(item.split()), e.stem))
    return out



def input_ids(root, chapter):
    """{id: text} for a chapter with `_inputs.yml`, else {}."""
    data = read_inputs(root, chapter)
    return {i: t for k in ("specified", "assumed") for i, t in data.get(k, [])}



# The brief's three blocks, in the order they are read and rendered. `targets:`
# is the newest: a published FACT the model must reproduce -- area, all-up
# weight, wing loading -- with the tolerance it must land inside.
#
# WHY ITS OWN BLOCK rather than a tolerance sniffed out of a `specified:` row.
# A real brief already carried `"**Horizontal stab**: span 213 mm, area 16
# in2, +/-10%."`, which is a tolerance on a MEASUREMENT and not a target at
# all. Matching on `+/-` would have read it as one.
#
# WHY NOT A CLAIM. `top speed 87 km/h` is what a programme exists to judge,
# and it stays an `assumed:` row. A claim in here is a claim the reconstruct
# gate will drive the model towards -- fitting it to the thing it was built to
# test, and reporting success.
BRIEF_BLOCKS = (("specified", "Specified"),
                ("targets", "Target"),
                ("assumed", "Assumed"))


def notebook_items(root):
    """[(kind, text)] from the notebook's brief -- `_inputs.yml` at its root."""
    data = parse_inputs(root / "_inputs.yml")
    return [(kind, t)
            for k, kind in BRIEF_BLOCKS for _, t in (data.get(k) or [])]


# A target the model may be CALIBRATED to rather than required to predict.
# Written at the end of the row and left in the rendered text on purpose: a
# reader should see which figures were reproduced and which were given.
GIVEN = re.compile(r"\(given\)\s*$", re.I)


def notebook_targets(root):
    """
    [(handle, text, given)] from the brief's `targets:` block, or [].

    `given` is the derive/calibrate split, and it is the difference between a
    check and an identity.

    A target that is a CONSEQUENCE OF THE GEOMETRY being reconstructed --
    wing area, MAC, tail volume, length -- must be derived. Assigning it
    destroys the only check on the planform, and the planform drives every
    aerodynamic answer. Measured on the FT Mini Corsair v1.0: seven of eight
    targets were assigned, five of them to an exact 0.00 %, and the entry
    reported "0.54 % worst error" as though that verified something.

    A target that is a PROPERTY YOU WOULD MEASURE OR ADJUST ON A BENCH --
    total mass, CG -- may be given. That is calibration, not cheating: those
    two are what almost every downstream answer rests on, and a derived mass
    model landing 10 % out would make stall, loading and climb all worse. An
    earlier draft of this banned assignment outright and would have forced
    exactly that.

    Derived is the default, because the failure is silent in that direction.
    """
    rows = parse_inputs(root / "_inputs.yml").get("targets") or []
    return [(h, t, bool(GIVEN.search(t))) for h, t in rows]



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
    # EVERY CHAPTER IN THE NOTEBOOK, not the subset being checked. An
    # `overwrites:` row points at ANOTHER chapter by construction, so scoping
    # the set of known names to the chapters under examination made a correct
    # row look broken: `check.py glider-notebook 04-thinner-foam` reported
    # `overwrites '01-foam-glider', which is not a chapter of this notebook`
    # and failed the lint gate. A cross-chapter reference has to be resolved
    # against the whole notebook, whatever slice is being linted.
    known = set(chapters_of(root))
    for c in chapters:
        # `_inputs.yml` CARRIES THEM TOO, for what a later entry here
        # superseded in an earlier one -- no fork, no approval, an assumption
        # is the writer's to revise. Same row shape, so the same checks, except
        # that a bare handle means this chapter's own entry.
        for raw in ((read_inputs(root, c) or {}).get("overwrites") or []):
            # `read_inputs` splits `- <id>: <text>` into a pair, where
            # `read_fork` hands back the raw line. Same file shape, two
            # readers, and a row here is `- <handle>: <why>` -- so the handle
            # is the first half either way.
            target = str(raw[0] if isinstance(raw, tuple) else raw
                         ).partition(":")[0].strip()
            src = target.partition("/")[0] if "/" in target else c
            stem = target.partition("/")[2] or target
            where = root / "chapters" / c / "_inputs.yml"
            if src not in known:
                out.append((where, (
                    f"overwrites {src!r}, which is not a chapter of this "
                    f"notebook")))
            elif (not (root / "chapters" / src / f"{stem}.qmd").exists()
                  and stem not in input_ids(root, src)):
                out.append((where, (
                    f"overwrites {target!r}, which is neither an entry of "
                    f"chapters/{src} nor an id it declares")))
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
            # AN ENTRY STEM IS A HANDLE TOO. An assumption a single entry made
            # has no `_inputs.yml` id -- nothing to point at but the entry that
            # made it -- and those are exactly the ones a fork breaks: "Wing
            # position: near mid-fuselage" was declared while building the
            # vehicle the fork copied. `_item_text` resolves both.
            if ENTRY_FILE.match(item_id):
                if not (root / "chapters" / parent / f"{item_id}.qmd").exists():
                    out.append((where, (
                        f"overwrites {parent}/{item_id!r}, which is not an "
                        f"entry of chapters/{parent}")))
                continue
            if item_id not in theirs:
                out.append((where, (
                    f"overwrites {parent}/{item_id!r}, which is not an id in "
                    f"chapters/{parent}/_inputs.yml"
                    + (" — its ids are: " + ", ".join(sorted(theirs))
                       if theirs else " — it has no _inputs.yml"))))
    return out



def _label(name):
    """An entry's name without its date, which is the same for every line."""
    return ENTRY_FILE.sub("", name)

