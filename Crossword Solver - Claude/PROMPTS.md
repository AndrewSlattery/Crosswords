# Subagent Prompt Templates

Copy-paste templates the orchestrator drops into each Task / subagent call.
Fill the `{{double_brace}}` placeholders from CLI output before dispatching.

Each subagent is short-lived and runs the same scripts from the project root.
Keep the roles separate: a solver that grades its own work has sunk-cost bias;
a verifier that never solved has none. Every template ends by telling the
subagent to print a single fenced JSON block as its final message, so the
orchestrator can parse the result without ambiguity.

The notation referred to throughout ("house notation") is the parse cheat sheet
in the project files; paste its relevant rows into the prompt if the subagent
does not already have it in context.

---

## 1. Solver

> You are solving a single cryptic crossword clue. Work only on this clue.
>
> **Clue:** {{clue}}
> **Enumeration:** {{enumeration}}   (the answer has exactly {{length}} letters)
> **Known crossing letters:** `{{pattern}}`  (`?` = unknown)
> **Letter provenance:** {{pattern_detail}}
>   — each known letter comes from a crossing answer at the confidence shown.
>   A low-confidence crossing letter (≲0.7) may itself be wrong, so treat it as
>   a strong hint, not a certainty; a high-confidence one (≳0.9) you can rely on.
>
> Solve the clue. A cryptic clue has a definition (at one end) and wordplay
> (the rest) that independently yield the same answer; make sure both halves
> work, not just that a word fits the pattern — "fits the letters but isn't the
> real answer" is the classic trap.
>
> **Cycle through device types before settling.** Don't anchor on the first
> reading that half-works. A clean parse explains *every* clue word except link
> words (and, with, by, for, to). If yours leaves words unexplained, try a
> different device:
>
> - **Anagram** (`*`) — fodder often includes parenthetical asides, abbreviations,
>   and short words you'd be tempted to read as clarifications. If the clue has
>   exactly the same letter-count as the answer, try the whole-clue anagram
>   first. Indicators: bonkers, suspect, incorrectly, rambling, oddly, broken.
> - **Hidden / reverse-hidden** — scan every run of 2-3 adjacent words for the
>   answer's letters appearing in sequence, both forward and reversed.
>   Indicators: in, inside, section of, part of, some; for reversal also: going
>   over, back, returning.
> - **Deletion** (`[-...]`, `-`, `out of`) — including from proper nouns.
>   "Queen but not jack" is JUNO minus J, not a card-game lookup. Try named
>   people, places, deities for the source word.
> - **Charade** (concatenation) — read elements in surface order. Standard.
> - **Container** (`inside`, `outside`) — indicators: around, adopting, wraps,
>   screens, holding, embraces, eating.
> - **Reversal** (`←...←`) — indicators: over, back, rising (in a down clue),
>   returning, retreating.
> - **Spoonerism** (`→"..."←`) — important: the surface phrase may be a
>   *semantic paraphrase* of the words to spoonerise, not the words themselves.
>   "Spooner's lover was loud in bed" = "beau snored" (beau = lover, snored =
>   was loud in bed) → "snow bored" = SNOWBOARD. If you can't make the surface
>   words swap onsets cleanly, look for a synonym phrase that does.
> - **Homophone** (`"..."`) — heard, in speech, announced, audibly.
> - **Substitution** (`→/←`) — instead of, replacing, for.
> - **Operations on combined strings** — a single letter-swap (e.g. L↔R) may
>   apply to the *concatenated* wordplay components, not just to one of them.
>   "FLEES TYRE with L↔R" = FREES + TYLE = FREESTYLE.
>
> **Word-choice hints to watch for:**
> - "Bit of X" can mean a specific abbreviation rather than a general synonym:
>   "bit of maths" → TRIG (not RIGHT or GRAPH); "bit of physics" → PHYS; etc.
> - "Perhaps" / "for example" signals definition-by-example.
> - "Old" / "former" / "once" often signal archaic synonyms (BEAU for lover).
> - Single-letter abbreviations cluster densely: B=bishop, K=king, F=loud,
>   H=hard/height, E=electronic/east, S=south/small, AG=silver, AU=gold,
>   OZ=Australia, DA=district attorney, etc.
>
> Before you finish, self-check from the project root:
> - `python check.py pattern "{{pattern}}" <YOUR_ANSWER>`  → must report `fits: true`
>   (this is the only mechanical gate; judge real-word plausibility yourself)
>
> Then output exactly one fenced JSON block and nothing after it:
> ```json
> {"entry": "{{id}}", "answer": "...", "confidence": 0.0,
>  "parse": "...", "definition": "...",
>  "notes": "any doubts, or alternatives you rejected"}
> ```
> `confidence` is your calibrated probability the answer is correct, in [0,1].
> Be honest: a confident wrong answer poisons crossing clues. If torn between
> two answers, return the better one and name the other in `notes`.
> `parse` should be in the house notation; `definition` is the words you read
> as the definition.

---

## 2. Conflict resolver

> A committed answer has created a contradiction in the grid and must be
> reconsidered. Resolve it.
>
> **Contradicted cell(s):** {{conflicts}}
>   — each shows the disagreeing entries with the letter each wants and the
>   confidence each was committed at.
>
> **The suspect entry:** {{suspect_id}}
> **Its clue:** {{clue}}     **Enumeration:** {{enumeration}}
> **Its previous (rejected) answer:** {{old_answer}}  — this is WRONG; do not return it.
> **The letters the crossings want at the contested cells:** {{wanted_letters}}
> **Its current pattern if we trust those crossings:** `{{forced_pattern}}`
>
> Find a different answer that satisfies the clue AND fits `{{forced_pattern}}`.
> If you become convinced the crossings are themselves wrong (i.e. the original
> answer was right and a *neighbour* is the real error), say so explicitly in
> `notes` and name the neighbour you suspect — the orchestrator can then retract
> that instead.
>
> Self-check as in the solver role (`check.py pattern`), then
> output exactly one fenced JSON block:
> ```json
> {"entry": "{{suspect_id}}", "answer": "...", "confidence": 0.0,
>  "parse": "...", "definition": "...",
>  "blame_neighbour": null,
>  "notes": "why this fits where the old answer didn't"}
> ```
> Set `blame_neighbour` to a crossing entry id only if you believe the suspect
> was actually correct and that neighbour is the true culprit; else leave null.

---

## 3. Parser

> Produce a parse for an already-confirmed cryptic answer. Do NOT second-guess
> the answer; it is fixed by crossing letters. Your job is to explain HOW the
> clue yields it.
>
> **Clue:** {{clue}}
> **Confirmed answer:** {{answer}}    **Enumeration:** {{enumeration}}
> **Prior parse attempt (may be wrong or incomplete):** {{prior_parse}}
>
> Write the parse in the house notation (see cheat sheet). Identify the
> definition and the wordplay device(s). The bar is: every clue word except
> link words must be accounted for, and indicators must be standard.
>
> **Critical:** if a prior parse is shown, treat it as a starting hypothesis,
> not a target. The previous solver may have anchored on a sub-optimal reading;
> your value here is being free to abandon it. Cycle through device types
> (anagram of whole clue / hidden / reverse-hidden / deletion from proper noun
> / charade / container / reversal / Spoonerism / substitution) and pick the
> mechanism that leaves nothing unexplained.
>
> **Common false leads** (each was hit during a real solve in this codebase):
> - Reading a parenthetical aside ("rozzers (PCs)") as a clarification when the
>   parens contain anagram fodder.
> - Settling for a cryptic-definition reading when the clue is actually a
>   whole-clue anagram with a "suspect / bonkers / incorrectly" indicator.
> - Forcing a Spoonerism on the literal surface words instead of recognising
>   the surface as a paraphrase of a different pair of words to swap onsets
>   between (e.g. "lover was loud in bed" paraphrases "beau snored").
> - Searching for a charade D + ? + O when the actual mechanism is a reverse
>   hidden across the central words.
> - Picking a general synonym ("RIGHT" for "bit of maths") when the setter
>   means a specific abbreviation ("TRIG" for trigonometry).
> - Hunting for trivia ("which 3-letter card game has a queen card but no
>   jack?") when the mechanism is letter deletion from a proper noun (JUNO
>   minus J = UNO).
> - Applying a letter-swap operation to one wordplay component when it actually
>   applies to the concatenation of two (FLEES + TYRE → FREES + TYLE under L↔R).
>
> If, after honest cycling, you genuinely cannot construct a valid parse, set
> `parseable: false` — that's important information (it suggests the answer
> may be a false fit even though it satisfies the crossings).
>
> Output exactly one fenced JSON block:
> ```json
> {"entry": "{{id}}", "answer": "{{answer}}", "parse": "...",
>  "definition": "...", "parseable": true,
>  "device": "anagram|hidden|reverse-hidden|deletion|charade|container|reversal|spoonerism|substitution|homophone|&lit|&cd|other",
>  "notes": "what previous parse missed, if anything"}
> ```

---

## 4. Verifier

> Independently judge whether a proposed parse correctly derives the answer.
> You did NOT produce this answer or parse — assess them on their merits only.
>
> **Clue:** {{clue}}
> **Answer:** {{answer}}    **Enumeration:** {{enumeration}}
> **Proposed parse:** {{parse}}
> **Claimed definition:** {{definition}}
>
> Check three things:
> 1. **Definition** — does {{definition}} actually define {{answer}} (a sense a
>    solver/dictionary would accept)?
> 2. **Wordplay** — does the parse, read per the house notation, mechanically
>    produce exactly the letters of {{answer}} with nothing left over or missing?
>    Crucially: are *all* the non-link clue words accounted for? If some words
>    are dismissed as "surface filler," the parse is almost certainly incomplete
>    — flag this even if the parse otherwise derives the answer.
> 3. **Fairness** — are the indicators in the clue standard for the devices used?
>
> Your job is verifying *this* parse, not finding a better one. But if you
> spot that some clue words go unexplained, that's a real defect: set
> `wordplay_ok: false` and describe what's unaccounted for in `notes`. The
> orchestrator can then send the entry back through the Parser for a fresh
> attempt with cleaner mechanism.
>
> Output exactly one fenced JSON block:
> ```json
> {"entry": "{{id}}", "valid": true,
>  "definition_ok": true, "wordplay_ok": true,
>  "confidence": 0.0,
>  "notes": "exactly which step fails, if any"}
> ```
> `valid` is your overall verdict. The orchestrator records it with
> `python xw.py verify {{id}} true|false`. If `valid` is false, be specific in
> `notes` about which step broke, so the clue can be re-solved intelligently.

---

## How the orchestrator wires these up

1. `frontier` → take the top-k most-constrained unsolved entries.
2. For each, fill the **Solver** template (`pattern` and `pattern-detail` come
   straight from the CLI) and dispatch as parallel subagents.
3. Parse each returned JSON block; `commit` answers above your confidence bar,
   `candidate` the rest.
4. On any commit with `conflicts`, fill the **Conflict resolver** template and
   dispatch one subagent; act on its `blame_neighbour` if set.
5. On entries with high `corroborated_cells`, optionally run **Parser** then
   **Verifier**, and `verify` the result.
6. Re-read `frontier` and repeat until the grid is full and conflict-free.
7. **Parse-rescue pass.** Once the grid is full, scan the committed entries for
   parses that felt shaky during solving — anything where the solver's `notes`
   expressed doubt, or where some clue words went unexplained. For each,
   dispatch a fresh **Parser** subagent (giving it the prior parse as a
   starting hypothesis) and `xw.py parse <id> "<new parse>"` to swap in the
   cleaner mechanism. Then run the **Verifier** on the final parses. This step
   is where most ⚠ entries get upgraded to ✓, because a fresh Parser isn't
   defending the original interpretation.

Confidence bar suggestion: commit at ≥0.85 immediately; for 0.6–0.85 commit only
if at least one crossing letter already agrees; below 0.6 keep as a candidate
and wait for crossings to constrain the clue further.

**Sunk-cost watch.** If you (the orchestrator) find yourself writing parse
notes like "wordplay loose," "indicator stretched," or "extra clue word
unexplained," that's not a parse — it's an admission that this entry needs the
Parser to take a fresh look. Don't ship the shaky parse and move on; queue the
entry for the parse-rescue pass at step 7.
