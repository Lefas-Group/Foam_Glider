"""
Every rule in the contract, one function each.

WHAT CHANGED TO GET HERE. These were 44 functions inside a 3,300-line `lint.py`,
interleaved with the parsers and regexes they use, and 21 of the 40 rules could
not name themselves -- ten written as blocks inside `check()`, eleven bundled
into four functions. Phase 6 gave each its own name and `@register` number;
this moves them somewhere they can be read.

A rule is a function of the context it asks for -- `root`, `chapters`,
`entries`, `pages`, `aero` -- returning `(where, message)` pairs. It does not
know its own number at runtime: `@register(n)` tells the registry, and the
registry tags the findings. Nothing here renders, shells out or writes.

READ WITH `shared.py` BESIDE IT: the parsers and regexes are there, and the
import list below is exactly what these rules reach for.
"""

# Detected from what these functions actually reference, not guessed: `ast` for
# the rules that parse a cell, `json` for the two that read a freeze, `re`
# throughout, and `defaultdict` for rule 2's block index. Rule 12 shells out to
# git but imports subprocess where it does so.
import ast
import json
import re
from collections import defaultdict

from .contract import register
from .shared import (
    SCAFFOLD_NOTEBOOK, machinery_names,
    BLOCK, BUDGET_NAMES, CITE_CALL, ENTRY_FILE,
    ENTRY_REFERENCE, ENTRY_SELF, ENTRY_TITLE, EXECD, FORK_SIMILARITY,
    HERO_PAIR, HERO_SOURCE, INDEX_SECTIONS, INLINE, INLINE_BODY,
    INPUT_CALLOUTS, INPUT_TITLES, MAX_CALLOUT_ITEM, MAX_FIG_CAP,
    MAX_INLINE_PER_SENTENCE, MAX_PROSE, MAX_TITLE_WORDS, PLACEHOLDER,
    RESULT_NUMBER, RUNTIME_SECONDS, SENTENCE, SWEPT_LITERAL, _bound,
    _code_only, _computes_nothing, _defs_of, _departure_targets, tables_in,
    _helper_usage, _label, _one_drift, _plausible_parent, _rendered_numbers,
    _visuals_of, body_prose, callouts_of, code_of, declared_items,
    entry_calls, entry_cells, fixed_count_solves, limits_of, notebook_items,
    prose_of, read_fork, read_inputs, rendered_by_footer, words,
)




@register(11)
def _notebook_drift(root):
    """
    Rule 11: the notebook's `_notebook.py` matches the canonical copy.

    `_notebook.py` is VENDORED into each notebook rather than shared from here,
    unlike this file. It is exec'd into every page at render time and its output
    is baked into the published HTML, so sharing it would make a notebook
    unrenderable without `nb` installed, and would put a render-affecting
    file outside the Quarto project -- where freeze cannot see edits to it, which
    is the failure mode that has already served stale pages here three times.

    IT USED TO BE JUSTIFIED BY PROPAGATION as well -- "an improvement to
    footer() shows up as a problem in every notebook that has not taken it" --
    and that argument is now about a set of size one. `RADICAL-GLIDER` is the
    only notebook `nb` drives; the other three are the design-notebook skill's or
    frozen corpus, and they drift on purpose. So the two reasons above are the
    whole of it, and both are about a SINGLE notebook: it must render without
    `nb` installed, and freeze must be able to see edits to the file.

    Byte equality is still the right test because nothing in the file is
    project-specific; any difference is either an un-propagated improvement or an
    accident, and both want a person to decide which.
    """
    # ONE copied file now. `_scratch/_probe_base.py` was the second, and was
    # checked here for the same reason -- an improvement to it once sat in one
    # notebook while the scaffold still held the old text. It is gone: probes
    # run in a kernel `nb` starts, and the cell that loads the chapter is
    # `nb/tools/probe_init.py`, an ordinary module that ships with `nb` and is
    # therefore incapable of drifting. Vendoring buys propagation and costs
    # this rule; one fewer copied file is one fewer of both.
    problems = []

    # (rule, where, message). THE NUMBER IS A FIELD NOW, not something a caller
    # greps out of the prose. `verifiers._problems` had to drop rule 12 before
    # a render -- the render IS its fix, so gating the render on it deadlocks --
    # and the only handle it had was `FREEZE_STALE = "but the freeze is not"`, a
    # substring of the message. Reword the message and the filter silently stops
    # working; what comes back is the deadlock, which cost three runs in a row.
    # This repo already learned that once: rules 35 and 39 key on the function
    # call rather than on comment wording, after keying on prose went stale.
    #
    # `None` where a check still bundles several rules -- `_budget_rules` covers
    # 16, 17, 18 and 28 between them, and attributing per finding means
    # splitting the function. The table below is therefore also the list of what
    # is left to split, which is the honest version of a gap.
    problems += _one_drift(SCAFFOLD_NOTEBOOK, root / "_notebook.py")
    return problems



@register(27)
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
    # THIS notebook's machinery, not the seed's -- see `machinery_names`.
    machinery = machinery_names(root)
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
                    if isinstance(name, ast.Name) and name.id in machinery:
                        out.append((f, f"rebinds `{name.id}`, which "
                                       f"_notebook.py still uses after your "
                                       f"code runs — the traceback would land "
                                       f"in a file you cannot edit; rename it"))
    return out



@register(26)
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



@register(25)
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



@register(24)
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
    scaffold placeholder for `defines:` -- the same failure one tier up, and
    the only thing that still catches an undescribed chapter now that nothing
    renames one.
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



@register(23)
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



@register(19)
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



@register(20)
def _entry_local_reaches_the_vehicle(root, chapters, entries):
    """
    Rule 20: an entry-local function that measures the aircraft.

    It is chapter machinery: a measurement of the aircraft, and two entries
    measuring the same thing differently is the failure `_analysis.py` exists to
    prevent. A function that only formats an already-computed value diverges
    harmlessly and stays where it is. WARNING while the false-positive rate is
    unknown -- a genuinely one-off measurement trips it, and forcing that into
    the prefix forever is its own cost.
    """
    out = []
    for c in chapters:
        u = _helper_usage(root, c, entries)
        target = u["model_names"] | set(u["shared"]) | u["expensive"]
        for e in u["mine"]:
            try:
                parsed = ast.parse(entry_cells(e.read_text()))
            except SyntaxError:
                continue
            for node in parsed.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                reached = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                hits = reached & target
                if hits:
                    out.append((e, f"(warning) `{node.name}()` is defined in the "
                                   f"entry but reaches the vehicle "
                                   f"({', '.join(sorted(hits)[:3])}) — a "
                                   f"measurement of the aircraft belongs in "
                                   f"_analysis.py, where a sibling cannot "
                                   f"reimplement it differently"))
    return out



@register(21)
def _dead_shared_helper(root, chapters, entries):
    """
    Rule 21: nothing reaches it -- not an entry, not another helper.

    Dead here is worse than dead elsewhere: someone calls the stale one and the
    chapter has two answers again.
    """
    out = []
    for c in chapters:
        u = _helper_usage(root, c, entries)
        if not u["analysis"].exists():
            continue
        for n in sorted(u["shared"]):
            if not u["by_entries"][n] and not u["internally"][n]:
                out.append((u["analysis"], f"(warning) `{n}()` is called by no "
                                           f"entry and no other helper — delete "
                                           f"it, or call it"))
    return out



@register(22)
def _internal_helper_is_public(root, chapters, entries):
    """
    Rule 22: internal-only, but public.

    It costs a line of the cached prefix and a line of `api()` on every run, and
    an entry that does not call it does not need to know it exists.

    THE `internally` TEST IS LOAD-BEARING, and is what the `elif` used to say.
    These two rules were one if/elif, so a helper that nothing calls at all
    reported 21 and stopped. As independent rules it would report both, which is
    a finding that did not exist before -- so 22 asks for a helper that IS
    called internally, which is exactly the branch the `elif` reached.
    """
    out = []
    for c in chapters:
        u = _helper_usage(root, c, entries)
        if not u["analysis"].exists():
            continue
        for n in sorted(u["shared"]):
            if (not u["by_entries"][n] and u["internally"][n]
                    and not n.startswith("_")):
                out.append((u["analysis"], f"(warning) `{n}()` is only called by "
                                           f"other _analysis.py functions — rename "
                                           f"it `_{n}` so it stays out of the "
                                           f"prefix and out of api()"))
    return out



@register(14)
def _one_visual_per_entry(root, entries):
    """Rule 14: an entry shows one visual, or two when one draws the aircraft."""
    found = []
    for f in entries:
        figures, seen, drawn = _visuals_of(root, f)
        # The cap is ONE, raised to two when one of the figures is a drawing of
        # the aircraft rather than a second plot. A schematic and a plot are
        # different claims -- "what does it look like" and "how does it behave"
        # -- and the old cap made the second displace the first, which is how
        # three chapters ended up with no picture of the aeroplane at all.
        # Lint cannot judge "schematic", but it can see which function drew it.
        cap = 2 if drawn and figures else 1
        n = len(figures) + len(seen)
        if n > cap:
            what = ", ".join(figures + [f"{r}×{c} table" for r, c in seen])
            found.append((f, (
                f"{n} visuals ({what}) — a table counts as a figure, and an "
                f"entry shows one" + (" (two, when one is a drawing of the "
                f"aircraft)" if drawn else "") + f". Delete whichever is not "
                f"carrying the answer")))
    return found



@register(15)
def _table_size(root, entries):
    """Rule 15: a table is at most 6x4, excluding the header."""
    found = []
    for f in entries:
        _figures, seen, _drawn = _visuals_of(root, f)
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



@register(12)
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

    # WHAT GIT TRACKS, for the absence half below. One call, reused per chapter.
    try:
        listed = subprocess.run(["git", "ls-files"], cwd=root,
                                capture_output=True, text=True, timeout=10)
        tracked = set(listed.stdout.split()) if not listed.returncode else None
    except (OSError, subprocess.SubprocessError):
        tracked = None

    found = []
    for c in chapters:
        # A COMMITTED PAGE WITH NO FREEZE AT ALL, which the staleness test below
        # cannot see: it compares a freeze against the code, and `if not frozen:
        # continue` means absence was silent. That is the one failure the rule
        # exists to catch, and it has happened twice -- a chapter lost its index
        # freeze and stayed that way through several commits, and a commit swept
        # nine of chapter 04's freeze files out of git.
        #
        # Silence there is expensive in a way staleness is not. A stale freeze
        # publishes a wrong number; a missing one makes the site RE-EXECUTE the
        # page, which for an entry is hundreds of seconds of aero solves, and
        # makes a fresh clone unrenderable without them.
        #
        # SCOPED TO WHAT GIT TRACKS, which is what makes it quiet in the cases
        # that should be quiet: a scaffolded notebook has no entries, and an
        # entry being written right now is untracked until it commits.
        #
        # A WARNING, not a block. The missing freeze usually belongs to a
        # SIBLING, and holding an unrelated entry hostage over it would be a new
        # way to wedge a run -- the remedy is a render, which the reader can
        # choose when to pay for.
        if tracked is not None:
            for e in sorted((root / "chapters" / c).glob("*.qmd")):
                if not ENTRY_FILE.match(e.name):
                    continue
                if f"chapters/{c}/{e.name}" not in tracked:
                    continue
                if not (root / "_freeze" / "chapters" / c / e.stem
                        / "execute-results" / "html.json").exists():
                    found.append((e, (
                        "(warning) is committed but has no freeze — the site "
                        "will RE-EXECUTE it rather than serve it, and a fresh "
                        "clone cannot render without re-solving. "
                        f"`quarto render chapters/{c}/{e.name}` rebuilds it")))
        frozen = list((root / "_freeze" / "chapters" / c).glob(
            "*/execute-results/html.json")) if (
            root / "_freeze" / "chapters" / c).exists() else []
        if not frozen:
            continue                        # nothing frozen: nothing to be stale
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
                f"NOT YOURS TO FIX — the run re-proves the chapter itself "
                f"after lint passes and the entry builds, and will show you any "
                f"answer that moved. Do not run a checker by hand: it re-"
                f"renders the notebook, costs two to three minutes a call, and "
                f"changes nothing the run was not going to do anyway."))
    return found




# WHAT AN ENTRY MAY SPEND, declared by the entry. Rules 16, 17, 18 and 28, which
# were one function called `_budget_rules`.
#
# These were chapter-scoped, read from an optional `_budget.py`. That file is
# gone: budgets belong to the entry, which is both the unit of work and the unit
# the user is asked about, since the render ceiling is granted at the prompt
# before the run starts.


@register(28)
def _budgets_are_declared(root, entries):
    """
    Rule 28: both budgets declared, neither None, and the solve inside the render.

    BLOCKS, and is the load-bearing one, because the ceiling is no longer
    advisory -- `build/render.render_deadline()` derives an actual subprocess
    timeout from it. An entry that declares nothing would be bounded by the
    notebook default silently; an entry that declares None would have no bound at
    all, which is the state that let a render hang unnoticed.
    """
    problems = []
    for e in entries:
        budget, ceiling = limits_of(root, e)
        src = entry_cells(e.read_text())
        found_b, _ = _bound(src, "SOLVE_BUDGET")
        found_c, _ = _bound(src, "ENTRY_CEILING")

        # Both declared, neither None.
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

        # Second half: a solve cannot outlive the render containing it.
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
    return problems



@register(18)
def _budgets_are_not_inputs(root, chapters, entries):
    """
    Rule 18: a budget is declared in the first cell, not as a Specified input.

    INVERTED from what it once was. Budgets used to be REQUIRED in the Specified
    callout, on the reasoning that a granted number is a Specified input. True,
    but it crowded out the thing the callout exists for: an entry whose only
    Specified items were two budgets recorded nothing about its own design.
    `footer()` prints them now, from the declarations themselves, so the page
    still shows them and the callout is free again.
    """
    problems = []
    for e in entries:
        spec = "".join(body for title, body in callouts_of(e.read_text())
                       if title in ("Specified", "New user specifications"))
        named = sorted(n for n in BUDGET_NAMES if n in spec)
        if named:
            problems.append(
                (e, f"declares {', '.join(named)} in the `## Specified` callout "
                    f"— footer() prints the budgets now, so that callout is for "
                    f"what the DESIGN was committed to. Delete the budget "
                    f"item(s); if nothing else was specified, say `None.`"))

    # The other half: a CHAPTER INDEX does not declare a budget. The scaffold
    # template already says so -- "Budgets do NOT go here: each entry declares
    # its own" -- but three indexes inherited the line from the chapter-budget
    # era, and it is not merely stale. The index RENDERS the number, so changing
    # the budget in force rewrites the index's output, which `verify` reports as
    # a changed value and the refactor gate then holds an unrelated entry for.
    # That happened: `index: +4. Solve budget 60 s`.
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



@register(17)
def _frozen_entry_stayed_under_its_ceiling(root, entries):
    """
    Rule 17: what the frozen page actually cost, against what it declared.

    WARNS below the ceiling, for the reason it always did: the same solve here
    measured 533.9 s against a 145 s baseline purely from load, so a hard block
    on wall clock would fail on a busy machine and pass on an idle one. It blocks
    only PAST the ceiling, where load cannot be the explanation.
    """
    problems = []
    for e in entries:
        _budget, ceiling = limits_of(root, e)
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
    return problems



@register(16)
def _no_solve_budget_override(root, chapters):
    """Rule 16: the budget is negotiated once, not overridden per call site."""
    problems = []
    for c in chapters:
        f = root / "chapters" / c / "_analysis.py"
        if not f.exists():
            continue
        try:
            parsed = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(parsed):
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
    return problems


# Rules 29 and 30 were one function, `_composition`, because they are both
# "how a chapter composes" -- which is a good way to group a docstring and a bad
# way to emit a finding: neither could say which rule it was. They share nothing
# but the loop over chapters, so splitting them cost the loop twice and bought
# both their numbers.
#
# The calibration that earned them stays here, above both, because it was done
# once across every chapter of all three notebooks: rule 29 matched the two
# lines from the failed run and nothing else, rule 30 matched that run's index
# and nothing else.


@register(29)
def _no_importing_the_chapter(root, chapters, entries):
    """
    Rule 29: a page importing `_model` or `_analysis` instead of using them.

    An ERROR, unlike its neighbours, because the page does not BUILD:
    `from _analysis import optimize_glider_unswept_c4` cost a whole run, dying
    at the render with ModuleNotFoundError after lint had passed clean. The
    names are already in scope; importing them is the mistake a fresh chapter
    invites, because there is no sibling to copy the convention from.
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
    return out



@register(30)
def _index_renders_its_model(root, chapters, entries):
    """
    Rule 30: a chapter index renders its own `_model.py`.

    Guards the justification rule 19 rests on -- "the vehicle goes in
    `_model.py` because the chapter index renders that file, so it is where a
    reader looks for the aircraft". The scaffold ships that block; a model that
    rewrites index.qmd with `write_file` rather than editing it drops the block
    and nothing noticed, leaving a chapter whose aircraft appears nowhere.
    """
    out = []
    for c in chapters:
        chapter = root / "chapters" / c
        # Two loose marks rather than one exact path: every index in the corpus
        # builds the path with an f-string over a loop variable
        # (`f"chapters/{c}/{_f}"`, with the loop named `_f`, `name` or `code` in
        # different chapters), so the literal `chapters/NN-name/_model.py`
        # appears in none of them. Naming the file AND its own chapter directory
        # is what they all share -- checked against all 12 indexes across the
        # three notebooks, where only the failing one misses both.
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



@register()
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



@register(32)
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



@register(38)
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



@register(41)
def _hero_is_computed(root, chapters, entries):
    """
    Rule 41. The hero value derives from a solve, not from a literal.

    Rule 1 already rejects an inline expression that computes nothing, so
    `[`{python} 0.714`]{.hero-value}` never survives. What it cannot see is one
    more hop: `[`{python} f"{crossing_span:.3f}"`]{.hero-value}` carries a Name
    and passes, while two cells up sits `crossing_span = 0.714`.

    That is not hypothetical. An entry answering "what is the smallest span
    that meets the target" swept six spans, hard-coded the crossing it had
    found while probing, and inserted that same number into the swept list so
    the figure would pass through it. Every number on the page was real; the
    root-find the page describes was never run. A reader cannot tell, and
    neither can a re-render -- which is the whole basis on which these entries
    are meant to be trusted.

    Checked against the ENTRY's own cells only. A literal that came from
    `_model.py`, from a sibling entry, or from a user specification is a
    different thing entirely -- rule 26 governs those -- and this rule must not
    fire on them, which is why `_bound` is asked about the entry source rather
    than about every name in scope.

    Two things keep it narrow, and both were put in after a false positive.

    EVERY name in a hero must be a literal, not merely one of them. Flagging any
    literal hit `launch_height / sink`, where the height is a specified 1.5 m
    and the sink is solved for, and it hit `value * MM`, a unit conversion. The
    literal there is a co-factor and something beside it was genuinely solved.

    And EVERY hero in the entry must fail before it reports, because a
    before/after entry publishes two. Reading only the first flagged the
    comparison entries whose opening hero is a sibling's published baseline --
    carried as a literal with a `# from <entry>` comment, which is the
    convention -- while the computed half sat in the very next span.

    What is left is the hero that rests on nothing computed at all:
    `f"{crossing_span*1000:.0f} mm"` with `crossing_span = 0.714` two cells up
    and no other name in sight.
    """
    out = []
    for f in entries:
        text = f.read_text()
        heroes = HERO_SOURCE.findall(text)
        if not heroes:
            continue                    # rule 12 owns a missing hero
        cells = entry_cells(text)
        literals = {}
        for hero in heroes:
            names = set()
            for expr in INLINE_BODY.findall(hero):
                try:
                    tree = ast.parse(expr.strip(), mode="eval")
                except SyntaxError:
                    names = None
                    break
                names |= {n.id for n in ast.walk(tree)
                          if isinstance(n, ast.Name)}
            if not names:
                literals = None         # rule 1 owns a hero computing nothing
                break
            here = {}
            for name in sorted(names):
                bound, value = _bound(cells, name)
                if bound and isinstance(value, (int, float)) \
                        and not isinstance(value, bool):
                    here[name] = value
            if len(here) != len(names):
                literals = None         # this hero was solved for; entry stands
                break
            literals.update(here)
        if not literals:
            continue
        shown = ", ".join(f"`{k}` = {v!r}" for k, v in literals.items())
        out.append((f, f"every hero value rests only on literals this entry "
                       f"assigns: {shown} (warning). A headline number has to "
                       f"be what the code worked out, not what you already "
                       f"knew it would be -- solve for it, or make the hero "
                       f"the quantity you actually solved for and give this "
                       f"one in the prose"))
    return out



@register(37)
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



@register(35)
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



@register(34)
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



@register(33)
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



@register(40)
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



@register(39)
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



@register(8)
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



@register(31)
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
        fork = read_fork(root, c)
        where = root / "chapters" / c / "_fork.yml"
        # SIMILARITY DEMANDS A DECLARATION; IT NO LONGER GATES ONE. Everything
        # below used to sit behind `if not close: continue`, so a fork that
        # REWROTE its model rather than copying it escaped every check on its
        # own record -- including the placeholder test three blocks down, whose
        # comment predicts exactly what then happened. Measured: RADICAL-GLIDER
        # 05-optimised-geometry parameterised `get_airplane` and added a CasADi
        # mass function, scoring 0.66 against its parent to a 0.85 threshold,
        # and committed with `summary: "TODO: what the design BECAME"` intact.
        # The front page rendered those words, twice, as its lineage label.
        #
        # `_plausible_parent` was already loosened this way -- a declared parent
        # need not be the most similar one -- and the completeness checks simply
        # did not come with it. They belong to the DECLARATION: if a chapter
        # says it is a fork, its record is checked whatever the diff says.
        if not fork or not fork.get("parent"):
            if not close:
                continue        # not a copy and claims no parent: not a fork
            ratio, parent = close[-1]
            out.append((where, (
                f"chapters/{c}/_model.py is {ratio:.0%} identical to "
                f"chapters/{parent}/_model.py and no _fork.yml says so. Write "
                f"one beside it: `parent: {parent}`, `at: <commit>`, and a "
                f"`changes:` list with one line per deliberate difference, so "
                f"that `diff` between the two files is the review")))
            continue
        # Against the DECLARED parent, not the most similar one -- they are the
        # same chapter for a copy and different for a rewrite, and the declared
        # one is what the `changes:` list is answerable to. None when the parent
        # does not resolve, which the next check refuses anyway.
        ratio = dict(kin).get(fork["parent"])
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
            # The percentage is a supporting fact, not the reason -- so it is
            # omitted rather than faked when the parent's model cannot be read.
            # A fork with no `changes:` is wrong at any similarity.
            how_far = (f" chapters/{c}/_model.py is "
                       f"{100 - ratio * 100:.0f}% different from it."
                       if ratio is not None else "")
            out.append((where, (
                f"names a parent but lists no changes.{how_far} One line "
                f"per deliberate difference — the differences ARE the chapter")))
    # Departures are checked on EVERY chapter, not only ones the similarity
    # test flagged: a fork that rewrote its model rather than copying it -- 05,
    # at 35% -- can still depart from an ancestor's declaration.
    out += _departure_targets(root, chapters)
    return out






# =============================================================================
# THE RULES THAT USED TO BE WRITTEN INSIDE `check()`.
#
# Ten rule numbers -- 1, 2, 3, 4, 5, 6, 7, 9, 10 and 13 -- were implemented as
# code blocks in one 214-line function, sharing its locals. That is why they
# emitted findings tagged `None`: a block in a loop has no name to register, so
# nothing could say which rule a finding belonged to. 108 of 143 findings across
# the corpus could not name their own rule.
#
# Each block is now a function with `@register(n)` on it, its comment carried
# across unchanged. Nothing about WHAT they detect changed -- the messages are
# the same strings and the characterization harness holds them to that; the only
# difference is that a finding now arrives with its number.
#
# RE-DERIVING `text` PER RULE IS FREE, which is what made this cheap. Each of
# these used one shared `text = f.read_text()` at the top of a loop; now each
# reads it again through `Entry`, where the read and every parse of it is cached
# for the whole run. Phase 3 is what pays for phase 6.
# =============================================================================


@register(13)
def _footer_renders_what_it_calls(root, chapters, entries):
    """Rule 13: an entry passes to footer() the shared helpers it calls."""
    problems = []
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
    return problems



@register(5)
def _fixed_count_solves_in_shared(root, chapters, aero):
    """Rule 5: a counted loop around a solve, in a chapter's shared modules."""
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
            for line in fixed_count_solves(f.read_text(), aero[c]):
                problems.append(
                    (f, f"line {line}: `for … in range(…)` runs a solve every "
                        f"trip and cannot stop early — iterate to a tolerance "
                        f"with a guard that raises"))
    return problems



@register(5)
def _fixed_count_solves_in_pages(pages, aero):
    """Rule 5: a counted loop around a solve, in a page's own cells."""
    problems = []
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
    return problems



@register(1)
def _hand_typed_numbers(pages):
    """Rule 1: a result number typed into prose instead of computed."""
    problems = []
    for f in pages:
        text = f.read_text()
        for n in dict.fromkeys(RESULT_NUMBER.findall(prose_of(text))):
            problems.append(
                (f, f"hand-typed number {n!r} in prose — use `{{python}} …`"))
    return problems



@register(1)
def _inline_computes_nothing(pages):
    """Rule 1, second half: an inline expression that reads and calls nothing."""
    problems = []
    for f in pages:
        text = f.read_text()
        for expr in dict.fromkeys(e for e in INLINE_BODY.findall(text)
                                  if _computes_nothing(e)):
            problems.append(
                (f, f"`{{python}} {expr.strip()}` computes nothing — it reads no "
                    f"variable and calls no function, so the number was typed "
                    f"by hand and rule 1 applies. Compute it, or if it belongs "
                    f"to an earlier chapter, say so in prose and link the entry"))
    return problems



@register(6)
def _prose_budget(pages):
    """Rule 6: the whole entry's running text, against one word budget."""
    problems = []
    for f in pages:
        text = f.read_text()
        # The three word budgets.
        n = words(body_prose(text))
        if n > MAX_PROSE:
            problems.append(
                (f, f"{n} words of prose, over the {MAX_PROSE}-word budget — "
                    f"answer, warnings and any other running text, added up; "
                    f"only Specified/Assumed and figure captions are excluded"))
    return problems



@register(9)
def _one_prose_section(pages):
    """Rule 9: an entry has one prose section -- the answer."""
    problems = []
    for f in pages:
        text = f.read_text()
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
    return problems



@register(10)
def _siblings_are_linked(pages):
    """Rule 10: a sibling entry named in prose is linked, not just named."""
    problems = []
    for f in pages:
        text = f.read_text()
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
    return problems



@register(7)
def _figure_caption_budget(pages):
    """Rule 7: a figure caption says what is plotted, inside a word budget."""
    problems = []
    for f in pages:
        text = f.read_text()
        for cap in re.findall(r"^\s*#\|\s*fig-cap:\s*(.+)$", text, re.M):
            n = words(cap.strip().strip('"'))
            if n > MAX_FIG_CAP:
                problems.append(
                    (f, f"figure caption is {n} words, over {MAX_FIG_CAP} — say "
                        f"what is plotted, not what to conclude from it"))
    return problems



@register(8)
def _callout_item_budget(pages):
    """
    Rule 8: one input item, one line of it.

    The same rule as `_input_item_budget`, on the other place an item can be
    written: that one reads `_inputs.yml`, this one reads the rendered callout in
    an entry. Both are rule 8 and both now say so; this one emitted `None`.
    """
    problems = []
    for f in pages:
        text = f.read_text()
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
    return problems



@register(4)
def _swept_without_a_decision(pages):
    """Rule 4: a design choice swept over a few values, never asked about."""
    problems = []
    for f in pages:
        text = f.read_text()
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
    return problems



@register(3)
def _answer_before_the_evidence(pages):
    """Rule 3: `**Answer.**` comes before the last code cell."""
    problems = []
    for f in pages:
        text = f.read_text()
        if "**Answer.**" in text:
            last_cell = text.rfind("```{python}")
            if text.index("**Answer.**") > last_cell:
                problems.append(
                    (f, "**Answer.** comes after the last code cell — it should "
                        "come before the evidence"))
    return problems



@register(2)
def _repeated_code_blocks(entries):
    """Rule 2: the same three code lines in two entries of one chapter."""
    problems = []
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



@register(42)
def _labelled_table_renders(root, entries):
    """
    Rule 42. A cell labelled `tbl-…` actually renders a table.

    `_notebook.py` sets `ast_node_interactivity = "none"`, which stops Jupyter
    echoing a cell's last expression -- it exists because a figure cell ending
    in `draw_three_view(...)` published `array([[<Axes3D: ...>]])` under its own
    figure. The note there records that it was checked against every freeze
    first and that nothing relied on last-expression display, which was true of
    the entries that existed then.

    It stopped being true the moment an entry built a table the ordinary pandas
    way and ended on `df.style.hide(axis="index").format(...)`. That value is a
    Styler, Jupyter renders a Styler by its repr, and the repr is what is turned
    off. Nothing failed: the page rendered, the caption rendered, `@tbl-mass`
    resolved to "Table 1", the code fold held the code that would have built it,
    and between them was nothing at all. It survived a render, a re-render and a
    read-back of the page before anyone noticed the table was not there.

    So the check is on the RENDERED output, which is the only place the
    difference is visible: an entry that labels a cell `tbl-...` is promising a
    table, and the frozen markdown has to contain one. `md_table()` prints, and
    print is untouched by the suppression -- which is why the notebook's own
    idiom was never affected and why it is the remedy.

    Numbers are deliberately not compared. One `tbl-` label and one rendered
    table is the whole test; rule 15 is what reads their size.
    """
    out = []
    for f in entries:
        labels = re.findall(r"^\s*#\|\s*label:\s*(tbl-[\w-]+)", f.read_text(), re.M)
        if not labels:
            continue
        frozen = (root / "_freeze" / "chapters" / f.parent.name / f.stem
                  / "execute-results" / "html.json")
        if not frozen.exists():
            continue          # rule 12 owns the missing-freeze case
        try:
            md = json.loads(frozen.read_text())["result"]["markdown"]
        except (ValueError, KeyError, TypeError):
            continue
        for label in labels:
            # The cell's own div, not the whole page: a sibling table elsewhere
            # would otherwise answer for a cell that rendered nothing.
            block = re.search(r"::: \{#" + re.escape(label) + r"[ \n].*?\n:::", md, re.S)
            if block and not tables_in(block.group(0)):
                out.append((f, (
                    f"`{label}` labels a cell that renders no table — the "
                    f"caption and the cross-reference come out, and nothing "
                    f"comes out between them. A last expression is not "
                    f"displayed (`_notebook.py` turns the echo off), so a cell "
                    f"ending in a DataFrame or a Styler prints nothing: build "
                    f"it with `md_table(header, rows)` in an `output: asis` "
                    f"cell instead")))
    return out


@register(43)
def _constants_against_inputs(root, chapters, entries):
    """
    Rule 43, a warning, and a COUNT rather than a judgement.

    `_model.py` fixes a number of constants; the chapter declares a number of
    inputs. Neither figure is wrong on its own and no ratio between them is
    required -- so this reports both and stops, which is the whole design.

    WHY IT DOES NOT TRY TO FIND GEOMETRY. The failure it exists for is a run
    that wrote a whole airframe -- chord, taper, six fuselage stations, five
    cut-part areas -- from memory and declared four mass inputs, so nobody was
    ever asked about the shape. The obvious rule is "flag undeclared geometry
    constants", and it cannot be written: `c_root_w = 0.140` and
    `SOLVE_BUDGET = 10.0` are the same thing to a parser, and a rule that
    catches one phrasing of a thing and misses the next is worse than no rule,
    because `lint clean` stops meaning CHECKED and starts meaning PROBABLY
    FINE. That false assurance is the same failure as a number carrying a
    citation it has not earned.

    So this computes a fact -- 23 against 4, on the run that prompted it -- and
    leaves the judgement with the person at the assumptions prompt, who is the
    one who can open the plan. Reported once per chapter that has an entry.
    """
    out = []
    for c in chapters:
        if not any(e.parent.name == c for e in entries):
            continue
        model = root / "chapters" / c / "_model.py"
        try:
            tree = ast.parse(model.read_text())
        except (OSError, SyntaxError):
            continue
        # Module level only. A constant inside a function is a local detail;
        # the vehicle is what the module binds.
        fixed = []
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Constant):
                continue
            if not isinstance(node.value.value, (int, float)) \
                    or isinstance(node.value.value, bool):
                continue
            fixed += [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not fixed:
            continue
        declared = len(declared_items(root, c))
        out.append((model, (
            f"(warning) `_model.py` fixes {len(fixed)} numeric constants and "
            f"this chapter declares {declared} input(s). Not a fault in "
            f"itself -- but every one of those {len(fixed)} that is a "
            f"dimension of the real aircraft, rather than something the model "
            f"computes, is a `declare_input` the person at the prompt never "
            f"got to check: {', '.join(f'`{n}`' for n in fixed[:6])}"
            f"{' …' if len(fixed) > 6 else ''}")))
    return out
