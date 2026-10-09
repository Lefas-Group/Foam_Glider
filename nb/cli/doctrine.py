"""
`nb doctrine [--setup | --coordinate | <page>]` -- the shared doctrine.

WHY A COMMAND RATHER THAN FIVE PATHS. Claude Code skills have no include
directive, so `.claude/skills/coordinate-design/SKILL.md` can only name files
and ask Claude to read them. Naming paths works, and it hard-codes the
grouping in a second place: regroup the Gemini prefix and the skill silently
keeps reading the old set. `--setup` and `--coordinate` are the SAME grouping
`coord/doctrine.py` hands the prefix, so one change moves both.

It is also one Bash call instead of N Reads, and `allowed-tools` already
permits `Bash(uv run --group nb python -m nb *)`.

NOT injected into the skill at load time with `!`command``. SKILL.md loads for
`nb listen` and `nb answer` too, and paying ~3k tokens on every load to serve
the case that needs it is the inverse of the reasoning `tools/refs.py` uses
about what belongs in a prefix.
"""

import sys

from ..coord import doctrine
from ..process.log import tell


def main(argv):
    wanted = [a for a in argv if not a.startswith("--")]
    if "--list" in argv or (not argv):
        tell("  the doctrine both coordinators read\n")
        for name, (title, when, who) in doctrine.PAGES.items():
            tell(f"    {name}")
            tell(f"      {title}")
            tell(f"      read it: {when}")
            tell(f"      for: {', '.join(who)}\n")
        tell("  uv run --group nb python -m nb doctrine --setup"
             "        # before `nb new`")
        tell("  uv run --group nb python -m nb doctrine --coordinate"
             "   # before the first `nb ask`")
        tell("  uv run --group nb python -m nb doctrine <page>")
        return 0

    if wanted:
        out = []
        for name in wanted:
            name = name if name.endswith(".md") else f"{name}.md"
            if name not in doctrine.PAGES:
                tell(f"  no page {name!r}. Known: "
                     f"{', '.join(sorted(doctrine.PAGES))}")
                return 2
            out.append(doctrine.read(name))
        print("\n\n".join(out))
        return 0

    # BOTH SPELLED OUT, rather than `setup if --setup else coordinate`.
    # `--coordinate` was documented and never literally read -- it worked only
    # by falling through the default, so a typo in it would silently serve the
    # setup pages instead of failing. A flag the usage names is a flag the
    # parser should recognise.
    if "--setup" in argv:
        audience = "setup"
    elif "--coordinate" in argv:
        audience = "coordinate"
    else:
        tell("  say which: --setup (before `nb new`) or --coordinate "
             "(before the first `nb ask`), or --list")
        return 2
    print(doctrine.text(audience))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
