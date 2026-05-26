"""
Core engine for the cryptic crossword solver suite.

Owns ALL grid state and constraint propagation. No language model reasoning
happens in here — this module is deterministic bookkeeping. Claude instances
talk to it only through the CLI scripts (grid.py, solve.py, etc.), never by
editing state directly.

State is persisted to a single JSON file (default: state.json) so that many
short-lived processes (one per subagent call) can all read and write the same
source of truth.

Key design choices, with rationale:

- Letters are tracked per CELL as a *weighted vote*, not a single guess. Each
  committed answer contributes a vote for the letter it wants in each of its
  cells. A cell's letter is only "hard" (locked) once two independent entries
  agree on it. Agreement-at-intersection is a far stronger signal than any
  single clue's self-reported confidence, so we lean on it heavily.

- The grid is always recomputable from the set of committed answers. We never
  mutate cells in place and try to undo later; instead, retracting an answer
  and recomputing the whole grid is cheap and impossible to get subtly wrong.
  This makes conflict resolution principled rather than guesswork.

- Every cell knows its provenance: which entries voted for which letters. That
  is exactly the information conflict resolution needs.
"""

from __future__ import annotations

import json
import os
import string
from dataclasses import dataclass, field, asdict
from typing import Optional


ALPHABET = set(string.ascii_uppercase)
DEFAULT_STATE_PATH = os.environ.get("CRYPTIC_STATE", "state.json")


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Cell:
    """A single light (non-blocked) square in the grid.

    In a standard grid a cell is crossed by at most two entries (one across,
    one down), so 'votes' has at most two entries. Each vote is the letter a
    committed crossing answer wants here, together with that answer's
    confidence — so a cell knows not just WHICH letter is suggested but how
    much to trust each suggestion.
    """
    row: int
    col: int
    # entry_id -> {"letter": str, "confidence": float}
    votes: dict = field(default_factory=dict)

    def possible(self) -> set:
        """Letters still consistent with all current votes."""
        if not self.votes:
            return set(ALPHABET)
        out = set(ALPHABET)
        for v in self.votes.values():
            out &= {v["letter"]}
        return out

    def letter(self) -> Optional[str]:
        """The agreed letter if all voters concur; else None.

        With at most two crossers, this is just 'they don't disagree'. A single
        committed crosser is enough to suggest a letter — we do NOT wait for the
        second word, because by the time both crossers are committed the cell is
        fully determined and helps no remaining clue. A single committed crosser
        is exactly the signal an unsolved clue needs.
        """
        if not self.votes:
            return None
        p = self.possible()
        return next(iter(p)) if len(p) == 1 else None

    def best_confidence(self) -> float:
        """Highest confidence among agreeing voters (0.0 if no votes)."""
        if not self.votes:
            return 0.0
        return max(v["confidence"] for v in self.votes.values())

    def corroborated(self) -> bool:
        """Both crossers committed AND they agree.

        This is the strong 'two independent words concur' signal. It is a
        VERIFICATION cue (evidence both answers are right), NOT the threshold
        for showing a letter in a solver's pattern — those are different jobs.
        """
        if len(self.votes) < 2:
            return False
        return len({v["letter"] for v in self.votes.values()}) == 1

    def conflicted(self) -> bool:
        return len(self.possible()) == 0


@dataclass
class Entry:
    """One across or down clue and everything we know about it."""
    id: str                     # e.g. "12A", "7D"
    direction: str              # "across" | "down"
    number: int
    clue: str
    length: int                 # total letter count (sum of enumeration)
    enumeration: list           # e.g. [4, 3] for "(4,3)"
    cells: list = field(default_factory=list)   # [[r,c], ...] in reading order
    # solver bookkeeping
    candidates: list = field(default_factory=list)  # list of Candidate dicts
    committed: Optional[str] = None                  # the answer written to grid
    committed_confidence: float = 1.0                # confidence of committed answer
    parse: Optional[str] = None
    verified: Optional[bool] = None                  # parse-check result


@dataclass
class Candidate:
    answer: str
    confidence: float
    parse: Optional[str] = None
    source: str = "solver"      # which role proposed it


# --------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------

class Grid:
    def __init__(self, data: dict):
        self.rows: int = data["rows"]
        self.cols: int = data["cols"]
        self.entries: dict = {}
        self._cells: dict = {}   # (r,c) -> Cell

        for e in data["entries"]:
            self.entries[e["id"]] = Entry(**e)

        # Build the set of light cells from the entries' cell lists.
        for entry in self.entries.values():
            for (r, c) in entry.cells:
                self._cells.setdefault((r, c), Cell(row=r, col=c))

        self._rebuild()

    # ---- persistence -----------------------------------------------------

    @classmethod
    def load(cls, path: str = DEFAULT_STATE_PATH) -> "Grid":
        with open(path) as f:
            return cls(json.load(f))

    def save(self, path: str = DEFAULT_STATE_PATH) -> None:
        data = {
            "rows": self.rows,
            "cols": self.cols,
            "entries": [self._entry_to_dict(e) for e in self.entries.values()],
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)   # atomic write, so concurrent readers never see half a file

    @staticmethod
    def _entry_to_dict(e: Entry) -> dict:
        d = asdict(e)
        return d

    # ---- core mechanism: rebuild grid from committed answers -------------

    def _rebuild(self) -> None:
        """Recompute every cell's votes from scratch using committed answers.

        This is the heart of the 'always recomputable' design. Call it after
        any commit or retraction. O(total letters), trivially cheap.
        """
        for cell in self._cells.values():
            cell.votes = {}
        for entry in self.entries.values():
            if not entry.committed:
                continue
            ans = entry.committed.replace(" ", "").replace("-", "").upper()
            conf = entry.committed_confidence
            for (r, c), ch in zip(entry.cells, ans):
                self._cells[(r, c)].votes[entry.id] = {
                    "letter": ch, "confidence": conf,
                }

    # ---- queries ---------------------------------------------------------

    def pattern(self, entry_id: str) -> str:
        """The known-letter pattern for an entry, e.g. '?A??E?'.

        A letter appears as soon as the SINGLE crossing word through that cell
        is committed — we do not wait for both words, because that is the only
        regime in which the pattern can ever help an unsolved clue (in a normal
        grid each cell has at most two crossers, so 'both committed' means the
        cell is already fully solved and helps nobody). Cells with no committed
        crosser, or with a contradiction, show '?'.
        """
        entry = self.entries[entry_id]
        out = []
        for (r, c) in entry.cells:
            cell = self._cells[(r, c)]
            # don't let the entry's own committed letters fill its pattern;
            # the pattern is about what CROSSINGS tell us.
            crossers = {eid: v for eid, v in cell.votes.items() if eid != entry_id}
            if not crossers:
                out.append("?")
                continue
            letters = {v["letter"] for v in crossers.values()}
            out.append(next(iter(letters)) if len(letters) == 1 else "?")
        return "".join(out)

    def pattern_detail(self, entry_id: str) -> list:
        """Per-cell provenance for an unsolved entry's pattern.

        Returns one dict per cell: the suggested letter (or None), and which
        crossing entry suggested it at what confidence. This is what lets a
        solver weigh a shaky crossing letter (conf 0.6) differently from a
        locked one (conf 0.95), and gives the conflict-resolver exactly the
        discriminating detail it needs.
        """
        entry = self.entries[entry_id]
        detail = []
        for i, (r, c) in enumerate(entry.cells):
            cell = self._cells[(r, c)]
            crossers = {eid: v for eid, v in cell.votes.items() if eid != entry_id}
            if not crossers:
                detail.append({"index": i, "letter": None, "from": None,
                               "confidence": None})
                continue
            # at most one crosser in a standard grid; report it
            eid, v = next(iter(crossers.items()))
            detail.append({"index": i, "letter": v["letter"], "from": eid,
                           "confidence": v["confidence"]})
        return detail

    def crossings(self, entry_id: str) -> list:
        """For each cell of the entry, which other entries cross it.

        Returns list of dicts: {index, row, col, crosses: [other_entry_ids]}.
        """
        entry = self.entries[entry_id]
        result = []
        for i, (r, c) in enumerate(entry.cells):
            others = [
                oid for oid, oe in self.entries.items()
                if oid != entry_id and [r, c] in oe.cells
            ]
            result.append({"index": i, "row": r, "col": c, "crosses": others})
        return result

    def conflicts(self) -> list:
        """All cells whose votes contradict, with full provenance."""
        out = []
        for (r, c), cell in self._cells.items():
            if cell.conflicted():
                out.append({
                    "row": r, "col": c,
                    "votes": dict(cell.votes),   # entry_id -> letter
                })
        return out

    def constraint_score(self, entry_id: str) -> float:
        """Fraction of an entry's cells whose crossing word is committed.

        These are the cells whose letters are pinned by a neighbour. The
        scheduler prioritises high-scoring entries: they're easier to solve and
        their answers are easier to verify, and solving them propagates further.
        """
        entry = self.entries[entry_id]
        if not entry.cells:
            return 0.0
        fixed = 0
        for (r, c) in entry.cells:
            cell = self._cells[(r, c)]
            crossers = [eid for eid in cell.votes if eid != entry_id]
            if crossers:
                fixed += 1
        return fixed / len(entry.cells)

    def unsolved(self) -> list:
        return [eid for eid, e in self.entries.items() if not e.committed]

    # ---- mutations (the only ways state changes) -------------------------

    def commit(self, entry_id: str, answer: str,
               confidence: float, parse: Optional[str] = None,
               source: str = "solver") -> dict:
        """Commit an answer to an entry and propagate.

        Returns a report: whether the commit introduced any contradiction,
        and which crossing entries just became more constrained (so the
        scheduler can re-queue them).
        """
        entry = self.entries[entry_id]
        clean = answer.replace(" ", "").replace("-", "")
        if len(clean) != entry.length:
            return {"ok": False,
                    "error": f"length {len(clean)} != expected {entry.length}"}

        # snapshot crossing patterns before, to detect newly-constrained ones
        before = {oid: self.pattern(oid)
                  for oid in self._all_crossing_ids(entry_id)}

        entry.committed = answer.upper()
        entry.committed_confidence = confidence
        entry.parse = parse
        self._record_candidate(entry, answer, confidence, parse, source)
        self._rebuild()

        after = {oid: self.pattern(oid) for oid in before}
        newly_constrained = [oid for oid in before
                             if before[oid] != after[oid]]

        # cells where this answer is now corroborated by an agreeing crosser
        corroborated = sum(
            1 for (r, c) in entry.cells
            if self._cells[(r, c)].corroborated()
        )

        return {
            "ok": True,
            "conflicts": self.conflicts(),
            "newly_constrained": newly_constrained,
            "corroborated_cells": corroborated,
            "total_cells": len(entry.cells),
        }

    def retract(self, entry_id: str) -> dict:
        """Remove an entry's committed answer and recompute the grid."""
        entry = self.entries[entry_id]
        entry.committed = None
        entry.committed_confidence = 1.0
        entry.parse = None
        entry.verified = None
        self._rebuild()
        return {"ok": True, "conflicts": self.conflicts()}

    def add_candidate(self, entry_id: str, answer: str, confidence: float,
                      parse: Optional[str] = None,
                      source: str = "solver") -> dict:
        """Record a candidate WITHOUT committing it to the grid.

        Lets a solver float several possibilities; the orchestrator (or an
        auto-commit rule) decides which to commit.
        """
        entry = self.entries[entry_id]
        self._record_candidate(entry, answer, confidence, parse, source)
        return {"ok": True, "candidates": entry.candidates}

    def set_verified(self, entry_id: str, ok: bool) -> dict:
        self.entries[entry_id].verified = ok
        return {"ok": True}

    def set_parse(self, entry_id: str, parse: str) -> dict:
        """Update the parse on a committed entry without re-running propagation.

        Useful for the parse-rescue pass: once the grid is full, a fresh Parser
        subagent may discover a cleaner mechanism for an answer locked by
        crossings. This swaps in the new parse without touching the answer or
        adding noise to the candidates list.
        """
        entry = self.entries[entry_id]
        if not entry.committed:
            return {"ok": False,
                    "error": f"{entry_id} has no committed answer to attach a parse to"}
        entry.parse = parse
        # When a parse is rewritten, any prior verifier verdict on the old
        # parse no longer applies — clear it so re-verification is required.
        entry.verified = None
        return {"ok": True, "id": entry_id, "parse": parse}

    # ---- helpers ---------------------------------------------------------

    def _record_candidate(self, entry: Entry, answer: str, confidence: float,
                          parse, source) -> None:
        entry.candidates.append({
            "answer": answer.upper(),
            "confidence": confidence,
            "parse": parse,
            "source": source,
        })
        # keep candidates sorted best-first
        entry.candidates.sort(key=lambda c: c["confidence"], reverse=True)

    def _all_crossing_ids(self, entry_id: str) -> set:
        out = set()
        for cx in self.crossings(entry_id):
            out.update(cx["crosses"])
        return out
