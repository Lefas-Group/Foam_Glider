"""
The model, and everything that shapes what it is asked.

`client` is the one provider seam; `loop` drives the conversation; `prefix` and
`briefs` build what the model reads; `session` is what a run accumulates;
`schema` the one structured payload it produces; `stuck` notices when it has
stopped getting anywhere; `budgets` bounds what a probe may spend.

`nb/tools/` is the agent's tool surface and belongs conceptually here. It stayed
at the top level on purpose: it is eleven modules deep and already a coherent
package, and moving it would re-point every relative import inside it for a
grouping win it already has.
"""
