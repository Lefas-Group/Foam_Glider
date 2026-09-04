"""
Lint, render and diff a notebook in one call. One copy, shared by every notebook.

    uv run python <skill>/check.py <notebook-dir> [chapter ...] [--no-render] [--ref REF]

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

A checker like lint.py and freezediff.py -- authoring-time, reads the notebook,
writes nothing into the rendered site -- so it lives in the skill and is not
vendored. It imports the other two rather than reimplementing either.
"""
import contextlib
import io
import pathlib
import re
import shutil
import subprocess
import sys

import freezediff
import lint


def _run(fn, argv):
    """Call another checker's main(), capturing what it printed."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(argv)
    return code, buf.getvalue()


def main(argv):
    if not argv:
        print(__doc__.strip().split("\n\n")[1].strip())
        return 2

    render = "--no-render" not in argv
    argv = [a for a in argv if a != "--no-render"]
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
                if l.startswith("  ") and (not render
                                           or "but the freeze is not" not in l)]
    if problems:
        print("\n".join(problems))
        print("\nlint       FAILED — fix these before rendering")
        return 1
    print("lint       0 problems" if not code else
          "lint       0 authoring problems (freeze is stale; rendering next)")

    if not render:
        print("render     skipped (--no-render)")
        return 0 if not code else 1

    # 2. Render. The freeze must go first: it tracks the page, not its includes,
    # so a change to _model.py or _analysis.py invalidates nothing and the
    # render would be a cache hit wearing a fresh render's clothes.
    for c in chapters:
        shutil.rmtree(root / "_freeze" / "chapters" / c, ignore_errors=True)
    shutil.rmtree(root / ".quarto", ignore_errors=True)
    r = subprocess.run(["quarto", "render", str(root)],
                       capture_output=True, text=True)
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
