"""
Asking a question without a terminal.

N agents cannot share one stdin, so a detached run writes its question to a file
and waits for a file in reply:

    _scratch/runs/<id>/question.json   {kind, name, why, options, asked_at}
    _scratch/runs/<id>/answer.json     {value, answered_at, by}

Files rather than a pipe or a socket, for a reason that is not convenience: a
question answered over a transport leaves no trace, and the whole point is that
the user can watch the conversation whoever is answering -- now themselves, later
a coordinator agent. On disk it is timestamped, greppable and still there
tomorrow, which is also what lets a coordinator that restarts pick the
conversation back up. Scrollback is not state.

It is also why `nb board` is a VIEW and not a supervisor. Kill it, restart it,
run two, answer from another terminal with `nb answer`, or let an agent write
the file: the run neither knows nor cares.

On timeout the run does not block for ever -- it leaves the question on disk and
exits, which is the shape the two existing stops already have, and `nb write`
resumes from the proposal exactly as it does for them.
"""

import json
import time

WAIT = 3600.0          # an hour: a person who steps away should not lose a run
POLL = 1.0


class Mailbox:
    """The question/answer pair for one run. `None` means "use stdin"."""

    def __init__(self, notebook, answers=None, wait=WAIT):
        self.notebook = notebook
        # Pre-answers, consulted before anything is asked. A coordinator that
        # already knows the foam thickness should not interrupt itself for it.
        self.answers = dict(answers or {})
        self.wait = wait

    def ask(self, kind, name, why="", options="", default=None):
        """
        Put a question and block until answered, or until `wait` expires.

        Returns the answer as a string, or `default` on timeout when there is
        one -- budgets and assumption confirmations have safe defaults and must
        never strand a run; a Specified input has none and stops instead.
        """
        from . import runstate
        if name in self.answers:
            return str(self.answers.pop(name))

        q = {"kind": kind, "name": name, "why": why, "options": options,
             "asked_at": time.time(), "run": self.notebook.run_id}
        self.notebook.run.mkdir(parents=True, exist_ok=True)
        self.notebook.answer_path.unlink(missing_ok=True)
        self.notebook.question_path.write_text(json.dumps(q, indent=1) + "\n")
        runstate.write(self.notebook, waiting_on=name)

        deadline = time.time() + self.wait
        try:
            while time.time() < deadline:
                try:
                    a = json.loads(self.notebook.answer_path.read_text())
                except (OSError, ValueError):
                    time.sleep(POLL)
                    continue
                self.notebook.question_path.unlink(missing_ok=True)
                return str(a.get("value", ""))
        finally:
            runstate.write(self.notebook, waiting_on=None)

        # Timed out. The question stays on disk: that is what makes this a
        # stopped run a coordinator can resume rather than an answer invented
        # on the run's behalf.
        if default is not None:
            return str(default)
        raise SystemExit(
            f"\n  no answer to {name!r} after {self.wait / 60:.0f} min. The "
            f"question is at\n  {self.notebook.question_path}\n"
            f"  Answer it and resume with `nb write {self.notebook.root.name}`.")


def answer(notebook, value, by="user"):
    """Write the reply for whichever run this notebook points at."""
    notebook.run.mkdir(parents=True, exist_ok=True)
    notebook.answer_path.write_text(
        json.dumps({"value": value, "answered_at": time.time(), "by": by},
                   indent=1) + "\n")
    return notebook.answer_path


def pending(notebook_or_dir):
    """The outstanding question for a run, or None."""
    d = getattr(notebook_or_dir, "run", notebook_or_dir)
    try:
        return json.loads((d / "question.json").read_text())
    except (OSError, ValueError):
        return None
