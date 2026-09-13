"""
verify -- does the page say anything the rendered output does not support?

The only justified second model call with its own context, and the context is
the point: it sees the RENDERED ARTEFACT and not the conversation. The failure
it exists to catch is prose written from what the model believed rather than from
what came out, and a reviewer who watched the believing is no use against it.

Mostly a figure problem. A caption claiming a crossover at 6 m/s when the curve
crosses at 8 is invisible to every lint rule -- rule 1 forces the numbers in prose
to be computed, but nothing forces a sentence about a SHAPE to match the shape.
"""

import json
import sys

from ..client import complete, config
from ..schema import VerifyResult
from ..tools import figures, verifiers
from ..log import say

BRIEF = """\
Below is a notebook entry exactly as it rendered: the prose with every inline
expression already evaluated, and the figures it produced.

Check one thing: does the prose claim anything the output does not support?

Report a finding only for a real contradiction —

  - a number in the prose that disagrees with the rendered value or the figure
  - a claim about a curve's shape, trend or crossing point that the figure
    contradicts
  - a caption describing something other than what is plotted
  - a reference to a figure, table or entry that is not there

Do NOT report: wording, structure, tone, word budgets, lint rules, missing
content, or anything you would have done differently. Those are owned elsewhere,
and a finding here costs a re-render.

If the prose is supported by the output, return ok with no findings.

--- rendered entry -------------------------------------------------------
{markdown}
--------------------------------------------------------------------------
"""


def rendered_markdown(notebook, chapter, stem):
    p = notebook.freeze / chapter / stem / "execute-results" / "html.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())["result"]["markdown"]
    except (ValueError, KeyError):
        return None


def check(notebook, chapter, stem, entry_path=None, render_first=True):
    """
    (VerifyResult, note). `note` explains a skip; None when the check ran.

    Renders deterministically first. In the stage-1 run the write loop happened
    to call render itself, but nothing requires it to, and verifying against a
    stale freeze is worse than not verifying at all.
    """
    from google.genai import types

    if render_first and entry_path:
        out = verifiers.render(notebook, str(entry_path.relative_to(notebook.root)))
        if "FAILED" in out:
            return None, f"render failed, nothing to verify:\n{out}"

    markdown = rendered_markdown(notebook, chapter, stem)
    if markdown is None:
        return None, f"no freeze for {chapter}/{stem}; cannot verify"

    parts = [types.Part.from_text(text=BRIEF.format(markdown=markdown))]
    pngs = figures.figure_paths(notebook, chapter, stem)
    for png in pngs:
        parts.append(types.Part.from_text(text=f"\nfigure: {png.name}"))
        parts.append(types.Part.from_bytes(
            data=png.read_bytes(), mime_type="image/png"))

    resp = complete([types.Content(role="user", parts=parts)],
                    config(response_schema=VerifyResult))
    return VerifyResult.model_validate_json(resp.text), None


def main(argv):
    """`python -m nb.phases.verify <notebook> <chapter> <stem>`"""
    from ..config import Notebook
    if len(argv) < 3:
        say("usage: python -m nb.phases.verify <notebook> <chapter> <stem>")
        return 2
    notebook = Notebook(argv[0])
    result, note = check(notebook, argv[1], argv[2], render_first=False)
    if note:
        say(f"  {note}")
        return 2
    say(f"  verify    {'ok' if result.ok else f'{len(result.findings)} finding(s)'}")
    for f in result.findings:
        say(f"    {f}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
