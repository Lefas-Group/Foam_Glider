"""
The terminal is the conversation. Everything else goes to the log.

`tell()` is what you must act on -- a question, a milestone, a failure, the
finished entry. It goes to stdout AND the log.
`say()` is detail -- one line per turn, the model's reasoning, per-probe budgets,
lint output. It goes to the log ONLY.

There is no flag for this. Both streams landed on the same terminal before, so
separating them meant redirecting one away -- and it cannot be stdout, because
that is where the blocking prompt is typed. An option everyone sets the same way
is a default wearing a disguise, and two output modes is two things to keep in
step, so `say()` simply stopped reaching the terminal.

Read the detail live from another tab with `nb watch <notebook>`, or afterwards
from `_scratch/run/status.log`, which is the same thing. That log is the only
copy, so anything a run's outcome depends on must be `tell()` -- a run that ends
without committing has to say so on the terminal or it ends in silence.

Deliberately NOT a JSONL event protocol. A coordinating agent reads prose
natively, and JSON costs more: the turn line is ~18 tokens as prose against ~30
as an object, with keys repeated on every line and a schema to keep in step in
two places. Anything that must be exact is a FILE read by path -- `run.json`
already works that way -- not a message to be parsed out of a stream.
"""

import os
import sys
import time

_log = None
_detached = False


def detach_output():
    """
    Stop `tell()` reaching stdout, for a run with nobody in front of it.

    Every run detaches, so the conversation happens through the run directory:
    board reads `run.json`, questions go to `question.json`, and the detail is
    in `status.log` either way. stdout is then not a terminal anyone is reading
    -- it is the SAME terminal the board is drawing on, and a banner printed
    into a `rich` Live region corrupts it. Two agents and it is unreadable.

    The log still gets everything, stamped, so nothing is lost: `nb watch` and
    a coordinator read the file, which is what they read anyway.
    """
    global _detached
    _detached = True


def detached():
    """
    True once `detach_output` has fired.

    Read by `_start`, which both `nb ask` and `nb resume` go through -- so a
    process that has already forked itself does not fork a second time, change
    its pid mid-question for no reason, and orphan whatever the board was
    watching.
    """
    return _detached


def open_log(notebook, phase="", question=""):
    """
    Start writing into `<notebook>/_scratch/run/status.log`.

    Appends rather than truncates, so a run can be compared with the one before
    it -- which is why it opens with a separator. Without one a watcher tailing
    the file cannot tell where the current run starts.
    """
    global _log
    close_log()
    notebook.run.mkdir(parents=True, exist_ok=True)
    _log = (notebook.run / "status.log").open("a")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # The PID goes in the header because it is what lets a watcher tell a run
    # that is WEDGED from one that DIED without a word. Both happened in one
    # week: a turn that blocked on a dead socket for 4h14m with the process
    # alive, and a run that vanished mid-edit. They need different responses.
    print(f"\n{'═' * 72}\n{stamp}  {phase}  pid {os.getpid()}  "
          f"{question[:60]}\n{'═' * 72}",
          file=_log, flush=True)
    return _log


def close_log():
    global _log
    if _log is not None:
        try:
            _log.close()
        finally:
            _log = None


# The gutter that marks a line as the model's reasoning rather than the run's
# own report. A bar, not the `·` the old format used: `·` is already the field
# separator inside budget lines ("15 s granted · 2 s used"), so the two read as
# the same kind of thing when scanning. `nb watch` dims anything carrying this.
GUTTER = "│ "
_STAMP_W = 10                   # len("HH:MM:SS") + two spaces
# Reasoning is indented one step PAST the run's own lines, so a turn reads as a
# heading with its thinking beneath it rather than as another status line.
_THOUGHT_INDENT = _STAMP_W + 2
# How much of a line the indent and gutter take, so a reader wrapping reasoning
# to its own terminal knows what it has left. There is no fixed width here any
# more -- see `thought`.
THOUGHT_MARGIN = _THOUGHT_INDENT + len(GUTTER)


def _stamped(args):
    """Prefix the first line with HH:MM:SS; continuation lines stay aligned."""
    if not args:
        return args
    head = str(args[0])
    if head.startswith(GUTTER[0]):
        return (" " * _THOUGHT_INDENT + head,) + args[1:]
    if head.startswith("═") or not head.strip():
        return (" " * _STAMP_W + head,) + args[1:]
    # Status lines arrive with two leading spaces of their own; the stamp
    # replaces that indent rather than adding to it, so the columns they were
    # written to line up under it.
    return (f"{time.strftime('%H:%M:%S')}  {head.lstrip(' ')}",) + args[1:]


def say(*args, **kw):
    """
    Detail. The log only -- never the terminal.

    Timestamped, because the log is now the ONLY live view of a run and a
    watcher has to be able to work out that nothing has happened for a while.
    Putting the clock here rather than in a heartbeat thread is deliberate: a
    daemon thread printing "still alive" keeps printing happily while the main
    thread is wedged, which is precisely the case worth detecting. The writer
    emits facts; `nb watch` decides when they have stopped arriving.
    """
    if _log is not None:
        print(*_stamped(args), file=_log, **kw)
        _log.flush()


def tell(*args, **kw):
    """
    Conversation. stdout, and the status log so the record is complete.

    Stamped in the LOG but not on the terminal: the log is read by a watcher
    working out whether anything is still happening, and a half-stamped file
    makes that arithmetic guesswork. The terminal has a human in front of it
    who does not need the time on every line. Detached, there is no such human
    and nothing goes to stdout at all -- see `detach_output`.
    """
    if not _detached:
        print(*args, **kw)
    if _log is not None:
        print(*_stamped(args), file=_log, **kw)
        _log.flush()


def thought(text):
    """
    What the model was reasoning, in a gutter so it never reads as output.

    Summaries, not raw chain of thought -- the API returns a condensed version.
    They cost nothing extra to generate: the thinking happens either way and is
    billed either way, measured at 398 vs 342 thought tokens with this off and
    on. They cost nothing to CARRY either, because `loop.py` shows them and then
    drops them before appending the turn, so they never re-enter the
    conversation -- which is also why they can confabulate freely here without
    misleading the model later.

    ONE PARAGRAPH, ONE LINE, UNWRAPPED. This used to hard-wrap to 66 columns
    on the way in -- 80 less the indent and the gutter -- and the reason was
    sound as far as it went: the summaries arrive as long single-line
    paragraphs, and letting the terminal wrap them sent every continuation
    line back to column 0, so the gutter marked only the first line of each
    and the rest ran under the timestamps. But THE WRITER DOES NOT KNOW THE
    READER'S WIDTH. On the 190-column terminal a board is usually opened in,
    66 columns is a third of the screen, and a file cannot be re-flowed once
    it is written.

    So the wrapping moved to the one place that knows: `nb watch`'s `_emit`
    already singles out gutter lines to dim them, and now wraps them to the
    console it is printing to. A paragraph is a single line in the file, so
    that stays correct while streaming -- there is no state to accumulate.

    THE COST, stated: `tail -f` and `cat` on `status.log` show long lines the
    terminal soft-wraps back to column 0, which is the complaint the fixed
    width was introduced to fix. `nb watch` is the reader this is written for
    and it is right at any width; the raw file is now worse in exchange.

    Markdown bold is stripped: the summaries head their sections with
    `**Like This**`, and the asterisks are noise in a terminal.
    """
    import re
    blank = False
    for para in (text or "").strip().splitlines():
        if not para.strip():
            blank = True
            continue
        if blank:
            say(GUTTER.rstrip())
            blank = False
        para = re.sub(r"\*\*(.+?)\*\*", r"\1", para.rstrip())
        say(f"{GUTTER}{para}")
