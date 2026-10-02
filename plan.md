# Sourcing geometry, and the clause that skipped it

Written 2026-10-02. Replaces the kernel plan, which is implemented — every run
below carries a `kernel.log` and spent 17–67 probes without exhausting its
pool. Nothing here is implemented yet.

Evidence throughout is one programme, `mighty-mini-mustang`, three committed
entries reconstructing the FT Mighty Mini Mustang MKR2 from its published
specification:

| run | question | tool calls | outcome |
|---|---|---:|---|
| `20261002-100435-b81e` | does it hit the claimed 156 g dry? | 103 | `max_turns`, resumed, stalled once, committed |
| `20261002-101821-023a` | level-flight stall speed? | 35 | committed |
| `20261002-102433-a21b` | what does it look like? | 44 | committed |

## The problem

All three entries are wrong in the same way, and the notebook cannot tell.

The brief carried seven scalar rows — span, area, aspect ratio, CG, power,
controls, construction. Nothing about form. Every other dimension in
`_model.py` was supplied by the model from its own memory of what a Mustang
looks like:

```python
c_root_w = 0.140      c_tip_w = 0.0986     dihedral_w = 3.0
x_le_w   = 0.120      b_h = 0.240          b_v = 0.120
fuse: 6 superellipse stations, shape=4.0, 485 mm long
S_fuse_shell = 0.0873   S_turtle_canopy = 0.0220   S_belly_scoop = 0.0150
S_formers_doublers = 0.0100   S_power_pod = 0.0200
```

Only `b_w` and `S_w_spec` came from the brief. Three consequences, in
increasing order of seriousness:

- **The mass answer may be an artefact.** Those five foam areas total
  0.134 m² — nearly twice the wing — and are ~47 g of the 87.2 g foam total.
  The headline finding was 195.2 g against a claimed 156 g. The 39 g overshoot
  is within the span of the invented areas.
- **The stall answer rests on a substitution.** The wing uses
  `asb.Airfoil("naca0006")` while the brief Specifies flat plate. Commented,
  never declared.
- **The notebook claims a provenance it does not have.** `_model.py` carries
  `# Reference surface areas of cut foam parts from FT plan sheet`. An invented
  number is wearing a citation.

Across 182 tool calls there were **four** `declare_input` calls — foam density,
electronics, hardware, glue. All mass, none geometry. The one that was declared
is the one that got corrected: the coordinator checked 348.7 g/m² against Flite
Test's own measurement at the assumptions prompt. The mechanism works. It was
never reached.

And the entry whose job was to show the shape certified itself — *"faithfully
matches the Flite Test planform … within 0.006 %"* — by comparing the model
against the two numbers the brief supplied. Circular, and it reads as external
validation.

**And the plan was one search away.** Nobody looked.

### The clause that caused it

`nb/agent/schema.py:44-51`, the `source` field description, ends:

> *"guessed: nobody knows, a different answer changes HOW ACCURATELY it is
> modelled, so you assumed it and said what it costs. **If the model or the
> plans already contain it, it is none of these: compute it.**"*

That last sentence assumes the plans are **present**. The run classified taper
ratio as a plan-derived quantity — correctly, it is on the plan — and the
instruction says plan-derived quantities are "none of these", so it did not
declare, it just wrote the number. Then it wrote `# from FT plan sheet`,
because that is the category it had been told to assign.

The agent followed the instruction. The instruction has a hole for the case
where the quantity is on a plan nobody has.

### The prompt fires at exactly the right moment

Call ordering in `b81e`, which decides the shape of item 1:

| call | what |
|---:|---|
| 50 | first probe touching geometry |
| 52–55 | the four `declare_input` calls |
| — | **assumptions prompt fires here** |
| 56 | more geometry probing |
| 60 | `_model.py` written |

So the prompt lands as geometry work begins and **before the model file
exists**. A correction there costs roughly one probe of rework — not a
rebuild, not a re-render. This is the cheapest point in the run at which a
wrong dimension can be caught, and it is already built.

## What the plan actually contains

Retrieved 2026-10-02, 462 KB, 18 pages, http 200, now committed to the notebook
root as `FT-Mini-Mustang-v1.0-Tiled.pdf`:

```
s3.amazonaws.com/plans.flitetest.com/stonekap/FT Mini Mustang v1.0 Tiled.pdf
```

Page 1 is a specification table:

| | imperial | metric |
|---|---|---|
| Length | 19 in | 482 mm |
| CG | 1.00 in | 25 mm |
| Wing span | 24 in | 622 mm |
| Wing area | 115 in² | 7.4 dm² |
| Dry weight | 5.5 oz | 156 g |
| **All-up weight** | 7.8 oz | **222 g** |
| **Wing loading** | 9.8 oz/ft² | **29.9 g/dm²** |
| Wing cubic loading | — | 10.9 |

Page 2 is a drawing key, and every entry in it is a fold type — A (above),
B (beside), C (cover). **The plan folds the wing.** The flat-plate row in the
brief is wrong at the source, not merely approximate.

**Measurement off the tiles is feasible and self-calibrating.** FT tiles print
at 100 %, and each carries an inch/cm scale bar, so `pdftoppm -r 150` yields
real millimetres directly from pixel counts — no span-scaling, no perspective
correction. Verified on tile 5 (`REAR TURTLE DECK`): page renders 7.5 × 10.5 in
at 150 dpi, outline recovered by thresholding at 128. One real cost: tiled
plans split parts across page boundaries, so an exact planform needs the tiles
stitched first. Scriptable, not free — and the reason item 1b has a time
problem.

**Identity caveat.** This is the FT Mini Mustang **v1.0**; the programme's
subject is the **Mighty Mini MKR2**. Same 115 in² area, 156 g dry weight and
25 mm CG, but 24 in span against the store page's 24.5 in. Same lineage, not
provably the same airframe. Do not transplant its numbers without checking.

### A quantified defect in a committed entry

`023a` computed 36.0 g/dm² wing loading from the invented 195.2 g dry mass and
derived an 8.80 m/s stall. The plan publishes **29.9 g/dm²**. That is 20 % high,
and the stall speed is overstated with it — nearer 8.0 m/s at the published
loading.

No longer a suspected weakness: a measurable error in committed work, and the
strongest argument for item 1. The number that would have caught it was on page
one of a free PDF, before any modelling began.

## A principle for the lint items

**A rule that misses is worse than no rule**, because "lint clean" stops
meaning *checked* and starts meaning *probably fine*. That false assurance is
the same disease as the false citation.

So: lint reports facts it can compute exactly — counts, diffs, presence. Where
only a fuzzy match is available, the rule belongs in the system instruction
instead, where it reads as guidance rather than a guarantee.

## The changes

### 1. The coordinator holds the source — skill only, no code

Two halves. Neither needs a mechanism built; both are skill text.

**1a — fetch before the first ask.** Minimal, not exhaustive:

> **If the aircraft already exists, find its plan before the first ask.** The
> agent cannot research — no network, sandboxed to `chapters/`. Every
> dimension you do not supply, it supplies from memory.
>
> FT plans are free, print 1:1 and carry a scale bar, so `pdftoppm -r 150`
> measures them in millimetres. **Page one is usually a specification table —
> read it before modelling anything.** Commit the file at the notebook root,
> as `RADICAL-GLIDER` already does with its X-Wing plan: a dated local copy
> outlives any URL.
>
> Put the headline specs in as `--spec` rows. `MAX_CALLOUT_ITEM = 10`
> (`contract/shared.py:204`) caps words **per row** and nothing caps the number
> of rows, so a dimension table fits — but do not transcribe one
> speculatively. 1b is better targeted.

**1b — check the assumptions prompt against the plan.** This is the half that
closes the loop, and it needs *nothing built at all*:

> When the assumptions prompt lists a dimension of the real aircraft and you
> hold the plan, check it before accepting. Correct with `N: <value>`, or send
> it back with `N: redo — why`. **Accepting a number you could have checked is
> how the taper ratio got in.**

The prompt is already a list of every number the run invented, shown to the
only party holding the plan, at the cheapest moment to change one (see the call
ordering above). It already accepts corrections. The capability has been there
the whole time; the instruction to use it has not.

**Why 1b beats transcribing up front.** Transcription is speculative — twenty
rows written, six used. At the prompt the run has named precisely which
dimensions it needs. Demand-driven beats guessing, and 1a exists mainly to make
1b fast: answering means reading a PDF already on disk rather than searching
the web inside a five-minute window.

**1c — the five-minute default is the one real constraint.** `interact.py:207`
builds the confirmation list, and the prompt takes a safe default after five
minutes. That is enough to correct a number already known; it is not enough to
rasterise and stitch tiles to measure one. The only code change item 1 needs:
a longer default when the batch is large, or a reply that buys time. Without
it, 1b silently degrades to accepting whatever was guessed.

### 2. Fix the clause

One string in `nb/agent/schema.py:50-51`:

```
  ...If the model or the plans already contain it, it is none of these:
  compute it.

→ ...If the MODEL already contains it, compute it. If a document would
  contain it but you do not have that document, it is guessed — declare it
  and say it was not measured.
```

No enum change, no `Literal` widening, and **none of the three `interact.py`
dispatch sites need touching** (`:207` building the confirmation list, `:886`
and `:1067` rendering Specified-vs-Assumed). Those three were the bulk of the
cut `recalled` proposal and the part most likely to silently no-op if one were
missed. Deleting that proposal removes the risk with it.

### 3. Make geometry reach the declaration, and sort it for the reviewer

The reworded clause removes the excuse; this makes the habit explicit and makes
1b fast to act on.

- **`system_instruction.md`** — a dimension of a real object not supplied in
  the brief is `guessed`, declared when written, not at the end. One input per
  *decision*, not per number: "fuselage cross-sections, assumed from
  photographs" is one row, not eighteen. That granularity rule already exists
  for inputs generally and only needs applying.
- **Mark object properties apart from modelling choices.** *Is this a property
  of the physical aircraft, or a choice about how to model it?* Taper ratio and
  glue mass are properties; `naca0006` is a modelling choice. Unlike "is this
  on the plan", this **is** decidable from inside the sandbox — it is about the
  nature of the quantity, not about what documents exist. Marking it in `why`
  tells the coordinator at a glance which rows 1b should check against the plan
  and which are the run's own decisions. A convention, not an enum value.
- **Never attribute a number to a document unless it was read in this run** —
  system instruction, not lint. An earlier draft made this a regex over *from
  the plan* / *per the drawing*; cut, because it catches one phrasing and
  misses the next, and a missed false citation is precisely the failure being
  guarded. Close to redundant once item 2 lands anyway.
- **An exact lint report, not a judgement.** Parse `_model.py` with `ast`,
  count module-level numeric constant assignments, print it beside the number
  of declared inputs: *"`_model.py` assigns 23 numeric constants; this chapter
  declares 4 inputs."* A computed fact with no semantics and no false
  negatives. It does not claim to find geometry — it reports a ratio and leaves
  the judgement to the human at the prompt.

### 4. Plumbing — the Q1 stall

Three independent causes, all cheap, all measured in `b81e`:

- **`search_files` returns absolute paths; `list_directory` returns bare
  names.** The first call returned
  `/Users/…/mighty-mini-mustang/chapters/01-mustang-as-drawn`, from which the
  run concluded paths look like `chapters/01-…`. Return root-relative paths.
- **`mcp_fs.py:156` strips both `chapters/` and the notebook name**, so
  `chapters/01-x/f` and `01-x/f` both resolve. Forgiving, but the run was never
  corrected and oscillated between the two forms for 103 calls. Keep accepting
  both; echo the canonical form back.
- **Resume is blind.** `nb resume` restored a run whose `stem` was set without
  telling it an entry was already open. It read for a file that did not exist,
  then ran `list_directory .`, `list_directory 01-…`, `search_files *`,
  `search_files **/*` back to back and hit `NO PROGRESS`. That episode is most
  of why Q1 needed two human interventions. Inject a state summary on resume:
  entry open, stem, what is written.

### 5. Figure read-back: ask whether the shape is right

The run looked at its own three-view twice. Its reasoning, verbatim:

> *"Ah, finally, a clean one! … That top-down and front view are perfect; I can
> see those wingtips with plenty of breathing room, no cropping, no awkward
> edges."*

It inspected a drawing that does not resemble a Mustang and passed it, because
the read-back instruction is about rendering quality — clipping, centring,
legibility — and never about fidelity. Add the fidelity question for any entry
drawing a reconstructed airframe. An instruction, not a rule; weak without a
reference in front of it, which is why it is last.

### 6. Show the brief on every chapter page

**For the reader, not the agent.** The agent already has the brief in full:
`prefix.py:137` emits it under *"## The aircraft — true of EVERY chapter"*, and
`prefix.py:282` says it is "reproduced in full further down this prompt" so no
turn is wasted trying to read a file above `chapters/`. The delivery channel
works — which is also why item 1a will land.

The chapter *pages* do not show it. `_notebook.py:912` reads `_active.yml`,
which `nb` builds from the ancestor **chapter** chain only. For a root chapter
that file is empty, so `if not total: return` prints nothing — and the
docstring justifies it: *"right … for a root chapter, which inherits from no
one."*

That is wrong. A root chapter inherits the brief; the prefix says so in as many
words. A reader opening `01-mustang-as-drawn` sees no constraints at all when
seven are in force.

- **Render the brief rows alongside the inherited ones**, and retitle
  *"Maintained from earlier chapters (N)"* to something that covers both —
  *"Specifications and assumptions in force (N)"*. Every chapter then carries
  the block, including the first.
- **Keep the two kinds distinct inside the callout.** A brief row can never be
  superseded — departing from one makes it a different notebook — while an
  inherited chapter item can be overwritten by a fork. Two sub-headings under
  the one collapsed callout: *From the brief (never superseded)* and
  *Inherited from earlier chapters*. One flat list would blur a distinction the
  rest of the system enforces.

**Cheaper than it looks.** `_render_active` runs with cwd at the notebook root,
and the notebook's own `index.qmd` already parses `_inputs.yml` with a plain
regex at render time. The chapter page can read that same file directly: **no
change to `nb/domain/inputs.py` and none to the `_active.yml` generator.** The
real cost is that `_notebook.py` is scaffolded per notebook, so existing
notebooks need the scaffold re-applied.

Compounds with item 1a: once the brief carries a dimension table, it appears on
every chapter page, which is where anyone auditing a reconstruction will look
for it.

## Cut from an earlier draft

Recorded so they are not re-proposed:

- **A fourth `source` value, `recalled`** — "knowable from a document we do not
  have". Two independent reasons, either sufficient.

  First, **it is not decidable by the party that would apply it.** To mark
  something `recalled` you must know the document exists and contains it. The
  agent cannot know that: from inside a sandbox with no network, *on the plan*
  and *nobody knows* are indistinguishable — both are things it cannot check,
  so it would have had to guess which category its guess belonged to. And for
  an agent that can never fetch anything, the category covers every fact about
  a real aircraft not supplied in the brief; a label that applies to everything
  in its class discriminates nothing. The coordinator *can* tell, because the
  coordinator can fetch — but discovering a source exists means having it, so
  the knowledge and the need for the label are mutually exclusive. **A
  taxonomy value only works if whoever must apply it can tell when it
  applies.**

  Second, it is unnecessary: item 2 shows the schema clause, not a missing
  category, is what skipped the declaration. `guessed` was always sufficient.

  The one residual case is a source confirmed to exist but unreachable — the
  Mustang plans are also on Scribd behind a paywall, and only the S3 copy made
  this session's retrieval possible. Rare, and free text covers it:
  `why = "taper: on v1.0 plan, paywalled, estimated"`.

- **The agent asking the coordinator "is this number on the plan?"** Same
  decidability failure. To ask, the run must know which of its numbers might be
  on a document it has never seen — so it would either ask about all of them,
  which is noise, or guess which to ask about, which is the thing it cannot do.
  Item 1b inverts it so **neither party does something it cannot**: the run
  declares what it assumed, which it knows; the coordinator checks what the
  plan settles, which it holds. Item 3's object-property marking gives the run
  the one useful contribution it *can* make, without needing to know what any
  document contains.

- **A per-chapter shape-provenance mode** (`plan:` / `recalled` / `designed`).
  Duplicates the assumptions system rather than extending it, and forces every
  from-scratch notebook to opt out of machinery built for reconstruction.
  `RADICAL-GLIDER` needs none of it.

- **A `_refs/` directory and a `read_plan` tool.** The auditability half is
  free today: the plan sits at the notebook root, which is what
  `RADICAL-GLIDER` already does. The only thing left would be the agent reading
  the plan itself — and once the coordinator is checking the assumptions list
  against it (1b), there is nothing for the agent to read it *for*.
  Infrastructure for a need that could not be demonstrated. Revisit only if
  coordinator checking proves to be the bottleneck in practice.

- **A lint regex for claimed provenance.** Fails the principle above; moved
  into the system instruction.

- **A new "geometry question" kind.** `ask_specified` already exists and was
  not used, and the reason looks structural: *specified*, *chapter* and
  *refactor* questions wait an hour, then exit `no_answer`. Asking is a bet
  that a human is at the board, and losing it kills the run; facing a dozen
  unknowns, an agent would take that bet twelve times, so it guesses instead.
  The five-minute assumptions prompt is already the cheap non-blocking ask —
  see 1b and 1c.

## Rejected: web research tools for the agent

Not on principle — for reasons specific to this system.

- **It does not fix the failure.** A run that invents and writes
  `# from FT plan sheet` will also skim a page and cite it. Web access without
  items 1–3 makes false provenance more convincing, not less.
- **Turn budget.** `b81e` hit `max_turns` at 103 calls with no network at all.
  A search–fetch–disambiguate loop is a turn sink dropped into a budget that is
  already failing.
- **Source quality.** Retailer listings quote 200 g for a Maker Foam sheet;
  that is packaging weight. Flite Test's own measurement of the same Adams
  board is 115 g. Choosing between them needed knowing Maker Foam *is* coated
  Adams.
- **Auditability.** A number from a URL that later 404s is uncheckable.
- **Injection.** Fetched pages are untrusted text entering a loop that writes
  code and commits it, inside a sandbox currently hermetic by design.

The better shape is **cache, don't fetch**: sources land in the repo as dated
files. Retrieval, rasterising, stitching and measuring need network, Bash and
Python — the coordinator has all three, the agent has none. Extraction is
coordinator work.

## Not a change, but unexplained

The notebook brief's first row now reads
`"**FT Mighty Mini Mustang MKR2**, Flite Test plan."`. What was written and
verified on disk was `"…, from the Flite Test plan."`. Two words were removed
from a file the design says is written by a person and never by a run.

The agent cannot reach it — the filesystem root is `<notebook>/chapters/`, and
an attempted `search_files(path="..")` in `a21b` was refused with *"Access
denied — path outside allowed directories"*. The only `_inputs.yml` writer
found in `nb` is `domain/inputs.py:350`, which targets `_active.yml`. No
account of this yet. Worth settling before the brief is trusted as immutable.

## What already works and needs nothing

Recorded so it is not changed by accident:

- **The sandbox holds.** Cross-notebook reads are impossible; the one escape
  attempt was refused.
- **The brief reaches the agent in full.** `prefix.py:137` emits it under
  *"The aircraft — true of EVERY chapter"*, and `:282` tells the run it is
  reproduced in the prompt so no turn is spent trying to read above
  `chapters/`. The Mustang failure was never a delivery problem — all seven
  rows arrived, and they said nothing about shape. Item 1a adds rows to a
  channel already proven to work.
- **The assumptions prompt is effective, and well timed.** The single
  geometry-adjacent input that was declared is the single one a human
  corrected, and it fires before `_model.py` exists. Items 2 and 3 exist to
  route more traffic through it; item 1b exists to make the coordinator use it
  properly. None of them replace it.
- **Recall is better than it looks.** The run guessed a 485 mm fuselage; the
  plan says 482 mm — 0.6 % out. The problem is not that memory is poor, it is
  that nothing distinguishes memory from measurement. Label it, do not distrust
  it.
- **Lint messages are already descriptive**, quoting the offending text rather
  than a bare rule number. The rule-hunting seen in two runs
  (`search_files "*rule*"`, `api_search "rule 5"`) is not caused by poor
  messages and is not addressed here.

## Order

1. **Items 1a and 1b** — zero code, available now, and together they would have
   caught the wing-loading error. Do these first whatever else happens.
2. **Item 2** — one string, and the most direct cause of the failure.
3. **Item 3** — the habit item 2 makes room for, plus the marking that makes 1b
   quick and one exact report.
4. **Item 1c** — the five-minute default. Needed before 1b can handle anything
   requiring measurement rather than lookup.
5. **Item 4** — unrelated to the rest, pure bug fixes, and the only item
   addressing a run that actually failed.
6. **Item 6** — reader-facing only, and worth most once 1a has filled the
   brief out. Independent of everything else; can land at any point.
7. **Item 5** — last, and weakest.

Items 1a, 1b and 2 are independent of each other and together address the whole
of the observed failure. Everything after them is hardening.

## Outstanding against the Mustang programme itself

Separate from the system work: the three committed entries rest on undeclared
geometry, and `023a`'s wing loading is now known to be 20 % high against the
published figure. They want re-running once item 1 lands and the plan is to
hand — not patching in place.
