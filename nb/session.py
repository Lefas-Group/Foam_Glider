"""
What one run accumulates.

Barely persisted. `run.json` carries the four things a crashed run cannot
recompute -- the chapter, the entry stem, what is left of the probe pool and
the granted ceiling -- and everything else lives only here, for the length of
one process. There used to be a `proposal.json` holding fifteen model-authored
fields as well, because the run deliberately ended in the middle and a second
process had to reconstruct what the first had decided. It does not end there
any more, so there is nothing to reconstruct.
"""

from .config import PROBE_POOL


class Session:
    def __init__(self, notebook, question, chapter=None,
                 metrics=None, probe_pool=PROBE_POOL):
        self.notebook = notebook
        self.question = question
        self.chapter = chapter
        self.metrics = metrics
        self.asked = {}          # name -> value, from ask_specified
        # name -> Input, from declare_input. A DICT, so re-declaring a quantity
        # corrects it rather than listing it twice -- which is what happens
        # when a probe revises its own assumption three turns later.
        self.inputs = {}
        # Why `inputs` is legitimately empty, from open_entry. An entry that
        # only reads a model already built has nothing of its own; an empty
        # list with no claim is an omission, and nothing could tell them apart.
        self.inputs_none_because = ""
        # Set by `fork_chapter` and `open_entry`, and read by the post-loop
        # sequence and `run.json`. `chapter_open` used to live here too, gating
        # every write until the chapter was settled; `--chapter` is required
        # now and settles it before the first token, so there is no ordering
        # left to enforce.
        self.chapter_msg = ""
        self.stem = None
        self.entry_path = None
        self.entry_title = ""
        # The chapter digest at the last `lint` call, so a second call over
        # unchanged bytes can say so instead of re-deriving the same answer.
        # Runs spend 2-5 lint calls in 8-16 turns and the transcripts show
        # consecutive ones with no edit between them.
        self._lint_at = None
        # Snapshotted at STARTUP, before the model's first turn, so it is the
        # chapter as it was committed: {filename: {function: source}}. The
        # write guard compares against it on every edit to a shared file, which
        # is the only way to tell an added `_analysis.py` helper from a changed
        # one -- and the difference is a refactor the user has to approve.
        self.before_bodies = {}
        self.siblings = 0
        # Solve seconds the PROBE cost, frozen at open_entry. Measured, never
        # estimated: `aero_report()` prints what the solves actually took, and
        # the number a model was asked for came back as 0.0.
        self.render_cost_s = 0.0
        # What the user agreed the new chapter carries, from `confirm_inherited`.
        # Both halves: `kept` is what may be stated one level up without
        # claiming anyone was asked, `struck` is what this chapter BREAKS --
        # the one part no computation could work out, and the reason the review
        # is a question rather than a lookup.
        self.inherited_kept = []
        self.inherited_struck = []
        # GRANTED AT THE PROMPT, never chosen by the model. Declared here
        # rather than stapled on by whoever built the session: they were read
        # through `getattr(..., None)` in four places, which is how a field
        # comes to be missing on one path and present on another. It was --
        # `allow_refactor` existed only on the resume path, and the merged
        # phase read it on both.
        self.render_ceiling = None
        self.pool_total = None
        # `_model.py` is writable and the chapter will be re-proved before the
        # commit. Set by `nb resume --allow-refactor`, read by the write guard.
        self.allow_refactor = False
        # handle -> (old text, why) for a declare_input that revises an
        # ASSUMPTION the chapter already holds. Assumptions need nobody's
        # approval, but the register has to know which value is in force --
        # without this it reported both and the next run could not tell.
        self.replaced_assumptions = {}
        # name -> (chapter, id) for an ask_specified that CHANGES
        # something the chapter already declares. The write phase turns
        # it into an `overwrites:` entry; without it the answer would be
        # recorded as a new input beside the one it displaced.
        self.replaced = {}
        # function -> one-line reason, from declare_refactor. Read by the
        # refactor gate, which otherwise names a changed function and nothing
        # else -- leaving the user to run `git diff` to judge it.
        self.refactor_notes = {}
        self.solves = 0
        self.solve_seconds = 0.0
        # Renders, and the pages they actually executed. Counted because the
        # cost of a render is the pages, not the call: a chapter target and an
        # entry target are one render each and sixteen pages against one.
        self.renders = 0
        self.pages_rendered = 0
        # Probe wall clock: a pool the agent spends from, not a per-probe cap.
        self.probe_pool = probe_pool
        self.probe_spent = 0.0
        # How many probes have run. Only ever compared against 1: the
        # first-probe notice fires once, and a bracketed block repeated every
        # probe would be the third competing with two that already matter.
        self.probes = 0

    def record_cost(self, solves, seconds):
        self.solves += solves
        self.solve_seconds += seconds

    def take_probe_budget(self, asked):
        """
        Grant `asked` seconds of probe wall clock, or whatever is left.

        Clamped rather than refused, for the same reason a wrong chapter number
        is renumbered rather than rejected: the agent cannot know what is left
        before it asks, and failing a run over a guess is the expensive way to
        say no.
        """
        if not self.probe_pool:
            return None, None
        left = max(0.0, self.probe_pool - self.probe_spent)
        return min(float(asked), left) if asked else left, left

    def record_probe(self, seconds):
        self.probes += 1
        self.probe_spent += seconds

    def record_render(self, pages):
        self.renders += 1
        self.pages_rendered += pages
        if self.metrics is not None:
            self.metrics.set(renders=self.renders,
                             pages_rendered=self.pages_rendered)

    @property
    def probe_left(self):
        if not self.probe_pool:
            return None
        return max(0.0, self.probe_pool - self.probe_spent)

    @staticmethod
    def key(name):
        """
        The name, normalised: case-folded and single-spaced.

        A QUANTITY IS THE SAME QUANTITY WHATEVER ITS CAPITALS. The model asked
        `ask_specified("static margin")`, the user answered, and then
        `declare_input("Static margin", source="asked")` was REFUSED -- "was
        never put through ask_specified" -- because the two were compared as
        raw strings. One wasted turn, and the refusal accused it of inventing
        an ask it had genuinely made, which is the worst kind of wrong message:
        the model reads it, believes it, and cannot see the difference.
        Observed live on 2026-09-24.

        Every comparison between an asked name and a declared one goes through
        here, so there is one answer to "is this the same input" rather than
        one per call site.
        """
        return " ".join(str(name).split()).casefold()

    def record_answer(self, name, value):
        self.asked[name] = value

    def was_asked(self, name):
        """True if this quantity was put through `ask_specified`, any casing."""
        k = self.key(name)
        return any(self.key(n) == k for n in self.asked)
