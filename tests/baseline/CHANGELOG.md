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

## Phase 6 — attribution

**Changed:** the `rule` field of 101 of 143 findings, from `None` to a number.
Nothing else. `(where, msg)` is byte-identical on all three notebooks, which is
what the default projection checks and what it reported throughout.

**Why:** 21 of the 40 declared rules could not name themselves. Ten were written
as code blocks inside `check()`, sharing its locals — a block in a loop has no
name to register. Eleven were bundled into four functions, each enforcing several
rules, so a finding from `_budget_rules` genuinely could not say whether it was
16, 17, 18 or 28.

All 40 now do. `tests/characterize.py --check --strict` passes, which is what it
was built to be able to say.

**One finding still carries `None`, and always will.** The transcription warning
(`_transcribed`) is a warning outside the numbered contract — it has no rule in
`RULES` and is registered with no number. So strict mode asks
`contract.unattributed()` whether every *declared* rule is attributable, rather
than failing on any `None` in the findings, which it could never pass.

**Faithfulness note.** Rules 21 and 22 were an `if/elif`: a helper nothing calls
at all reported 21 and stopped. Split naively they would report both, which is a
finding that did not exist before. Rule 22 therefore now tests `internally[n]`
explicitly — that is exactly the branch the `elif` reached, and why the counts
did not move.

## Phase 8 — no vendoring, no facade

**Changed:** rule 11's message on two notebooks. It names the file it compared
against, and that file moved; the remedy sentence changed too:

```
- differs from nb/vendored/notebook.py … — copy the canonical version down, or
  promote the local change up so every notebook gets it
+ differs from nb/scaffold/_notebook.py … — the copy here is the one that
  renders, so decide which is right: take the seed's version down, or lift this
  change up into it
```

**Why the path moved.** `nb/vendored/` held one file and existed to hold it.
That file is copied into each notebook by `nb new`, alongside `_model.qmd`,
`_quarto.yml` and five other templates — which is what `nb/scaffold/` is for. It
is the eighth scaffold file, not a vendored library, and "vendoring" was a word
left over from when four modules that were never copied anywhere shared the
directory with it.

**Why the remedy changed.** It used to end "so every notebook gets it", which was
true when four notebooks were kept in step and is now an argument about a set of
size one. The honest remedy is two-way and says so: the notebook's copy is the
one that renders, the seed is what the next notebook starts from, and a person
decides which way a difference goes.

**A behaviour fix rides along, with no finding to show for it.** Rule 27 asks
which names an entry must not rebind, and read them from `MACHINERY`, computed
**once at import** from the seed. So the two notebooks whose `_notebook.py` has
drifted were checked against a name list their own file does not bind — 43 names
against their actual 12 and 27. It reads the notebook under test now. No finding
moved, because no entry in the corpus rebinds a name in the difference; the rule
was simply reading the wrong file.
