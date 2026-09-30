# Why the baseline moved

`characterize.py` exists to say "nothing changed". So every time it legitimately
has to change, the reason belongs here — the same discipline `nb/corpus.py`
applies to `EXPECTED`, and for the same reason: a baseline that can be
regenerated without justification stops being evidence of anything.

A line here is a claim that the diff was intended. If you cannot write the line,
the diff is a bug.

---

## Phase 1 — un-vendoring

**Changed:** two findings, one each in `aircraft-notebook` and
`optimised-glider-notebook`. Rule 11's message names the canonical
`_notebook.py` it compared against, and that file moved:

```
- differs from …/nb/vendor/notebook.py (first at line 15) — copy the canonical …
+ differs from nb/vendored/notebook.py (first at line 15) — copy the canonical …
```

**Why:** `nb/vendor/` held five modules and only `notebook.py` was ever vendored
into a notebook; the other four were there so `config.py` could put them on
`sys.path`. They are ordinary `nb` modules now, and the one genuinely vendored
file moved to `nb/vendored/`, where the word is true.

The finding itself is unchanged — same file, same line, same remedy. Only the
path it quotes moved, which is the change.

**Also in this entry:** the harness now strips the repo root from messages before
recording them. Rule 11's message carried an absolute path, so the baseline was
valid on exactly one machine. This is a change to the harness, not to lint.

**Not fixed here, deliberately:** that lint emits an absolute path to the model at
all. Making it repo-relative would be an improvement to a message, and phase A
may not change messages. It belongs with the phase 7 sweep.
