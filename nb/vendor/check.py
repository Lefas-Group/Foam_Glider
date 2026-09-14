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
import pathlib
import re
import shutil
import subprocess
import sys

import freezediff
import lint

# _budget.py is here because it sets the solve budget, and a budget that binds
# changes the answer -- so editing it can move a frozen number exactly as editing
# the model can. It was omitted at first, which would have let a budget change
# leave every page in the chapter serving values the current limits do not
# produce.
MODEL_FILES = ("_model.py", "_analysis.py", "_model.qmd", "_budget.py")

# Of what _budget.py holds, only this can change an answer: a solve budget that
# binds truncates a solve. ENTRY_CEILING is read by the linter alone and
# PROBE_BUDGET_CHAPTER by the scratch watchdog alone, so neither can move a
# rendered number -- and treating the whole file as model-affecting would make
# raising a lint threshold cost a full chapter re-render, which is how a
# correctness rule turns into a reason to avoid the tooling.
BUDGET_RESULT_SYMBOLS = {"SOLVE_BUDGET"}


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
            # In _budget.py, only the solve budget can move a number; the rest is
            # tooling. Everywhere else, any changed constant takes the chapter.
            consts |= (result[1] & BUDGET_RESULT_SYMBOLS if name == "_budget.py"
                       else result[1])
        if consts:
            whole.append(c)
            why.append(f"{c}: {', '.join(sorted(consts)[:3])} — read anywhere")
            continue
        defs = lint._defs_of(root / "chapters" / c)
        hit = []
        for page in sorted((root / "chapters" / c).glob("*.qmd")):
            if page.name.startswith("_"):
                continue
            reach = _closure(defs, lint.entry_calls(page.read_text()))
            if reach & funcs:
                hit.append(f"{c}/{page.stem}")
        pages += hit
        why.append(f"{c}: {len(hit)} page(s) reach {', '.join(sorted(funcs)[:3])}")
    return whole, pages, "; ".join(why) if why else "nothing stale"


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
    for c in whole:
        shutil.rmtree(root / "_freeze" / "chapters" / c, ignore_errors=True)
    for p in pages:
        shutil.rmtree(root / "_freeze" / "chapters" / p, ignore_errors=True)
    served = [c for c in chapters if c not in whole]
    print(f"freeze     discarded {len(whole)} chapter(s), {len(pages)} page(s)"
          f"; {len(served)} chapter(s) served from cache — {why}")
    shutil.rmtree(root / ".quarto", ignore_errors=True)
    r = lint.render_quarto(root, root)
    blob = r.stdout + r.stderr
    if r.returncode:
        # Show the traceback and the cell it came from, not Quarto's chatter.
        keep = [l for l in blob.splitlines()
                if re.search(r"error|Error|ERROR|Traceback|assert", l)]
        print("\n".join(keep[:30]) or blob[-2000:])
        print("\nrender     FAILED")
        return 1
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
