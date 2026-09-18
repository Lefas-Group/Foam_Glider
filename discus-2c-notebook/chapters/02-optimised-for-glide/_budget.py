# This chapter's solve limits, agreed with the user on 2026-09-17 when the
# chapter was created. Deliberately NOT inherited from the parent chapter: a
# fork copies _model.py and _analysis.py only, so a new chapter starts on the
# notebook defaults until someone decides otherwise.
#
# Sized for what the entries here actually run -- a gradient optimization over
# eleven variables with AeroBuildup and stability derivatives in the loop --
# not for a cheaper probe.
SOLVE_BUDGET = 300.0   # s for any one solve
ENTRY_CEILING = 600.0  # s for one entry, checked by lint rule 17
