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

### PREFER A STORE PNG THAT CARRIES ITS OWN ALPHA

Retailers cut their product shots, so a store `.png` often arrives already
masked — and a vendor's own cut-out is GROUND TRUTH, better than anything a
segmentation model infers from the flattened image. `mask` uses it in
preference to the model whenever it is there, and `reference` marks those rows
`alpha` in the `cut` column.

Measured on the FT A-10 Warthog: its store photograph is 84% transparent, and
against that alpha the model's own mask scored IoU 0.82, taking in **21.6%
extra area** — most of it the enclosed gap between the port tail fin, the
tailplane and the nacelle, which is exactly the region that defines a
twin-boom tail. The silhouette was of a different aeroplane, and nothing in
the numbers said so.

So when a store offers the same frame as a `.png` and a `.jpg`, take the
`.png`. The JPEG has been flattened onto white and the cut-out is gone.

**And read the `cut` column when a mask looks wrong.** A poor silhouette on an
`alpha` row is a bug in `nb`, not a hard photograph — chasing it as a hard
photograph is how twenty minutes goes missing.

### REJECT THESE BEFORE YOU FETCH THEM

Four frames that cost a mask and give nothing back. Measured on the FT A-10
Warthog, whose coordinator added three photographs that were all "from front,
above" and one of them held in somebody's hands:

1. **Anything held by a person.** A salient-object model cannot know the hand
   is not part of the aeroplane, and there is deliberately no parameter to
   tell it — on one store photograph every model tested kept the hand. The
   mask is then an aeroplane-plus-hand silhouette with a perfectly clean
   boundary, so no number catches it and every pose fitted against it is
   wrong. Same for a stand, a bench clamp, or a hand steadying a wingtip.
2. **A video thumbnail**, unless nothing else exists. Compressed, usually
   captioned, often with a face or a play button composited over the
   aircraft — all of which the mask takes in.
3. **A frame at the same angle as one you already have.** Three photographs
   from the front and above are ONE photograph; the second and third cost a
   mask each and tell you nothing the first did not.
4. **A build or assembly shot** — parts on a table, a half-skinned airframe,
   a wing panel on its own. It is not the aeroplane.

**IoU WILL NOT SAVE YOU HERE, and this is the trap.** The spread table
compares SILHOUETTES, not cameras. Those three Warthog frames scored 0.30 to
0.48 — comfortably "distinct" — while being the same viewpoint photographed at
three different distances with the aircraft at three different roll angles. A
low IoU means the outlines differ; it does not mean the cameras do.

So the test is the one you apply BEFORE the number exists: **say in words where
each camera is, and keep a frame only if that sentence differs from every
sentence you have already written.** If two of your `.txt` descriptions open the
same way, you have one photograph.

**A frame you reject is worth saying out loud.** `source` the page and record
why — "held by hand", "same angle as X" — so the next coordinator does not
fetch it again.

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
