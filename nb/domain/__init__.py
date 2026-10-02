"""
What a notebook IS, apart from how it is checked or built.

`inputs` is the declared record -- what a chapter was told and what it assumed,
with the ids that `ask_specified` and `_fork.yml` both take. `manifest` is the
chapter manifest, this system's substitute for memory across runs.

`config.Notebook` belongs here too and has not moved: it is imported as
`..config` by nearly every module, and `config.py` also holds the model settings
and the budgets, which are not domain. Splitting that file is its own decision.
"""
