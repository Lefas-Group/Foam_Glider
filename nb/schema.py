"""
The structured payloads the model produces.

Pydantic earns its place twice here: `model_json_schema()` is the tool
declaration, and `model_validate()` is the check on the way back in. A malformed
`propose` therefore comes back as a message the model can read and fix, rather
than a KeyError inside a handler.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Input(BaseModel):
    """One input the question needed that was not already fixed."""

    name: str = Field(description="The quantity, e.g. 'static margin'")
    kind: Literal["derivable", "specified", "unknown"] = Field(
        description=(
            "derivable: the model or the plans already contain it -- compute it, "
            "never declare it. specified: a different answer changes WHAT WE ARE "
            "BUILDING -- ask via ask_specified. unknown: a different answer "
            "changes HOW ACCURATELY WE MODELLED IT -- assume and say what it costs."
        ))
    value: Optional[str] = Field(default=None, description="The value used")
    owner: Literal["user", "agent", "assumed"] = Field(
        description=(
            "user: they answered. agent: they delegated it and you answered, so "
            "say why. assumed: nobody knows -- only valid for kind=unknown."
        ))
    why: str = Field(description="Ten words at most -- lint rule 8 counts them")

    @model_validator(mode="after")
    def _discipline(self):
        if self.kind == "derivable":
            raise ValueError(
                f"'{self.name}' is derivable -- compute it, don't declare it.")
        if self.kind == "specified" and self.owner == "assumed":
            raise ValueError(
                f"'{self.name}' is Specified but owner is 'assumed'. A Specified "
                f"input is asked, every time -- use ask_specified. If you answered "
                f"it yourself because it was a one-sentence call, owner is 'agent'.")
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
            "entry: the same model as an existing chapter. new_chapter: a "
            "different model, fidelity or vehicle -- confirm via ask_specified "
            "first, since it decides whether both answers are kept."))
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
    queue: list[str] = Field(
        default_factory=list,
        description=(
            "Further distinct questions in the same ask, one entry each. Facets "
            "of a SINGLE comparison (cost, fidelity, applicability) are one "
            "question, not three."))
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
            "the last commit rather than the working tree, with the header "
            "rule 31 requires already written. Leave empty for a genuinely new "
            "aircraft."))
    chapter_categories: list[str] = Field(
        default_factory=list,
        description=(
            "Only for route='new_chapter'. What this chapter VARIES, drawn from "
            "the notebook's `_categories.yml` -- read it first, and use its "
            "terms exactly (rule 36 refuses anything else, because 5mm/5 mm/"
            "5 mm foam as three tags is how a grouping stops working). Tag what "
            "distinguishes this chapter from its neighbours, not everything "
            "true of it: a constraint every chapter shares is not an axis. If "
            "the chapter varies something the file has no term for, say so in "
            "the proposal rather than inventing one -- adding an axis is a "
            "decision about what the notebook is exploring."))
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
    def _one_visual(cls, v):
        if len(v) > 1:
            raise ValueError(
                f"{len(v)} figures proposed; rule 14 allows one visual per entry "
                f"(a table counts as a figure). Choose the one that carries the "
                f"answer and drop the rest.")
        return v


