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


def _stored(notebook):
    p = _store(notebook)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def _recall(notebook, k):
    d = _stored(notebook)
    if not d or d.get("key") != k:
        return None
    # TTL is a server-side lease; treat our own record as stale a little early
    # rather than discovering expiry mid-run.
    if time.time() - d.get("created", 0) > int(CACHE_TTL.rstrip("s")) - 120:
        return None
    return d.get("name")


def _release(notebook, verbose=True):
    """
    Delete the cache this notebook last created, if any.

    Storage is billed per token-hour for as long as an explicit cache is held --
    $4.50/1M/hour on Pro, so a ~14k prefix is about 6c an hour. A run uses its
    cache for two or three minutes and then supersedes it, because the manifest
    changes on commit and the manifest is part of the key. Without this the
    orphan bills for the remaining fifty-seven minutes, which was roughly 40% of
    what the cache saved in the first place.

    Never fatal: an already-expired handle 404s, and losing a cache is a cost
    problem, not a correctness one.
    """
    d = _stored(notebook)
    if not d or not d.get("name"):
        return
    try:
        client().caches.delete(name=d["name"])
        if verbose:
            print(f"  cache     released {d['name'].split('/')[-1][:12]}")
    except Exception:
        pass          # already expired, or deleted by hand


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

    # Superseding: whatever the record names is about to be replaced, whether the
    # key changed (a commit moved the manifest) or the lease went stale. Release
    # it before creating the next one so only one is ever held.
    #
    # Single-user CLI assumption: two runs building at once could release each
    # other's cache. The loser rebuilds, which costs a cache-write, not a run.
    _release(notebook, verbose=verbose)

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


def release(notebook, verbose=True):
    """Public: drop the cache this notebook holds. See `_release`."""
    _release(notebook, verbose=verbose)


def main(argv):
    """
    python -m nb.cache <notebook> [--purge]

    Lists what is held and what it costs. `--purge` deletes every cache on the
    account -- for orphans left by a crashed run, which bill until their TTL
    expires with nothing to show for it.
    """
    import sys
    from .config import Notebook

    if not argv:
        print(main.__doc__.strip())
        return 2
    Notebook(argv[0])          # validates the path

    caches = list(client().caches.list())
    if not caches:
        print("  no caches held")
        return 0

    total = 0
    for c in caches:
        n = c.usage_metadata.total_token_count
        total += n
        print(f"  {c.name.split('/')[-1][:12]}  {n:>7,} tokens  "
              f"expires {c.expire_time:%H:%M:%S}")
    # Pro rate. Flash is $0.50/1M/hr, so this over-reports there -- deliberately,
    # since the number is only ever used to decide whether to bother purging.
    print(f"\n  {len(caches)} held, {total:,} tokens — "
          f"~${total * 4.50 / 1e6:.4f}/hour at the Pro storage rate")

    if "--purge" in argv:
        for c in caches:
            try:
                client().caches.delete(name=c.name)
                print(f"  deleted {c.name.split('/')[-1][:12]}")
            except Exception as e:
                print(f"  could not delete {c.name.split('/')[-1][:12]}: {e}")
        _store(Notebook(argv[0])).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
