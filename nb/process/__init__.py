"""
A run as an operating-system fact: its state, its locks, its mailbox, its log.

`runstate` is `run.json` -- what a run IS while it is still running. `locks`
guards rendering and chapter writes; `detach` takes a run out of the terminal's
session; `mailbox` and `coordinator` carry questions between a run and whoever
answers them; `metrics` records one row per run; `log` is where all of it is
said.
"""
