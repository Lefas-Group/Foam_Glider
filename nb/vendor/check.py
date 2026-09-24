"""
Lint, render and diff a notebook in one call. One copy, shared by every notebook.

    uv run python nb/vendor/check.py <notebook-dir> [chapter ...] [--no-render] [--all] [--ref REF]

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
writes nothing into the rendered site -- so it lives in `nb/vendor/` and is not
vendored. It imports the other two rather than reimplementing either.
"""
import ast
import contextlib
import fcntl
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import freezediff
import lint

# `_budget.py` used to be here: a chapter-wide solve budget that binds truncates
# a solve, so editing it could move a frozen number exactly as editing the model
# can. That concern dissolved when budgets moved to the ENTRY. An entry's
# SOLVE_BUDGET now lives in the entry's own cells, and Quarto keys that page's
# freeze on its own content -- so changing it already invalidates exactly the one
# page it can affect, with no chapter-wide rule needed to arrange it.
MODEL_FILES = ("_model.py", "_analysis.py", "_model.qmd")


# The render lock, held from the moment the freezes are moved until `main`
# returns. `nb/locks.py` owns the same file and explains the race:
# `_freeze/site_libs/` belongs to the Quarto project, so two renders on one
# notebook fail four trials out of four.
#
# check.py took NO lock until 2026-09-18, which is worse than an unlocked
# render: this is the one process that MOVES freeze trees aside and puts them
# back, so another agent rendering through that window sees pages appear and
# disappear under it. Observed once and unambiguously: a check running
# 13:22:09-13:25:22 straight through another agent's locked render at 13:24:15,
# which hit the site_libs race the lock exists to prevent and survived only on
# its retry.
#
# Duplicated rather than imported: check.py is vendored beside the notebook and
# runs with no `nb` on the path. Five lines of `fcntl` is the cheaper of the
# two wrongs; the file path is the contract between them.
_LOCK_FH = None


def _take_render_lock(root, timeout=900):
    """
    Block until the notebook's render lock is free, then hold it.

    Proceeds WITHOUT it on timeout, following `nb/locks.py`: a check refused
    outright leaves the caller with no verdict, while a check that races loses
    a render it can retry. Released by `_drop_render_lock` in `main`'s
    `finally`; the kernel dropping it on death is the backstop, and a killed
    check leaves nothing to recover -- it leaves freezes missing, which rule 12
    reports.
    """
    global _LOCK_FH
    # IDEMPOTENT, and that is not cosmetic: `flock` is per open file
    # description, so a second `open` + `LOCK_EX` from THIS process would wait
    # on the fd this process already holds and never be woken. Both call sites
    # below can fire in one run -- a recovery unstash, then the render.
    if _LOCK_FH is not None:
        return True
    path = root / "_scratch" / "render.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    deadline = time.time() + timeout
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() >= deadline:
                print("freeze     proceeding without the render lock — "
                      "timed out waiting for another render")
                fh.close()
                return False
            time.sleep(0.25)
    fh.seek(0)
    fh.truncate()
    fh.write(f"{os.getpid()}\n")
    fh.flush()
    _LOCK_FH = fh          # kept alive on purpose: closing it drops the lock
    return True


def _drop_render_lock():
    """
    Release it at the end of `main`, not at process exit.

    The kernel would do it on exit anyway, and that backstop is what makes a
    killed check safe. But check.py is IMPORTED and called in-process by the
    write phase, which renders under the same lock through `nb/locks.py` -- and
    `flock` blocks a second fd in the same process as readily as another
    process's. Holding to exit would deadlock `nb write` against itself the
    first time anything rendered after a check.
    """
    global _LOCK_FH
    if _LOCK_FH is not None:
        fh, _LOCK_FH = _LOCK_FH, None
        with contextlib.suppress(OSError):
            fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


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
def _drop(root, rels):
    """
    Delete the freezes a render must rebuild, and return what went.

    DELETED, NOT MOVED ASIDE. This used to stash them under `_scratch/` with a
    manifest, and put them back file by file if the render failed -- three
    functions, an on-disk manifest for crash recovery, and a merge that had to
    be per-file because "one rebuilt page made the chapter directory exist and
    every page the render never reached was left unrestored". All of it existed
    because a failed render would otherwise leave a chapter with no freeze,
    INVISIBLY: one chapter lost its index freeze and stayed that way through
    several commits.

    It is not invisible any more. Rule 12 reports a committed page with no
    freeze, which is the same fact the restore was protecting against, said by
    the contract instead of repaired by recovery code. The freezes are also
    COMMITTED, so `git checkout --` recovers them at any point, from any kind
    of death, without a manifest -- the restore was re-implementing git over a
    directory git already tracks.

    So a failed check now leaves the freezes gone, lint says so on the next
    run, and a render or a `git checkout` fixes it. Ninety lines of recovery
    for a path that has never executed, replaced by a rule that cannot be
    skipped.
    """
    gone = []
    for rel in rels:
        d = root / "_freeze" / "chapters" / rel
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            gone.append(str(rel))
    return gone


def main(argv):
    try:
        return _main(argv)
    finally:
        _drop_render_lock()


def _main(argv):
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
    # HELD PAST THE CITATION PASS BELOW: the window that has to be exclusive is
    # the whole time the freeze is not where it belongs, not just the two render
    # calls inside it. Nothing is set aside any more, so there is no recovery
    # pass before it either -- rule 12 is what notices.
    _take_render_lock(root)
    _drop(root, list(whole) + list(pages))
    served = [c for c in chapters if c not in whole]
    print(f"freeze     dropped {len(whole)} chapter(s), {len(pages)} page(s)"
          f"; {len(served)} chapter(s) served from cache — {why}")
    shutil.rmtree(root / ".quarto", ignore_errors=True)
    r = lint.render_quarto(root, root)
    blob = r.stdout + r.stderr
    if r.returncode:
        # Show the traceback and the cell it came from, not Quarto's chatter.
        keep = [l for l in blob.splitlines()
                if re.search(r"error|Error|ERROR|Traceback|assert", l)]
        print("\n".join(keep[:30]) or blob[-2000:])
        print("\nrender     FAILED — any page this render did not reach now "
              "has no freeze.\n           Rule 12 names each of them; a render "
              "or `git checkout -- _freeze`\n           puts them back.")
        return 1

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
        _drop(root, citing)
        r2 = lint.render_quarto(root, root)
        if r2.returncode:
            blob2 = r2.stdout + r2.stderr
            keep = [l for l in blob2.splitlines()
                    if re.search(r"error|Error|ERROR|Traceback|assert", l)]
            print("\n".join(keep[:30]) or blob2[-2000:])
            print("\nrender     FAILED on the citation pass — rule 12 names "
                  "any page left without a freeze")
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
