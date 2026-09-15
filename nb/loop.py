"""
The agent loop. Used by both phases.

The one invariant that matters: never RECONSTRUCT a model turn.

Model turns carry thought signatures -- encrypted blobs holding the model's
reasoning state. The first function_call part of each step must carry its
signature back exactly as received, or the next request fails with "Function
call ... is missing a thought_signature". Gemini 3 validates this strictly;
2.5 did not. Verified here with a negative control: appending the Content whole
returns 200, rebuilding the turn from name+args returns 400.

FILTERING the part list is not reconstructing it. A signature is an attribute of
a Part, so a Part that survives a filter carries its signature with it; a Part
built fresh from `name` and `args` does not. That is the whole distinction, and
it is what lets `_spoken()` drop thought summaries below.

Reconstructing would also discard the cached prefix. Filtering does not, as long
as it is done EVERY turn: implicit caching matches a byte prefix, and a
conversation that is consistently built the same way still grows monotonically.
What breaks caching is editing history retroactively -- sending a turn one way
and then a different way later.
"""

import json

from .client import complete
from .config import MAX_TURNS
from .log import thought


class Refactor(Exception):
    """
    Declared in `tools/interact.py`; defined here so `loop` can let it through.

    Lives beside `Terminal` because it is the same kind of thing -- a handler
    that ends the run rather than returning to it -- and the loop's catch-all
    would otherwise turn it into a tool error the model would try to work
    around.
    """


class Terminal(Exception):
    """A handler that ends the loop -- `propose`. Carries its result."""

    def __init__(self, payload):
        super().__init__("terminal tool called")
        self.payload = payload


def _spoken(turn):
    """
    The turn as the model should hear it back: everything except its thinking.

    Thought SUMMARIES arrive inside the model turn, so appending it whole means
    every later turn re-sends them and the model reads its own summaries as
    context. Measured, those summaries confabulate on short turns -- one decided
    `lint` meant "micro-debris, possibly from instrumentation, lab coats or even
    the atmosphere" -- and that is not something to feed back.

    Safe because the enforced signature is not on a thought part. Google's
    documentation: the signature is attached "only to the first functionCall
    part", and the 400 fires when "the first functionCall part in any step of the
    current turn lacks its thought_signature". Signatures elsewhere are
    "recommended" and not validated -- but the last part of a response may carry
    one, so a thought part that has a signature is kept anyway. That condition
    should never fire, since thoughts come first; it costs nothing and it is the
    only way this could quietly degrade reasoning.
    """
    from google.genai import types
    parts = turn.parts or []
    keep = [p for p in parts
            if not getattr(p, "thought", None)
            or getattr(p, "thought_signature", None)]
    if len(keep) == len(parts):
        return turn                     # nothing to drop; hand back the original
    return types.Content(role=turn.role, parts=keep)


def _log(path, turn, extra=None):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"parts": [
        {"thought": p.text} if getattr(p, "thought", None) else
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

    # A DEADLINE, not a guillotine. A run that hits max_turns is killed with no
    # warning and nothing written: flash burned all 40 and produced nothing,
    # never short of budget, just never deciding. Told how little is left, a
    # model can propose what it has or say what is missing -- both worth more
    # than the wall. Once, at 70%, because a countdown every turn becomes
    # wallpaper and costs cache on each append.
    warn_at = int(max_turns * 0.7)
    for n in range(max_turns):
        if n == warn_at:
            contents.append({"role": "user", "parts": [{"text":
                f"{max_turns - n} of your {max_turns} turns remain. Finish with "
                f"what you have: call the tool that ends this phase, or stop and "
                f"say plainly what is still missing. Running out is the one "
                f"outcome that produces nothing at all."}]})
        resp = complete(contents, cfg)
        turn = resp.candidates[0].content
        _log(transcript, turn)         # the record keeps the thinking
        # The turn's own line FIRST, then the reasoning behind it. Printing the
        # thoughts first put every `turn N` line after the block it belonged to,
        # so it read as a heading for the NEXT turn -- which is most of why the
        # log was hard to follow.
        if on_turn:
            on_turn(n, resp, turn)
        # Shown, then dropped: telemetry, never conversation, and never fed back.
        for part in (turn.parts or []):
            if getattr(part, "thought", None) and part.text:
                thought(part.text)
        contents.append(_spoken(turn))

        calls = [p.function_call for p in (turn.parts or []) if p.function_call]
        if not calls:
            return resp, contents, None

        parts = []
        for c in calls:
            try:
                out = handlers[c.name](**dict(c.args))
            except Terminal:
                raise                  # must not be swallowed by the catch below
            except Refactor:
                raise                  # a declared stop, not a tool failure
            except KeyError:
                out = {"error": f"no such tool: {c.name}"}
            except Exception as e:
                # Every call gets an answer, including a failed one: an
                # unanswered function_call is an error on the next request.
                out = {"error": f"{type(e).__name__}: {e}"}
            if isinstance(out, dict) and "_image" in out:
                # An image has to arrive as an inline part; put through a
                # function_response it is just a base64 string the model cannot
                # see and pays ~18x the tokens for. Both parts share this turn,
                # which the API accepts (verified).
                parts.append(types.Part.from_function_response(
                    name=c.name,
                    response={"figure": out["name"], "note": "attached below"}))
                parts.append(types.Part.from_bytes(
                    data=out["_image"], mime_type=out["mime_type"]))
            else:
                parts.append(types.Part.from_function_response(
                    name=c.name,
                    response=out if isinstance(out, dict) else {"result": out}))

        # All responses in ONE turn. Splitting them degrades parallel calling.
        contents.append(types.Content(role="user", parts=parts))

    raise RuntimeError(f"max turns ({max_turns}) exceeded without a proposal")
