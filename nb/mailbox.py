"""
Asking a question without a terminal.

N agents cannot share one stdin, so a detached run writes its question to a file
and waits for a file in reply:

    _scratch/runs/<id>/question.json   {kind, name, why, options, asked_at}
    _scratch/runs/<id>/answer.json     {value, answered_at, by, replying_to}

`replying_to` carries the question's `asked_at`, so a reply cannot be taken as
the answer to a question it was not written for.

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

    def ask(self, kind, name, why="", options="", default=None, wait=None):
        """
        Put a question and block until answered, or until `wait` expires.

        `wait` overrides the mailbox's own deadline for one question. An hour is
        right for a budget the run cannot proceed without; it is wrong for "you
        look stuck, shall I carry on?", where the safe answer is yes and an hour
        of silence would cost more than the thing being asked about.

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

        deadline = time.time() + (self.wait if wait is None else wait)
        try:
            while time.time() < deadline:
                # Blocked on a question is where a run spends most of its idle
                # life, so it is the one place a stop MUST be noticed -- asking
                # a run to stop and having it sit there for the rest of the hour
                # would make the command a lie.
                if runstate.stop_requested(self.notebook):
                    from .loop import Stopped
                    raise Stopped(f"stopped while waiting on {name!r}")
                try:
                    a = json.loads(self.notebook.answer_path.read_text())
                except (OSError, ValueError):
                    time.sleep(POLL)
                    continue
                # An answer says WHICH question it answers, and one that names
                # a different question is not ours to take. Deleting
                # `answer.json` before asking is nearly enough, and the gap it
                # leaves is the dangerous one: a reply written for the previous
                # question, landing in the instant between that delete and this
                # read, is consumed as the answer to THIS one -- a value the
                # user never gave, attributed to them, in a system whose whole
                # point is that the record of what they said is true. `nb
                # board` guards its own half by remembering what it answered;
                # this guards every other writer, including a coordinator and
                # a second board.
                #
                # A missing `replying_to` is ACCEPTED: a hand-written
                # `answer.json` is a supported escape hatch and must keep
                # working. Everything written through `answer()` carries one.
                if "replying_to" in a and a["replying_to"] != q["asked_at"]:
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
            f"\n  no answer to {name!r} after "
            f"{(self.wait if wait is None else wait) / 60:.0f} min. The "
            f"question is at\n  {self.notebook.question_path}\n"
            f"  Answer it and resume with `nb resume {self.notebook.root.name}`.")


def answer(notebook, value, by="user", replying_to=None):
    """
    Write the reply for whichever run this notebook points at.

    Stamped with the `asked_at` of the question on disk, so the run can refuse
    a reply meant for a question it has already moved past -- see `Mailbox.ask`.
    Read here rather than required from the caller: every caller would look it
    up the same way, and one that forgot would silently reopen the hole.
    """
    notebook.run.mkdir(parents=True, exist_ok=True)
    if replying_to is None:
        replying_to = (pending(notebook) or {}).get("asked_at")
    body = {"value": value, "answered_at": time.time(), "by": by}
    # OMITTED, not written as null, when there is no question to point at. A
    # null would be a `replying_to` that matches nothing, so the run would
    # ignore the answer for ever -- and "nothing is pending right now" is
    # exactly the case where a caller is racing the run and the permissive old
    # behaviour is the safe one.
    if replying_to is not None:
        body["replying_to"] = replying_to
    notebook.answer_path.write_text(json.dumps(body, indent=1) + "\n")
    return notebook.answer_path


def pending(notebook_or_dir):
    """The outstanding question for a run, or None."""
    d = getattr(notebook_or_dir, "run", notebook_or_dir)
    try:
        return json.loads((d / "question.json").read_text())
    except (OSError, ValueError):
        return None
