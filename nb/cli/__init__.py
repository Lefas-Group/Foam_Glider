"""
One module per command, and nothing else.

It was `phases/`, from when a run had two -- probe-and-propose, then write --
with `proposal.json` between them. There is one phase now, so the directory name
described nothing; and two of its files were not commands at all. `write.py` was
the 600-line post-typing pipeline (freeze refresh, prose read-back, commit) and
is `build/publish.py`; `common.py` is the setup two commands share.

So the rule this directory can now state: a file here is a `nb <verb>`, and
`__main__.py` dispatches to its `main()`.
"""
