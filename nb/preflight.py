"""
Invariants the agent can never fix, checked before a single token is spent.

Each of these would otherwise surface as a dead end partway through a run: the
model would read a lint failure it has no way to repair, or reach for a binary
that is not there. Five milliseconds here buys that back.
"""

import shutil
import os
import re
import sys

from .config import NB, Notebook, SYSTEM_INSTRUCTION


# "# The 39 rules lint checks", then a fenced block of "NN  description".
RULE_HEADING = re.compile(r"^# The (\d+) rules lint checks", re.M)
RULE_LINE = re.compile(r"^\s*(\d+)  \S", re.M)


def _rule_list_problems(text):
    """
    The rule list in the system instruction matches the rules lint enforces.

    It is hand-written ON PURPOSE -- the descriptions are tuned for the model
    ("no sweeping a decision that should have been asked -- record it as
    Specified"), and deriving them from lint's function names would make them
    worse. What a hand-written list cannot do is notice a rule it was never
    told about.

    IT WAS EIGHT BEHIND. The heading said 32 while lint enforced through 40, and
    four of the missing ones -- 33, 35, 37, 39 -- are blocking and are tripped by
    the very edits the write brief asks for ("EDIT index.qmd, fill both
    callouts"). The old version of this check compared the list only against
    ITSELF: heading count, contiguity, duplicates. All three passed, because a
    list can be perfectly self-consistent and still describe a different system.

    So it is compared against `lint.RULES` now, which is what a check of a copy
    has to be. Contiguity is gone with it: 36 was retired and its number is not
    reused, so the registry -- not `range(1, max)` -- decides what exists.
    """
    import lint
    head = RULE_HEADING.search(text)
    if not head:
        return ["system instruction has no '# The N rules lint checks' heading"]
    claimed = int(head.group(1))
    nums = [int(n) for n in RULE_LINE.findall(text[head.end():])]
    if not nums:
        return ["the rule list is empty"]
    out = []
    if len(nums) != claimed:
        out.append(f"rule list: heading says {claimed} but {len(nums)} are listed")
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    if dupes:
        out.append("rule list: duplicated: rule "
                   + ", ".join(str(d) for d in dupes))
    missing = sorted(set(lint.RULES) - set(nums))
    if missing:
        out.append("rule list: lint enforces "
                   + ", ".join(f"{n} ({lint.RULES[n]})" for n in missing)
                   + " and the model is never told — add it to "
                     "system_instruction.md")
    extra = sorted(set(nums) - set(lint.RULES))
    if extra:
        out.append("rule list: names rule "
                   + ", ".join(str(n) for n in extra)
                   + ", which lint does not enforce — a rule the model obeys "
                     "for nothing")
    return out


def _code_only(path):
    """
    A file with its comments and docstrings stripped.

    `_dead_config` used to grep the raw text, so a constant MENTIONED in prose
    counted as read. That is not hypothetical: `PROBE_WALL_CLOCK = 960.0` sat
    dead in `config.py` while the only occurrence of the name anywhere else was
    inside a docstring in `lint.py` -- and the guard passed. A check that a
    comment can satisfy is a check about comments.
    """
    import io
    import tokenize
    try:
        src = path.read_text()
    except (OSError, UnicodeDecodeError):
        return ""
    out, prev_end, prev_type = [], (1, 0), tokenize.INDENT
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                continue
            # A STRING alone on a logical line is a docstring. Anything else --
            # a message, a regex, a path -- is code and must still count.
            if (tok.type == tokenize.STRING
                    and prev_type in (tokenize.INDENT, tokenize.NEWLINE,
                                      tokenize.NL, tokenize.DEDENT)):
                prev_type = tok.type
                prev_end = tok.end
                continue
            out.append(tok.string)
            prev_type, prev_end = tok.type, tok.end
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src                      # unparseable: fall back to the text
    return " ".join(out)


def _dead_config():
    """
    Constants in `config.py` that nothing reads.

    Three of these bit in one week. `TEMPLATES` pointed at a directory that had
    been deleted. `CACHE_TTL` outlived the explicit cache. Worst, a second
    `DEFAULT_ENTRY_CEILING` sat here disagreeing with the notebook's own copy --
    tightening it looked like it worked and changed nothing, because the value
    in force came from `_notebook.py` and always had.

    A dead constant is not untidy, it is a lie about where a number comes from,
    and the cost is paid by whoever next tries to change it.
    """
    import re
    src = (NB / "config.py").read_text()
    names = re.findall(r"^([A-Z][A-Z0-9_]+) *=", src, re.M)
    out = []
    for name in names:
        used = False
        for f in NB.rglob("*.py"):
            if f.name == "config.py" or "__pycache__" in f.parts:
                continue
            if re.search(rf"\b{name}\b", _code_only(f)):
                used = True
                break
        if not used:
            out.append(f"config.{name} is read by nothing — delete it, or the "
                       f"next person will change it and wonder why nothing moved")
    return out


def check(root):
    """Return a list of failures. Empty means go."""
    notebook = Notebook(root)
    bad = []

    # Rule 11, run through the vendored linter itself rather than reimplemented,
    # so the two can never disagree about what "byte-identical" means. It covers
    # `_notebook.py` AND `_scratch/_probe_base.py` -- the second was added after
    # an improvement sat in one notebook while the scaffold still held the old
    # text, drift invisible precisely because nothing compared them.
    import lint
    for where, msg in lint._notebook_drift(notebook.root):
        bad.append(f"rule 11: {where.name if where else ''} {msg}")

    if not (notebook.root / "_quarto.yml").exists():
        bad.append(f"no _quarto.yml in {notebook.root}")

    # check.py shells out to both. Without quarto it cannot render; without git
    # it silently falls back to re-rendering everything, which is correct but
    # slow enough to look like a hang.
    for binary, why in (("quarto", "render"), ("git", "freeze scoping and diffs")):
        if shutil.which(binary) is None:
            bad.append(f"{binary} not on PATH -- needed for {why}")

    if not SYSTEM_INSTRUCTION.exists():
        bad.append(f"no system instruction at {SYSTEM_INSTRUCTION}")
    else:
        bad += _rule_list_problems(SYSTEM_INSTRUCTION.read_text())

    bad += _dead_config()

    if not os.environ.get("GEMINI_API_KEY"):
        bad.append("GEMINI_API_KEY unset")

    # Deliberately NOT checked: the AeroSandbox version the API index was built
    # against. library_explorer walks the installed package on first call and
    # caches in-process, so the inventory is always the version the notebook
    # actually imports. There is no stored index to go stale.

    return bad


def main(argv):
    """
    `print`, not `say`. This is a COMMAND: `say` writes to the run log and
    nothing else, and outside a run there is no log open -- so every invocation
    of `python -m nb.preflight` produced an exit code and not one line of
    output, which is indistinguishable from it passing.
    """
    if not argv:
        print("usage: uv run --group nb python -m nb.preflight <notebook>")
        return 2
    bad = check(argv[0])
    for b in bad:
        print(f"  {b}")
    print(f"\npreflight {'FAILED' if bad else 'ok'}"
          f"{f' -- {len(bad)} problem(s)' if bad else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
