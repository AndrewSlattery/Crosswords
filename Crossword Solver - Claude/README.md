# Cryptic Crossword Solver Suite

A toolkit that lets a Claude Code session solve a full cryptic grid far more
efficiently than working one clue at a time in its head. **Deterministic code
owns the grid and all the bookkeeping; Claude instances do only the per-clue
reasoning.** That division of labour is the whole point — never try to hold
grid state in your head when these tools hold it perfectly.

If you are the orchestrating instance, read this file fully before starting.

---

## How the "tools" work

There is no special tool-registration. Every tool is just a command-line
script you run with `python`, and grid state lives in one JSON file
(`state.json`) that all script invocations share. A subagent solving a single
clue runs the very same scripts. So "calling a tool" = running a bash command
and reading its JSON output.

Two scripts:

- `xw.py` — the grid: state, patterns, crossings, commit, retract, conflicts.
- `check.py` — cheap deterministic gates: is-this-a-real-word, does-it-fit-the-pattern.

Run `python xw.py help` for the full subcommand list. All output is JSON;
add `--pretty` for readable output. State path overridable with `--state` or
the `CRYPTIC_STATE` env var; wordlist via `CRYPTIC_WORDLIST` (default `words.txt`).

Commit exit codes: `0` clean, `1` rejected (e.g. wrong length), `2` committed
**but the grid is now contradictory** — branch on this.

---

## The mental model

The grid is two coupled constraint problems: the crossword layer (a CSP over a
shared letter grid) and the clue layer (each clue an independent reasoning
task). The scripts own the first; you and your subagents own the second.

Two rules the engine enforces, which you should internalise:

1. **A letter shows in a clue's pattern as soon as its single crossing word is
   committed.** In a normal grid each cell has at most two crossers (one across,
   one down), so a letter is pinned the moment the *one* word crossing it lands —
   waiting for both would be useless, since by then the cell is fully solved and
   helps no remaining clue. Each pattern letter carries provenance and the
   crossing answer's confidence (`xw.py pattern-detail <id>`), so a solver can
   trust a 0.95 crossing letter more than a 0.6 one.

2. **Corroboration is a separate, stronger signal used for *verification*, not
   patterning.** When both the across and the down through a cell agree, that
   cell is *corroborated* — two independent answers concurring. `commit` reports
   how many of an answer's cells are corroborated; high corroboration is strong
   evidence the answer is right. Don't confuse this with the patterning rule:
   one tells unsolved clues what letters to expect, the other tells you how much
   to trust answers already placed.

3. **The grid is always recomputed from committed answers.** Retracting an
   answer and recomputing is exact and cheap, so conflict resolution is
   principled, never guesswork. You never hand-edit cells.

---

## The solving loop (orchestrator's job)

```
0. python xw.py from-text puzzles/<puzzle>.txt --init      # if starting from raw text
   # OR: python xw.py init puzzles/<puzzle>.json           # if you already have JSON
1. python xw.py stats                # optional: sanity-check the load
2. Repeat until no unsolved entries and no conflicts:
   a. python xw.py frontier        # unsolved entries, MOST-CONSTRAINED FIRST
   b. Dispatch the top few as PARALLEL subagents (one clue each).
   c. Each subagent returns answer + confidence + parse; you commit them.
   d. After each commit, read `conflicts` and `newly_constrained` from output.
        - newly_constrained entries -> re-queue them (their pattern shrank).
        - conflicts -> run the conflict-resolution routine below.
   e. Optionally dispatch a verifier on freshly-locked entries.
3. PARSE RESCUE: for every entry whose parse felt shaky during solving
   (some clue words unexplained, indicators stretched, solver expressed
   doubt), dispatch a fresh Parser subagent with the prior parse as a hint,
   then `xw.py parse <id> "<new parse>"` to swap in the cleaner mechanism.
4. VERIFY: dispatch a Verifier on each final parse, then `xw.py verify <id> ...`.
5. python xw.py state --pretty      # final grid
```

Concurrent commits are safe: every mutating command holds an exclusive
filesystem lock on `<state>.lock` for the duration of its load-mutate-save
cycle, so parallel subagents cannot lose each other's writes. Readers are
unlocked (writes are atomic via `os.replace`).

**Parallelism = breadth across independent clues, not many instances on one
clue.** Clues with no shared cells can be solved simultaneously with zero
coordination because the grid layer serialises every write. Always solve the
most-constrained clues first: a clue that's half-checked by crossings is both
easier to solve and easier to verify, and its answer cascades confidence onward.

Do **not** harden letters by over-committing on raw confidence. Prefer to
`candidate` uncertain answers (float them without writing the grid) and only
`commit` when either confidence is high or a crossing already agrees.

### Parse rescue: why the post-solve pass matters

When the grid is locked and every cell agrees, the *answers* are essentially
guaranteed correct (cross-checked from two directions). The *parses*, however,
are whatever the Solver guessed under time pressure, and they're systematically
worse than what a fresh Parser would produce — because the original Solver
anchored on an interpretation that happened to fit and stopped looking. Real
patterns observed in this codebase, where the Solver's first parse was
plausible-but-wrong and a fresh Parser found the elegant mechanism:

| Solver thought… | Setter actually meant… |
|---|---|
| Cryptic def | Whole-clue anagram with parenthetical fodder ("suspect" was the indicator) |
| Spoonerism of literal surface words | Spoonerism of a *semantic paraphrase* ("lover was loud in bed" → "beau snored" → SNOW BORED) |
| Charade D + ISC + O | Reverse-hidden inside adjacent words ("chicag**OCSID**etectives") |
| Card-game trivia about queens/jacks | Letter deletion from a proper noun (JUNO − J = UNO) |
| Synonym substitution (RIGHT for "bit of maths") | Specific abbreviation (TRIG) |
| Letter-swap on one wordplay component | Letter-swap on the *concatenation* of two (FLEES TYRE → FREES TYLE under L↔R) |
| Anagram of one synonym | Anagram of two synonyms together (SHOULD + DRAPE → SHOULDER PAD) |

Every one of these is a category of mechanism a Solver under pressure can miss
but a Parser with the answer locked will spot. Always run the rescue pass.

---

## The roles (each a subagent prompt)

Keep these separate. A solver that also verifies its own work has sunk-cost
bias; a verifier that never solved has none.

### Solver
Input: the clue, its enumeration, and the current `pattern` (e.g. `?A??E?`).
Task: solve the cryptic clue, respecting the pattern. Return the answer, a
confidence in [0,1], and a parse in the house notation (see the parse cheat
sheet in the project files). Before returning, self-check with
`python check.py pattern <PAT> <ANSWER>`.

Solvers should cycle through device types (anagram of the whole clue,
hidden/reverse-hidden, deletion from proper noun, charade, container,
reversal, Spoonerism, substitution) rather than locking onto the first
plausible reading — see `PROMPTS.md` for the full checklist. A clean parse
explains every clue word except link words; if yours leaves words unexplained,
try a different device.

### Conflict resolver
Triggered when a commit returns conflicts. Routine:
  1. `python xw.py conflicts` — each contradicted cell now lists the disagreeing
     entries *with their letters and confidences*, so the weak link is often
     visible immediately (e.g. `1A: C@0.9` vs `1D: S@0.6` → suspect 1D).
  2. If confidences are close, the prime suspect is the entry with the **fewest
     committed crossers** (lowest `constraint_score`) — it has the least
     independent corroboration.
  3. `python xw.py retract <suspect>` to restore a clean grid.
  4. Re-dispatch a solver for the suspect, passing the conflict context: "your
     previous answer X conflicts with crossing letters strongly suggesting
     pattern `?A?T?`; find an alternative that fits." This conflict-aware
     re-prompt is where the instance earns its keep — far better than a cold retry.

### Parser
Input: clue + the confirmed answer (+ optionally a prior parse). Output: a
parse in house notation. Run this both:
- **Reactively**, on any entry where the Solver's wordplay didn't fully
  decompose ("surface filler" notes, indicators stretched), and
- **Routinely**, in the parse-rescue pass after the grid is solved — for every
  committed answer, since a Parser with the answer locked is systematically
  better than a Solver who guessed under pressure.

The Parser must be willing to discard a prior parse, not defend it: that's the
whole point of separating the role. A correct parse is strong evidence the
answer is right; an answer that *can't* be parsed cryptically but happens to
fit the letters is the classic false-fit and should be treated as suspect.
Once the Parser returns, swap in the new parse with `python xw.py parse <id>
"<new parse>"` (no answer change, no propagation, but clears any prior verify
verdict so the new parse will get judged afresh).

### Verifier
Input: (clue, answer, parse). Output: a single judgement — does the parse
validly derive this answer per the notation, does the definition match, and
are *all* the non-link clue words accounted for? Record it with `python xw.py
verify <id> true|false`. The verifier never proposes answers; that
independence is the point. If the parse is correct *as far as it goes* but
leaves clue words unexplained, that's a defect — set `valid: false` and the
orchestrator will route the entry back through the Parser.

---

## Command quick reference

| Command | Purpose |
|---|---|
| `xw.py from-text <file> [--out PATH] [--init]` | parse ASCII-grid+clue-list text into puzzle JSON (and/or load straight into state) |
| `xw.py init <puzzle.json>` | load a puzzle into fresh state |
| `xw.py state` | ASCII grid + solved/unsolved/conflicts |
| `xw.py stats` | progress glance: solved/total, verified, conflicts, cells filled/corroborated |
| `xw.py frontier` | unsolved entries ranked by constraint (scheduler view) |
| `xw.py entry <id>` | one clue: text, pattern, candidates, parse, verified |
| `xw.py pattern <id>` | known-letter pattern, e.g. `?A??E?` (a letter once its one crosser is committed) |
| `xw.py pattern-detail <id>` | per-cell: suggested letter, which entry suggested it, at what confidence |
| `xw.py crossings <id>` | which entries cross this one, and at which index |
| `xw.py candidate <id> <ans> <conf> [--parse "..."]` | float a candidate, don't write grid |
| `xw.py commit <id> <ans> <conf> [--parse "..."] [--source ...]` | write answer + propagate |
| `xw.py retract <id>` | remove a committed answer, recompute grid |
| `xw.py parse <id> "<parse>"` | swap an entry's parse in place (no propagation; clears the verify verdict) |
| `xw.py verify <id> true\|false` | record verifier verdict |
| `xw.py conflicts` | all contradicted cells with provenance |
| `check.py pattern <PAT> <ANSWER>` | does it fit `?A?`-style pattern? |

---

## Puzzle file format

There are two ways in:

**A. From plain text** (recommended for human-pasted puzzles). Put an ASCII
grid using `?` for lights and `.` (or `#`) for blocks, then a blank line, then
`Across` / `Down` headers with numbered clues. Enumerations like `(4,5)` or
`(5-2)` go at the end of each clue. See `puzzles/sample.txt` for a worked
15×15 example. Then:

```
python xw.py from-text puzzles/sample.txt --init
```

The parser numbers cells the standard way, infers across/down slots, validates
that every slot has a clue (and vice versa) and that each clue's enumeration
sums to the slot length. Mismatches fail loudly at parse time rather than
silently corrupting state.

**B. From JSON.** A puzzle is JSON with `rows`, `cols`, and `entries`. Each
entry lists its cells as `[row, col]` pairs **in reading order** (left-to-right
for across, top-to-bottom for down). Crossings are inferred automatically from
shared cells, so you only have to get the coordinates right. See
`puzzles/example.json` for a complete worked grid (CAT/ORE/BEE across).

```json
{
  "rows": 3, "cols": 3,
  "entries": [
    {"id": "1A", "direction": "across", "number": 1,
     "clue": "Feline that's heard to wander (3)",
     "length": 3, "enumeration": [3],
     "cells": [[0,0],[0,1],[0,2]]}
  ]
}
```

---

## Files

- `engine.py` — the grid model and constraint propagation. Pure, deterministic,
  no model reasoning. Read it if you want to understand the voting/hardening rules.
- `xw.py` — CLI over the engine. Includes the text→JSON parser (`from-text`).
  This is the main tool surface.
- `check.py` — pattern-fits-answer gate (the only deterministic answer check).
- `puzzles/example.json` — a complete tiny worked example (3×3).
- `puzzles/sample.txt` — a full 15×15 cryptic in the text input format.

## What deliberately is *not* here

- No model calls inside the engine — that's a feature; propagation must be exact.
- No automatic committing — you decide what to commit, so an over-confident
  wrong answer can't poison the grid behind your back.
- No undo log — the grid recomputes from committed answers, which is simpler
  and cannot drift out of sync.
