"""
Paths, model settings and budgets. Imported early by everything else, for the
constants below.

IT USED TO PUT `nb/vendor` ON sys.path. Four modules lived there -- `lint`,
`check`, `freezediff`, `library_explorer` -- importing each other by bare name,
and the insert was what made that work. None of them was ever vendored anywhere:
they sat in `vendor/` because they had been lifted out of the design-notebook
skill, where they were loose files in a project directory.

They are ordinary `nb` modules now and import each other relatively, so the path
mutation is gone with them. It was not free: `sys.path.insert` at import time
means any `import lint` ANYWHERE in the process resolves to this one, including
in code that has nothing to do with `nb`.

AND THERE IS NO `vendored/` EITHER. One file genuinely is copied into each
notebook -- `_notebook.py`, which Quarto execs at render time, so it has to be a
file inside the Quarto project and a notebook has to render without `nb`
installed. But "vendored" was never what that made it: `nb new` writes it
alongside `_model.qmd`, `_quarto.yml` and five others, and it lives with them in
`scaffold/`. Rule 11 still polices the copy; it just polices it against the seed
it was scaffolded from rather than against a library.
"""

import os
import pathlib

NB = pathlib.Path(__file__).resolve().parent
REFERENCES = NB / "references"
SCAFFOLD = NB / "scaffold"
SYSTEM_INSTRUCTION = NB / "system_instruction.md"

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
# SWITCHED TO FLASH ON 2026-09-29, by decision rather than by measurement: the
# four runs above stand and have not been repeated. Left in place because a
# comment that contradicts the line under it is the exact failure `nb eval`
# exists to prevent -- a model swap was once decided off a stale comment here
# and reversed the same morning.
#
# What would settle it, in the columns `nb eval` already prints: pro sits at 34
# runs, 27 committed, 0.07 first-pass lint violations per entry. Flash has to
# COMMIT to be compared at all -- its failure was never knowledge or budget, it
# was 25 to 40 turns of probing without ever proposing an answer. Watch the ok
# count first; first-pass violations only mean something once entries exist.
#
# $NB_MODEL overrides it for one run, in either direction -- the quota is per
# MODEL per day (250), so a day spent on one leaves the other's bucket whole.
# `NB_MODEL=gemini-3.1-pro-preview` is the way back.
MODEL = os.environ.get("NB_MODEL", "gemini-3.8-flash")

# THE COORDINATOR'S MODEL, deliberately not `MODEL`. The daily quota is per
# model, so a coordinator on pro and runs on flash draw on two buckets of 250
# rather than one -- and a programme spends far more turns running than
# coordinating, so putting them on one bucket would let a busy afternoon of runs
# starve the thing that decides what to run next.
#
# Pro rather than flash because the coordinator's job is the one flash was bad
# at: not knowledge or budget, but deciding. Its recorded failure was 25 to 40
# turns of probing without ever proposing an answer, and choosing the next
# question is that same act with nothing else to hide behind.
COORD_MODEL = os.environ.get("NB_COORD_MODEL", "gemini-3.1-pro-preview")

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

# Raised from 40 once `stuck.Detector` existed. At 40 the cap was doing
# detection work it is bad at -- a run that wedged at turn 10 burned thirty more
# before anything stopped it -- so it had to stay tight, which also meant a
# genuinely hard entry could run out of room. With stuck runs caught at ~8
# barren turns, the cap goes back to being what it is for: a bound on spend, and
# a guarantee that the process ends whatever else fails.
#
# `outcome = max_turns` is therefore now a DIAGNOSTIC, not a routine ending. It
# means the run spent its whole budget and the detector never fired: either a
# genuinely hard entry or a blind spot in the heuristic, and both are worth
# opening. `python -m nb eval <notebook>` lists outcomes by run.
#
# 60 -> 80 on 2026-09-29, because the diagnostic fired on a run that was not
# stuck: flash averages 50.6 turns to a commit against pro's 28.0, and one run
# hit the cap during its CLOSING LINT with the entry already written -- a 53 s
# resume recovered it whole. A cap that ends a run which has done all the work
# is measuring the model's turn appetite, not bounding spend. Pro's runs are
# nowhere near either number, so this costs them nothing.
#
# $NB_MAX_TURNS overrides it for one run, the way $NB_MODEL does above: a model
# whose appetite differs again should not need a commit to find out.
MAX_TURNS = int(os.environ.get("NB_MAX_TURNS", "80"))   # per agent loop
MAX_LINT_ATTEMPTS = 3   # write -> lint -> write
# write -> render -> write, on a page that does not BUILD. It used to be
# deliberately separate from the verify budget, so that a build error could not
# eat a round the prose check needed. Verify is gone; this is not, because lint
# has passed by the time it runs and nothing else notices a page that fails to
# execute.
#
# 2, up from 1. The argument for 1 was that a traceback naming the line takes
# one turn to fix and a second attempt means the model is guessing -- true of a
# traceback, and the fault it missed is the OTHER kind. A render can also fail
# for a reason the entry did not cause: exit 124, killed on a deadline sized as
# if the freeze would spare its pages, which a TARGETED render never does. Two
# runs died that way on 2026-09-18, one of them ending `verify_failed` having
# never verified anything. `build.render.will_execute` removes that cause; this makes
# the next one survivable rather than terminal, at the price of one extra turn
# on the rare genuine guess.
MAX_RENDER_FIXES = 2

# Every handler truncates its own output. Tracebacks keep the tail, listings the
# head; the cap is the same either way.
TRUNCATE = 8000

# ---------------------------------------------------------------- budgets

# No PROBE_WALL_CLOCK here. There was one -- 960 s -- and nothing read it: the
# probe deadline comes from `budgets.probe_wall_clock()`, which is the per-probe
# grant and nothing else. `_dead_config` did not catch
# it because the only occurrence of the name in the tree was inside a docstring
# in `lint.py`, and that check greps `*.py` as text. Same shape as the
# DEFAULT_ENTRY_CEILING note below, which is the failure it was written for.

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
# via `contract.shared._defaults`, which is right -- a notebook has to render without `nb`
# installed, so the number it renders under belongs to it. A second copy here
# could only ever disagree, and did: this one said 20 s while the notebook said
# 200 s, and the notebook won every time.


def new_run_id():
    """
    Sortable, short, and unique enough: `20260916-145233-a3f2`.

    The TIME is in it, not just the date. A first version used `%Y%m%d-` plus
    four random hex, so two runs on the same day sorted by their random suffix
    and "the most recent run" resolved to whichever happened to sort last --
    which `nb resume` then resumed. Caught by a detached run being answered into
    the wrong directory.
    """
    import datetime
    import secrets
    return (datetime.datetime.now().strftime("%Y%m%d-%H%M%S-")
            + secrets.token_hex(2))


class Notebook:
    """Every path the system needs, derived from the notebook root."""

    def __init__(self, root, run_id=None):
        self.root = pathlib.Path(root).resolve()
        if not (self.root / "chapters").is_dir():
            raise SystemExit(f"{self.root} is not a notebook (no chapters/)")
        self.chapters_dir = self.root / "chapters"
        self.freeze = self.root / "_freeze" / "chapters"
        self.scratch = self.root / "_scratch"
        # PER RUN, because `_scratch/run/` assumed one writer: a second agent
        # overwrote the first's run.json -- its only resume point -- and,
        # worse, its probe script, which is WRITTEN AND THEN EXECUTED. Two
        # agents probing within a second and one runs the other's code,
        # attributing the answer to the wrong question, silently.
        #
        # `run_id=None` resolves to the most recent existing run, so
        # `nb resume` stays one command and a single-agent session never sees
        # an id.
        self.run_id = run_id or self._latest_run() or new_run_id()
        self.run = self.scratch / "runs" / self.run_id
        # freezediff resolves git paths against the notebook's parent.
        self.repo = self.root.parent

    def _latest_run(self):
        """
        The most recently TOUCHED run, by mtime rather than by name.

        Belt and braces with the sortable id above: an id is only as ordered as
        the clock that made it, and a directory copied or restored keeps its
        name while getting a new mtime. What `nb resume` wants is "the run I was
        just in", which is a fact about the filesystem.
        """
        d = self.scratch / "runs"
        if not d.is_dir():
            return None
        runs = [p for p in d.iterdir() if p.is_dir()]
        if not runs:
            return None
        return max(runs, key=lambda p: p.stat().st_mtime).name

    def runs(self):
        """Every run directory, newest first -- what `nb board` enumerates."""
        d = self.scratch / "runs"
        if not d.is_dir():
            return []
        return sorted((p for p in d.iterdir() if p.is_dir()),
                      key=lambda p: p.name, reverse=True)

    @property
    def run_state(self):
        """The live registry: what this run is, and what it is waiting for."""
        return self.run / "run.json"

    @property
    def question_path(self):
        return self.run / "question.json"

    @property
    def answer_path(self):
        return self.run / "answer.json"

    @property
    def kernel_log(self):
        """ipykernel's own stdout/stderr. NOT cell output, which rides iopub."""
        return self.run / "kernel.log"

    @property
    def transcript_path(self):
        return self.run / "transcript.jsonl"

    def chapters(self):
        from .contract.shared import chapters_of
        return chapters_of(self.root)

    def entries(self, chapter):
        """Entry .qmd files, date-prefixed, in chronological order."""
        from .contract.shared import ENTRY_FILE
        d = self.chapters_dir / chapter
        return sorted(p for p in d.glob("*.qmd") if ENTRY_FILE.match(p.name))

    def __repr__(self):
        return f"Notebook({self.root.name})"
