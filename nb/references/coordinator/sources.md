# Find what the aircraft is made of, before you build it

**THE RUN CANNOT RESEARCH.** It has no network and is sandboxed to
`chapters/`. Every dimension you do not supply, it supplies from memory — and
an invented chord looks exactly like a measured one in the finished entry. A
row that states the number is worth five that state its absence.

So: find the figures, `source` them, and only then call `new`.

## Read the page, do not trust the summary

`search` finds pages reliably and reports figures off them unreliably.
Measured: asked for the FT Little Piggy's published wingspan, search answered
that it was not prominently published — while the store page prints `29 in
(736.6 mm)`, which `fetch` returns in plain text. So `fetch` the page and read
the number yourself. `source` enforces this: it refuses a URL you have not
fetched this session.

**Record the absences too.** `WING AREA and WING LOADING are NOT published.
Neither is thrust.` is a result. An unknown you name is one the run declares;
an unknown you leave silent is one it invents and attributes.

## Research the MATERIALS, not just the airframe

**Every target rests on a constant, and the constant is usually published
somewhere other than the product page.** A dry-mass target is areal density
times developed area plus component masses: supply the target and withhold the
density and you have asked for a number while hiding what it is made of.

So before `new`, go and get — and `source` — whatever the targets depend on:

| target | what it rests on | where it lives |
|---|---|---|
| dry mass | foam areal density; motor, ESC, servo, prop, gear masses | the foam supplier; the motor and power-pack pages |
| all-up mass | the above, plus battery mass | pack listings for the cell count named |
| CG | component masses AND their stations | masses published; stations are yours to fit |
| wing loading | wing area and all-up mass | both usually derived, not printed |

A sheet size and a sheet weight give you an areal density, and both are
printed: `510 × 750 mm, 112 g` is `0.293 kg/m²`. Cross-check it against a
second supplier if you can — Adams Readi-Board gives 0.297 for the same
nominal board, which is how you know the first number was not a typo.

Put each one in `spec` as its own row, with its units. Measured, 2026-10-08:
a brief carried `Dry mass: 531.5 g` as a target and **no areal density at
all**, the run guessed 0.40 kg/m² against a real 0.293, and the entry it
committed is worthless. The target was right; the thing it was made of was
missing.
