"""Output shaping. Every handler truncates its own result before returning."""

from .config import TRUNCATE


def tail(s, cap=TRUNCATE):
    """For anything that fails at the end: tracebacks, solver output, renders."""
    s = s or ""
    return s if len(s) <= cap else f"[... {len(s) - cap} chars elided ...]\n{s[-cap:]}"


def head(s, cap=TRUNCATE):
    """For anything that matters at the start: listings, file contents, search."""
    s = s or ""
    return s if len(s) <= cap else f"{s[:cap]}\n[... {len(s) - cap} chars elided ...]"
