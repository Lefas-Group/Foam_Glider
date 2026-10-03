# Reconstruct: one brief, one entry

Written 2026-10-03, after `2c38a74 skillupgrade` shipped and a second Mustang
programme ran against it. Nothing here is implemented yet.

## Where the last plan got to

Two programmes, same aircraft, same published specification — one before the
changes, one after.

| | first | second |
|---|---|---|
| `declare_input` calls, of which geometry | 4, **none** | 10, **all** |
| stalls, turn-cap hits, human unsticks | 1, 1, 2 | 0, 0, 0 |
| wing loading vs published 29.9 g/dm² | 36.0, **+20 %**, unnoticed | 32.4, **+8.3 %**, stated as the answer |

The loop works. What remains is an 8.3 % reconstruction error and a three-view
that is recognisably a Mustang but not this Mustang.

## The problem, attributed

Four items reached the model as guesses:

| missing | why |
|---|---|
| tail moment arm | one number on the full-size page — **not measured** |
| vertical stab area | one number — **not measured** |
| dihedral | *"gauge on plan, angle unread"* — **not read** |
| fuselage cross-sections | 8 × 4 numbers — **no good home** |

All six reached the assumptions prompt. The coordinator answered in **61 s of
a 480 s window** and corrected **one**. So this was never a missing channel
and never time pressure — seven minutes went unused. What was missing was any
basis for choosing between them.

And every fuselage station used `shape=4`, AeroSandbox's superellipse exponent
where 2 is a circle and high values approach a rectangle. That is why the
render is a smooth pod where the real aircraft is a slab-sided foam box with a
step behind the canopy. Nobody specified it, and nobody could have known to —
**the coordinator wrote nineteen rows of description without ever seeing what
they produced**, until an entry rendered five minutes later and committed.

## The split that decides the design

- **Numeric convergence** — does the model hit the published scalars? This is
  arithmetic, and it is the iterate-to-tolerance shape the ordinary entry
  contract discourages. The agent is good at it.
- **Visual resemblance** — does it look like the aircraft? Measured evidence
  says the agent is poor at this: *"Ah, finally, a clean one! … no cropping,
  no awkward edges"*, written while looking at an airframe that did not
  resemble a Mustang.

The difference is not eyesight, it is the **reference**. The agent was asked
"is this figure OK?" with nothing to compare against, so it answered about
composition. The coordinator holds the plan and the photograph, because the
coordinator fetched them.

**The agent converges on numbers; the coordinator judges resemblance.**

## 1. It all goes in the brief

No new file. `_inputs.yml` gains a third block beside `specified:` and
`assumed:`.

```yaml
specified:
  - subject:      "**FT Mighty Mini Mustang MKR2**, from the Flite Test plan."
  - construction: "**Folded Maker Foam**, hand cut and hot glued."
  - span:         "**Span**: 622 mm (24.5 in) tip to tip."
  - layout:       "**Low wing**, tractor prop, conventional tail."
  - fuselage:     "**Fuselage**: slab-sided box, stepped behind the canopy."
  - power:        "**Power**: 2205 2300 kv, 6x4.5 prop, 3S."
  - controls:     "**Controls**: aileron, elevator, rudder; 12 deg throws."

targets:
  - wing-area:    "**Wing area**: 7.42 dm2 (115 in2), +/-2%."
  - auw:          "**All-up weight**: 222 g with 850 mAh pack, +/-5%."
  - wing-loading: "**Wing loading**: 29.9 g/dm2 published, +/-3%."

assumed:
  - landing-gear: "**Landing gear**: not modelled, retracted in cruise."
  - claimed-speed: "**Claimed top speed** 87 km/h on 3S, to verify."
```

**Why the brief and not a `chapters/_reference.md`.** Three costs vanish:

- **The guard is free.** `_inputs.yml` is at the notebook root, *outside the
  sandbox* — run `a21b` tried `search_files(path="..")` and got *"Access
  denied"*. A file under `chapters/` is writable by a run and would have
  needed a new guard.
- **No prefix line, no read instruction.** The brief is already quoted in full
  in the prefix on every call.
- **It renders on the overview**, so a reader sees what the reconstruction is
  held to, on the front page.

**Targets are their own block, not inferred.** The second programme already
wrote `"**Horizontal stab**: span 213 mm, area 16 in2, +/-10%."` — a tolerance
on a *measurement*, not a target. Sniffing for `+/-` would misread it. A
`targets:` block is unambiguous and costs a small parser change.

**Targets are facts, never claims.** Area, mass and CG are things the model
must reproduce or it is not this aircraft; `top speed 87 km/h` is what the
programme exists to judge and stays an `assumed:` row. Put a claim in
`targets:` and the run will adjust drag until it hits, fitting the model to
the thing it was built to test.

**Most targets cost no measuring.** Length, CG, span, area, dry weight, AUW,
wing loading and cubic loading are *printed on page one* of the plan. Reading
them is cheap and always worth it — that is the number that caught the 8.3 %.
Pixel-measuring tiles is the expensive part, and it is **demand-driven**: do
it when a target misses or the three-view looks wrong. The second programme
measured root and tip chord speculatively and left unmeasured the four things
that mattered.

**Shape goes in as prose, not coordinates.** *"slab-sided box, stepped behind
the canopy"* is two rows and would have prevented the pod. The failure was
nobody saying it, not nobody supplying a station table. If a stitched,
measured station table ever does materialise and reads badly as brief rows,
add a file then — with evidence rather than in anticipation.

**The brief shrinks.** The second programme ran to nineteen rows because there
was nowhere else to put things, including four "not extracted" apologies.
Those disappear: their absence from `targets:` is the signal, and the run
declares what it had to assume.

## 2. `nb reconstruct` writes one ordinary entry

**It produces an entry, in a chapter that already exists.** `nb new` makes the
chapter; `nb reconstruct <nb> --chapter 01-…` writes its first entry and
leaves `_model.py` as the chapter's vehicle. Nothing new is created.

And the entry is **conventional** — a question, a hero value, two visuals:

```
Can we reconstruct the FT Mighty Mini Mustang within tolerance?

1.8% — worst error across published targets

[three-view]  [bar chart: error vs tolerance, per target]
```

That is what the second programme's first entry already was, reached through
`nb ask`. Which means **no new output format and no contract exception**:
rule 14 already allows two visuals when one draws the aircraft, which is
exactly `three-view + error chart`.

```
nb reconstruct <nb> --chapter X
    probe, build from the brief, render a three-view, declare
 -> PROMPT: assumptions + three-view + target table
 -> "2: 8.2 in2"                              correct a number
    "4: redo — fuselage is a slab-sided box"  reject the shape
 -> re-probe, rebuild, re-render, prompt again
 -> ... until Enter
 -> iterate to targets, write the entry, commit.
```

**No new agent tool.** An earlier draft proposed `preview_model()`; the run
can already build in a `probe`, and `probing.md` already tells it to
`fig.savefig("_scratch/_probe_fig.png")` and `read_figure` the result. All
that is structurally required is that **the prompt names a figure** — one line
of wiring, plus a line in the brief saying to render one before opening the
entry. If the run skips it the prompt has no figure: degraded, not broken.

**The iteration loop already exists.** `interact.py:1023` — a rejected
assumption does not end the run; it hands the rejection back and tells the run
to re-probe, revise with `declare_input`, and call `open_entry` again, which
re-fires the prompt. The coordinator can reject a shape, see it rebuilt and
reject again, inside one run, with no new machinery.

**Cheap, because `ask` and `resume` are already two briefs into one shared
`_execute`** (`run.py:233` and `:400`). A third is idiomatic. **The targets
gate is the only genuinely new machinery in this plan**: parse `targets:`,
compute, compare, iterate.

**Why the loop is needed despite the gate.** Targets are numeric, and a model
can hit area, mass and wing loading with a completely wrong fuselage — which
is what happened: 8.3 % out on area *and* a smooth pod. A numeric gate would
never flag the pod. Left to run on a bad brief, the targets loop would
converge around the wrong shape and commit it looking like a success.

**The targets block defines what "reconstructed" means**, and it scales:

| `targets:` | what the run is gated on |
|---|---|
| empty | build it and show me — the eye at the prompt is the only gate. Shape-first work: the X-Wing, a pig |
| geometry only | span, area, MAC, tail volume. No mass model needed |
| geometry and mass | the full published spec sheet |

Same command throughout, no mode flag, and the shape-first case needs no
separate machinery.

**Why a separate brief** rather than asking through `nb ask`: reconstruction
is converge-to-tolerance, and the ordinary contract is built for answering a
question once. Rule 5 bans `for … in range()` around a solve; rule 6 caps
prose at 100 words. The closing gate differs too — targets met, not question
answered.

**Budget.** Iterating inside a live run holds the chapter lock and spends the
run's turns: five rejections means five rebuilds. A reconstruct run wants a
larger probe pool and turn cap than an ordinary question — reasonable for a
once-per-chapter activity.

### Controlling it without new rules

**No new lint rules.** The existing contract already does the work:

- **Rule 1** — no hand-typed number in prose. Any error the entry quotes must
  be a `{python}` expression, so the comparison is computed, not asserted.
- **Rule 41** — the hero derives from a solve, not a literal. The hero is the
  worst target error, so it cannot be typed in.
- **Rule 14** — two visuals when one draws the aircraft. Exactly the pair this
  entry wants.
- **Rule 3, 6, 26** — answer before the last cell, 100 words, one question.
  All apply unchanged.

Everything else is **brief text**, which is free: render a three-view before
opening the entry; report every target with its error; say which targets
failed rather than quietly loosening them. A rule that could only be written
fuzzily belongs in the brief, by the same test that kept rule 43 a count
rather than a judgement.

The one thing that is *not* instruction is the gate itself — compute the
targets, compare, and refuse to finish while one is out of tolerance without
saying so. That is code, and it is the only code this item adds.

## 3. Fold the brief into the inheritance system

`prefix.py:138` and `_inputs.root.yml.tmpl` say the brief is *"never
superseded"*. Too strong: doubling the span is the same programme, and forcing
it into a new notebook throws away the lineage — which this repo already pays
for, since `glider-notebook` is the X-Wing at a different foam thickness with
no link back.

**Keep authorship, drop immutability.** `_inputs.yml` stays written by a
person, never a run; but a run changing a row already needs `ask_specified`
and a fork approval, both of which put a person in the loop. So the notebook
root becomes the root of the ancestry chain: `domain/inputs.py` walks the
brief as the oldest ancestor, `_active.yml` carries its rows keyed
`brief/<handle>`, and `_fork.yml`'s `overwrites:` can name one.

This deletes the second chapter-page callout from the previous plan — once the
brief is an ancestor, `_active.yml` already contains it. Visibility comes from
the lineage diagram, not a ledger: with several forks each overwriting
different rows there is no notebook-wide answer to "what is in force", only a
per-chapter one, which the chapter page already gives.

## 4. Two sections on the overview

**The aircraft** — the brief as declared, now including the targets.
**Chapters** — the lineage diagram, alone. Rule 34 checks the front page's
generated block is intact, so this goes through the scaffold and rule 34's
checker moves with it.

## Deferred, with triggers

- **An autonomous builder loop.** Every rejection costs a coordinator turn,
  and the run starts each rebuild without the reasoning behind the last one. A
  builder keeping its own conversation would be cheaper in coordinator turns,
  the cost that matters. **Trigger:** dialling in one aircraft takes many
  rejections rather than two or three.
- **Plan access for the reconstruct brief.** Reproduction is its whole job, so
  the honesty argument that bars it from ordinary runs is weaker here.
  **Trigger:** the reject-at-prompt loop proves insufficient. Costs unchanged:
  ~1,300 tokens per page, rasterising, and a listing saying whether an asset
  is a photograph (proportions) or an orthographic plan (dimensions).
- **A file for tabular geometry.** **Trigger:** a stitched, measured station
  table actually materialises and reads badly as brief rows.

## Rejected

- **`chapters/_reference.md`.** Everything it held fits in the brief, which is
  outside the sandbox (so the guard is free), already in the prefix (so no
  read instruction), and rendered on the overview (so the targets are
  visible).
- **A `preview_model()` tool.** Everything it would do is already available
  through `probe` and `read_figure`; only the prompt wiring was ever needed.
- **A separate `nb preview` command.** A second code path that writes
  geometry, and so one that can diverge from what ships.
- **New lint rules for reconstruct entries.** Rules 1, 41 and 14 already force
  the comparison to be computed and the visuals to be right; the rest is brief
  text.
- **A three-view on the overview.** That page executes nothing by design:
  `index.qmd` deliberately omits `_model.qmd` because `_notebook.py` imports
  aerosandbox and matplotlib — *"the whole point of this page is that it reads
  source and executes none of it. It re-renders on every commit; it costs 10 s
  because nothing here imports a model."* A three-view needs the model built,
  so it would break that and slow every commit. Unnecessary anyway: the
  reconstruction is entry 01, so the aircraft is the first thing a reader
  meets, and that figure re-renders from the model where a pasted copy would
  go stale.
- **Plan access for ordinary runs.** The six declarations exist *because* the
  run could not verify them; `why: "Plan unextracted"` is the most useful
  thing it produced. A measurement it cannot make is one it must declare; one
  it can *almost* make is one it will claim.
- **A structured `_geometry.yml`.** AeroSandbox schema in the coordinator's
  hands, and it presupposes topology.
- **Handing a description to a separate consumer to rebuild from.**
  Descriptions are not fully determining, so expecting a different agent to
  reproduce one is incoherent. Resolved by the run writing the model.
- **A provenance-marking convention.** The second programme already wrote
  *"Plan unextracted; physical geometry"* in `why` unprompted.

## Order

1. **Item 1** — the `targets:` block and a shorter brief. Small parser change;
   item 2 reads it.
2. **Item 2** — the brief and prompt wiring first, then the targets gate.
3. **Item 3**, then **item 4**.

## Outstanding

- Reconstructed wing area 6.85 dm² against a published 7.42 — wing loading
  +8.3 %. Items 1 and 2 are the fix; re-run the first entry afterwards.
- Top speed is 150.4 km/h against a claimed 87 km/h, **+74 %**, and the gap
  survived grounding the propeller polar in APC manufacturer data — an
  independent source, which is what makes the finding strong. The model says
  the aircraft is pitch-speed limited with a 9.1× thrust excess at the claimed
  speed. Either the claim is not a top-speed figure or the drag model is badly
  low. That is the obvious next question.
- The first programme's brief lost two words from `_inputs.yml`, a file a run
  never writes, and nothing in `nb` accounts for it. That notebook has been
  deleted, so the evidence is gone. Watch for a recurrence — item 3 raises the
  stakes, since a brief that *can* be overwritten should be overwritten only
  through the fork gate.
