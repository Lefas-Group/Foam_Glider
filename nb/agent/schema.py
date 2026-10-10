"""
The one structured payload the model produces.

There was a second, `Proposal`, with fifteen fields -- and `model_json_schema()`
on it WAS the `propose` declaration, 44% of the whole tool surface. Weighed, it
was mostly not a schema: four descriptions (`figures`, `route`, `forked_from`,
`title`) were 57% of all its field text and every one restated doctrine that is
already in `system_instruction.md`, shared and cached once. It is gone with the
gate it fed; `fork_chapter` and `open_entry` take the few parameters that are
genuinely per-call and point at the instruction for the rest.

`Input` stays, and pydantic still earns its place twice on it: the validator is
what holds `why` to rule 8's ten words at the moment of declaring, rather than
after a whole document has been assembled around it.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ONE field says where an input came from, where there used to be three.
# `kind` (derivable|specified|unknown), `owner` (user|agent|assumed) and `scope`
# (new|chapter|notebook) between them allowed 27 combinations; across every
# recorded proposal, THREE occurred, and they are exactly `source`'s three.
#
# `derivable` existed only to be rejected -- a lesson, not a state, and the
# instruction's triage table already teaches it. `scope` carried the longest
# description of any field here, longer than `kind` and `owner` combined, for a
# single validator; and the level is not a property of an item, it is WHERE THE
# ITEM IS DECLARED. A thing in `chapters/04/_inputs.yml` is chapter-level
# because it is in that file, and a field saying otherwise is just something to
# disagree with the filesystem about.
#
# EVERY DOCSTRING HERE WAS SHIPPED, back when this class rendered into a tool
# declaration through `model_json_schema()`: the reasoning above, written as a
# docstring, cost 110 tokens per request. It no longer renders anywhere -- the
# `declare_input` declaration is hand-written -- but the habit is worth keeping,
# because the day something re-derives a schema from here it will ship again.
class Input(BaseModel):
    """One input the question needed that was not already fixed."""

    name: str = Field(description="The quantity, e.g. 'static margin'")
    value: Optional[str] = Field(default=None, description="The value used")
    source: Literal["asked", "decided", "guessed"] = Field(
        description=(
            "asked: a different answer changes WHAT WE ARE BUILDING and you "
            "put it to the user with ask_specified. decided: you asked, they "
            "handed it back, and you chose -- say why. guessed: a different "
            "answer changes HOW ACCURATELY it is modelled, so you assumed it "
            "and said what it costs -- this covers BOTH what nobody knows AND "
            "what a document would settle but you do not have that document. "
            "If the MODEL already contains it, it is none of these: compute "
            "it. A dimension of a real aircraft that the brief did not give "
            "you is guessed, however confident the recollection: declare it, "
            "and say in `why` that it was not measured."))
    why: str = Field(description="Ten words at most -- the same budget rule 8 "
                                 "puts on the item this becomes")

    @model_validator(mode="after")
    def _discipline(self):
        # THE CONTRACT'S OWN COUNTER, not `str.split()`. `words()` treats an
        # inline `{python}` expression as the one thing a reader takes in,
        # which is the whole reason it exists -- counting the source verbatim
        # penalises the habit rule 1 enforces. This used to split on
        # whitespace and so disagreed with every other word budget in the
        # system about the same text.
        #
        # NOT `item_words`: that strips a leading `**Label**:` because an
        # input ITEM is written `**CG**: 64 mm …` and the handle is not
        # prose. A `why` is the reason alone and carries no handle, so the
        # label rule has nothing to do here.
        #
        # This is a PROXY for rule 8, not the same check. Rule 8 counts the
        # rendered item -- name, value and reason together -- which is longer
        # than this. Ten here keeps the item that will be built from it
        # inside ten there, which is why the budget is the same number.
        from ..contract.shared import words
        n = words(self.why)
        if n > 10:
            raise ValueError(
                f"'{self.name}': why is {n} words, budget is 10.")
        return self
