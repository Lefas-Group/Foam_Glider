"""
The coordinator's end of the mailbox.

ONE MAILBOX, NOT TWO. The coordinator is a participant in the mailbox that
already exists, at a reserved run id, rather than a second protocol beside it:
`notebook.runs()` globs every directory under `runs/`, so `nb board` discovers
it for free, `nb answer <nb> coordinator "…"` addresses it by id like any run,
and the question/answer pair on disk means the same thing at both levels.

    _scratch/runs/
      20260925-155817-41a8/   run.json question.json run.lock   <- a process
      coordinator/            run.json question.json log.jsonl  <- turn-based

THE RESERVED ID HOLDS NO LOCK, and that is the difference that matters. A run
is one process suspended mid-conversation: kill it and its question outlives
it, so `alive()` is how the system avoids addressing an answer to a corpse --
`nb answer` refuses, `nb board` skips, `nb clean` reclaims. A COORDINATOR has
no process to be alive. It is a sequence of turns with nothing running in
between, and its `answer.json` is read by a later turn rather than by a
suspended reader, so there is no corpse to address and nothing for liveness to
mean. Every place that asks "is this still going?" therefore has to ask about
the reserved id first: `phases/answer.py`, `phases/board.py` (twice) and
`phases/clean.py`. `is_coordinator` is that question, in one place, so the
three cannot drift.

The log is separate from the questions on purpose. `log.jsonl` is what the
coordinator DECIDED and why -- the half of the programme that is otherwise only
in a Claude Code transcript, in a format nothing here can read. `nb note` puts
it where the board can show it, interleaved with the questions and endings it
explains.
"""

import json
import time

from ..config import Notebook

DIR = "coordinator"
POLL = 1.0
# Four hours. A run's undefaulted question expires at `mailbox.WAIT` (an hour),
# so a wait longer than that outlives the thing it is waiting to answer -- but
# the coordinator may be holding several runs' worth of programme, and a waiter
# that gives up first turns a slow human into a dead loop with no record. It
# ends by printing why, which a backgrounded waiter turns into a wake-up.
TIMEOUT = 14400.0


def is_coordinator(run_id):
    """True for the reserved id, whatever shape it arrives in."""
    return str(getattr(run_id, "name", run_id)) == DIR


def mailbox_for(notebook):
    """The notebook, addressed at the reserved run id."""
    return Notebook(notebook.root, run_id=DIR)


def touch(notebook, **fields):
    """
    Ensure `runs/coordinator/run.json` exists, merging `fields` into it.

    Written by hand rather than through `runstate.write`, which stamps the
    CALLING process's pid: every `nb note` is a different short-lived process,
    so the registry would report whichever one ran last as the coordinator's
    process -- a pid belonging to something that has already exited, which is
    exactly the fiction the lock was introduced to end.
    """
    nb = mailbox_for(notebook)
    nb.run.mkdir(parents=True, exist_ok=True)
    try:
        state = json.loads(nb.run_state.read_text())
    except (OSError, ValueError):
        state = {"run": DIR, "started": time.time()}
    state.update(fields)
    state["updated"] = time.time()
    tmp = nb.run_state.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n")
    tmp.replace(nb.run_state)
    return state


def log_path(notebook):
    return mailbox_for(notebook).run / "log.jsonl"


def note(notebook, text, kind="note"):
    """
    Append one line to the programme log.

    `kind` distinguishes a DIRECTION -- what the user asked for -- from the
    notes explaining what was done about it. It was a text convention before
    ("direction: …" as the first words of a note), which nothing could find
    reliably and which the board could not pin. Absent on every line written
    so far, and defaulted here, so those still read as notes.

    LINE BREAKS SURVIVE; nothing else does. This collapsed all whitespace,
    which made a note of several lines impossible -- so the one thing the
    coordinator can say in its own voice could not be a summary of where the
    programme stands, only a sentence. The board's panel takes newlines
    happily and `log.jsonl` escapes them, so the restriction bought nothing.
    A one-line note comes out of this byte-identical, which is every note
    written so far.
    """
    lines = [" ".join(l.split()) for l in str(text).splitlines()]
    # Blank runs collapse to one: a model writing a heading and a list leaves
    # double spacing behind it, and the board has no room to spare.
    kept = [l for n, l in enumerate(lines)
            if l or (n and lines[n - 1])]
    text = "\n".join(kept).strip()
    if not text:
        return None
    touch(notebook)
    with log_path(notebook).open("a") as fh:
        fh.write(json.dumps({"at": time.time(), "kind": kind,
                             "text": text}) + "\n")
    return text


def direction(notebook, text):
    """Record what the user asked for. The board pins the newest one."""
    return note(notebook, text, kind="direction")


def current_direction(notebook):
    """
    The direction in force, or None.

    THE EPOCH OF THE PROGRAMME, not just a caption. Everything before it
    belongs to a previous direction in the same notebook, which is history the
    board deliberately does not replay -- so this is what bounds the
    conversation as well as what heads it.
    """
    found = [n for n in notes(notebook) if n.get("kind") == "direction"]
    return found[-1] if found else None


def notes(notebook, after=0.0):
    """Every note written after `after`, oldest first."""
    out = []
    try:
        for line in log_path(notebook).read_text().splitlines():
            try:
                got = json.loads(line)
            except ValueError:
                continue                      # a torn final line, not a crash
            if got.get("at", 0) > after:
                got.setdefault("kind", "note")
                out.append(got)
    except OSError:
        pass
    return out


def post(notebook, name, prompt="", why="", options="", default=None):
    """
    Put a question to the human and RETURN AT ONCE.

    Posting and waiting are separate commands because they fail differently. A
    foreground shell call in the coordinator's harness is capped at ten
    minutes, so an ask-and-block command would routinely be killed with the
    question already on disk -- the board showing a question nobody is waiting
    for, which reads exactly like one that is about to be relayed. Split, the
    post cannot fail part-way and only the wait can time out, which waiting
    again repairs.
    """
    nb = mailbox_for(notebook)
    nb.run.mkdir(parents=True, exist_ok=True)
    q = {"kind": "coordinator", "name": name,
         "prompt": prompt or f"What is the {name}?", "why": why,
         "how": "", "options": options,
         "default": None if default is None else str(default),
         "asked_at": time.time(), "run": DIR}
    nb.answer_path.unlink(missing_ok=True)
    nb.question_path.write_text(json.dumps(q, indent=1) + "\n")
    touch(notebook, waiting_on=name, question=name)
    return q


def reply(notebook, q=None):
    """
    The answer to the escalation, if one is on disk YET -- one pass, no block.

    EXTRACTED from `wait` so a caller that is already blocking on something
    else can poll this as one more source. The coordinator agent waits on runs
    and on the human in a single tool call, and `wait(timeout=0)` cannot serve
    it: a zero deadline fails the loop test before reading the file at all, so
    it would answer None however long the reply had been sitting there.

    Consuming is part of it. A reply read and left on disk is one the next pass
    reads again, so this deletes the pair and records the exchange exactly as
    `wait` always did -- which means it must not be called speculatively.
    """
    from . import mailbox
    nb = mailbox_for(notebook)
    if q is None:
        q = mailbox.pending(nb.run) or {}
    try:
        got = json.loads(nb.answer_path.read_text())
    except (OSError, ValueError):
        return None
    # `replying_to` guards the same mistake it guards for a run: an answer
    # written before this question was posted belongs to the previous one.
    if "replying_to" in got and got["replying_to"] != q.get("asked_at"):
        return None
    nb.question_path.unlink(missing_ok=True)
    nb.answer_path.unlink(missing_ok=True)
    value = str(got.get("value", ""))
    # RECORDED LIKE ANY OTHER EXCHANGE. A run's `Mailbox._record` appends
    # every question and answer to its `run.json`, which is what the board
    # reads the conversation from; nothing does that for an escalation,
    # so the one question the person actually answered was the one the
    # history could not show.
    state = touch(notebook, waiting_on=None, question=None)
    answered = list(state.get("answered") or [])
    # THE SAME SHAPE A RUN RECORDS, field for field -- see
    # `mailbox.Mailbox._record`. The prompt used to be written into `why`,
    # which left `prompt` empty, and the board fell back to "What is the
    # direction?" over the real question with the real question printed
    # underneath it as though it were the justification.
    answered.append({"kind": "specified", "name": q.get("name", ""),
                     "prompt": q.get("prompt", ""),
                     "why": " ".join((q.get("why") or "").split())[:300],
                     "value": value, "source": got.get("by") or "user",
                     "asked_at": q.get("asked_at"), "at": time.time()})
    touch(notebook, answered=answered)
    return value


def wait(notebook, timeout=TIMEOUT, poll=POLL):
    """
    Block until the question is answered. Returns the answer, or None on
    timeout with the question left on disk for the next waiter.
    """
    from . import mailbox
    q = mailbox.pending(mailbox_for(notebook).run) or {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = reply(notebook, q)
        if got is not None:
            return got
        time.sleep(poll)
    return None
