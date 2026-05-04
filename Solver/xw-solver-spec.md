# AI Cryptic Crossword Solver: V2 Specification

## 1. System Architecture: The Client-Server Split
The most critical improvement over V1 is security and rate-limiting[cite: 1]. V1 exposed the LLM API key and hammered the API directly from the browser[cite: 1]. V2 requires a decoupled architecture[cite: 1].

### Frontend (React/Next.js)
- **Responsibility:** Grid rendering, user input, and state visualization[cite: 1].
- **State Management:** Uses a lightweight global store (like Zustand or Redux) to manage `GridState`, `ClueList`, and `WorkerStatuses`[cite: 1]. 
- **Communication:** Listens to Server-Sent Events (SSE) or WebSockets from the backend to watch the grid update in real-time as workers solve clues[cite: 1].

### Backend (Node.js/Python Serverless)
- **Responsibility:** Securely holding API keys, managing the job queue, calling the Dictionary/LLM, and enforcing rate limits[cite: 1].
- **Queue System:** Implements a strict task queue (e.g., BullMQ for Node, or Celery for Python)[cite: 1]. This replaces the dangerous `setInterval` loop from V1 and prevents HTTP 429 (Too Many Requests) errors[cite: 1].

## 2. The Heuristic Engine (Dictionary & Constraints)
V1 used the Datamuse API, which leans heavily American[cite: 1]. V2 must be localized for standard UK cryptic crosswords[cite: 1].

- **UK Lexicon:** Integrate a UK-specific dictionary database (like a downloaded UK Scrabble dictionary or a specialized crossword corpus) into the backend[cite: 1].
- **Constraint Scoring:** Before sending a clue to the LLM, the backend queries the lexicon with the current pattern (e.g., `?A?T?`)[cite: 1].
    - If 0 words fit: The grid is corrupted[cite: 1]. Trigger immediate arbitration on intersecting letters[cite: 1].
    - If 1 word fits: Force the LLM to verify *only* that specific word against the cryptic wordplay[cite: 1].
    - If >10 words fit: Pass the top 10 most common words to the LLM as hints[cite: 1].

## 3. The LLM Engine: Few-Shot Prompting with Strict Notation
Cryptic crosswords require highly lateral thinking, which LLMs struggle with natively[cite: 1]. V2 must use "Few-Shot" prompting and enforce a rigid, symbolic parsing notation to allow programmatic validation[cite: 1, 2]. 

A full parse will almost always have one of the following forms: `<...> X = Y` or `X = Y <...>`, depending on which end of the clue the definition is found[cite: 2].

### The Solver Prompt Template:
```json
{
  "system_instruction": "You are a master British Cryptic Crossword solver. You follow strict Ximenes rules. You must output your parse using strict Keynesian symbolic notation: <definition> ANSWER = WORDPLAY.",
  "few_shot_examples": [
    {
      "input": "Clue: 'Blackmail material to strike down MP with—corruption involving mother' (9). Pattern: K?M?R?M?T",
      "output": {
        "answer": "KOMPROMAT",
        "definition": "Blackmail material",
        "wordplay": "KO (strike down) + MP + ROT (corruption) outside MA (mother)",
        "parse": "<blackmail material> KOMPROMAT = KO MP + ROT outside MA",
        "confidence": "HIGH"
      }
    },
    {
      "input": "Clue: 'Awful man beginning to intimidate us in Paris' (7). Pattern: ?E?N?U?",
      "output": {
        "answer": "HEINOUS",
        "definition": "awful",
        "wordplay": "HE (man) + I (beginning to intimidate) + NOUS (us in Paris)",
        "parse": "<awful> HEINOUS = HE I_ NOUS",
        "confidence": "HIGH"
      }
    }
  ],
  "user_prompt": "Clue: {clue_text} ({length}). Pattern: {pattern}. Known candidates: {candidates}."
}
```

## 4. The Arbitration Loop (Conflict Resolution)
When Worker A's answer writes over Worker B's answer, V2 adds algorithmic logic *before* calling the expensive LLM Arbiter[cite: 1].

### The V2 Arbitration Algorithm:
1. **Mathematical Check:** Does removing Worker A's letter result in 0 dictionary matches for Worker A's clue?[cite: 1]. If yes, and Worker B still has options, Worker A wins automatically[cite: 1]. No LLM needed[cite: 1].
2. **Indicator Verification Check (Programmatic Scan):**
    - *Homophones:* If the parse claims a homophone (uses `"`), the backend scans the clue for valid audio, speech, setting, or interlocutor indicators (e.g., "heard", "in speech", "announced", "aloud", "listener")[cite: 4].
    - *Letter Selection:* If the parse claims initial/final letter selection, the backend scans for valid positional indicators categorised under First, Middle, Last, or Outside (e.g., "beginner", "front", "centre", "close", "ultimate", "empty")[cite: 3].
    - *Anagrams:* If the parse claims an anagram (uses `*`), the backend scans for anagram indicators (e.g., "bonkers", "somehow", "rambling")[cite: 2].
    - *Containment/Insertion:* If the parse claims containment (uses `inside/outside`), the backend scans for containment indicators[cite: 2].
    - *Reversals:* If the parse claims a reversal (uses `←...←`), the backend scans for reversal indicators (e.g., "upside-down")[cite: 2].
    - If required indicators are missing based on the parsed notation, downgrade that worker's confidence score automatically[cite: 1].
3. **Double-Definition (DD) Heuristic Check:** 
    - If Worker A's parse claims a double definition (e.g., `<def1> ANSWER <def2>`), the backend validates both `def1` and `def2` against a synonym API for the `ANSWER`[cite: 1, 2]. 
    - If both halves successfully map as synonyms, Worker A strongly wins the arbitration over a complex wordplay parse from Worker B that lacks proper indicators[cite: 1].
4. **Confidence Check:** Did Worker A return `HIGH` confidence and Worker B return `LOW` confidence?[cite: 1]. Worker A wins automatically[cite: 1].
5. **The LLM Judge:** If both are mathematically possible, both pass indicator checks, and both claim `HIGH` confidence, *then* summon the LLM Arbiter[cite: 1]. 
    - **Prompt Requirement:** Force the Arbiter to explicitly map the symbolic parse string back to the original clue words to prove the exact sequence works before outputting a final JSON decision[cite: 1].

## 5. The Execution Loop (The "Main" Function)
1. **Initialize:** Parse the raw text into the `GridState`[cite: 1].
2. **Prioritize:** Sort unsolved clues by Constraint Level (Clues with the most known letters go first[cite: 1]. Clues with 0 known letters go last)[cite: 1].
3. **Dispatch:** Send the top N clues to the Backend Queue (where N is your API rate limit)[cite: 1].
4. **Process:** Backend workers fetch dictionary candidates -> Prompt LLM -> Return JSON to the main thread[cite: 1].
5. **Commit or Arbitrate:** 
    - If the answer fits the grid perfectly, commit it and update `GridState`[cite: 1].
    - If it clashes, freeze those two clues and run the Arbitration Algorithm[cite: 1].
6. **Repeat:** Re-sort the remaining clues based on the newly updated `GridState` and dispatch the next batch[cite: 1]. Stop when the grid is full or all remaining clues fail 3 consecutive attempts[cite: 1].