"""
The agent loop.

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
from .stuck import Detector


class Stopped(Exception):
    """
    Someone asked this run to stop -- `nb stop`, or a coordinator.

    Raised rather than returned so it unwinds through the same `finally` that
    every other ending uses, and caught by the phases so the stop is RECORDED.
    A run that vanishes without an outcome is indistinguishable from one that
    crashed, and telling those apart is most of what the board is for.
    """


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


# One tool result, capped. A probe already truncates itself to TRUNCATE before
# it is returned, so this is the belt to that braces -- and the record is for
# reconstructing a run, not for replaying it.
RESULT_CAP = 4000


def _write(path, rec):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _log(path, turn, extra=None):
    """One MODEL turn: its thinking, its text, and the calls it made."""
    if path is None:
        return
    rec = {"role": "model", "parts": [
        {"thought": p.text} if getattr(p, "thought", None) else
        {"text": p.text} if p.text else
        {"function_call": {"name": p.function_call.name,
                           "args": dict(p.function_call.args)}}
        for p in (turn.parts or []) if p.text or p.function_call]}
    if extra:
        rec.update(extra)
    _write(path, rec)


def _log_results(path, results):
    """
    What the tools ANSWERED, which makes this a transcript rather than half of
    one.

    It recorded model turns and nothing else, so the file said what the model
    said and never what it was replying to. You could not tell from it what
    lint reported, whether the first-probe notice fired, or what a user
    answered -- and each of those has been wanted: confirming a prompt had
    fired at all needed a `say()` line added specially, because the transcript
    could not show it.

    Written as its own line with `role: "tool"`, after the model turn it
    answers, so a reader walks the file in order and sees call then result.
    Images are noted rather than embedded -- the bytes are already on disk
    under the freeze, and a base64 blob in a log is unreadable either way.
    """
    if path is None or not results:
        return
    out = []
    for call, result in results:
        if isinstance(result, dict) and "_image" in result:
            body = {"image": result.get("name"), "bytes": len(result["_image"])}
        elif isinstance(result, dict):
            body = {k: v for k, v in result.items() if k != "_image"}
        else:
            body = {"result": str(result)[:RESULT_CAP]}
        out.append({"name": call.name, "response": body})
    _write(path, {"role": "tool", "results": out})


def run(contents, cfg, handlers, transcript=None, max_turns=MAX_TURNS,
        on_turn=None, on_stuck=None, should_stop=None):
    """
    Drive the loop until the model stops calling tools, or a Terminal fires.

    Returns nothing. A stop RAISES -- `Stopped` carries the
    and the caller catches it -- so the three-tuple this used to return had a
    third element that was None on every path that reached a `return`, and
    nothing read any of it.

    `on_stuck(found)` is called when the run has gone `stuck.BARREN_LIMIT` turns
    without writing or measuring anything, and returns text to put to the model
    (or raises to end the run). It lives here rather than in the phase because
    this is where the turns actually happen, and because a detector that only
    runs while somebody has the board open is not a detector.
    """
    from google.genai import types

    # A DEADLINE, not a guillotine. A run that hits max_turns is killed with no
    # warning and nothing written: flash burned all 40 and produced nothing,
    # never short of budget, just never deciding. Told how little is left, a
    # model can propose what it has or say what is missing -- both worth more
    # than the wall. Once, at 70%, because a countdown every turn becomes
    # wallpaper and costs cache on each append.
    warn_at = int(max_turns * 0.7)
    detector = Detector()
    for n in range(max_turns):
        # Checked before spending a request, not after: the point of stopping a
        # run is to stop paying for it.
        if should_stop and should_stop():
            raise Stopped(f"stopped after {n} turns")
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
            return

        parts, results = [], []
        for c in calls:
            # LOOKED UP OUTSIDE the try, so only a missing NAME can produce
            # "no such tool". Inside it, any KeyError raised by the handler's
            # own body -- a dict miss deep in `probe`, say -- was reported as
            # the tool not existing, and a model told its tool does not exist
            # stops using it and starts looking for another. That is the
            # shape of the worst run this system has had.
            try:
                fn = handlers[c.name]
            except KeyError:
                results.append((c, {"error": f"no such tool: {c.name}"}))
                parts.append(types.Part.from_function_response(
                    name=c.name, response={"error": f"no such tool: {c.name}"}))
                continue
            try:
                out = fn(**dict(c.args))
            except Stopped:
                # Someone asked this run to stop, from inside a tool -- the
                # mailbox raises it when a question is waiting and `nb stop`
                # arrives. Swallowed, it became a tool ERROR the model tried to
                # work around, and the run carried on until the `should_stop`
                # check at the top of the next iteration: one more request
                # bought and paid for after the stop was asked for.
                raise
            except Exception as e:
                # Every call gets an answer, including a failed one: an
                # unanswered function_call is an error on the next request.
                out = {"error": f"{type(e).__name__}: {e}"}
            results.append((c, out))
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
        _log_results(transcript, results)

        # AFTER the responses, never between a call and its answer: an
        # unanswered function_call is a 400 on the next request. It also needs
        # the outputs, since a productive tool that ERRORED is not progress --
        # so the check cannot happen before the handlers run.
        found = detector.turn(results) if on_stuck else None
        if found:
            nudge = on_stuck(found)
            if nudge:
                contents.append({"role": "user", "parts": [{"text": nudge}]})

    raise RuntimeError(f"max turns ({max_turns}) exceeded")
