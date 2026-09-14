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
two places. Anything that must be exact is a FILE read by path -- `proposal.json`
already works that way -- not a message to be parsed out of a stream.
"""

import sys
import time

_log = None


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
    print(f"\n{'═' * 72}\n{stamp}  {phase}  {question[:60]}\n{'═' * 72}",
          file=_log, flush=True)
    return _log


def close_log():
    global _log
    if _log is not None:
        try:
            _log.close()
        finally:
            _log = None


def say(*args, **kw):
    """Detail. The log only -- never the terminal."""
    if _log is not None:
        print(*args, file=_log, **kw)
        _log.flush()


def tell(*args, **kw):
    """Conversation. stdout, and the status log so the record is complete."""
    print(*args, **kw)
    if _log is not None:
        print(*args, file=_log, **kw)
        _log.flush()


def thought(text):
    """
    What the model was reasoning, indented so it never reads as output.

    Summaries, not raw chain of thought -- the API returns a condensed version.
    They cost nothing extra to generate (the thinking happens either way and is
    billed either way) and ~250 tokens/turn of conversation to carry, because
    they arrive inside the model turn, which `loop.py` appends whole.
    """
    for line in (text or "").strip().splitlines():
        say(f"        · {line}")
