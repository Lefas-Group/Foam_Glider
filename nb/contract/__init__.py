"""
The lint contract: what makes an entry well-formed, checked without running it.

Pure by intent -- an `Entry` or a `Chapter` in, findings out. Nothing here
renders, shells out or touches git; that is `nb/build/`. The rules themselves
still live in `nb/lint.py` and move here next, which is why this package holds
only `parse` for now.
"""
