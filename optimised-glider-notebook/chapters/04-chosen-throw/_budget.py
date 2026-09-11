# =============================================================================
# What this chapter is allowed to spend. Agreed with the user, 2026-09-11, and
# declared in index.qmd as Specified -- lint rule 18 checks the two agree.
#
# ITS OWN FILE ON PURPOSE. A fork copies _model.py and _analysis.py, so it does
# NOT copy this: a new chapter starts on the notebook defaults, which is the
# safe state, and going unbudgeted becomes the deliberate act of creating a
# file. This chapter exists because the opposite happened -- it was forked from
# 02-flight-path and silently inherited `SOLVE_BUDGET = None` together with a
# comment ("its pages are already frozen") that was untrue of a chapter with no
# pages at all.
#
# SIZED FROM THE CONFIGURATION THE ENTRIES RUN, which is the other half of that
# failure. The first value here was 180 s, taken from a 70 s solve at n=30,
# while the entries solve at n=60 and need about 210 s. Every entry solve was
# therefore truncated and, because the budget then defaulted to returning its
# last iterate, published: the same code gave 11.22 s, 9.50 s and 8.92 s on
# three runs. 600 s clears the requirement with room, so the budget never binds
# and the answers are reproducible; if it ever does bind, the solve now raises
# rather than handing back a half-finished design.
#
# The ceiling carries four solves, because the problem is multi-modal and one
# start reports a basin rather than an optimum.
# =============================================================================
SOLVE_BUDGET = 600.0   # s for any one solve; entries need ~210 s at n=60

# Raised 400 -> 600 s by the user, 2026-09-11, after the first value blocked a
# render on load alone. The speed-sweep entry measured 384.8 s, so 400 left four
# percent of headroom -- against a machine-load swing measured at ~1.5x elsewhere
# in this notebook, and written into why.md as the very reason rule 17's lower
# tier only warns. The same entry then came back at 421 s doing identical work
# for identical numbers.
#
# 600 s is that 385 s measurement times the documented swing. It still binds on
# anything that genuinely grows: the chapter's other entries run 251-315 s.
ENTRY_CEILING = 600.0  # s for one entry, checked by lint rule 17

# Granted by the user, 2026-09-11, for probing THIS chapter. Sized from what the
# probes here have actually taken rather than chosen: one n=60 solve runs
# 204-212 s, the four-arm speed sweep 385 s, and the three-point grid-convergence
# study about 580 s. 900 s covers the largest of those with room for the ~1.5x
# swing machine load has produced, and still stops a runaway.
#
# The notebook default is 300 s and is deliberately tight. Hitting it is supposed
# to force a choice -- cheaper probe, or ask -- so this override exists because it
# was asked for and agreed, not because a probe was inconvenient.
PROBE_BUDGET_CHAPTER = 900.0
