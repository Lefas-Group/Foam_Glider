"""
Did any rendered number move? One copy, shared by every notebook.

    uv run python <skill>/freezediff.py <notebook-dir> [chapter ...] [--ref REF]

Compares every entry's rendered output against a git ref (default HEAD) and
reports what changed. Exits non-zero if anything did, so it can gate a commit.

This is the other half of lint rule 12. That rule says "you changed the model
and did not re-render"; this one answers "you re-rendered -- here is what moved."
Reach for it after any change to a chapter's `_model.py` or `_analysis.py`: a
model correction, a material change, a dependency upgrade that shifts every
polar, or a refactor that is supposed to change nothing at all.

WHY GIT IS THE INSTRUMENT. `_freeze/**/execute-results/html.json` stores each
page's rendered markdown with its inline expressions ALREADY EVALUATED, and the
figure PNGs sit beside it -- all committed, because a notebook commits its freeze
so a fresh clone renders without re-solving. So the baseline exists before you
start: there is no "capture before" step to run or to forget. Scraping the
rendered HTML instead is a trap worth naming, since a code cell closes with a
single `</div>` and the obvious pattern eats the prose that follows it.

WHY THIS IS NOT `git diff`. Each html.json holds a whole page's markdown as ONE
JSON string, so a single changed digit -- or merely the runtime line -- reports
the entire page as modified. This parses both sides and diffs the markdown as
text.

It lives in the skill rather than in each notebook for the same reason `lint.py`
does: it is a CHECKER. It runs at authoring time, reads the notebook, and writes
nothing into the rendered site, so a notebook does not need it present to render.
`_notebook.py` is the opposite, which is why that one is vendored and this is not.

USAGE NOTE, and it is not optional. Freeze tracks the page, not its includes, so
editing `_model.py` invalidates nothing. Delete the freeze before re-rendering or
you are comparing a fresh render against a cache hit and the match is an
artefact:

    rm -rf <notebook>/_freeze/chapters/<chapter> <notebook>/.quarto
    quarto render <notebook>
    uv run python <skill>/freezediff.py <notebook>

There is no `--no-freeze` flag. `stale()` below catches the case anyway, because
that false pass has already happened here once.
"""
import difflib
import hashlib
import json
import pathlib
import re
import subprocess
import sys

from lint import ENTRY_FILE, chapters_of, _label

# The four things that differ between two renders of identical code. Each was
# found by cold-rendering an unmodified tree and reading what came back: after
# these substitutions that diff is EMPTY and the figure PNGs are byte-identical,
# which is the property that makes this instrument trustworthy. Verify it that
# way again if it ever starts reporting noise.
#
# The seconds are masked but the SOLVE COUNT is kept -- masking the whole runtime
# line once hid a real 18 -> 2, which was the point of the change being checked.
RUNTIME = re.compile(r"Executed in [0-9.]+ s")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
CELL_ID = re.compile(r"\{#[0-9a-f]{8}( |\})")
FIG_ID = re.compile(r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def markdown_of(blob):
    """The page's rendered markdown, with per-render noise normalised away."""
    d = json.loads(blob)
    md = d["result"]["markdown"] if isinstance(d.get("result"), dict) else ""
    md = RUNTIME.sub("Executed in … s", md)
    md = FENCE.sub("<code cell>", md)
    md = CELL_ID.sub(r"{#ID\1", md)
    md = FIG_ID.sub("-UUID", md)
    return [l for l in md.splitlines() if l.strip()]


def at_ref(repo, ref, rel):
    """A file's bytes at a git ref, or None if it is not there."""
    r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=repo,
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def stale(entry_qmd, frozen_md):
    """
    Is this freeze from an older version of its own page?

    Comparing a fresh render against a cache hit shows a spurious match, and that
    has produced a false pass here: a mistyped working directory meant the freeze
    was never deleted and the render never ran, and everything reported
    unchanged. So check the frozen markdown still contains the page's current
    visible code before trusting any comparison built on it.
    """
    if not entry_qmd.exists():
        return []
    want = []
    for cell in re.findall(r"```\{python\}(.*?)```", entry_qmd.read_text(), re.S):
        # A cell with echo/include false never echoes its source into the
        # markdown, so its lines are legitimately absent and prove nothing.
        if re.search(r"^\s*#\|\s*(echo|include):\s*false", cell, re.M):
            continue
        want += [l.strip() for l in cell.splitlines()
                 if l.strip() and not l.strip().startswith("#")]
    return [l for l in want if l not in frozen_md]


def figures(root, repo, ref, chapters):
    """
    Figure PNGs whose bytes moved, as [(label, filename)].

    Numbers alone cannot see a chart change: an entry whose answer IS a plot can
    have every bar move while its three printed values stay put. Matplotlib
    embeds no timestamp, so within one environment a pure refactor leaves these
    byte-identical and any difference here is real.
    """
    moved = []
    for c in chapters:
        for p in sorted((root / "_freeze" / "chapters" / c).glob(
                "*/figure-html/*.png")) if (
                root / "_freeze" / "chapters" / c).exists() else []:
            old = at_ref(repo, ref, str(p.relative_to(repo)))
            now = p.read_bytes()
            if old is None:
                moved.append((p.parts[-3], f"{p.name} (new)"))
            elif hashlib.sha256(old).digest() != hashlib.sha256(now).digest():
                moved.append((p.parts[-3], p.name))
    return moved


def main(argv):
    if not argv:
        print(__doc__.strip().split("\n\n")[1].strip())
        return 2
    ref = "HEAD"
    if "--ref" in argv:
        i = argv.index("--ref")
        if i + 1 >= len(argv):
            print("  --ref needs a git ref")
            return 2
        ref = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    root = pathlib.Path(argv[0]).resolve()
    if not (root / "chapters").is_dir():
        print(f"  {root} is not a notebook (no chapters/ directory)")
        return 2
    repo = root.parent
    chapters = argv[1:] or chapters_of(root)

    changed = absent = 0
    for c in chapters:
        base = root / "_freeze" / "chapters" / c
        for p in sorted(base.glob("*/execute-results/html.json")) if base.exists() else []:
            label = p.parts[-3]
            frozen = json.loads(p.read_text())["result"]["markdown"]
            missing = stale(root / "chapters" / c / f"{label}.qmd", frozen)
            if missing:
                print(f"  {_label(label)}: STALE FREEZE — {len(missing)} current "
                      f"code line(s) absent from it, e.g. {missing[0][:60]!r}. "
                      f"Delete _freeze/chapters/{c}/ and render before trusting "
                      f"any comparison")
                changed += 1
                continue
            old = at_ref(repo, ref, str(p.relative_to(repo)))
            if old is None:
                print(f"  {_label(label)}: not in {ref} — no baseline")
                absent += 1
                continue
            a, b = markdown_of(old.decode()), markdown_of(p.read_text())
            delta = [l for l in difflib.unified_diff(a, b, lineterm="", n=0)
                     if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            if delta:
                changed += 1
                print(f"\n  {_label(label)}:")
                for l in delta[:40]:
                    print(f"    {l[:200]}")
                if len(delta) > 40:
                    print(f"    … {len(delta) - 40} more")

    moved = figures(root, repo, ref, chapters)
    if moved:
        print("\n  figures:")
        for label, name in moved:
            print(f"    {_label(label)}: {name}")

    print(f"\n{changed} page(s) changed, {len(moved)} figure(s) changed, "
          f"{absent} without a baseline, vs {ref}")
    return 1 if (changed or moved or absent) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
