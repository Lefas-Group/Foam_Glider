# Choosing, cutting and checking reference photographs

The targets check the model against published NUMBERS. Nothing checks its
SHAPE. One reconstruction reproduced all eight published figures to 0.40%
while missing its power pod entirely and lofting a smooth pod where the real
aircraft is a slab-sided box — both obvious the moment it was drawn over a
photograph.

**ANGULAR SPREAD IS THE WHOLE POINT.** Each camera position pins down what it
happens to show and says nothing about the rest: a head-on frame fixes span,
dihedral and tip cant and tells you nothing about chord; a frame from below is
the only place wing incidence shows; a three-quarter from above fixes the
planform and hides the gear. **Shape faults survive in exactly the directions
nobody photographed.**

Two frames from one shoot are ONE photograph — they fit the same pose and hide
the same faults. Retailers shoot a product once and recolour it, so "two store
photos" is usually one viewpoint twice: one such pair measured IoU 0.87, and
another that differed in paint, framing and apparent elevation still measured
0.82. `reference` prints the pairwise table; keep the spread.

**THREE OR FOUR FRAMES, and stop.** The spread is what you are buying, and
four well-separated angles buy all of it; a fifth that repeats an angle
already held costs a `read_image` to choose, an overlay to inspect tinted and
a term in every fit, and checks nothing the other four did not. If a candidate
does not show a direction none of the others do, leave it out.

So `read_image` every candidate before adding it. You are choosing ANGLES, and
you cannot do that from a filename.

**The description is read as FACT and nothing checks it.** Say where the
camera is. Measured: a photograph named `belly` and described as "seen from
BELOW and BEHIND" was actually from ABOVE — gold canopy, dorsal spine and the
top of the wing all visible. Every fit returned elev +36° from the first call,
nobody read it back, and the description reached committed prose.

### LOOK AT EVERY OVERLAY

`mask` cuts with a segmentation model. It is good — better than hand-cut rules
— and **it reports nothing when it is wrong.**

Its characteristic failure is taking in something that is not the aircraft:
on one store photograph every model tested kept the hand holding the
aeroplane. A hand-plus-aeroplane silhouette has a perfectly clean boundary, so
`noise` and `rough` cannot see it. The numbers corroborate; they do not check.

**Judge the FILL, not the edge.** A boundary drawn over a busy photograph
reads as correct wherever it follows a real edge — and the crease between a
lit facet and a shaded one IS a real edge, so a mask that dropped an entire
shaded underside still draws a convincing line. Three masks once passed that
inspection while missing a belly, a chin, two legs and two wheels. Tinted, the
hole is unmissable.

**When it is wrong, change the photograph, not the code.** There is
deliberately no parameter — a salient-object model cannot know the hand is not
part of the aeroplane. Use a different frame, and say in its `.txt` what you
did.

Then `reference` until it is clean, and only then `reconstruct`.
