"""
The explicit cache.

Gemini offers two mechanisms: implicit (automatic, 75% off a matched prefix,
best effort) and explicit (a cache object with a TTL, guaranteed). This system's
prefix is frozen by construction -- sorted tool list, byte-identical system
instruction, whole-notebook context -- which is the case explicit caching exists
for, and the reason the system stays on generate_content rather than moving to
the Interactions API, where explicit caching is unavailable.

Keyed on hash(system + tools + manifest), so it is reused across both commands
and across runs, and rebuilt only when the manifest changes -- i.e. after a
commit. Below 4,096 tokens nothing caches at all and no error is raised, so the
size check is not optional.

Measured: 8,127 of 8,136 prompt tokens served from cache, 9 billed fresh.
"""

import hashlib
import json
import time

from google.genai import types

from .client import client
from .config import CACHE_TTL, MODEL

FLOOR = 4096   # Gemini 3.x. Below this it silently does not cache.


def key(system_instruction, tool_decls):
    # MODEL is part of the key because a cached content object belongs to the
    # model that created it. Without this, switching model reuses the other
    # model's cache: caches.get() succeeds, and generate_content then fails on
    # the mismatch -- a confusing error a long way from its cause.
    h = hashlib.sha256()
    h.update(MODEL.encode())
    h.update(system_instruction.encode())
    for d in tool_decls:
        h.update(d.name.encode())
        h.update(json.dumps(d.parameters_json_schema or {}, sort_keys=True).encode())
    return h.hexdigest()[:16]


def _store(notebook):
    return notebook.run / "cache.json"


def _remember(notebook, k, name):
    notebook.run.mkdir(parents=True, exist_ok=True)
    _store(notebook).write_text(json.dumps(
        {"key": k, "name": name, "created": time.time()}))


def _recall(notebook, k):
    p = _store(notebook)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except ValueError:
        return None
    if d.get("key") != k:
        return None
    # TTL is a server-side lease; treat our own record as stale a little early
    # rather than discovering expiry mid-run.
    if time.time() - d.get("created", 0) > int(CACHE_TTL.rstrip("s")) - 120:
        return None
    return d.get("name")


def build(notebook, system_instruction, tools, verbose=True):
    """
    Return a cache handle, reusing one when the prefix has not changed.

    Returns None when the prefix is under the floor -- the caller then passes
    system_instruction and tools inline and implicit caching does what it can.
    """
    decls = [d for t in tools for d in (t.function_declarations or [])]
    k = key(system_instruction, decls)

    existing = _recall(notebook, k)
    if existing:
        try:
            client().caches.get(name=existing)
            if verbose:
                print(f"  cache     reused {existing.split('/')[-1]}")
            return existing
        except Exception:
            pass   # expired or deleted server-side; fall through and rebuild

    try:
        c = client().caches.create(
            model=MODEL,
            config=types.CreateCachedContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                ttl=CACHE_TTL,
                display_name=f"nb-{notebook.root.name}"))
    except Exception as e:
        # The floor is the overwhelmingly likely cause, and the server says so
        # only obliquely. Carry on uncached rather than failing the run.
        if verbose:
            print(f"  cache     not created ({str(e)[:90]}) -- running uncached")
        return None

    _remember(notebook, k, c.name)
    if verbose:
        n = c.usage_metadata.total_token_count
        print(f"  cache     created {n} tokens"
              f"{'' if n >= FLOOR else f' -- UNDER THE {FLOOR} FLOOR, will not cache'}")
    return c.name
