@echo off
REM ============================================================
REM  Crossword solver - dashboard launcher
REM
REM  Usage (run from anywhere; it cd's to its own folder):
REM    dashboard.bat                 just open the live dashboard
REM    dashboard.bat puzzle.txt      load an ASCII-grid + clue-list file, then open
REM    dashboard.bat puzzle.json     load a puzzle JSON, then open
REM
REM  Leave this window open during the solve (Ctrl-C stops the dashboard),
REM  then tell Claude Code: "solve the puzzle in state.json".
REM ============================================================
setlocal
cd /d "%~dp0"

if not "%~1"=="" (
  if /I "%~x1"==".json" (
    echo Loading puzzle JSON: %~1
    python xw.py init "%~1"
  ) else (
    echo Loading puzzle text: %~1
    python xw.py from-text "%~1" --init
  )
  if errorlevel 1 (
    echo.
    echo Puzzle failed to load ^(see error above^); dashboard not started.
    pause
    exit /b 1
  )
)

REM Warm the wordlist cache so the first candidate query is instant (no-op if fresh).
python wordlist.py info >nul 2>&1

echo.
echo Dashboard at http://127.0.0.1:8000   ^(Ctrl-C to stop^)
REM Open the browser a couple of seconds after the server has bound its port.
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & explorer http://127.0.0.1:8000"
python xw.py serve
