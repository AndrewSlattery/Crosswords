#!/usr/bin/env python3
"""
check.py — cheap deterministic gates that need no language model.

Currently a single check:
  pattern <PAT> <ANSWER>   does ANSWER fit a pattern like ?A??E? (? = any)

(`word` lookup was removed: there's no wordlist shipped with the suite, and a
solver claiming "fits the letters but isn't a real phrase" was rarely the real
failure mode in practice. The parse-check by the verifier role is the much
stronger gate against false fits.)
"""

import argparse
import json
import sys


def fits_pattern(pattern: str, answer: str) -> bool:
    a = answer.upper().replace(" ", "").replace("-", "")
    p = pattern.upper()
    if len(a) != len(p):
        return False
    return all(pc == "?" or pc == ac for pc, ac in zip(p, a))


def main():
    ap = argparse.ArgumentParser(description="Deterministic answer checks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("pattern"); s.add_argument("pattern"); s.add_argument("answer")
    args = ap.parse_args()

    ok = fits_pattern(args.pattern, args.answer)
    print(json.dumps({"pattern": args.pattern.upper(),
                      "answer": args.answer.upper(), "fits": ok}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
