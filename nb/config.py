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

# Thought SUMMARIES, returned as `thought` parts inside the model turn. OFF by
# default; `--thoughts` turns them on for a run you are debugging.
#
# They were on, and reading two runs' logs said no. On a turn whose real work is
# one tool call, the summariser pads ~150 words of filler, and with little real
# reasoning to summarise it confabulates: one turn decided lint meant "micro-
# debris, possibly from instrumentation, lab coats or even the atmosphere", and
# several summarised the act of summarising rather than the work.
#
# That would be tolerable if it stayed on the terminal. It does not: thought
# parts arrive INSIDE candidates[0].content, which `loop.py` appends whole, so
# every later turn re-sends them and the model reads its own nonsense as context.
#
# Anthropic avoids this structurally -- their API strips prior-turn thinking and
# excludes it from context accounting, and Claude Code shows it as ephemeral
# terminal UI on top of that. Gemini has no equivalent, and pruning `contents`
# ourselves breaks the implicit-caching byte prefix, which costs more than it
# saves. So it is all-or-nothing, and off is the better default: a run is
# reproducible from proposal.json, so re-running with --thoughts is cheap.
INCLUDE_THOUGHTS = False

MAX_TURNS = 40          # per agent loop
MAX_CONSULTS = 3        # open-ended guidance can loop; a Specified input cannot
MAX_LINT_ATTEMPTS = 3   # write -> lint -> write
MAX_VERIFY_ATTEMPTS = 2  # write -> render -> verify -> write
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

# Total probe wall clock one phase may spend, seconds. The AGENT divides it: a
# cheap probe asks for twenty seconds, a multistart for four hundred, and a
# probe that asks for more than remains gets what remains rather than a refusal.
#
# The watchdog in `_notebook.py` polls every 15 s, so enforcement is coarse to
# about that -- a 5 s grant kills at 15 s, measured. That is fine for what this
# is for: the win is a cheap probe costing 15 s instead of the flat 300 s it
# used to be allowed, not second-level precision.
#
# This is the first bound on a run's compute that actually exists. Each probe was
# capped at PROBE_BUDGET, but nothing capped how MANY probes a run could take --
# ten legitimate ones is fifty minutes, and only MAX_TURNS would have stopped it.
#
# Sized generously: the point is to catch a run that has lost the plot, not to
# ration an honest one. None disables it.
PROBE_POOL = 900.0

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

    def claimable_stub(self):
        """
        A scaffolded chapter nothing has been written into yet, or None.

        `nb new` must create a chapter -- `_quarto.yml`'s `auto: "chapters"` dies
        on an empty `chapters/` -- and that chapter's `_model.py` is empty, so
        the first `ask` correctly refuses to build on it and routes
        `new_chapter`. Without this the notebook ends up with a dead 01 beside a
        real 02. The stub is a slot, not a corpse: the first real chapter takes
        it over, keeping its number.

        Emptiness is judged by `module_summary`, the same test whose output the
        model is shown, so the two can never disagree about what empty means.

        An empty `_model.py` is NOT sufficient on its own -- a chapter that has
        just been created and described has one too, and would otherwise be
        clobbered by the next chapter created after it. The index still carrying
        the scaffold's placeholder is what says nobody has claimed this yet.
        """
        from .prefix import module_summary
        from .tools.scaffold import PLACEHOLDER
        for name in self.chapters():
            d = self.chapters_dir / name
            try:
                if any(d.glob("[0-9]*.qmd")):
                    continue
                if any(module_summary(d / "_model.py")):
                    continue
                index = (d / "index.qmd").read_text()
            except OSError:
                # Renamed or removed while being inspected -- another run
                # claiming it, which is exactly the answer we wanted.
                continue
            if PLACEHOLDER not in index:
                continue
            return name
        return None

    def entries(self, chapter):
        """Entry .qmd files, date-prefixed, in chronological order."""
        import lint
        d = self.chapters_dir / chapter
        return sorted(p for p in d.glob("*.qmd") if lint.ENTRY_FILE.match(p.name))

    def __repr__(self):
        return f"Notebook({self.root.name})"
