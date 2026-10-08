"""
The contract itself: which rules exist, what each is called, and why.

WHY THIS IS ITS OWN MODULE. A rule number lived in three places -- `RULES` for
its label, `WHY` for its reason, and a `_tag(n, ...)` call in `check()` binding
it to an implementation -- all hand-synchronised. `unexplained()` exists because
of that: it AST-scrapes this file to find rules nobody wrote a reason for, which
is a detector for a problem the structure created.

`register()` closes the loop. A check declares the rule it enforces, the registry
refuses a number that is not declared here, and the binding is beside the code
instead of in a list two thousand lines away.

WHAT IS STILL SPLIT, honestly: 21 of the 40 rules have no implementation the
registry can name. Ten are written inline inside `check()`; eleven are bundled
into four functions that emit findings tagged `None`, because one function
enforcing four rules cannot say which one a finding belongs to. `unattributed()`
reports them, so the gap is a list rather than an impression -- and that list is
the work the next phase does.

`RULES` and `WHY` keep their exact contents. `preflight._rule_list_problems`
compares the model's hand-written rule list against `RULES` for COVERAGE, and
argues -- correctly -- that the model-facing wording should stay hand-written
because it is tuned for the model. Nothing here changes that.
"""

import ast
import inspect
import pathlib
import re


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
    43: "A run reconstructing a real aeroplane wrote its chord, taper, six "
        "fuselage stations and five cut-part areas straight into `_model.py` "
        "from memory, declared four mass inputs and nothing else, and "
        "captioned the lot `# from the plan sheet`. Nobody had the plan, so "
        "nobody was ever asked, and a wing loading 20% above the "
        "manufacturer's published figure reached a committed entry. The "
        "obvious rule -- flag undeclared GEOMETRY constants -- cannot be "
        "written: `c_root_w = 0.140` and `SOLVE_BUDGET = 10.0` are the same "
        "thing to a parser. A rule that catches one phrasing and misses the "
        "next is worse than none, because `lint clean` stops meaning CHECKED "
        "and starts meaning PROBABLY FINE. So this counts, and leaves the "
        "judgement with the person at the assumptions prompt, who is the one "
        "who can open the plan.",
    45: "`compare_to_photo` says when its camera fit cannot be trusted -- a "
        "parameter on a bound, an outline that does not track the aircraft, "
        "or a residual above 1%, where another seed usually does better. The "
        "F-16 Viper reconstruction fitted its three-quarter view at 2.86%, "
        "was told in the same string that a better basin existed, had no "
        "probe pool left to look for one, printed the note into the entry -- "
        "and wrote that the overlay CONFIRMS the planform. The hedge and the "
        "claim were on the same page and nothing compared them. Shape is the "
        "one thing no published target checks, so an overlay is the whole of "
        "that evidence, and citing a hedged one spends it on nothing.",
    46: "A question arrived at the notebook as a title and nothing else, so "
        "the page said WHAT was asked and never why it was worth asking. The "
        "programme's reasoning lived in the coordinator's conversation and on "
        "the board, both of which are transcripts nobody reads back, while "
        "the entry -- the thing that is committed, rendered and read a month "
        "later -- carried no trace of it. Two entries can answer adjacent "
        "questions in sequence and a reader cannot tell whether the second "
        "followed from the first or from a change of mind. The justification "
        "is the coordinator's, written at `nb ask`, and it is carried verbatim "
        "rather than paraphrased: a reason rewritten by the party it was "
        "given to is not a record of the decision.",
    47: "`footer()` renders the source of every shared function the entry "
        "called, collapsed, which is the method and not a description of it. "
        "A reader deciding whether to unfold forty lines of optimiser setup "
        "had only the function names to go on, and the entry's prose is about "
        "the AIRCRAFT -- rule 6's words are spent on the answer, correctly. "
        "So the summary sits with the source rather than in the prose, has "
        "its own budget, and is folded away beside it: the reader who wants "
        "to know how the number was got opens one box and finds a sentence "
        "before the code.",
    48: "An entry built a symbol inside an inline expression and the page "
        "showed the backslashes. Quarto inserts an inline expression's "
        "result as literal text and never re-parses it as markdown or as "
        "LaTeX, so markup assembled in the f-string arrives as characters. "
        "It renders without error and lints clean, which is why it needs a "
        "rule rather than a paragraph. The math belongs in the markdown, "
        "where its dollar signs are seen; the expression carries the "
        "number.",
    44: "A reconstruction reported 0.54% worst error across eight published "
        "targets, and seven of the eight had been ASSIGNED rather than "
        "predicted -- five to an exact 0.00%. `_model.py` held "
        "`x_cg_target = 0.085 + 0.038`, a component list summing to exactly "
        "156 g, and a battery mass computed as published AUW minus dry "
        "weight. A target the model is built to hit is not a check, it is an "
        "identity, and the entry reads as verification. Banning assignment "
        "outright was tried on paper and is worse: total mass and CG are "
        "what you measure and adjust on a bench, almost every downstream "
        "answer rests on them, and a derived mass model 10% out makes stall, "
        "loading and climb all worse. So the rule bites only on targets that "
        "are a CONSEQUENCE OF THE GEOMETRY being reconstructed -- those are "
        "the ones whose assignment destroys the check. Mark the others "
        "`(given)`.",
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
    # SCANS THE PACKAGE, not this file. It used to read `__file__`, which was
    # right while every check lived in lint.py -- and would have silently
    # started reporting seventeen false gaps the moment this table moved out of
    # that file, which it just did. Worse, it returns [] on OSError, so a broken
    # version reports "no gaps" and `corpus.py` believes it.
    documented = set(WHY)
    from ..config import NB
    for f in sorted(NB.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        try:
            tree = ast.parse(f.read_text())
        except (OSError, SyntaxError):
            continue
        for n in ast.walk(tree):
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
    11: "`_notebook.py` byte-matches the canonical copy",
    12: "a committed page has a freeze, and it is not older than its model",
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
    41: "the hero value derives from a solve, not from a literal",
    42: "a cell labelled `tbl-…` renders a table",
    43: "(warning) how many constants `_model.py` fixes, against inputs declared",
    44: "(warning) a DERIVED target is not written into `_model.py` as a literal",
    45: "(warning) an overlay's note reaches the page, and is not hedged",
    46: "the entry carries the question's justification as its `subtitle`",
    47: "`footer(…)` carries a `method=` summary of the code the entry wrote",
    48: "an inline `{python}` expression produces a value, never markup",
}


def _tag(rule, rows):
    """`[(where, msg)]` -> `[(rule, where, msg)]`."""
    return [(rule, where, msg) for where, msg in rows]


# =============================================================================
# BINDING A CHECK TO ITS RULE.
#
# `@register(n)` says "this function enforces rule n", next to the function, and
# refuses a number `RULES` does not declare -- so a typo is an ImportError
# rather than a finding that quietly reports the wrong rule.
#
# `covers=` is for the four functions that enforce several rules at once. They
# emit `None` as their rule, exactly as `_tag(None, ...)` did, because a finding
# from `_budget_rules` genuinely cannot say whether it is 16, 17, 18 or 28. The
# declaration is the difference: the gap is now enumerable rather than inferred
# from a `None` in a dispatch list.
# =============================================================================
_REGISTERED = []


def register(number=None, covers=()):
    """Bind a check to the rule it enforces. See the block comment above."""
    for n in ((number,) if number is not None else ()) + tuple(covers):
        if n not in RULES:
            raise ValueError(f"rule {n} is not declared in RULES")
    if number is not None and covers:
        raise ValueError("a check is one rule or several, not both")

    def bind(fn):
        _REGISTERED.append((number, tuple(covers), fn))
        fn._rule = number
        fn._covers = tuple(covers)
        return fn
    return bind


def implemented():
    """Rule numbers some registered check enforces, attributably or not."""
    out = set()
    for number, covers, _ in _REGISTERED:
        if number is not None:
            out.add(number)
        out |= set(covers)
    return out


def unattributed():
    """
    Declared rules whose findings cannot name them. The phase-6 worklist.

    Two kinds, and they are fixed differently: a rule inside a BUNDLE needs the
    bundle split; a rule with no registered check at all is written inline in
    `check()` and needs lifting out. Both end with `@register(n)` on a function.
    """
    bundled = {n for _, covers, _ in _REGISTERED for n in covers}
    attributable = {n for n, _, _ in _REGISTERED if n is not None}
    return sorted(set(RULES) - attributable), sorted(bundled)


def run(**context):
    """
    Every registered check, findings tagged with the rule it enforces.

    CALLED BY PARAMETER NAME, because the checks do not share a signature and
    never did: `_notebook_drift(root)`, `_prose_enumeration(pages)`,
    `_title_is_a_question(entries)`, `_index_ordering(root, chapters)` and
    twenty of `(root, chapters, entries)`. The hand-written dispatch list carried
    that variety as twenty-four slightly different call sites; passing a context
    and taking the subset each asks for carries it once.

    A check asking for something the context does not hold is a TypeError at the
    call, naming the parameter -- which is the right failure for a wiring
    mistake, and better than the silent one where a dispatch line is simply
    never added.
    """
    out = []
    for number, _covers, fn in _REGISTERED:
        wanted = inspect.signature(fn).parameters
        out += _tag(number, fn(**{k: v for k, v in context.items() if k in wanted}))
    return out
