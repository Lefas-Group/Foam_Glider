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

    So it is compared against `contract.RULES` now, which is what a check of a copy
    has to be. Contiguity is gone with it: 36 was retired and its number is not
    reused, so the registry -- not `range(1, max)` -- decides what exists.
    """
    from .contract.contract import RULES
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
    missing = sorted(set(RULES) - set(nums))
    if missing:
        out.append("rule list: lint enforces "
                   + ", ".join(f"{n} ({RULES[n]})" for n in missing)
                   + " and the model is never told — add it to "
                     "system_instruction.md")
    extra = sorted(set(nums) - set(RULES))
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


SHINGLE = 10


def _shingles(text):
    """Normalised N-word runs, for the duplication check below."""
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    return {" ".join(words[i:i + SHINGLE])
            for i in range(max(0, len(words) - SHINGLE + 1))}


def _doctrine_problems():
    """
    The coordinator doctrine has ONE copy, and the registry knows every page.

    Two checks, and the second is the one that matters. `_rule_list_problems`
    above exists because a hand-copied list went eight rules stale, and the
    fix there was to compare the copy against the source. Here the fix is
    stronger: there is no copy to compare. `.claude/skills/coordinate-design/`
    and `nb/coord/` are two coordinators reading one set of pages, so a
    sentence appearing in both means the split has started to come apart --
    and a duplicated paragraph is how it begins every time.

    Ten words, because shorter runs collide on ordinary prose ("so a run that
    has already been") while a real duplicated sentence runs far longer.
    """
    from .coord import doctrine
    bad = list(doctrine.problems())

    skill = NB.parent / ".claude" / "skills" / "coordinate-design" / "SKILL.md"
    if not skill.exists():
        return bad
    theirs = _shingles(skill.read_text())
    for name in doctrine.PAGES:
        # A PAGE THAT IS NOT THERE is already reported above, and reading it
        # here raised FileNotFoundError straight out of `check()` -- a
        # preflight that crashes instead of listing what is wrong is the one
        # thing this module exists not to do.
        if not doctrine.path(name).exists():
            continue
        shared = theirs & _shingles(doctrine.read(name))
        if shared:
            one = min(shared)
            bad.append(f"doctrine: SKILL.md repeats {name} -- {one!r}. "
                       f"The skill points at the pages; it does not copy them.")
    return bad


#: Flags the code reads that `USAGE` deliberately does not name. Each is here
#: for a reason, and the list is short on purpose -- the check is worth nothing
#: if the answer to every finding is to add a line to it.
#:
#:   --porcelain     git's, inside a subprocess. Not an `nb` flag at all.
#:   --close-window  internal: `nb ask` passes it to the watcher it spawns.
#:   --detach        the old spelling of `--quiet`, kept working, not advertised.
#:   --help          handled before dispatch, and universal.
UNDOCUMENTED_ON_PURPOSE = {"--porcelain", "--close-window", "--detach",
                           "--help"}

FLAG = re.compile(r"""["'](--[a-z][a-z0-9-]*)["']""")
USAGE_FLAG = re.compile(r"--[a-z][a-z0-9-]*")


def _usage_problems():
    """
    `USAGE` and the parsers agree about which flags exist.

    THE SAME FAILURE AS THE RULE LIST, one layer out. `__main__.py`'s docstring
    is hand-written help, and hand-written help drifts from the parser beneath
    it silently: `nb new --target` was parsed, rendered into every brief, and
    depended on by the coordinator doctrine, while the usage text had never
    heard of it. Four more were the same -- `--stop`, `--model`, `--options`,
    `--default` -- and one, `--coordinate`, ran the other way: named in the
    usage and never actually tested for, so it worked only by falling through
    a default.

    Both directions matter. A flag the code reads and the usage omits is a
    capability nobody finds; a flag the usage names and the code never reads is
    one that fails in a way no error message explains.
    """
    main = NB / "__main__.py"
    src = main.read_text()
    usage_end = src.index('"""', 3)
    documented = set(USAGE_FLAG.findall(src[:usage_end]))

    parsed = set()
    for f in [main, *sorted((NB / "cli").glob("*.py"))]:
        text = f.read_text()
        if f == main:
            text = text[usage_end:]
        parsed |= set(FLAG.findall(text))

    out = []
    for flag in sorted(parsed - documented - UNDOCUMENTED_ON_PURPOSE):
        out.append(f"usage: {flag} is parsed and the help never mentions it")
    for flag in sorted(documented - parsed):
        out.append(f"usage: the help names {flag} and no parser reads it")
    return out


def _example_problems():
    """
    Every `nb <command>` quoted in the doctrine is a command that exists.

    A doctrine page is read by a model that will type what it says. The worked
    `cut(...)` script that used to live in the skill is gone with the API it
    called, so there is little Python left to bind-check -- but the pages are
    thick with `nb` invocations, and a renamed subcommand would leave both
    coordinators confidently calling something that is not there.

    Read out of the dispatch chain rather than a list, for the reason
    `tools/api.py` introspects instead of quoting.
    """
    main = (NB / "__main__.py").read_text()
    known = set(re.findall(r'cmd == "([a-z_]+)"', main))
    known |= {c for grp in re.findall(r'cmd in \(([^)]*)\)', main)
              for c in re.findall(r'"([a-z_]+)"', grp)}
    if not known:
        return ["usage: no subcommands found in the dispatch chain"]

    pages = []
    doc_dir = NB / "references" / "coordinator"
    if doc_dir.is_dir():
        pages += sorted(doc_dir.glob("*.md"))
    skill = NB.parent / ".claude" / "skills" / "coordinate-design" / "SKILL.md"
    if skill.exists():
        pages.append(skill)

    out = []
    for page in pages:
        # ANCHORED, because `uv run --group nb python -m nb ask` contains the
        # string "nb python" and a bare `\bnb (\w+)` reports it as a missing
        # command. The two forms that are real invocations are `-m nb <cmd>`
        # and inline code starting `` `nb <cmd>  ``.
        for cmd in sorted(set(re.findall(r"(?:-m nb|`nb) ([a-z_]+)",
                                         page.read_text()))):
            if cmd not in known:
                out.append(f"doctrine: {page.name} says `nb {cmd}` and there "
                           f"is no such command")
    return out


def _import_problems():
    """
    Every module in `nb` imports. Two lines, and it catches what nothing else
    does.

    MOVED HERE FROM `nb.corpus`, which was deleted when the lint-calibration
    corpus it was built around stopped existing: two of its three frozen
    notebooks are gone and the rules those counts calibrated are settled. The
    sweep was the one part of that file with nothing to do with notebooks or
    rules, and it earns its place on a measurement -- a preflight run imports
    26 of the 81 modules here, so 55 were covered by no check at all,
    including the whole of `nb.coord`, `process/mailbox.py` and `cli/watch.py`.
    A syntax error in any of them surfaced only when somebody ran that command
    by hand. It happened twice in one session: a heredoc edit ran off the end
    of a string literal in `new.py` and was found several commits later.

    With `tests/` gone this is the only automated proof that `nb`'s own code
    still loads.
    """
    import importlib
    import pkgutil

    out = []
    for mod in pkgutil.walk_packages([str(NB)], "nb."):
        # NOT A MODULE, despite living here. `nb.tools.probe_init` is the
        # source text `kernel.py` sends as a probe kernel's first cell: it
        # execs the chapter into whatever namespace it lands in and reads
        # $NB_ROOT to know which one. Importing it runs that at import time,
        # in a process where neither is true.
        #
        # It is a real file rather than a string literal in `kernel.py` so that
        # it is linted and syntax-checked like everything else -- which this
        # loop would otherwise be the one thing to refuse. Skipped by name
        # because the alternative, a try/except around the env read, would make
        # a kernel that never loaded its chapter look healthy.
        if mod.name == "nb.tools.probe_init":
            continue
        try:
            importlib.import_module(mod.name)
        except Exception as e:                       # noqa: BLE001 -- report all
            out.append(f"import failed: {mod.name}: {type(e).__name__}: {e}")
    return out


def check(root):
    """Return a list of failures. Empty means go."""
    notebook = Notebook(root)
    bad = []
    bad.extend(_doctrine_problems())
    bad.extend(_usage_problems())
    bad.extend(_example_problems())
    # ONE MORE ENTRY IN `bad`, not an early return. `corpus` reported broken
    # imports first and bailed before anything else ran, on the grounds that
    # nothing downstream could be trusted. Here every other check is already
    # independent of it -- they read text off disk -- so a failed import reads
    # like any other failure, and a reader gets the whole list in one pass.
    bad.extend(_import_problems())

    # Rule 11, run through the contract's own check rather than reimplemented,
    # so the two can never disagree about what "byte-identical" means. It covers
    # `_notebook.py` alone now; `_scratch/_probe_base.py` was the second until
    # probes moved into a kernel and its job passed to `nb/tools/probe_init.py`,
    # which ships with `nb` and so cannot drift.
    from .contract.rules import _notebook_drift
    for where, msg in _notebook_drift(notebook.root):
        bad.append(f"rule 11: {where.name if where else ''} {msg}")

    if not (notebook.root / "_quarto.yml").exists():
        bad.append(f"no _quarto.yml in {notebook.root}")

    # check.py shells out to the first two. Without quarto it cannot render;
    # without git it silently falls back to re-rendering everything, which is
    # correct but slow enough to look like a hang.
    #
    # `npx` is not check.py's -- it is ours, and it was the one binary this
    # check did not name. `mcp_fs` spawns
    # `npx -y @modelcontextprotocol/server-filesystem` with no fallback, and
    # that server IS `read_text_file`, `edit_file` and `write_file`. So on a
    # machine without Node this whole function said "ok", the run started,
    # FORKED INTO THE BACKGROUND, and then died where nobody was looking. A
    # green light followed by a detached failure is the worst shape a missing
    # dependency can take, and it is the first thing a fresh clone hits.
    for binary, why in (("quarto", "render"),
                        ("git", "freeze scoping and diffs"),
                        ("npx", "the MCP filesystem server -- install Node")):
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
