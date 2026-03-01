import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Check, Brain, X, Play, Pause, BookOpen, AlertCircle, RefreshCw, Search, Activity, Scale, Zap } from 'lucide-react';

// --- CONFIGURATION ---
const apiKey = "AIzaSyCgrU5U-kbjx5VN-HjN2Zoh8www6hnKXes";
const MODEL_NAME = 'gemini-3.1-pro-preview';
const STAGNATION_TIMEOUT = 5000;  // 5 seconds before adding a helper
const MAX_SCALABLE_WORKERS = 250;  // Increased cap
const MIN_WORKERS = 100;            // Start with and maintain at least 4 workers

// --- API CLIENT ---

async function fetchGemini(prompt, schema = null, signal = null) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL_NAME}:generateContent?key=${apiKey}`;
  
  const body = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: schema ? { 
      responseMimeType: "application/json", 
      responseSchema: schema 
    } : {}
  };

  let attempt = 0;
  const maxRetries = 3;

  while (attempt < maxRetries) {
    try {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      if (!apiKey) throw new Error("API Key is missing (not injected).");

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: signal
      });

      if (!response.ok) {
        const status = response.status;
        const errorText = await response.text();
        
        if (status === 400) throw new Error(`Bad Request (400): ${errorText}`);
        if (status === 401) throw new Error(`Unauthorized (401): Invalid API Key.`);
        if (status === 403) throw new Error(`Forbidden (403): Access denied.`);
        if (status === 429 || status >= 500) throw new Error(`Transient Error (${status}). Retrying...`);
        
        throw new Error(`API Error ${status}: ${errorText}`);
      }

      const data = await response.json();
      const candidate = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (!candidate) throw new Error("Empty response from model.");

      const cleanJson = candidate.replace(/```json|```/g, '').trim();
      return schema ? JSON.parse(cleanJson) : cleanJson;

    } catch (err) {
      if (err.name === 'AbortError') throw err;
      if (err.message.includes("Unauthorized") || err.message.includes("Forbidden") || err.message.includes("Bad Request")) {
        throw err;
      }
      attempt++;
      if (attempt >= maxRetries) throw err;
      await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, attempt)));
    }
  }
}

async function fetchDatamuse(pattern, signal) {
  if (!pattern.includes('?') && !pattern.includes(' ')) return [];
  try {
    const q = encodeURIComponent(pattern.replace(/-/g, ' '));
    // CHANGED: Max 10. We only need to know if it's "unique" (1) or "loose" (>2).
    const res = await fetch(`https://api.datamuse.com/words?sp=${q}&max=10`, { signal }); 
    if (!res.ok) return [];
    const data = await res.json();
    return data.map(i => i.word.toUpperCase());
  } catch (e) {
    return []; 
  }
}

// --- SCHEMAS & CONSTANTS ---

const SOLVER_SCHEMA = {
  type: "OBJECT",
  properties: {
    answer: { type: "STRING" },
    parse: { type: "STRING" },
    explanation: { type: "STRING" },
    confidence: { type: "STRING", enum: ["HIGH", "MEDIUM", "LOW"] }
  },
  required: ["answer", "parse", "explanation", "confidence"]
};

const ARBITER_SCHEMA = {
  type: "OBJECT",
  properties: {
    winner: { type: "STRING", enum: ["A", "B"] },
    reason: { type: "STRING" }
  },
  required: ["winner", "reason"]
};

const SCORE_MAP = { "HIGH": 3, "MEDIUM": 2, "LOW": 1 };

// --- GRID UTILITIES ---

const GridEngine = {
  parseInput: (text) => {
    const lines = text.trim().split('\n').map(l => l.trim());
    const grid = [];
    const clues = { across: [], down: [] };
    let section = '';

    lines.forEach(line => {
      if (!line) return;

      const isGridRow = /^[A-Z\?\.\#\s]+$/i.test(line) && 
                        (line.includes('?') || line.includes('.') || line.includes('#')) &&
                        !/^(Across|Down)$/i.test(line);

      if (isGridRow) {
        const cleanLine = line.replace(/\s+/g, '');
        grid.push(cleanLine.toUpperCase().split('').map(c => ({
          type: (c === '.' || c === '#') ? 'black' : 'white',
          val: /[A-Z]/.test(c) ? c : '',
          num: null
        })));
      } 
      else if (/^Across/i.test(line)) section = 'across';
      else if (/^Down/i.test(line)) section = 'down';
      else if (section) {
        const m = line.match(/^(\d+)\.?\s*(.+?)\s*[(\[]([\d,-]+)[)\]]$/);
        if (m) {
          clues[section].push({
            num: parseInt(m[1]),
            text: m[2],
            lenStr: m[3],
            len: m[3].split(/[,-]/).reduce((a, b) => a + parseInt(b), 0),
            dir: section,
            id: `${m[1]}-${section}`
          });
        }
      }
    });

    let n = 1;
    if (grid.length > 0) {
      for (let r = 0; r < grid.length; r++) {
        for (let c = 0; c < grid[0].length; c++) {
          if (grid[r][c].type === 'black') continue;
          const isAcross = (c === 0 || grid[r][c-1].type === 'black') && (c + 1 < grid[0].length && grid[r][c+1].type !== 'black');
          const isDown = (r === 0 || grid[r-1][c].type === 'black') && (r + 1 < grid.length && grid[r+1][c].type !== 'black');
          if (isAcross || isDown) grid[r][c].num = n++;
        }
      }
    }
    return { grid, clues };
  },

  getCells: (grid, num, dir) => {
    for (let r = 0; r < grid.length; r++) {
      for (let c = 0; c < grid[0].length; c++) {
        if (grid[r][c].num === num) {
          const cells = [];
          if (dir === 'across') {
            let i = c;
            while (i < grid[0].length && grid[r][i].type !== 'black') cells.push({r, c: i++});
          } else {
            let i = r;
            while (i < grid.length && grid[i][c].type !== 'black') cells.push({r: i++, c});
          }
          return cells;
        }
      }
    }
    return [];
  },

  getCrossingClueId: (grid, r, c, currentDir, allClues) => {
    const oppositeDir = currentDir === 'across' ? 'down' : 'across';
    for (const clue of allClues[oppositeDir]) {
      const cells = GridEngine.getCells(grid, clue.num, oppositeDir);
      if (cells.some(cell => cell.r === r && cell.c === c)) {
        return clue.id;
      }
    }
    return null;
  },

  getPattern: (grid, clue) => {
    const cells = GridEngine.getCells(grid, clue.num, clue.dir);
    if (cells.length === 0) return "?".repeat(clue.len);
    
    let pattern = "";
    let cellIdx = 0;
    const parts = clue.lenStr.split(/[,-]/).map(Number);
    
    parts.forEach((len, idx) => {
      for (let k = 0; k < len; k++) {
        if (cellIdx < cells.length) {
          pattern += grid[cells[cellIdx].r][cells[cellIdx].c].val || "?";
          cellIdx++;
        }
      }
      if (idx < parts.length - 1) pattern += (clue.lenStr.includes(',') ? " " : "-");
    });
    return pattern;
  },

  getPatternMasked: (grid, clue, maskR, maskC) => {
    const cells = GridEngine.getCells(grid, clue.num, clue.dir);
    if (cells.length === 0) return "?".repeat(clue.len);
    
    let pattern = "";
    let cellIdx = 0;
    const parts = clue.lenStr.split(/[,-]/).map(Number);
    
    parts.forEach((len, idx) => {
      for (let k = 0; k < len; k++) {
        if (cellIdx < cells.length) {
          const cell = cells[cellIdx];
          if (cell.r === maskR && cell.c === maskC) {
              pattern += "?"; 
          } else {
              pattern += grid[cell.r][cell.c].val || "?";
          }
          cellIdx++;
        }
      }
      if (idx < parts.length - 1) pattern += (clue.lenStr.includes(',') ? " " : "-");
    });
    return pattern;
  },

  updateGrid: (grid, clue, answer) => {
    const newGrid = grid.map(row => row.map(cell => ({ ...cell })));
    const cells = GridEngine.getCells(newGrid, clue.num, clue.dir);
    const cleanAns = answer.replace(/[^A-Z]/g, '');
    
    cells.forEach((pos, i) => {
      if (i < cleanAns.length) {
        newGrid[pos.r][pos.c].val = cleanAns[i];
      }
    });
    return newGrid;
  }
};

// --- MAIN APP ---

const App = () => {
  const [mode, setMode] = useState('input'); 
  const [inputText, setInputText] = useState('');
  const [grid, setGrid] = useState([]);
  const [clues, setClues] = useState({ across: [], down: [] });
  const [solutions, setSolutions] = useState({}); 
  const [failedClues, setFailedClues] = useState(new Map()); 
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('idle');
  const [parseError, setParseError] = useState(null);
  const [activeOps, setActiveOps] = useState({}); 
  const [workingCount, setWorkingCount] = useState(0);
  const [concurrencyLimit, setConcurrencyLimit] = useState(MIN_WORKERS); 

  // Refs
  // AUTHORITATIVE STATE: These refs hold the absolute latest state, updated synchronously.
  // Workers and queue processors read these to avoid React render lag.
  const latestGridRef = useRef([]);
  const latestSolutionsRef = useRef({});
  const failedCluesRef = useRef(new Map());
  
  // Queue Management
  const solutionQueueRef = useRef([]);
  const isProcessingQueueRef = useRef(false);
  
  const activeContextRef = useRef(new Map());
  const workerCounter = useRef(0);
  const logCounter = useRef(0);
  const lastActionTimeRef = useRef(Date.now()); 
  const lastDecrementTimeRef = useRef(0);

  // Note: We still use effects to keep refs in sync if manual setGrid is used,
  // but logic should primarily write to Ref then State.
  useEffect(() => { failedCluesRef.current = failedClues; }, [failedClues]);
  
  const log = useCallback((msg, type = 'info') => {
    setLogs(prev => {
        logCounter.current += 1;
        return [{ id: logCounter.current, msg, type, time: new Date().toLocaleTimeString() }, ...prev];
    });
  }, []);

  const activeCells = useMemo(() => {
    if (grid.length === 0) return new Set();
    const cells = new Set();
    Object.values(activeOps).forEach(op => {
        const cList = GridEngine.getCells(grid, op.clue.num, op.clue.dir);
        cList.forEach(c => cells.add(`${c.r},${c.c}`));
    });
    return cells;
  }, [activeOps, grid]);

  const handleLoad = () => {
    setParseError(null);
    try {
      const { grid: newGrid, clues: newClues } = GridEngine.parseInput(inputText);
      if (newGrid.length === 0) throw new Error("No valid grid detected.");
      if (newClues.across.length === 0 && newClues.down.length === 0) throw new Error("No clues detected.");
      
      // Initialize authoritative state
      latestGridRef.current = newGrid;
      latestSolutionsRef.current = {};
      
      setGrid(newGrid);
      setClues(newClues);
      setSolutions({});
      setFailedClues(new Map());
      setMode('solver');
      log("Crossword loaded successfully.", "success");
    } catch (e) {
      setParseError(e.message);
    }
  };

  const updateOp = (workerId, data) => {
      setActiveOps(prev => {
          if (!data) {
              const next = { ...prev };
              delete next[workerId];
              return next;
          }
          return { ...prev, [workerId]: { ...(prev[workerId] || {}), ...data } };
      });
  };

  const solveClue = async (clue, signal, workerId) => {
    // ALWAYS read from latestGridRef to ensure we aren't using stale state
    const pattern = GridEngine.getPattern(latestGridRef.current, clue);
    updateOp(workerId, { type: 'solving', clue, pattern });

    let candidates = [];
    try { candidates = await fetchDatamuse(pattern, signal); } catch (e) {}

    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');

    updateOp(workerId, { candidates });

    const makePrompt = (pat, cands, isBlind) => `
      You are a champion British Cryptic Crossword Solver. Accuracy is paramount.
      
      CLUE: ${clue.num} ${clue.dir}: "${clue.text}"
      LENGTH: ${clue.lenStr}
      CURRENT PATTERN: ${pat} ${isBlind ? "(Ignore letters, previous guess likely wrong)" : ""}
      KNOWN LETTERS: ${pat.replace(/[^A-Z]/g, '').length}
      DICTIONARY MATCHES: ${cands.length > 0 ? cands.join(', ') : "None found"}

      STRICT PROTOCOL:
      1. DEFINITION: Locate the definition (usually start or end). It must be a precise synonym for the answer.
      2. WORDPLAY: Analyze the remainder. Look for:
         - Anagrams (indicators: broken, wildly, off, fresh...)
         - Hidden words (indicators: in, some, part of...)
         - Containers (indicators: outside, within, around...)
         - Charades (parts added together)
         - Homophones (indicators: heard, reportedly...)
         - Double Definitions
      3. VERIFICATION: Construct the answer letter-by-letter from the wordplay. Does it match the definition?
      4. PATTERN CHECK: The answer MUST fit the pattern "${pat}" exactly (unless Blind Mode).

      CRITICAL RULES:
      - If the definition is weak or the wordplay is loose, DO NOT GUESS.
      - If a candidate from the dictionary fits the definition BUT NOT the wordplay, reject it.
      - PREFER WORDPLAY over simple synonyms.
      - Use UK spelling.

      Task: Return the single best answer and its precise parse.
      Return standard JSON.
    `;

    const result1 = await fetchGemini(makePrompt(pattern, candidates, false), SOLVER_SCHEMA, signal);
    
    const knownLetters = pattern.replace(/[^A-Z]/g, '').length;
    if (result1.confidence !== 'HIGH' && knownLetters > 0) {
        if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
        updateOp(workerId, { retro: true }); 
        
        const blindPattern = pattern.replace(/[A-Z]/g, '?'); 
        const result2 = await fetchGemini(makePrompt(blindPattern, [], true), SOLVER_SCHEMA, signal);

        if (result2.confidence === 'HIGH') {
             const score1 = SCORE_MAP[result1.confidence] || 0;
             const score2 = SCORE_MAP[result2.confidence] || 0;
             if (score2 > score1) {
                 const cleanAns2 = result2.answer.toUpperCase().replace(/[^A-Z]/g, '');
                 if (cleanAns2.length === clue.len) return { ...result2, answer: cleanAns2 };
             }
        }
    }

    const cleanAns = result1.answer.toUpperCase().replace(/[^A-Z]/g, '');
    if (cleanAns.length !== clue.len) throw new Error(`Length mismatch`);
    return { ...result1, answer: cleanAns };
  };

  const arbitrateClash = async (challenger, incumbent, signal, conflictR, conflictC, workerId) => {
    updateOp(workerId, { arbitration: true });
    
    // Constraint Check: How many words fit the *other* crossers for these slots?
    // Use authoritative grid
    const patternA = GridEngine.getPatternMasked(latestGridRef.current, challenger.clue, conflictR, conflictC);
    const patternB = GridEngine.getPatternMasked(latestGridRef.current, incumbent.clue, conflictR, conflictC);
    
    let countA = "Unknown";
    let countB = "Unknown";

    try {
        const [resA, resB] = await Promise.all([
            fetchDatamuse(patternA, signal),
            fetchDatamuse(patternB, signal)
        ]);
        countA = resA.length >= 10 ? "10+" : resA.length;
        countB = resB.length >= 10 ? "10+" : resB.length;
    } catch (e) {}

    const prompt = `
      You are the Chief Crossword Editor. There is a collision in the grid.
      You must choose which answer is correct and which is an impostor.

      COLLISION AT: Row ${conflictR + 1}, Col ${conflictC + 1}

      CANDIDATE A (Challenger):
      Clue: "${challenger.clue.text}" (${challenger.clue.lenStr})
      Proposed Answer: ${challenger.answer}
      Context: Pattern "${patternA}" allows ${countA} dictionary words.

      CANDIDATE B (Incumbent):
      Clue: "${incumbent.clue.text}" (${incumbent.clue.lenStr})
      Existing Answer: ${incumbent.answer}
      Context: Pattern "${patternB}" allows ${countB} dictionary words.

      EVALUATION LOGIC:
      1. PARSE STRENGTH: Which answer has a watertight cryptic derivation? A precise anagram or hidden word is better than a vague double definition.
      2. DEFINITION ACCURACY: Which answer is a better synonym for its definition indicator?
      3. CONSTRAINT THEORY: If Candidate A fits a pattern that allows ONLY 1 word, while Candidate B fits a pattern allowing 50 words, A is statistically more likely to be the "anchor" answer, assuming its parse holds up.
      4. OSCAM'S RAZOR: Which answer is a more common/reasonable word?

      DECISION:
      - If one is definitely right and the other definitely wrong, pick the winner.
      - If both seem plausible, pick the one with the TIGHTER constraints (fewer possible matches).
      - If Candidate A is weak/dubious, stick with B (Incumbent).

      Return JSON: { "winner": "A" | "B", "reason": "Detailed critique of why one failed." }
    `;

    try {
        return await fetchGemini(prompt, ARBITER_SCHEMA, signal);
    } catch (e) {
        return { winner: "B", reason: "Arbitration failed." }; 
    }
  };

  // --- SERIALIZED QUEUE PROCESSOR ---
  const processSolutionQueue = async () => {
    if (isProcessingQueueRef.current) return;
    isProcessingQueueRef.current = true;

    try {
      while (solutionQueueRef.current.length > 0) {
        const item = solutionQueueRef.current.shift(); // FIFO
        const { clue, solution, workerId } = item;
        
        // --- LOGIC START ---
        const currentGrid = latestGridRef.current;
        const currentSolutions = latestSolutionsRef.current;

        const cells = GridEngine.getCells(currentGrid, clue.num, clue.dir);
        const cleanAns = solution.answer;
        
        let defeatedClueIds = new Set();
        let incumbents = new Map(); 
        let isValid = true;

        // Check conflicts against AUTHORITATIVE grid
        for (let i = 0; i < cells.length; i++) {
          const curr = currentGrid[cells[i].r][cells[i].c].val;
          if (curr && curr !== cleanAns[i]) {
            const incumbentId = GridEngine.getCrossingClueId(currentGrid, cells[i].r, cells[i].c, clue.dir, clues);
            if (incumbentId && currentSolutions[incumbentId]) {
              const dir = incumbentId.includes('across') ? 'across' : 'down';
              const incumbentClue = clues[dir].find(c => c.id === incumbentId);
              if (incumbentClue) {
                 incumbents.set(incumbentId, { 
                     clue: incumbentClue, 
                     answer: currentSolutions[incumbentId].answer,
                     r: cells[i].r,
                     c: cells[i].c
                 });
              }
            } else {
               // Conflict with a fixed letter (or orphan letter), not a solution we track?
               // Usually implies a manual entry or previous deletion.
               // We will treat orphan letters as hard constraints for now.
            }
          }
        }

        // Arbitrate
        for (const [incumbentId, incData] of incumbents) {
            const adjudication = await arbitrateClash(
                { clue: clue, answer: cleanAns },
                { clue: incData.clue, answer: incData.answer },
                null,
                incData.r,
                incData.c,
                workerId
            );

            if (adjudication.winner === 'A') {
                defeatedClueIds.add(incumbentId);
                log(`Arbitration: '${cleanAns}' > '${incData.answer}'`, "success");
            } else {
                log(`Arbitration: '${cleanAns}' rejected`, "error");
                isValid = false;
                break; 
            }
        }

        if (isValid) {
            let nextGrid = currentGrid.map(row => row.map(cell => ({ ...cell })));
            
            defeatedClueIds.forEach(defeatedId => {
                const dir = defeatedId.includes('across') ? 'across' : 'down';
                const defeatedClue = clues[dir].find(c => c.id === defeatedId);
                if (defeatedClue) {
                    const dCells = GridEngine.getCells(nextGrid, defeatedClue.num, defeatedClue.dir);
                    dCells.forEach(({r, c}) => {
                        const crossingId = GridEngine.getCrossingClueId(nextGrid, r, c, defeatedClue.dir, clues);
                        const isProtected = crossingId && currentSolutions[crossingId] && !defeatedClueIds.has(crossingId);
                        if (!isProtected) nextGrid[r][c].val = ''; 
                    });
                }
            });

            nextGrid = GridEngine.updateGrid(nextGrid, clue, cleanAns);
            
            // ATOMIC UPDATE OF AUTHORITATIVE STATE
            latestGridRef.current = nextGrid;
            const nextSolutions = { ...currentSolutions, [clue.id]: solution };
            defeatedClueIds.forEach(id => delete nextSolutions[id]);
            latestSolutionsRef.current = nextSolutions;

            // SYNC UI
            setGrid(nextGrid);
            setSolutions(nextSolutions);

            // Success side effects
            setFailedClues(prev => {
                const next = new Map(prev);
                next.delete(clue.id);
                if (defeatedClueIds.size > 0) {
                    defeatedClueIds.forEach(id => next.delete(id));
                }
                return next;
            });

            activeContextRef.current.forEach((ctx, wId) => {
                if (ctx.clueId === clue.id) {
                    ctx.controller.abort();
                }
            });

            lastActionTimeRef.current = Date.now();
            if (Date.now() - lastDecrementTimeRef.current > 10000) { 
                 setConcurrencyLimit(prev => Math.max(MIN_WORKERS, prev - 1));
                 lastDecrementTimeRef.current = Date.now();
            }

            if (defeatedClueIds.size === 0) {
                 log(`Solved ${clue.num}${clue.dir[0]}: ${cleanAns}`, "success");
            }
        } else {
            // Failed arbitration or valid check
             setFailedClues(prev => {
                 const next = new Map(prev);
                 const ex = next.get(clue.id) || { attempts: 0 };
                 // Just increment attempts, don't change crossers count blindly
                 next.set(clue.id, { crossers: -1, attempts: ex.attempts + 1 });
                 return next;
             });
        }
        // --- LOGIC END ---
      }
    } finally {
      isProcessingQueueRef.current = false;
    }
  };

  const queueSolution = (clue, solution, workerId) => {
      solutionQueueRef.current.push({ clue, solution, workerId });
      processSolutionQueue();
  };

  // --- DYNAMIC SCALING LOOP ---
  useEffect(() => {
    if (status !== 'working') return;
    
    lastActionTimeRef.current = Date.now();

    const scaler = setInterval(() => {
       const elapsed = Date.now() - lastActionTimeRef.current;
       
       if (elapsed > STAGNATION_TIMEOUT) {
           setConcurrencyLimit(prev => {
               if (prev < MAX_SCALABLE_WORKERS) {
                   lastActionTimeRef.current = Date.now(); // Reset timer for NEXT increase
                   return prev + 1;
               }
               return prev;
           });
       }
    }, 1000);

    return () => clearInterval(scaler);
  }, [status]);

  // --- MAIN WORKER LOOP ---
  useEffect(() => {
      if (status !== 'working') return;

      const spawnWorker = () => {
          // Cap removed so we never block new work, even if old workers are still finishing
          // if (workingCount >= concurrencyLimit) return;

          const activeOpsList = Object.values(activeOps);
          const allClues = [...clues.across, ...clues.down];
          
          let candidates = allClues.filter(c => {
             // 1. Must not be solved (check authoritative)
             if (latestSolutionsRef.current[c.id]) return false;

             // 2. Must not be ALREADY worked on with the CURRENT pattern
             const currentPattern = GridEngine.getPattern(latestGridRef.current, c);
             const alreadyWorkingOnPattern = activeOpsList.some(op => 
                 op.clue.id === c.id && op.pattern === currentPattern
             );
             return !alreadyWorkingOnPattern;
          });
          
          let fresh = [];
          let retriable = [];

          candidates.forEach(c => {
              const currentPattern = GridEngine.getPattern(latestGridRef.current, c);
              const currentCrossers = currentPattern.replace(/[^A-Z]/g, '').length;
              const failInfo = failedCluesRef.current.get(c.id);

              if (!failInfo) fresh.push(c);
              else if (currentCrossers > failInfo.crossers) fresh.push(c);
              else if (failInfo.attempts < 3) retriable.push(c);
          });

          let pool = fresh.length > 0 ? fresh : retriable;
          if (pool.length === 0) {
              if (workingCount === 0) {
                 if (Object.keys(latestSolutionsRef.current).length < allClues.length) {
                    log("Stopped: All remaining clues failed max retries.", "warning");
                 } else {
                    log("Puzzle Complete!", "success");
                 }
                 setStatus('idle');
              }
              return;
          }

          pool.sort((a, b) => {
             const patA = GridEngine.getPattern(latestGridRef.current, a).replace(/[^A-Z]/g, '').length;
             const patB = GridEngine.getPattern(latestGridRef.current, b).replace(/[^A-Z]/g, '').length;
             if (patA !== patB) return patB - patA;
             return a.len - b.len; 
          });

          const target = pool[0];
          
          setWorkingCount(prev => prev + 1);
          
          (async () => {
             const controller = new AbortController();
             const pat = GridEngine.getPattern(latestGridRef.current, target);
             const crossers = pat.replace(/[^A-Z]/g, '').length;
             const workerId = `w-${++workerCounter.current}`;
             
             activeContextRef.current.set(workerId, { controller, clueId: target.id });

             try {
                 const sol = await solveClue(target, controller.signal, workerId);
                 
                 // --- SMART STALE CHECK (against Authoritative Grid) ---
                 const currentPat = GridEngine.getPattern(latestGridRef.current, target);
                 if (currentPat !== pat) {
                     const cells = GridEngine.getCells(latestGridRef.current, target.num, target.dir);
                     const hasConflict = cells.some((c, i) => {
                         const val = latestGridRef.current[c.r][c.c].val;
                         return val && val !== sol.answer[i];
                     });

                     if (hasConflict) {
                         log(`Discarding '${sol.answer}' (conflicts with new crossers).`, "warning");
                         return; 
                     }
                     log(`Keeping '${sol.answer}' (fits new crossers).`, "success");
                 }
                 // -------------------------

                 // Enqueue instead of applying directly
                 queueSolution(target, sol, workerId);

             } catch (e) {
                 if (e.name === 'AbortError') {
                     // Interrupted
                 } else if (e.message.includes("Unauthorized")) {
                     setStatus('error');
                 } else {
                     setFailedClues(prev => {
                         const next = new Map(prev);
                         const ex = next.get(target.id) || { attempts: 0 };
                         next.set(target.id, { crossers, attempts: ex.attempts + 1 });
                         return next;
                     });
                 }
             } finally {
                 // Clean up this specific worker
                 activeContextRef.current.delete(workerId);
                 updateOp(workerId, null);
                 setWorkingCount(prev => prev - 1);
             }
          })();
      };

      const interval = setInterval(spawnWorker, 500);
      return () => clearInterval(interval);

  }, [status, workingCount, concurrencyLimit, activeOps, clues, grid]);

  const rows = grid.length;
  const cols = grid[0]?.length || 0;
  const isJumbo = rows > 15 || cols > 15;
  
  const cellSize = isJumbo ? "w-5 h-5 text-xs" : "w-8 h-8 text-lg";
  const numSize = isJumbo ? "text-[6px] top-0 left-0.5" : "text-[9px] top-0.5 left-0.5";

  if (mode === 'input') {
    return (
      <div className="min-h-screen bg-neutral-900 text-white p-4 flex items-center justify-center font-sans">
        <div className="w-full max-w-2xl bg-neutral-800 p-6 rounded-lg shadow-xl border border-neutral-700">
          <h1 className="text-2xl font-bold mb-4 text-emerald-400 flex items-center gap-3">
            <Brain className="w-8 h-8" /> Cryptic Solver Pro
          </h1>
          <div className="bg-neutral-900/50 p-4 rounded-lg mb-4 text-sm text-neutral-300 border border-neutral-800">
             <p className="font-bold mb-2 text-emerald-500">Format Instructions:</p>
             <ul className="list-disc list-inside space-y-1">
               <li>Use <code>?</code> for empty cells and <code>.</code> for black blocks.</li>
               <li>Include headers <code>Across</code> and <code>Down</code>.</li>
               <li>Clues must end with length in parentheses, e.g., <code>(5)</code>.</li>
             </ul>
          </div>
          <textarea
            className="w-full h-64 bg-neutral-950 border border-neutral-700 rounded-lg p-4 font-mono text-sm text-neutral-200 mb-4 focus:ring-2 focus:ring-emerald-500 outline-none"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            placeholder={`?????.???\n?.?.?.?.?\nAcross\n1 Example Clue (5)\nDown\n2 Another One (3)`}
          />
          {parseError && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-500/50 rounded text-red-200 text-sm flex items-center gap-2">
              <AlertCircle size={16} />{parseError}
            </div>
          )}
          <button onClick={handleLoad} className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-bold text-lg transition-colors flex items-center justify-center gap-2">
            <Play className="w-5 h-5" /> Start Solving
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-neutral-900 text-white p-2 font-sans flex flex-col md:flex-row gap-2 overflow-hidden">
      
      {/* LEFT: Grid & Controls */}
      <div className="w-full md:w-1/3 flex flex-col gap-2 h-1/2 md:h-full">
        <div className="bg-neutral-800 p-2 rounded-lg border border-neutral-700 shadow-lg flex-1 overflow-auto flex">
            <div className="inline-block m-auto p-2">
                {grid.map((row, r) => (
                  <div key={r} className="flex">
                    {row.map((cell, c) => {
                      const isActive = activeCells.has(`${r},${c}`);
                      const cellColor = cell.type === 'black' ? 'bg-black' : isActive ? 'bg-emerald-200 text-black' : 'bg-white text-black';
                      return (
                        <div key={c} className={`${cellSize} border border-neutral-600 flex items-center justify-center relative ${cellColor} font-bold`}>
                          {cell.num && <span className={`absolute ${numSize} text-neutral-500 leading-none font-normal`}>{cell.num}</span>}
                          {cell.val}
                        </div>
                      );
                    })}
                  </div>
                ))}
            </div>
        </div>

        <div className="bg-neutral-800 p-2 rounded-lg border border-neutral-700 shadow-lg flex-shrink-0">
          <div className="flex gap-2 items-center">
            {status === 'working' ? (
              <button onClick={() => setStatus('paused')} className="flex-1 bg-amber-600 hover:bg-amber-500 py-2 rounded-md font-semibold flex items-center justify-center gap-2 text-xs">
                <Pause className="w-3 h-3"/> Pause
              </button>
            ) : (
              <button onClick={() => { setFailedClues(new Map()); setStatus('working'); }} className="flex-1 bg-emerald-600 hover:bg-emerald-500 py-2 rounded-md font-semibold flex items-center justify-center gap-2 text-xs">
                <Play className="w-3 h-3"/> Auto Solve
              </button>
            )}
            <button onClick={() => {setMode('input'); setInputText(''); setStatus('idle');}} className="px-3 py-2 bg-neutral-700 hover:bg-neutral-600 rounded-md text-xs">New</button>
            <div className={`flex-1 px-2 text-[10px] font-mono text-center py-2 rounded-md ${status === 'error' ? 'bg-red-900/50 text-red-200' : 'bg-neutral-950 text-neutral-400'}`}>
              {status.toUpperCase()} ({workingCount} working)
            </div>
          </div>
        </div>
      </div>

      {/* MIDDLE: Clues */}
      <div className="w-full md:w-1/3 flex flex-col gap-2 h-1/2 md:h-full min-h-0">
        {['across', 'down'].map(dir => (
          <div key={dir} className="flex-1 bg-neutral-800 rounded-lg border border-neutral-700 flex flex-col overflow-hidden">
            <div className="p-2 bg-neutral-750 border-b border-neutral-700 font-bold text-emerald-400 uppercase text-xs tracking-wider">{dir}</div>
            <div className="flex-1 overflow-y-auto p-1 space-y-1">
              {clues[dir].map(clue => {
                const sol = solutions[clue.id];
                return (
                  <div 
                    key={clue.id}
                    className={`p-2 rounded-md text-xs transition-colors border ${sol ? 'border-emerald-800 bg-emerald-900/10' : 'border-transparent'} ${failedClues.has(clue.id) && !sol ? 'opacity-50' : ''}`}
                  >
                    <div className="flex justify-between items-start">
                      <span className="font-bold text-neutral-300 mr-1.5">{clue.num}.</span>
                      <span className="text-neutral-200 flex-1 leading-tight text-sm">{clue.text}</span>
                      <span className="text-neutral-500 text-[10px] ml-1 whitespace-nowrap">({clue.lenStr})</span>
                    </div>
                    {sol && (
                      <div className="mt-1.5 pl-2 border-l-2 border-emerald-600">
                        <div className="font-mono font-bold text-emerald-400 text-sm">{sol.answer}</div>
                        <div className="text-xs text-neutral-300 mt-0.5 leading-snug">{sol.explanation}</div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* RIGHT: Active Clue + Logs */}
      <div className="w-full md:w-1/3 flex flex-col gap-2 h-full overflow-hidden">
        
        {/* Active Operations Panel */}
        <div className="h-64 flex-shrink-0 bg-neutral-800 rounded-lg border border-neutral-700 flex flex-col overflow-hidden">
           <div className="p-2 bg-emerald-900/30 border-b border-emerald-800/50 font-bold text-emerald-400 text-xs flex items-center gap-2">
             <Activity className="w-3 h-3"/> Active Operations
           </div>
           <div className="p-2 overflow-y-auto flex-1 space-y-2">
             {Object.keys(activeOps).length > 0 ? Object.values(activeOps).map(op => (
                <div key={op.clue.id + op.pattern} className="bg-neutral-900/50 p-2 rounded border border-neutral-700">
                  <div className="flex justify-between items-start mb-1">
                    <div className="text-xs text-white font-bold">
                      <span className="text-emerald-400 mr-1">{op.clue.num}{op.clue.dir[0]}.</span> 
                      {op.clue.lenStr}
                    </div>
                    {op.arbitration && <span className="text-[9px] bg-purple-900 text-purple-200 px-1 rounded font-bold">ARBITRATING</span>}
                    {op.retro && <span className="text-[9px] bg-amber-900 text-amber-200 px-1 rounded font-bold">RETRO</span>}
                  </div>
                  <div className="text-[10px] text-neutral-400 truncate mb-1">{op.clue.text}</div>
                  <div className="flex flex-col gap-1 mt-1.5">
                     <div className="font-mono text-emerald-300 text-[10px] tracking-widest bg-black/20 p-1 rounded border border-emerald-900/30 text-center">{op.pattern}</div>
                     <div className="text-[10px] min-h-[1.2em] flex items-center">
                       {op.candidates === undefined ? (
                          <span className="text-neutral-600 animate-pulse flex items-center gap-1">
                            <Search className="w-2.5 h-2.5" /> Searching dict...
                          </span>
                       ) : op.candidates.length > 0 ? (
                          <span className="text-amber-200/80 truncate">
                            <span className="text-neutral-500 mr-1">Matches:</span>
                            {op.candidates.slice(0, 4).join(', ')}
                            {op.candidates.length > 4 && <span className="opacity-50"> +{op.candidates.length - 4}</span>}
                          </span>
                       ) : (
                          <span className="text-neutral-600 italic">No dictionary matches</span>
                       )}
                     </div>
                  </div>
                </div>
             )) : (
               <div className="h-full flex items-center justify-center text-neutral-600 text-xs">
                 Waiting for task...
               </div>
             )}
           </div>
        </div>

        <div className="flex-1 bg-neutral-800 rounded-lg border border-neutral-700 flex flex-col overflow-hidden">
          <div className="p-2 bg-neutral-750 border-b border-neutral-700 font-bold text-neutral-400 text-xs flex items-center gap-2">
            <BookOpen className="w-3 h-3"/> Activity Log
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2 font-mono text-xs">
            {logs.map(log => (
              <div key={log.id} className={`p-1.5 rounded border-l-2 ${log.type === 'error' ? 'border-red-500 bg-red-900/10 text-red-200' : log.type === 'success' ? 'border-emerald-500 bg-emerald-900/10 text-emerald-200' : log.type === 'warning' ? 'border-amber-500 bg-amber-900/10 text-amber-200' : 'border-neutral-500 bg-neutral-900 text-neutral-400'}`}>
                <span className="opacity-50 block mb-0.5 text-[10px]">{log.time}</span>
                {log.msg}
              </div>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
};

export default App;