"""
The agent loop. Used by both phases.

The one invariant that matters: append `resp.candidates[0].content` WHOLE.

Model turns carry thought signatures -- encrypted blobs holding the model's
reasoning state. The first function_call part of each step must carry its
signature back exactly as received, or the next request fails with "Function
call ... is missing a thought_signature". Gemini 3 validates this strictly;
2.5 did not. Verified here with a negative control: appending the Content whole
returns 200, rebuilding the turn from name+args returns 400.

Reconstructing a turn from extracted text drops the signature, and it is also
what would discard the cached prefix. Both failures have the same fix, which is
to never do it.
"""

import json

from .client import complete
from .config import MAX_TURNS


class Terminal(Exception):
    """A handler that ends the loop -- `propose`. Carries its result."""

    def __init__(self, payload):
        super().__init__("terminal tool called")
        self.payload = payload


def _log(path, turn, extra=None):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"parts": [
        {"text": p.text} if p.text else
        {"function_call": {"name": p.function_call.name,
                           "args": dict(p.function_call.args)}}
        for p in (turn.parts or []) if p.text or p.function_call]}
    if extra:
        rec.update(extra)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def run(contents, cfg, handlers, transcript=None, max_turns=MAX_TURNS,
        on_turn=None):
    """
    Drive the loop until the model stops calling tools, or a Terminal fires.

    Returns (response, contents, terminal_payload). `terminal_payload` is None
    when the model simply stopped.
    """
    from google.genai import types

    for n in range(max_turns):
        resp = complete(contents, cfg)
        turn = resp.candidates[0].content
        contents.append(turn)          # WHOLE -- signatures included
        _log(transcript, turn)
        if on_turn:
            on_turn(n, resp, turn)

        calls = [p.function_call for p in (turn.parts or []) if p.function_call]
        if not calls:
            return resp, contents, None

        parts = []
        for c in calls:
            try:
                out = handlers[c.name](**dict(c.args))
            except Terminal:
                raise                  # must not be swallowed by the catch below
            except KeyError:
                out = {"error": f"no such tool: {c.name}"}
            except Exception as e:
                # Every call gets an answer, including a failed one: an
                # unanswered function_call is an error on the next request.
                out = {"error": f"{type(e).__name__}: {e}"}
            parts.append(types.Part.from_function_response(
                name=c.name,
                response=out if isinstance(out, dict) else {"result": out}))

        # All responses in ONE turn. Splitting them degrades parallel calling.
        contents.append(types.Content(role="user", parts=parts))

    raise RuntimeError(f"max turns ({max_turns}) exceeded without a proposal")
