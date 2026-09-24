"""
The one provider seam.

Everything model-facing goes through `complete()`. Swapping provider means a
second implementation of this function -- roughly fifty lines -- not a rewrite.

Deliberately NOT routed through an abstraction layer (LiteLLM, LangChain chat
models). At one provider they buy nothing, and two things here would be at their
mercy: thought-signature round-tripping, a recurring defect in framework code
because a normalised message shape has nowhere to put an opaque provider blob;
and -- when there was one -- explicit-cache lifecycle, which a
chat-completions shape models poorly.
"""

import re

from google import genai
from google.genai import types

# Aliased: `config` is already a function in this module.
from . import config as settings
from .config import API_TIMEOUT_MS, MODEL, THINKING_LEVEL

_client = None


def client():
    global _client
    if _client is None:
        # The SDK's default is NEVER retry -- `retry_args(None)` returns
        # `stop_after_attempt(1)`. So a single 429 or 503 killed a run outright,
        # discarding up to 960 s of solves and everything the conversation had
        # established. Six attempts is ~31 s of patience (1+2+4+8+16, jittered)
        # against a loss measured in minutes.
        #
        # Retrying belongs HERE, below the seam, not in the loop: tenacity wraps
        # `_request_once` with the request already serialised, so the bytes on
        # the wire are identical on every attempt -- thought signatures included.
        # A retry built one layer up would rebuild the request, which is the
        # thing `loop.py` exists to never do.
        #
        # Retriable by default: 408, 429, 500, 502, 503, 504, and httpx
        # transient errors. A 400 -- a missing signature, a bad schema -- is not
        # retried, which is right: it would fail identically five times.
        # ...but retrying is worth nothing without a DEADLINE, which is what
        # this was missing. A run hung for 4h14m in `_ssl__SSLSocket_read`
        # after a render: the connection died silently -- no FIN, no RST -- so
        # read(2) simply never returned. That produces no status code and
        # raises nothing, so the six attempts above had nothing to catch and
        # never fired. Unset, `timeout` leaves httpx with no read deadline at
        # all, and the failure is indistinguishable from a slow think.
        #
        # 300 s against measured latency across 16 completed runs: 13.3 s per
        # turn median, 54.4 s at the worst run average. That is ~5x the worst
        # case seen, which leaves room for a single turn well above its run's
        # average while still bounding a dead socket at six attempts x 5 min
        # rather than forever. Milliseconds, per the SDK.
        _client = genai.Client(http_options=types.HttpOptions(
            timeout=API_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=6)))
    return _client


def thinking():
    # MINIMAL is in the enum but 400s on both candidate models; LOW/MEDIUM/HIGH
    # are the usable range.
    # Read through the module, not a from-import: `--thoughts` sets
    # config.INCLUDE_THOUGHTS at startup, and a name bound at import time would
    # never see the change.
    return types.ThinkingConfig(
        thinking_level=getattr(types.ThinkingLevel, THINKING_LEVEL),
        include_thoughts=settings.INCLUDE_THOUGHTS)


def config(tools=None, system_instruction=None, response_schema=None,
           max_output_tokens=None):
    """
    A GenerateContentConfig.

    There used to be a `cached_content` branch here, mutually exclusive with
    `system_instruction` and `tools` because a cache object carries both. It is
    gone with the explicit cache: implicit caching needs nothing declared and
    measured at roughly twice the hit rate.
    """
    # AFC is on by default, so every call takes the SDK's function-calling path,
    # logs a warning once per process, and deep-copies the config each turn. It
    # then breaks immediately, because the map it builds comes from CALLABLES in
    # `tools` and we pass only declarations -- so it costs nothing today, by
    # accident. Disabling it says so on purpose, and stops the SDK ever executing
    # a handler behind the loop's back if a callable is passed here by mistake.
    kw = {"thinking_config": thinking(),
          "automatic_function_calling":
              types.AutomaticFunctionCallingConfig(disable=True)}
    if system_instruction:
        kw["system_instruction"] = system_instruction
    if tools:
        kw["tools"] = tools
    if response_schema is not None:
        kw["response_mime_type"] = "application/json"
        kw["response_schema"] = response_schema
    if max_output_tokens:
        kw["max_output_tokens"] = max_output_tokens
    return types.GenerateContentConfig(**kw)


# A daily quota is not a transient error and the six retries above cannot help:
# the reset is hours away, not seconds. Caught here so it ends the run with the
# one fact that matters -- when it can be tried again -- instead of a stack
# trace ending in `raise ClientError(status_code, response_json, response)`,
# which says nothing about what to do and buries the retry time in a 900-byte
# JSON blob.
_QUOTA = re.compile(r"retryDelay['\"]?[:=]\s*['\"]?(\d+)s")


def complete(contents, cfg, model=MODEL):
    from google.genai import errors
    try:
        return client().models.generate_content(
            model=model, contents=contents, config=cfg)
    except errors.ClientError as e:
        if getattr(e, "code", None) != 429:
            raise
        m = _QUOTA.search(str(e))
        wait = (f" Try again in about {int(m.group(1)) // 60} min."
                if m else "")
        raise SystemExit(
            f"\n  API quota exhausted for {model}.{wait}\n"
            f"  Nothing was committed; the entry is on disk and "
            f"`nb resume <notebook>` picks the entry up where it stopped.") from None


def usage(resp):
    """(prompt, cached, output) tokens. `cached` is the number that matters."""
    u = resp.usage_metadata
    return (u.prompt_token_count or 0,
            u.cached_content_token_count or 0,
            u.candidates_token_count or 0)
