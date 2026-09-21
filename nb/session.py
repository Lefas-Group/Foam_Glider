"""
What one run accumulates.

Not persisted -- `proposal.json` is the only thing that crosses the process
boundary. This exists so the handlers that ask the human, and the handlers that
spend solve seconds, can agree on what has happened so far.
"""

from .config import MAX_CONSULTS, PROBE_POOL


class Session:
    def __init__(self, notebook, question, chapter=None, carry_queue=None,
                 metrics=None, probe_pool=PROBE_POOL):
        self.notebook = notebook
        self.question = question
        self.chapter = chapter
        # Questions still owed from a multi-question ask. Merged into the
        # proposal by `propose` rather than by asking the model to copy them
        # forward: the queue is bookkeeping, not judgement.
        self.carry_queue = list(carry_queue or [])
        self.metrics = metrics
        self.asked = {}          # name -> value, from ask_specified
        # function -> one-line reason, from declare_refactor. Read by the
        # refactor gate, which otherwise names a changed function and nothing
        # else -- leaving the user to run `git diff` to judge it.
        self.refactor_notes = {}
        self.consults = 0
        # Which phase owns this session. Set by `phases.common.setup`, and read
        # by anything whose MESSAGE differs between the two -- the probe pool
        # running out tells the ask phase to propose, and there is no `propose`
        # in the write phase, so saying it there sends the model looking for a
        # tool it does not have. That exact shape has cost this system two runs.
        self.phase = None
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

    def record_answer(self, name, value):
        self.asked[name] = value

    @property
    def consults_left(self):
        return MAX_CONSULTS - self.consults
