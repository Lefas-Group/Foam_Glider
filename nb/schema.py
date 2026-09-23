"""
The structured payloads the model produces.

Pydantic earns its place twice here: `model_json_schema()` is the tool
declaration, and `model_validate()` is the check on the way back in. A malformed
`propose` therefore comes back as a message the model can read and fix, rather
than a KeyError inside a handler.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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
# EVERY DOCSTRING HERE IS SHIPPED. Pydantic puts a class docstring into
# `model_json_schema()`, which is the `propose` declaration, which is 46% of the
# tool surface -- so the reasoning above lives in a comment and the model reads
# only what it needs. Writing it as a docstring cost 110 tokens per request.
class Input(BaseModel):
    """One input the question needed that was not already fixed."""

    name: str = Field(description="The quantity, e.g. 'static margin'")
    value: Optional[str] = Field(default=None, description="The value used")
    source: Literal["asked", "decided", "guessed"] = Field(
        description=(
            "asked: a different answer changes WHAT WE ARE BUILDING and you "
            "put it to the user with ask_specified. decided: you asked, they "
            "handed it back, and you chose -- say why. guessed: nobody knows, "
            "a different answer changes HOW ACCURATELY it is modelled, so you "
            "assumed it and said what it costs. If the model or the plans "
            "already contain it, it is none of these: compute it."))
    why: str = Field(description="Ten words at most -- lint rule 8 counts them")

    @model_validator(mode="after")
    def _discipline(self):
        if len(self.why.split()) > 10:
            raise ValueError(
                f"'{self.name}': why is {len(self.why.split())} words, budget is 10.")
        return self


class Proposal(BaseModel):
    """
    What `nb ask` hands to the gate, and `nb write` reads back.

    Everything `nb write` needs is here: it does not get the probe transcript,
    because the entry's own code cells re-run the computation at render time.
    """

    title: str = Field(
        description=(
            "The question THIS entry answers, phrased as ONE question ending "
            "in '?', 18 words at most (rule 26) — aim for about eight. "
            "REPHRASE the ask: strip anything that holds for the whole chapter, "
            "because that lives in its index.qmd, and turn a brief into a "
            "question. 'optimise a glider for trimmed glide. It is constructed "
            "of foam 5mm thick…' is a brief; 'Which planform gives the lowest "
            "sink rate?' is its question. It becomes the entry title, the "
            "sidebar text and the filename."))
    question: str = Field(
        description=("What was actually asked, verbatim. Never edited — the "
                     "title may be rephrased, so this is the record of the "
                     "request, and it is what the commit message carries."))
    chapter: str = Field(description="Chapter directory name, e.g. '04-chosen-throw'")
    route: Literal["entry", "new_chapter"] = Field(
        description=(
            "A chapter is a VEHICLE, so the test is mechanical: would this "
            "question change `_model.py`? new_chapter only when the MODEL "
            "differs -- different material, different design, or different "
            "variables free to the optimiser. entry for everything else, "
            "however large: a new objective, different bounds, a multistart, a "
            "finer sweep, more strips, a different aero method, or any new "
            "measurement of the same vehicle all live in `_analysis.py` and "
            "belong in the chapter that already holds that vehicle. Rule 31 "
            "and the lineage diagram both measure `_model.py` similarity and "
            "nothing else, so a fork the model file does not justify is a "
            "chapter the notebook cannot draw."))
    rationale: str = Field(
        description="One line: what is held constant between arms, and what differs")
    findings: str = Field(
        description="The answer, and what the probe actually established")
    working_code: str = Field(
        description="The probe code that produced the answer, ready to adapt")
    figures: list[str] = Field(
        default_factory=list,
        description=(
            "Caption per intended visual, 50 words each. ONE visual or none, "
            "and a table counts as one -- including a table built in a string "
            "and shown with display(Markdown(...)), which rule 14 now counts "
            "whether or not you labelled it. TWO are allowed when one of them "
            "DRAWS THE AIRCRAFT: a three-view and a plot are different claims, "
            "and the drawing no longer has to displace the answer. Match the "
            "form to the question: a DRAWING when the answer is what something "
            "IS -- a shape, a layout, a geometry, anything asking what it looks "
            "like or what its dimensions are; a PLOT when the answer is how it "
            "BEHAVES -- a trend, a trade, a crossing; a TABLE when quantities "
            "are being compared side by side and neither of those is the point. "
            "The test is not 'would a plot look good' but 'is the visual THE "
            "ANSWER'. A figure that repeats what the sentence already said is "
            "worse than the sentence."))
    render_cost_s: float = Field(
        description="Solve seconds from aero_report(), never a guess")
    inputs: list[Input] = Field(default_factory=list)
    inputs_none_because: str = Field(
        default="",
        description=(
            "ONLY when `inputs` is genuinely empty: one line saying why this "
            "question needed nothing specified and assumed nothing new. A real "
            "state -- an entry that only reads a model already built has "
            "nothing of its own -- but it is a CLAIM, and an empty list with "
            "no claim is an omission. `propose` refuses that. Inheriting "
            "everything from the chapter is a perfectly good reason; say so."))
    chapter_title: str = Field(
        default="",
        description=(
            "Only for route='new_chapter'. The CHAPTER's name, two or three "
            "words in the style of 'Flight path' or 'Chosen throw' — not the "
            "entry's question."))
    forked_from: str = Field(
        default="",
        description=(
            "Only for route='new_chapter', and only when this chapter's vehicle "
            "is a COPY of an existing one: the chapter directory it is copied "
            "from, e.g. '03-unswept-c4'. The copy is then made for you, from "
            "the last commit rather than the working tree, with `_fork.yml` "
            "already written. Leave empty for a genuinely new aircraft. Where "
            "the new vehicle makes one of the parent's recorded specifications "
            "or assumptions FALSE, say so in `_fork.yml`'s `overwrites:` when "
            "you fill it in -- the record is append-only, so nothing else will "
            "ever mark the old one as replaced."))
    chapter_defines: str = Field(
        default="",
        description=(
            "Only for route='new_chapter'. What defines this chapter: the aero "
            "method, the section, what is left out. It goes in index.qmd and is "
            "the one place those assumptions are stated — entry prose must not "
            "repeat them."))
    handoff: str = Field(
        default="",
        description=(
            "Notes for the HUMAN, not for the page: anything you noticed that "
            "was not asked about, and would make a good next question. This is "
            "the skill's 'interesting things go in chat, never into the "
            "notebook' — it is read by a person and never copied into the entry."))

    @model_validator(mode="after")
    def _new_chapter_is_described(self):
        if self.route == "new_chapter" and not self.chapter_title.strip():
            raise ValueError(
                "route='new_chapter' needs chapter_title: the chapter's own "
                "name ('Flight path'), not the entry's question. Without it the "
                "chapter would be titled after one question it happens to hold.")
        if self.route == "new_chapter" and not self.chapter_defines.strip():
            raise ValueError(
                "route='new_chapter' needs chapter_defines: the aero method, the "
                "section, what is left out. index.qmd is the one place those "
                "assumptions are stated.")
        return self

    @field_validator("figures")
    @classmethod
    def _visual_budget(cls, v):
        # TWO, matching rule 14 and the field description above it. It was one,
        # and the description three lines up already said "TWO are allowed when
        # one of them DRAWS THE AIRCRAFT" -- so a model doing exactly what it
        # was told got a ValueError from `propose`, and the repair it reaches
        # for is to drop the three-view. That is the failure rule 14 was
        # LOOSENED to prevent: "three chapters ended up with no picture of the
        # aeroplane at all".
        #
        # Which of the two is a drawing cannot be judged from a caption, so the
        # cap here is the ceiling and lint does the judging -- `_visuals_and_
        # tables` counts the rendered page and allows the second only when
        # DRAWING matched the source. A proposal for two plots therefore passes
        # here and is caught there, with the page to point at.
        if len(v) > 2:
            raise ValueError(
                f"{len(v)} figures proposed; rule 14 allows one visual per "
                f"entry (a table counts as a figure), or two when one of them "
                f"DRAWS THE AIRCRAFT. Choose the one that carries the answer, "
                f"plus at most a drawing, and drop the rest.")
        return v


