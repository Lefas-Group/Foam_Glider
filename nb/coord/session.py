"""
What one coordinating session accumulates.

Almost nothing, and deliberately. The programme's state is on disk -- the
mailbox, `coordinator/log.jsonl`, git, the `listened_at` watermark -- because
the coordinator has always been able to be a person, a terminal or an agent,
interchangeably. What lives here is only what is true of THIS loop and would be
wrong to persist.

`reported` is the spin guard. `cli/listen.py` re-reports a standing question on
every call on purpose: a question nothing has answered is outstanding work, and
suppressing it would hide the case ignored longest. For a person at a terminal
that is the correct pressure. For a model in a tool loop it is a tight loop --
`wait` returns instantly, the model has nothing new, it waits again -- so the
agent-side rule is the inverse: having told you about a question once, `wait`
will not block for it again until you have acted on it.

`fetched` is empty in stage 1 and is where the research ledger goes: `source`
may only record a URL that `fetch` returned in this session. Not persisted, and
that is the point -- a page read by a previous run of `nb coordinate` proves
nothing about what this one read.
"""

import pathlib
import time


class Coordination:
    def __init__(self, notebook, direction="", model=None, wanted=""):
        self.notebook = notebook
        # What the user asked for, this session. Recorded to the board before
        # the first `ask` so nothing in the programme predates its reason.
        self.direction = direction
        self.model = model
        # The directory the USER named on the command line. In setup mode
        # there is no notebook yet, but there is already a name, and it is
        # not the model's to choose -- see `tools._new`.
        self.wanted = wanted
        self.started = time.time()
        # Set by the `finish` tool. The loop ends when the model stops calling
        # tools either way; this is how the caller tells a deliberate ending
        # from a model that simply stopped talking.
        self.finished = False
        self.summary = ""
        # run id -> the `asked_at` of the question already put to the model.
        self.reported = {}
        # Runs already reported DEAD. Same spin, different event: `listen.py`
        # re-reports a death on every pass for the same reason it re-reports a
        # question -- it is outstanding work -- so without this `wait` returns
        # instantly for ever on a corpse. Worse than the question case,
        # because a death is cleared by `clean` or `resume` rather than by
        # `answer`, and until those existed the model had no way out at all.
        self.reported_dead = set()
        # Runs this session launched, so `finish` can refuse to walk away from
        # one still in flight. Not read off the board: a run launched by
        # somebody else is not this session's to wait for.
        self.launched = []
        # normalised url -> {"sha256", "bytes", "at"}. Stage 2.
        self.fetched = {}
        self._tmp = None
        # (url, text) recorded before `new` existed. Flushed by `adopt`.
        self.pending_sources = []
        # How many times `new` has failed. A tool that fails the same
        # way twice is a tool the model cannot fix by trying again.
        self.new_failures = 0

    def adopt(self, notebook):
        """
        Take ownership of the notebook `new` just created.

        Anything already fetched moves with it, so a plan sheet pulled down
        before the directory existed does not have to be pulled down again --
        and, more to the point, stays citable: `source` checks the LEDGER, and
        the ledger is keyed on the URL rather than on where the bytes landed.
        """
        import shutil
        old = self._tmp
        self.notebook = notebook
        if old is not None and old.is_dir():
            dest = self.scratch_dir()
            dest.mkdir(parents=True, exist_ok=True)
            for f in old.iterdir():
                shutil.move(str(f), dest / f.name)
            shutil.rmtree(old, ignore_errors=True)
            self._tmp = None
        # WHAT WAS SOURCED BEFORE THERE WAS ANYWHERE TO PUT IT. The research
        # that fills the brief necessarily precedes the `new` that creates the
        # directory `SOURCES.txt` lives in, so `source` buffers and this is
        # where the buffer lands.
        if self.pending_sources:
            from . import research
            research.write_sources(notebook, self.pending_sources)
            self.pending_sources = []
        # How many times `new` has failed. A tool that fails the same
        # way twice is a tool the model cannot fix by trying again.
        self.new_failures = 0
        # THE DIRECTION, RECORDED THE MOMENT THERE IS SOMEWHERE TO RECORD IT.
        # Observed live: setting an aircraft up, the model's first call was
        # `direction` -- correctly, the doctrine says to record it before
        # anything else -- and it was refused, because the log lives inside a
        # notebook that `new` had not yet created. It then got on with the
        # research and never came back to it, so the programme would have run
        # with nothing pinned above it on the board.
        #
        # The session has held the user's words since launch, so nothing needs
        # asking: write them here. A later `direction` call still works and is
        # how a PIVOT is marked.
        from ..process import coordinator
        if self.direction and not coordinator.current_direction(notebook):
            coordinator.direction(notebook, self.direction)
        return notebook

    def seen(self, run_id, asked_at):
        """True if this exact question has already been put to the model."""
        return self.reported.get(run_id) == asked_at

    def mark(self, run_id, asked_at):
        self.reported[run_id] = asked_at

    def acted(self, run_id):
        """
        Forget a run's question, so the next one on it blocks normally again.

        Called on `answer`, `stop`, `resume` and `clean` -- the four things
        `listen.py` names as ending the pressure a standing question applies.
        """
        self.reported.pop(run_id, None)
        self.reported_dead.discard(run_id)

    def scratch_dir(self):
        """
        Where `fetch` puts what it pulls down, for this session only.

        UNDER THE NOTEBOOK once there is one, so a plan sheet sits beside the
        aircraft it describes and `nb clean` territory covers it. Before `new`
        has run there is no notebook, so it falls back to a temp directory --
        which is the whole reason setting an aircraft up and coordinating it
        are one command: the research that fills `--spec` has to happen before
        the directory `--spec` goes into exists.
        """
        if self.notebook is not None:
            return self.notebook.scratch / "coordinator" / "fetched"
        if self._tmp is None:
            import tempfile
            self._tmp = pathlib.Path(tempfile.mkdtemp(prefix="nb-coord-"))
        return self._tmp
