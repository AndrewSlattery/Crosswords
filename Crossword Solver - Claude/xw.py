#!/usr/bin/env python3
"""
xw.py — the command-line interface to the grid engine.

This is THE tool surface. Every Claude instance (orchestrator or subagent)
interacts with grid state only by running subcommands of this script via bash.
All output is JSON on stdout so it's easy to read back programmatically, with
a --pretty flag for human/agent-readable views.

Run `python xw.py help` for the full list. Quick reference:

  from-text <file> [--out PATH | --init]   parse ASCII-grid+clue-list text into
                                            a puzzle.json (or load it straight
                                            into fresh state)
  init <puzzle.json>          load a puzzle definition into fresh state
  state                       full grid as ASCII + summary
  stats                       progress glance: solved, verified, conflicts, cells
  entry <id>                  one clue: text, length, current pattern, candidates
  pattern <id>                just the known-letter pattern, e.g. ?A??E?
  pattern-detail <id>         per-cell suggested letter + source entry + confidence
  crossings <id>              which entries cross this one, and where
  frontier                    unsolved entries ranked by how constrained they are
  candidate <id> <ans> <conf> [--parse "..."]   float a candidate, don't commit
  commit <id> <ans> <conf> [--parse "..."]      write an answer + propagate
  retract <id>                remove a committed answer
  verify <id> <true|false>    record a verifier's parse-check verdict
  parse <id> "<parse>"        swap an entry's parse in place (no commit/propagate)
  conflicts                   list every contradicted cell with provenance

Exit code is 0 on success, 1 on error, 2 on a commit that introduced a conflict
(so a script/agent can branch on it).

Concurrency: every command that mutates state holds an exclusive lock on
<state>.lock for the duration of its load->modify->save cycle, so parallel
subagent commits cannot lose updates. Readers are not locked (writes are
atomic via os.replace).
"""

import argparse
import contextlib
import json
import os
import re
import sys
import time

from engine import Grid, DEFAULT_STATE_PATH


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------

def _print(obj, pretty=False):
    if pretty and isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, indent=2 if pretty else None))


# --------------------------------------------------------------------------
# Cross-platform exclusive file lock
# --------------------------------------------------------------------------
#
# We use mkdir-as-lock: os.mkdir is atomic on every platform we care about,
# fails cleanly if the directory already exists, and needs no platform-specific
# imports. Held duration is a few milliseconds (load JSON, mutate object, write
# JSON), so contention is mild. A stale lock (process killed mid-commit) clears
# automatically after STALE_LOCK_SECONDS based on its mtime.

LOCK_TIMEOUT_SECONDS = 30
STALE_LOCK_SECONDS = 60


@contextlib.contextmanager
def _state_lock(state_path):
    lock_dir = state_path + ".lock"
    parent = os.path.dirname(lock_dir) or "."
    os.makedirs(parent, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError:
            # If the lock looks stale (older than STALE_LOCK_SECONDS), clear it.
            try:
                age = time.time() - os.path.getmtime(lock_dir)
                if age > STALE_LOCK_SECONDS:
                    try:
                        os.rmdir(lock_dir)
                    except OSError:
                        pass
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Could not acquire state lock {lock_dir} within "
                    f"{LOCK_TIMEOUT_SECONDS}s (another writer may be stuck)."
                )
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Text -> puzzle JSON parser
# --------------------------------------------------------------------------
#
# Input shape (whitespace-tolerant, in this order):
#
#   <ASCII grid: contiguous lines of ?/./# (and letters, optionally)>
#   <blank line(s)>
#   Across
#   1 Clue text (4,5)
#   6 Clue text (4)
#   ...
#   Down
#   1 Clue text (5)
#   2 Clue text (3)
#   ...
#
# Light cells: '?' or any letter A-Z (pre-fills are accepted but not committed
# here — they'd need to go through commit() to count as known).
# Blocked cells: '.' or '#'.
#
# Numbering follows the standard crossword convention: a light cell gets a
# number iff it starts an across run (no light to its left AND >=1 light to
# its right) or a down run (no light above AND >=1 light below). At most one
# number per cell, in row-major order.
#
# We validate that the parsed slot lengths agree with the parsed enumerations,
# and that every numbered slot has a clue and vice versa. Failures raise
# ValueError with a specific message — better to fail at parse time than feed
# the engine a malformed grid.

BLOCK_CHARS = set(".#")
LIGHT_CHARS = set("?") | {chr(c) for c in range(ord("A"), ord("Z") + 1)} \
                       | {chr(c) for c in range(ord("a"), ord("z") + 1)}
GRID_LINE_RE = re.compile(r"^[?.#A-Za-z]+$")
HEADER_RE = re.compile(r"^\s*(across|down)\b.*$", re.IGNORECASE)
# Capture: number, clue body, enumeration (digits + , - or spaces inside parens).
CLUE_RE = re.compile(
    r"^\s*(\d+)[\s.):]+\s*(.*?)\s*\(([\d,\-\s]+)\)\s*$"
)


def parse_text_puzzle(text):
    """Parse ASCII grid + Across/Down clue lists into a puzzle.json-shaped dict.

    Returns {"rows": int, "cols": int, "entries": [...]}. Raises ValueError on
    any structural inconsistency (mismatched lengths, missing clues, etc.).
    """
    lines = text.splitlines()

    # ---- 1. Locate the grid block ---------------------------------------
    i = 0
    while i < len(lines) and not GRID_LINE_RE.match(lines[i].strip()):
        i += 1
    grid_lines = []
    while i < len(lines) and GRID_LINE_RE.match(lines[i].strip()):
        grid_lines.append(lines[i].strip())
        i += 1
    if not grid_lines:
        raise ValueError("No grid found in input (expected lines of ?/./# chars)")

    rows = len(grid_lines)
    cols = max(len(line) for line in grid_lines)
    bad = [(r, len(line)) for r, line in enumerate(grid_lines) if len(line) != cols]
    if bad:
        raise ValueError(
            f"Grid rows are uneven (cols={cols}); offending rows={bad}"
        )

    def is_light(r, c):
        if r < 0 or r >= rows or c < 0 or c >= cols:
            return False
        return grid_lines[r][c] not in BLOCK_CHARS

    # ---- 2. Number cells, identify slot starts --------------------------
    numbered = {}        # (r, c) -> number
    slots = {}           # (number, direction) -> [[r, c], ...]
    n = 0
    for r in range(rows):
        for c in range(cols):
            if not is_light(r, c):
                continue
            starts_across = (not is_light(r, c - 1)) and is_light(r, c + 1)
            starts_down = (not is_light(r - 1, c)) and is_light(r + 1, c)
            if not (starts_across or starts_down):
                continue
            n += 1
            numbered[(r, c)] = n
            if starts_across:
                cells = []
                cc = c
                while is_light(r, cc):
                    cells.append([r, cc])
                    cc += 1
                slots[(n, "across")] = cells
            if starts_down:
                cells = []
                rr = r
                while is_light(rr, c):
                    cells.append([rr, c])
                    rr += 1
                slots[(n, "down")] = cells

    # ---- 3. Parse clue lists --------------------------------------------
    clues = {}   # (number, direction) -> (clue_text, enumeration_list)
    direction = None
    for line in lines[i:]:
        stripped = line.strip()
        if not stripped:
            continue
        h = HEADER_RE.match(stripped)
        if h:
            direction = h.group(1).lower()
            continue
        if direction is None:
            continue
        m = CLUE_RE.match(stripped)
        if not m:
            # Tolerate trailing notes/legend lines after the clues; skip silently.
            continue
        num = int(m.group(1))
        body = m.group(2).strip()
        enum_raw = m.group(3)
        enum = [int(x) for x in re.findall(r"\d+", enum_raw)]
        if not enum:
            raise ValueError(f"Clue {num}{direction[0].upper()} has empty enumeration")
        # Reconstruct a clean clue string that includes the enumeration suffix,
        # since solvers expect to see it in the displayed clue.
        # Preserve separators (',' vs '-') from the original enum string.
        clue_text = f"{body} ({enum_raw.strip()})"
        clues[(num, direction)] = (clue_text, enum)

    # ---- 4. Reconcile slots vs clues ------------------------------------
    slot_keys = set(slots.keys())
    clue_keys = set(clues.keys())
    missing_clues = sorted(slot_keys - clue_keys)
    extra_clues = sorted(clue_keys - slot_keys)
    if missing_clues:
        raise ValueError(
            "Grid has slots with no matching clue: "
            + ", ".join(f"{n}{d[0].upper()}" for n, d in missing_clues)
        )
    if extra_clues:
        raise ValueError(
            "Clues with no matching slot in grid: "
            + ", ".join(f"{n}{d[0].upper()}" for n, d in extra_clues)
        )

    # ---- 5. Build entry records, validating enumeration sums ------------
    entries = []
    for (num, dirn), cells in sorted(slots.items()):
        clue_text, enum = clues[(num, dirn)]
        length = len(cells)
        if sum(enum) != length:
            raise ValueError(
                f"{num}{dirn[0].upper()}: enumeration {enum} sums to {sum(enum)}, "
                f"but the grid slot has {length} cells"
            )
        entries.append({
            "id": f"{num}{dirn[0].upper()}",
            "direction": dirn,
            "number": num,
            "clue": clue_text,
            "length": length,
            "enumeration": enum,
            "cells": cells,
        })

    return {"rows": rows, "cols": cols, "entries": entries}


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def cmd_from_text(args):
    """Parse a text-format puzzle and either print, save, or init state from it."""
    with open(args.input, encoding="utf-8") as f:
        text = f.read()
    data = parse_text_puzzle(text)
    summary = {
        "rows": data["rows"],
        "cols": data["cols"],
        "entries": len(data["entries"]),
    }
    wrote_anything = False
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        summary["out"] = args.out
        wrote_anything = True
    if args.init:
        grid = Grid(data)
        with _state_lock(args.state):
            grid.save(args.state)
        summary["state"] = args.state
        wrote_anything = True
    if not wrote_anything:
        # Just print the JSON itself, not a summary, so the user can redirect.
        _print(data, args.pretty)
        return
    summary["ok"] = True
    _print(summary, args.pretty)


def cmd_init(args):
    with open(args.puzzle, encoding="utf-8") as f:
        data = json.load(f)
    grid = Grid(data)
    with _state_lock(args.state):
        grid.save(args.state)
    _print({"ok": True, "entries": len(grid.entries),
            "rows": grid.rows, "cols": grid.cols}, args.pretty)


def cmd_state(args):
    grid = Grid.load(args.state)
    ascii_grid = render_ascii(grid)
    summary = {
        "solved": [e.id for e in grid.entries.values() if e.committed],
        "unsolved": grid.unsolved(),
        "conflicts": grid.conflicts(),
    }
    if args.pretty:
        print(ascii_grid)
        print()
        print(json.dumps(summary, indent=2))
    else:
        _print({"grid": ascii_grid, **summary})


def cmd_stats(args):
    """Quick progress glance — handy for an orchestrator to log between rounds."""
    grid = Grid.load(args.state)
    total = len(grid.entries)
    solved = sum(1 for e in grid.entries.values() if e.committed)
    verified = sum(1 for e in grid.entries.values() if e.verified is True)
    rejected = sum(1 for e in grid.entries.values() if e.verified is False)
    cells_total = len(grid._cells)
    cells_filled = sum(1 for c in grid._cells.values() if c.letter() is not None)
    cells_corroborated = sum(1 for c in grid._cells.values() if c.corroborated())
    conflicts = len(grid.conflicts())
    _print({
        "entries": {
            "total": total, "solved": solved,
            "unsolved": total - solved,
            "verified": verified, "verify_rejected": rejected,
            "pct_solved": round(100 * solved / total, 1) if total else 0.0,
        },
        "cells": {
            "total": cells_total,
            "filled": cells_filled,
            "corroborated": cells_corroborated,
            "pct_filled": round(100 * cells_filled / cells_total, 1) if cells_total else 0.0,
        },
        "conflicts": conflicts,
    }, args.pretty)


def cmd_entry(args):
    grid = Grid.load(args.state)
    e = grid.entries[args.id]
    out = {
        "id": e.id, "clue": e.clue, "length": e.length,
        "enumeration": e.enumeration,
        "pattern": grid.pattern(args.id),
        "pattern_detail": grid.pattern_detail(args.id),
        "committed": e.committed, "parse": e.parse, "verified": e.verified,
        "candidates": e.candidates,
        "constraint_score": round(grid.constraint_score(args.id), 3),
    }
    _print(out, args.pretty)


def cmd_pattern(args):
    grid = Grid.load(args.state)
    _print(grid.pattern(args.id), args.pretty)


def cmd_pattern_detail(args):
    grid = Grid.load(args.state)
    _print(grid.pattern_detail(args.id), args.pretty)


def cmd_crossings(args):
    grid = Grid.load(args.state)
    _print(grid.crossings(args.id), args.pretty)


def cmd_frontier(args):
    """Unsolved entries, most-constrained first — the scheduler's view."""
    grid = Grid.load(args.state)
    rows = []
    for eid in grid.unsolved():
        rows.append({
            "id": eid,
            "clue": grid.entries[eid].clue,
            "pattern": grid.pattern(eid),
            "constraint_score": round(grid.constraint_score(eid), 3),
        })
    rows.sort(key=lambda r: r["constraint_score"], reverse=True)
    _print(rows, args.pretty)


def cmd_candidate(args):
    with _state_lock(args.state):
        grid = Grid.load(args.state)
        res = grid.add_candidate(args.id, args.answer, args.conf,
                                 parse=args.parse, source=args.source)
        grid.save(args.state)
    _print(res, args.pretty)


def cmd_commit(args):
    with _state_lock(args.state):
        grid = Grid.load(args.state)
        res = grid.commit(args.id, args.answer, args.conf,
                          parse=args.parse, source=args.source)
        if not res["ok"]:
            _print(res, args.pretty)
            sys.exit(1)
        grid.save(args.state)
    _print(res, args.pretty)
    if res["conflicts"]:
        sys.exit(2)   # signal: commit succeeded but the grid is now contradictory


def cmd_retract(args):
    with _state_lock(args.state):
        grid = Grid.load(args.state)
        res = grid.retract(args.id)
        grid.save(args.state)
    _print(res, args.pretty)


def cmd_verify(args):
    with _state_lock(args.state):
        grid = Grid.load(args.state)
        res = grid.set_verified(args.id, args.value == "true")
        grid.save(args.state)
    _print(res, args.pretty)


def cmd_parse(args):
    """Update an entry's parse string in place (no answer change, no propagation).

    Use this for the parse-rescue pass after the grid is solved: a fresh
    Parser subagent may discover a cleaner mechanism for an already-locked
    answer, and you want to swap the parse without piling up new candidates.
    Clears any prior verifier verdict on the entry — re-verify the new parse.
    """
    with _state_lock(args.state):
        grid = Grid.load(args.state)
        res = grid.set_parse(args.id, args.parse)
        if not res["ok"]:
            _print(res, args.pretty)
            sys.exit(1)
        grid.save(args.state)
    _print(res, args.pretty)


def cmd_conflicts(args):
    grid = Grid.load(args.state)
    _print(grid.conflicts(), args.pretty)


def render_ascii(grid: Grid) -> str:
    """A human/agent-readable picture of the grid.

    '#' = blocked, '.' = light but unknown, letter = resolved cell,
    '*' = a cell currently in contradiction.
    """
    chars = [["#"] * grid.cols for _ in range(grid.rows)]
    for (r, c), cell in grid._cells.items():
        if cell.conflicted():
            chars[r][c] = "*"
        elif cell.letter():
            chars[r][c] = cell.letter()
        else:
            chars[r][c] = "."
    return "\n".join(" ".join(row) for row in chars)


def build_parser():
    # Common options live on a parent parser so they're accepted both before
    # AND after the subcommand (argparse is fussy about ordering otherwise).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", default=DEFAULT_STATE_PATH,
                        help="path to state file (default: %(default)s)")
    common.add_argument("--pretty", action="store_true",
                        help="human-readable output")

    p = argparse.ArgumentParser(description="Cryptic crossword grid tool",
                                parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name):
        return sub.add_parser(name, parents=[common])

    s = add("from-text")
    s.add_argument("input", help="path to a text file: ASCII grid + Across/Down clue list")
    s.add_argument("--out", help="write puzzle.json to this path")
    s.add_argument("--init", action="store_true",
                   help="also load it into fresh state at --state")
    s.set_defaults(fn=cmd_from_text)

    s = add("init"); s.add_argument("puzzle"); s.set_defaults(fn=cmd_init)
    s = add("state"); s.set_defaults(fn=cmd_state)
    s = add("stats"); s.set_defaults(fn=cmd_stats)
    s = add("entry"); s.add_argument("id"); s.set_defaults(fn=cmd_entry)
    s = add("pattern"); s.add_argument("id"); s.set_defaults(fn=cmd_pattern)
    s = add("pattern-detail"); s.add_argument("id"); s.set_defaults(fn=cmd_pattern_detail)
    s = add("crossings"); s.add_argument("id"); s.set_defaults(fn=cmd_crossings)
    s = add("frontier"); s.set_defaults(fn=cmd_frontier)
    s = add("conflicts"); s.set_defaults(fn=cmd_conflicts)

    s = add("candidate")
    s.add_argument("id"); s.add_argument("answer"); s.add_argument("conf", type=float)
    s.add_argument("--parse"); s.add_argument("--source", default="solver")
    s.set_defaults(fn=cmd_candidate)

    s = add("commit")
    s.add_argument("id"); s.add_argument("answer"); s.add_argument("conf", type=float)
    s.add_argument("--parse"); s.add_argument("--source", default="solver")
    s.set_defaults(fn=cmd_commit)

    s = add("retract"); s.add_argument("id"); s.set_defaults(fn=cmd_retract)

    s = add("verify")
    s.add_argument("id"); s.add_argument("value", choices=["true", "false"])
    s.set_defaults(fn=cmd_verify)

    s = add("parse")
    s.add_argument("id"); s.add_argument("parse")
    s.set_defaults(fn=cmd_parse)

    s = add("help"); s.set_defaults(fn=lambda a: print(__doc__))
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.fn(args)
