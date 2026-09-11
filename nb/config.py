"""
Paths, model settings and budgets. Imported first by everything else, because
importing it is what puts `nb/vendor` on the path.

The vendored modules (`lint`, `check`, `freezediff`, `library_explorer`) use
same-directory imports of each other, so they have to be reachable as top-level
names rather than as `nb.vendor.lint`.
"""

import pathlib
import sys

NB = pathlib.Path(__file__).resolve().parent
VENDOR = NB / "vendor"
REFERENCES = VENDOR / "references"
TEMPLATES = VENDOR / "templates"
SCAFFOLD = NB / "scaffold"
SYSTEM_INSTRUCTION = NB / "system_instruction.md"

if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

# ---------------------------------------------------------------- model

# Measured, not assumed. On the same question, same prefix, same tools:
#
#   gemini-3.8-flash       25+ turns, never proposed, across three runs. It
#                          picked the right chapter, then wandered -- reading
#                          entries, grepping, and using `probe` to walk the
#                          filesystem. A planning failure, not a knowledge one:
#                          more prompt did not fix it.
#   gemini-3.1-pro-preview 2 turns. One probe, then propose.
#
# Flash is a false economy here: the cheap model spent twenty times the turns
# and produced nothing. Re-run the comparison on first-pass lint violations once
# entries are being written -- that is the metric that decides it long-term.
MODEL = "gemini-3.1-pro-preview"

# MINIMAL is in the enum but 400s on both candidate models. LOW/MEDIUM/HIGH are
# the usable range, and this is the main cost lever.
THINKING_LEVEL = "HIGH"

MAX_TURNS = 40          # per agent loop
MAX_CONSULTS = 3        # open-ended guidance can loop; a Specified input cannot
MAX_LINT_ATTEMPTS = 3   # write -> lint -> write
CACHE_TTL = "3600s"

# Every handler truncates its own output. Tracebacks keep the tail, listings the
# head; the cap is the same either way.
TRUNCATE = 8000

# ---------------------------------------------------------------- budgets

# `_notebook.py` runs its own watchdog that os._exit(9)s a probe at PROBE_BUDGET
# (300 s, or PROBE_BUDGET_CHAPTER where a chapter raised it). Ours sits above it
# so that watchdog fires first: it knows why it killed the probe and says so,
# where a subprocess timeout only knows that time ran out.
PROBE_WALL_CLOCK = 960.0

# Documented in `_notebook.py` but never enforced there -- no code reads it.
# Chapters that care declare ENTRY_CEILING in their own `_budget.py`.
DEFAULT_ENTRY_CEILING = 200.0


class Notebook:
    """Every path the system needs, derived from the notebook root."""

    def __init__(self, root):
        self.root = pathlib.Path(root).resolve()
        if not (self.root / "chapters").is_dir():
            raise SystemExit(f"{self.root} is not a notebook (no chapters/)")
        self.chapters_dir = self.root / "chapters"
        self.freeze = self.root / "_freeze" / "chapters"
        self.scratch = self.root / "_scratch"
        self.run = self.scratch / "run"
        # freezediff resolves git paths against the notebook's parent.
        self.repo = self.root.parent

    @property
    def proposal_path(self):
        return self.run / "proposal.json"

    @property
    def transcript_path(self):
        return self.run / "transcript.jsonl"

    def chapters(self):
        import lint
        return lint.chapters_of(self.root)

    def entries(self, chapter):
        """Entry .qmd files, date-prefixed, in chronological order."""
        import lint
        d = self.chapters_dir / chapter
        return sorted(p for p in d.glob("*.qmd") if lint.ENTRY_FILE.match(p.name))

    def __repr__(self):
        return f"Notebook({self.root.name})"
