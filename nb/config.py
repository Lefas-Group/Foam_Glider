"""
Paths, model settings and budgets. Imported first by everything else, because
importing it is what puts `nb/vendor` on the path.

The vendored modules (`lint`, `check`, `freezediff`, `library_explorer`) use
same-directory imports of each other, so they have to be reachable as top-level
names rather than as `nb.vendor.lint`.
"""

import os
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
# Flash was then tried as the default and failed a FOURTH time, on the first
# real question put to it: 40 turns, no proposal, nothing written. It was never
# short of budget -- 24 probes in three minutes using 74 s of a 300 s pool --
# and the physics was sound; it derived the foam CG and rearranged the ballast
# equation correctly. It simply never committed to an answer, interleaving
# read_reference, api_search and bash exactly as the runs above did.
#
# So the measurement stands, now on four runs and a rewritten prefix: flash
# probes well and does not decide. The metric that would reopen it is
# first-pass lint violations per entry, which metrics.py records per run
# alongside the model that served it; pro sits at 0 across its last six.
#
# $NB_MODEL overrides it for one run, in either direction -- the quota is per
# MODEL per day (250), so a day spent on one leaves the other's bucket whole.
MODEL = os.environ.get("NB_MODEL", "gemini-3.1-pro-preview")

# MINIMAL is in the enum but 400s on both candidate models. LOW/MEDIUM/HIGH are
# the usable range, and this is the main cost lever.
THINKING_LEVEL = "HIGH"

# Thought SUMMARIES, returned as `thought` parts inside the model turn. ON, and
# no flag: `loop.py` SHOWS them and then drops them before appending the turn, so
# they never re-enter the conversation and cost nothing but screen space -- which
# they do not take either, since telemetry no longer reaches the terminal.
#
# They were off for a while because appending the turn whole meant the model read
# its own summaries back, and those confabulate on short turns: one decided that
# `lint` meant "micro-debris, possibly from instrumentation, lab coats or even
# the atmosphere". Dropping them is safe because Google's documentation puts the
# enforced signature "only to the first functionCall part" -- see `_spoken()`.
#
# The thinking happens either way and is billed either way: measured 398 vs 342
# thought tokens with this off and on, which is variance, not a surcharge.
INCLUDE_THOUGHTS = True

MAX_TURNS = 40          # per agent loop
MAX_CONSULTS = 3        # open-ended guidance can loop; a Specified input cannot
MAX_LINT_ATTEMPTS = 3   # write -> lint -> write
MAX_VERIFY_ATTEMPTS = 2  # write -> render -> verify -> write
# write -> render -> write, on a page that does not BUILD. Its own budget, not a
# slice of the verify one: the page has to render before verify has anything to
# read, so charging a build error to verify leaves the entry a round short of
# fixing whatever verify then finds. One is enough for the failure this exists
# for -- a traceback naming the line -- and a second usually means the model is
# guessing rather than reading it.
MAX_RENDER_FIXES = 1
CACHE_TTL = "3600s"

# Every handler truncates its own output. Tracebacks keep the tail, listings the
# head; the cap is the same either way.
TRUNCATE = 8000

# ---------------------------------------------------------------- budgets

# `_notebook.py` runs its own watchdog that os._exit(9)s a probe at PROBE_BUDGET
# (300 s, or the per-probe grant in $NB_PROBE_BUDGET). Ours sits above it
# so that watchdog fires first: it knows why it killed the probe and says so,
# where a subprocess timeout only knows that time ran out.
PROBE_WALL_CLOCK = 960.0

# Total probe wall clock one phase may spend, seconds. The AGENT divides it: a
# cheap probe asks for twenty seconds, a multistart for four hundred, and a
# probe that asks for more than remains gets what remains rather than a refusal.
#
# The watchdog in `_notebook.py` polls every 15 s, so enforcement is coarse to
# about that -- a 5 s grant kills at 15 s, measured.
#
# 120 s, down from 900. Measured across every run in nb-metrics.db, a question
# has consumed 15 s, 32 s, 74 s and 120 s of pool -- so this sits ON the worst
# observed rather than above it, deliberately. The failure it now catches is the
# one that actually happened: a run that has lost the plot probes cheaply and
# endlessly (24 probes, 74 s, no proposal), which a generous pool cannot
# distinguish from progress. A question that genuinely needs more is asked for
# at the prompt, where a human sees the number.
#
# None disables it.
PROBE_POOL = 120.0

# Deadline on ONE API request, milliseconds. Without it a silently dead socket
# blocks read(2) forever: a run sat in `_ssl__SSLSocket_read` for 4h14m after a
# render, and the six retries in `client.py` never fired because a dead
# connection raises nothing for them to catch.
#
# 300 s is ~5x the worst latency measured over 16 completed runs (13.3 s per
# turn median, 54.4 s at the worst run average), so it leaves room for one slow
# turn while bounding the dead-socket case at 6 attempts rather than forever.
API_TIMEOUT_MS = 300_000

# No DEFAULT_ENTRY_CEILING here. There was one, and nothing read it: the prompt
# default and lint's fallback both come from the NOTEBOOK's own `_notebook.py`
# via `lint._defaults`, which is right -- a notebook has to render without `nb`
# installed, so the number it renders under belongs to it. A second copy here
# could only ever disagree, and did: this one said 20 s while the notebook said
# 200 s, and the notebook won every time.


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
