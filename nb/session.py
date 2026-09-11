"""
What one run accumulates.

Not persisted -- `proposal.json` is the only thing that crosses the process
boundary. This exists so the handlers that ask the human, and the handlers that
spend solve seconds, can agree on what has happened so far.
"""

from .config import MAX_CONSULTS


class Session:
    def __init__(self, notebook, question, chapter=None):
        self.notebook = notebook
        self.question = question
        self.chapter = chapter
        self.asked = {}          # name -> value, from ask_specified
        self.consults = 0
        self.solves = 0
        self.solve_seconds = 0.0

    def record_cost(self, solves, seconds):
        self.solves += solves
        self.solve_seconds += seconds

    def record_answer(self, name, value):
        self.asked[name] = value

    @property
    def consults_left(self):
        return MAX_CONSULTS - self.consults
