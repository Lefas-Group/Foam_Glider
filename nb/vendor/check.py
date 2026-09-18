"""
Lint, render and diff a notebook in one call. One copy, shared by every notebook.

    uv run python <skill>/check.py <notebook-dir> [chapter ...] [--no-render] [--all] [--ref REF]

Runs the three checks in the order that costs least: lint first, because almost
every authoring mistake is catchable without a render and finding one afterwards
means paying for the render twice; then a cold render; then freezediff. Stops at
the first hard failure. Exits non-zero if anything failed or moved.

The report is deliberately short, and ends with the only thing that decides what
to do next -- which figures changed. "Read every figure after every render" is
how a verification pass gets expensive; "read the one that moved" is the same
rigour for a fraction of the cost, and freezediff hashes the PNGs to tell them
apart.

    lint       0 problems
    render     ok (7 pages)
    values     2 page(s) changed, 1 figure(s) changed
    figures to read:
      05-why-has-the-aspect-ratio-been-driven-so-low  fig-ar-output-1.png

`--no-render` is the fast path while drafting: lint alone, no two-minute render.
`--ref` is passed through to freezediff.

`--all` discards every freeze and re-executes the whole notebook. By default only
what an edit can have invalidated is discarded, which is what keeps adding one
entry from costing twenty minutes -- but that scoping reads the call graph, and a
page it wrongly spares is a page freezediff never gets to compare. So `--all` is
the release gate: fast path while authoring, exhaustive run before committing.

A checker like lint.py and freezediff.py -- authoring-time, reads the notebook,
writes nothing into the rendered site -- so it lives in the skill and is not
vendored. It imports the other two rather than reimplementing either.
"""
import ast
import contextlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys

import freezediff
import lint

# `_budget.py` used to be here: a chapter-wide solve budget that binds truncates
# a solve, so editing it could move a frozen number exactly as editing the model
# can. That concern dissolved when budgets moved to the ENTRY. An entry's
# SOLVE_BUDGET now lives in the entry's own cells, and Quarto keys that page's
# freeze on its own content -- so changing it already invalidates exactly the one
# page it can affect, with no chapter-wide rule needed to arrange it.
MODEL_FILES = ("_model.py", "_analysis.py", "_model.qmd")


def _run(fn, argv):
    """Call another checker's main(), capturing what it printed."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(argv)
    return code, buf.getvalue()


def _dirty(root):
    """Paths git reports as modified, relative to the repo."""
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None                      # no git: cannot scope, so do not try
    if out.returncode:
        return None
    return {line[3:].strip().strip('"') for line in out.stdout.splitlines()}


def _top_level(text):
    """{name: normalised source} for top-level defs and assignments, or None."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = ast.dump(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = ast.dump(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = ast.dump(node.value) if node.value else ""
    return out


def _changed_symbols(root, rel):
    """
    (changed function names, changed constant names) for one edited model file.

    Compares ASTs rather than diff hunks, so reformatting is not a change and a
    renamed symbol shows up as both a removal and an addition. Returns None when
    anything is uncertain -- no git history, a syntax error, a file that never
    parsed -- because the caller must then fall back to discarding the whole
    chapter. Uncertainty is allowed to cost time; it is never allowed to serve a
    stale number.
    """
    path = root / rel
    try:
        old = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=root,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if old.returncode:
        return None                      # new file, or not in HEAD
    before, after = _top_level(old.stdout), _top_level(path.read_text())
    if before is None or after is None:
        return None

    names = set(before) | set(after)
    changed = {n for n in names if before.get(n) != after.get(n)}
    # A function is callable and traceable; anything else is a constant that
    # could be read anywhere in the chapter, and the call graph will not show it.
    is_func = {n for n in changed
               if str(after.get(n, "")).startswith(("FunctionDef", "AsyncFunctionDef"))
               or str(before.get(n, "")).startswith(("FunctionDef", "AsyncFunctionDef"))}
    return is_func, changed - is_func


def _closure(defs, seed):
    """Every chapter-defined name reachable from `seed` through the call graph."""
    seen, queue = set(), list(seed)
    while queue:
        name = queue.pop()
        if name in seen or name not in defs:
            continue
        seen.add(name)
        queue.extend(defs[name][1])
    return seen


CITE = re.compile(r"""cite\(\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']""")


def _citations(root, chapters):
    """
    [(citing page, cited chapter, cited entry)] across the notebook.

    Read from source, not from a registry: a citation is a call in a cell, and
    anything that had to be declared somewhere else could be declared wrongly.
    """
    out = []
    for c in chapters:
        for page in sorted((root / "chapters" / c).glob("*.qmd")):
            if page.name.startswith("_"):
                continue
            for cited_c, cited_e in CITE.findall(page.read_text()):
                out.append((page, cited_c, cited_e))
    return out


def _freeze_targets(root, chapters, force_all):
    """
    What to discard before rendering: (whole chapters, individual pages, note).

    Freeze tracks the page and not its includes, so an edit to a chapter's model
    really can leave every entry in it serving numbers the model no longer
    produces -- that is why anything is discarded at all. But discarding the
    WHOLE chapter for any model edit is merely the conservative choice, not the
    correct one: adding a helper that only the new entry calls cannot move a
    single existing value, and paying ~1175 s to re-derive that is how adding a
    0.1 s entry came to cost twenty minutes.

    So: constants and unparseable edits take the chapter, tracked function edits
    take only the pages that can reach them, and everything else takes nothing.
    """
    if force_all:
        return list(chapters), [], "all (--all)"
    dirty = _dirty(root)
    if dirty is None:
        return list(chapters), [], "all (no git to compare against)"
    if any(p.endswith("_notebook.py") for p in dirty):
        return list(chapters), [], "all (_notebook.py is exec'd into every page)"

    whole, pages, why = [], [], []
    for c in chapters:
        edited = [n for n in MODEL_FILES
                  if any(p.endswith(f"chapters/{c}/{n}") for p in dirty)]
        if not edited:
            continue
        funcs, consts = set(), set()
        for name in edited:
            if name.endswith(".qmd"):    # the shim: not analysable, assume broad
                consts.add(name)
                continue
            result = _changed_symbols(root, f"chapters/{c}/{name}")
            if result is None:
                consts.add(name)
                continue
            funcs |= result[0]
            consts |= result[1]
        if consts:
            whole.append(c)
            why.append(f"{c}: {', '.join(sorted(consts)[:3])} — read anywhere")
            continue

        # The chapter INDEX renders `_model.py` and `_analysis.py` verbatim
        # (rule 30), so ANY edit to either moves what it publishes -- including
        # a comment-only one, which changes no symbol and therefore invalidates
        # no entry. Without this, adding the fork header rule 31 demands left
        # `check` discarding nothing, the index freeze older than its own
        # source, and rule 12 reporting a stale freeze that only a full `--all`
        # re-prove could clear -- re-solving a whole chapter to republish a
        # comment. `write.py::_refresh_index_freeze` has always done this for
        # its own runs; `check` did not. Below the `consts` branch, which
        # already takes the whole chapter and the index with it.
        if (root / "chapters" / c / "index.qmd").exists():
            pages.append(f"{c}/index")
        defs = lint._defs_of(root / "chapters" / c)
        hit = []
        for page in sorted((root / "chapters" / c).glob("*.qmd")):
            if page.name.startswith("_"):
                continue
            reach = _closure(defs, lint.entry_calls(page.read_text()))
            if reach & funcs:
                hit.append(f"{c}/{page.stem}")
        pages += hit
        why.append(f"{c}: index, and {len(hit)} page(s) reach "
                   f"{', '.join(sorted(funcs)[:3]) or 'no changed symbol'}")

    # CITATIONS, the one cross-chapter edge in the graph. A page that quotes
    # another entry's hero value holds a copy of it in its own freeze, so
    # re-rendering the cited entry without re-rendering the citing one leaves
    # the quote silently stale -- which is transcription with extra steps, the
    # exact failure `cite()` exists to end. Everything above this line is
    # intra-chapter; this is deliberately the only exception, and it is computed
    # from the calls themselves rather than from anything anyone maintains.
    #
    # Chapter granularity on purpose: an entry is discarded when the chapter it
    # cites is touched at all, without asking whether the specific cited entry
    # moved. Over-discarding costs a render; under-discarding publishes a wrong
    # number.
    touched = set(whole) | {p.split("/")[0] for p in pages}
    cited_pages = []
    for page, cited_c, _ in _citations(root, chapters):
        stem = f"{page.parent.name}/{page.stem}"
        if (cited_c in touched and page.parent.name not in whole
                and stem not in pages and stem not in cited_pages):
            cited_pages.append(stem)
    if cited_pages:
        pages += cited_pages
        why.append(f"{len(cited_pages)} page(s) cite a chapter being re-rendered")

    return whole, pages, "; ".join(why) if why else "nothing stale"


# Where a freeze goes while the render that replaces it is still in doubt.
# Under `_scratch/`, which is gitignored, so a half-finished check cannot turn
# into a commit.
FREEZE_STASH = pathlib.Path("_scratch") / "freeze-stash"


def _stash(root, rels):
    """
    Move the freezes aside rather than deleting them.

    Deleting first and rebuilding second is only safe if the rebuild always
    happens. It does not: a render that fails leaves the chapter with no freeze
    at all, and the caller may stop before it ever renders again -- which is how
    one chapter lost its index freeze, invisibly, and stayed that way through
    several commits. The deletion lives only in the working tree, so `git
    restore` was the recovery, and nothing said so.

    A manifest goes in beside the moved trees so `_unstash` works after a crash
    as well as after a caught failure. A list held in memory would not survive
    the kill that most needs it.
    """
    stash = root / FREEZE_STASH
    shutil.rmtree(stash, ignore_errors=True)
    moved = []
    for rel in rels:
        src = root / "_freeze" / "chapters" / rel
        if not src.is_dir():
            continue
        dst = stash / "trees" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append(str(rel))
    if moved:
        (stash / "manifest.json").write_text(json.dumps(moved, indent=1))
    return moved


def _discard(root):
    """
    Throw the stash away. Only ever after a render that SUCCEEDED.

    Not `_unstash`: a successful render rebuilds every page that should exist,
    so anything still in the stash is a page that should NOT -- an entry renamed
    or removed since. Merging it back would resurrect the freeze of a page that
    is gone, and hand freezediff something to compare that has no source.
    """
    shutil.rmtree(root / FREEZE_STASH, ignore_errors=True)


def _unstash(root):
    """
    Put back whatever `_stash` moved, and return what was restored.

    Merged FILE BY FILE, not tree by tree. Quarto writes a freeze only once its
    page has executed, so anything already present is a real result and the
    stashed copy is the older of the two -- but a failed render typically
    rebuilds SOME of a chapter's pages and not others. Comparing whole trees,
    one rebuilt page made the chapter directory exist and every page the render
    never reached was left unrestored: the original bug, reintroduced one level
    down. Found by testing exactly that case.
    """
    stash = root / FREEZE_STASH
    if not (stash / "manifest.json").exists():
        shutil.rmtree(stash, ignore_errors=True)
        return []
    trees = stash / "trees"
    back = set()
    for src in sorted(trees.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(trees)
        dst = root / "_freeze" / "chapters" / rel
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        # The page is the directory holding execute-results/ or figure-html/,
        # which is what a reader counts -- not the files inside it.
        back.add(str(rel.parent.parent))
    shutil.rmtree(stash, ignore_errors=True)
    return sorted(back)


def main(argv):
    if not argv:
        print(__doc__.strip().split("\n\n")[1].strip())
        return 2

    render = "--no-render" not in argv
    force_all = "--all" in argv
    argv = [a for a in argv if a not in ("--no-render", "--all")]
    ref_args = []
    if "--ref" in argv:
        i = argv.index("--ref")
        if i + 1 >= len(argv):
            print("  --ref needs a git ref")
            return 2
        ref_args = ["--ref", argv[i + 1]]
        argv = argv[:i] + argv[i + 2:]

    root = pathlib.Path(argv[0]).resolve()
    if not (root / "chapters").is_dir():
        print(f"  {root} is not a notebook (no chapters/ directory)")
        return 2
    chapters = argv[1:] or lint.chapters_of(root)

    # A stash left by a previous run means that run was KILLED between moving
    # the freezes and rebuilding them -- SIGKILL, a closed lid, a machine that
    # slept. Neither the failure branch nor the `except` above got to run, so
    # recovery has to happen the next time anyone looks. Before the lint, since
    # rule 12 reads the freeze.
    recovered = _unstash(root)
    if recovered:
        print(f"freeze     restored {len(recovered)} tree(s) left by an "
              f"interrupted check")

    # 1. Lint, cheaply, before spending a render on an entry that will fail it.
    #
    # Rule 12 ("the freeze is older than the model") is excluded from THIS pass
    # when a render is coming: it is a complaint that the render about to happen
    # is exactly the fix, so gating the render on it deadlocks. The post-render
    # lint below runs the full set, so nothing is skipped, only reordered.
    code, out = _run(lint.main, [str(root)] + chapters)
    problems = [l for l in out.splitlines()
                if l.startswith("  ") and "(warning)" not in l
                and (not render or "but the freeze is not" not in l)]
    if problems:
        print("\n".join(problems))
        print("\nlint       FAILED — fix these before rendering")
        return 1
    print("lint       0 problems" if not code else
          "lint       0 authoring problems (freeze is stale; rendering next)")

    if not render:
        print("render     skipped (--no-render)")
        return 0 if not code else 1

    # 2. Render. Discard the freeze for whatever the edit can actually have
    # invalidated -- see _freeze_targets() for why that is not "everything".
    # Quarto's own freeze then re-executes the pages whose .qmd changed, which
    # is the new or edited entry, so nothing here needs to handle that case.
    whole, pages, why = _freeze_targets(root, chapters, force_all)
    _stash(root, list(whole) + list(pages))
    served = [c for c in chapters if c not in whole]
    print(f"freeze     set aside {len(whole)} chapter(s), {len(pages)} page(s)"
          f"; {len(served)} chapter(s) served from cache — {why}")
    shutil.rmtree(root / ".quarto", ignore_errors=True)
    try:
        r = lint.render_quarto(root, root)
    except BaseException:
        # Including KeyboardInterrupt: a Ctrl-C during a two-minute render is
        # the likeliest way to be left with nothing, and the least likely
        # moment to remember that the freeze was moved.
        back = _unstash(root)
        print(f"freeze     restored {len(back)} tree(s) — render interrupted")
        raise
    blob = r.stdout + r.stderr
    if r.returncode:
        # Show the traceback and the cell it came from, not Quarto's chatter.
        keep = [l for l in blob.splitlines()
                if re.search(r"error|Error|ERROR|Traceback|assert", l)]
        print("\n".join(keep[:30]) or blob[-2000:])
        # Put back what the failed render did not rebuild. A page it DID reach
        # keeps its new freeze; the rest go back to what they were, so a failed
        # check leaves the notebook exactly as it found it.
        back = _unstash(root)
        if back:
            print(f"freeze     restored {len(back)} tree(s) the render "
                  f"did not rebuild")
        print("\nrender     FAILED")
        return 1
    _discard(root)          # the render rebuilt everything that should exist

    # SECOND PASS, for citations only. `cite()` reads the cited page's freeze,
    # and this run discarded the freezes it was about to rebuild -- so a citing
    # page rendered above may have quoted the COMMITTED value while the page it
    # quotes was being rebuilt beside it. Quarto renders in an order nobody
    # controls, so that is not a thing to schedule around; it is a thing to
    # redo once everything cited is current again.
    #
    # Cheap: only the citing pages are discarded, everything else is served from
    # the freeze just written. Skipped entirely when the notebook cites nothing,
    # which is every notebook until it does.
    citing = sorted({f"{page.parent.name}/{page.stem}"
                     for page, _, _ in _citations(root, chapters)})
    if citing:
        print(f"cite       re-rendering {len(citing)} citing page(s) now that "
              f"what they quote is current")
        _stash(root, citing)
        try:
            r2 = lint.render_quarto(root, root)
        except BaseException:
            _unstash(root)
            raise
        if r2.returncode:
            blob2 = r2.stdout + r2.stderr
            keep = [l for l in blob2.splitlines()
                    if re.search(r"error|Error|ERROR|Traceback|assert", l)]
            print("\n".join(keep[:30]) or blob2[-2000:])
            _unstash(root)
            print("\nrender     FAILED on the citation pass")
            return 1
        _discard(root)
    # Count what was actually executed, not Quarto's chatter -- it prints
    # "Output created:" once for the whole project, not once per page.
    pages = sum(len(list((root / "_freeze" / "chapters" / c).glob(
        "*/execute-results/html.json"))) for c in chapters
        if (root / "_freeze" / "chapters" / c).exists())
    print(f"render     ok ({pages} pages)")

    # 2b. The full lint, now that the freeze is current -- rule 12 among them.
    code, out = _run(lint.main, [str(root)] + chapters)
    if code:
        print(out.strip())
        print("\nlint       FAILED after render")
        return 1

    # 3. What moved.
    code, out = _run(freezediff.main, [str(root)] + chapters + ref_args)
    body, _, summary = out.rstrip().rpartition("\n")
    print(f"values     {summary.strip()}")
    if body.strip():
        print(body.rstrip())
    return 1 if code else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
