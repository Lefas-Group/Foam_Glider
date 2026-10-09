# Specified, Target, Assumed: what goes in a brief

**A published DIMENSION is an input, not a target.** Span, length, wheel
diameter, propeller size — anything linear the manufacturer prints — SETS the
model's scale, and is what makes a silhouette fit identifiable at all: with
span free, size trades against camera distance and the fit goes degenerate.
Those go in `spec`.

`target` is for what the geometry must PRODUCE and no constant can be typed
as: wing area, wing loading, aspect ratio, a dry mass that falls out of area
times areal density, CG.

Measured, on an F-16 reconstruction: span and length went in as targets, the
run built a wing, got 734 mm, and solved for the tip station that makes
`span()` return the published 914 mm. The entry's headline — "0.39%, all
airframe targets inside tolerance" — was the model being compared with itself.

**`assume` is what is assumed ABOUT THE AIRCRAFT. Never a directive.** Both
blocks render verbatim into the front page and every chapter that inherits
them. A row phrased as an instruction becomes one of the aeroplane's declared
assumptions, on every page, for ever.

    GOOD  **Airfoil**: flat foam plate, a declared stand-in.
    GOOD  **Planform** is fitted to photographs, not measured.
    BAD   **Never pixel-measure**; optimise the silhouette instead.
    BAD   **Thrust not published**; assume and declare it.

The test: **could this sentence be true or false of the real aeroplane?** If
it is an instruction to whoever builds the model, it does not belong in a
brief. And prefer to CLOSE a gap rather than describe it — "thrust not
published, assume one" had a run inventing 16.7 N against a vendor's published
2240 g. You can research; it cannot.
