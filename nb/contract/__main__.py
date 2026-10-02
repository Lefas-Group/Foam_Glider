"""
`python -m nb.contract <notebook-dir> [chapter ...]` -- lint, without a run.

A shim, so the command works and `main` stays beside `check` in `__init__`. It
was `python -m nb.lint`, and the guard for it briefly lived in `shared.py`,
where `__name__` is never `"__main__"` -- the command exited silently with
status 0, which reads as a clean notebook.
"""

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
