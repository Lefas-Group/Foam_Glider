"""
The one provider seam.

Everything model-facing goes through `complete()`. Swapping provider means a
second implementation of this function -- roughly fifty lines -- not a rewrite.

Deliberately NOT routed through an abstraction layer (LiteLLM, LangChain chat
models). At one provider they buy nothing, and two things here would be at their
mercy: thought-signature round-tripping, a recurring defect in framework code
because a normalised message shape has nowhere to put an opaque provider blob;
and explicit-cache lifecycle, which a chat-completions shape models poorly.
"""

from google import genai
from google.genai import types

from .config import MODEL, THINKING_LEVEL

_client = None


def client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def thinking():
    # MINIMAL is in the enum but 400s on both candidate models; LOW/MEDIUM/HIGH
    # are the usable range.
    return types.ThinkingConfig(
        thinking_level=getattr(types.ThinkingLevel, THINKING_LEVEL))


def config(tools=None, cached_content=None, system_instruction=None,
           response_schema=None, max_output_tokens=None):
    """
    A GenerateContentConfig.

    `cached_content` and `system_instruction` are mutually exclusive: the cache
    object already carries the system instruction and the tool declarations, and
    passing either alongside it is an error.
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
    if cached_content:
        kw["cached_content"] = cached_content
    else:
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


def complete(contents, cfg, model=MODEL):
    return client().models.generate_content(
        model=model, contents=contents, config=cfg)


def usage(resp):
    """(prompt, cached, output) tokens. `cached` is the number that matters."""
    u = resp.usage_metadata
    return (u.prompt_token_count or 0,
            u.cached_content_token_count or 0,
            u.candidates_token_count or 0)
