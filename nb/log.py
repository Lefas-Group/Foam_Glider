"""
Two streams: telemetry on stderr, conversation on stdout.

`say()` is progress -- turn lines, lint output, what the model was thinking.
`tell()` is the conversation: a question that needs answering, the proposal, the
rendered entry. Anything a coordinator (or a person) has to ACT on.

Unredirected the terminal looks exactly as it did before, because both land
there. `2>/dev/null` leaves only the conversation; `2>run.log` keeps both apart.
Everything `say()` writes is also mirrored to `_scratch/run/status.log`, which is
what you read after a run has died.

Deliberately NOT a JSONL event protocol. A coordinating agent reads prose
natively, and JSON costs more: the turn line is ~18 tokens as prose against ~30
as an object, with keys repeated on every line and a schema to keep in step in
two places. Anything that must be exact is a FILE read by path -- `proposal.json`
already works that way -- not a message to be parsed out of a stream.
"""

import sys

_log = None


def open_log(notebook):
    """Start mirroring `say()` into `<notebook>/_scratch/run/status.log`."""
    global _log
    close_log()
    notebook.run.mkdir(parents=True, exist_ok=True)
    _log = (notebook.run / "status.log").open("a")
    return _log


def close_log():
    global _log
    if _log is not None:
        try:
            _log.close()
        finally:
            _log = None


def say(*args, **kw):
    """Telemetry. stderr, and the status log."""
    print(*args, file=sys.stderr, **kw)
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
