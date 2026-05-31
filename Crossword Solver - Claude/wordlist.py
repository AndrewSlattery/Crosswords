#!/usr/bin/env python3
"""
wordlist.py — deterministic candidate generation from a word list.

Given a clue's current crossing-letter pattern (e.g. ?A?T?), enumerate the
listed words that fit. This narrows — sometimes settles — a clue *before* any
model is spent on it:

  0 matches  -> the pattern fits NO listed word. Strong hint that a crossing
                letter is wrong — OR the answer is a name/phrase not in the
                list. Investigate; do NOT blindly retract. (verdict "none")
  1 match    -> almost certainly the answer. Dispatch only to CONFIRM the
                wordplay, not to solve from scratch. (verdict "unique")
  2..FEW_MAX -> hand the list to the solver as hints. (verdict "few")
  > FEW_MAX  -> too open to help; solve normally. (verdict "many")

It also backs a cheap real-word gate (`contains`) for sanity-checking an
answer a solver returns — though remember the list is not exhaustive, so a
miss is a yellow flag, not proof of a bad answer.

Source: WordWeb.txt next to this script by default (override with the
CRYPTIC_WORDLIST env var). Each entry is normalized to bare A-Z — de-accented
(café -> CAFE), with spaces / hyphens / apostrophes removed — so a multi-word
answer like "DEADBEAT DAD" normalizes to DEADBEATDAD and matches an 11-cell
grid pattern, exactly as the engine stores committed answers. Entries that
still contain digits or other junk after normalizing are dropped.

A length-bucketed cache (wl_cache/<len>.txt) is built on first use and rebuilt
whenever the source file changes, so a query reads only the one length it needs.
All output is JSON. Subcommands: build | match <PAT> | contains <ANSWER> | info.
"""

import argparse
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.environ.get("CRYPTIC_WORDLIST", os.path.join(HERE, "WordWeb.txt"))
CACHE_DIR = os.path.join(HERE, "wl_cache")
MANIFEST = os.path.join(CACHE_DIR, "manifest.json")
MAX_LEN = 40          # ignore absurdly long phrases; no grid needs them
FEW_MAX = 12          # 2..FEW_MAX matches -> "few" (worth passing as hints)


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

_STRIP = {" ", "-", "'", "’", ".", "·"}   # removed before matching


def normalize(raw):
    """Fold a raw list entry to bare uppercase A-Z, or None if unusable.

    De-accents (NFKD + drop combining marks), uppercases, removes the
    separators a grid ignores, and rejects anything left with non-ASCII or
    non-letter characters (digits, stray symbols, surviving accents).
    """
    w = unicodedata.normalize("NFKD", raw.strip())
    w = "".join(c for c in w if not unicodedata.combining(c))
    w = "".join(c for c in w if c not in _STRIP).upper()
    if not w or not w.isascii() or not w.isalpha():
        return None
    return w


# --------------------------------------------------------------------------
# Cache build / freshness
# --------------------------------------------------------------------------

def _detect_encoding(src):
    with open(src, "rb") as f:
        head = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def build_cache(src=DEFAULT_SRC):
    """(Re)build the length-bucketed cache from the source list."""
    enc = _detect_encoding(src)
    buckets = {}
    with open(src, encoding=enc) as f:
        for raw in f:
            w = normalize(raw)
            if w and len(w) <= MAX_LEN:
                buckets.setdefault(len(w), set()).add(w)

    os.makedirs(CACHE_DIR, exist_ok=True)
    for fn in os.listdir(CACHE_DIR):           # clear any stale buckets
        if fn.endswith(".txt"):
            os.remove(os.path.join(CACHE_DIR, fn))

    counts, total = {}, 0
    for length, words in buckets.items():
        ordered = sorted(words)
        counts[str(length)] = len(ordered)
        total += len(ordered)
        with open(os.path.join(CACHE_DIR, f"{length}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(ordered))

    st = os.stat(src)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"src": os.path.abspath(src), "encoding": enc,
                   "mtime": st.st_mtime, "size": st.st_size,
                   "total": total, "counts": counts}, f, indent=2)
    return {"total": total, "lengths": len(counts)}


def _cache_fresh(src):
    if not os.path.exists(MANIFEST):
        return False
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
        st = os.stat(src)
        return (m.get("src") == os.path.abspath(src)
                and m.get("mtime") == st.st_mtime
                and m.get("size") == st.st_size)
    except (OSError, ValueError):
        return False


def ensure_cache(src=DEFAULT_SRC):
    if not _cache_fresh(src):
        build_cache(src)


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------

def _bucket_path(length):
    return os.path.join(CACHE_DIR, f"{length}.txt")


def matches(pattern, src=DEFAULT_SRC):
    """All listed words fitting a ?A?T?-style pattern (full list, not truncated)."""
    ensure_cache(src)
    pat = pattern.upper()
    path = _bucket_path(len(pat))
    if not os.path.exists(path):
        return []
    rx = re.compile("^" + "".join("[A-Z]" if ch == "?" else re.escape(ch)
                                  for ch in pat) + "$")
    with open(path, encoding="utf-8") as f:
        return [w for w in (line.strip() for line in f) if w and rx.match(w)]


def contains(answer, src=DEFAULT_SRC):
    """Is answer (after normalizing) present in the list? (Soft real-word gate.)"""
    w = normalize(answer)
    if not w:
        return False
    ensure_cache(src)
    path = _bucket_path(len(w))
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        return any(line.strip() == w for line in f)


def verdict(n):
    if n == 0:
        return "none"
    if n == 1:
        return "unique"
    if n <= FEW_MAX:
        return "few"
    return "many"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Deterministic candidate generation")
    ap.add_argument("--src", default=DEFAULT_SRC, help="word list path")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="force a cache rebuild")
    sub.add_parser("info", help="cache stats")
    s = sub.add_parser("match", help="words fitting a pattern")
    s.add_argument("pattern")
    s.add_argument("--limit", type=int, default=50, help="max matches to print")
    s = sub.add_parser("contains", help="is an answer a listed word?")
    s.add_argument("answer")
    args = ap.parse_args()

    if args.cmd == "build":
        print(json.dumps({"ok": True, **build_cache(args.src)}, indent=2))
    elif args.cmd == "info":
        ensure_cache(args.src)
        with open(MANIFEST, encoding="utf-8") as f:
            print(f.read())
    elif args.cmd == "match":
        found = matches(args.pattern, args.src)
        print(json.dumps({
            "pattern": args.pattern.upper(), "count": len(found),
            "verdict": verdict(len(found)),
            "matches": found[:args.limit],
            "truncated": len(found) > args.limit,
        }, indent=2))
        sys.exit(0 if found else 1)
    elif args.cmd == "contains":
        print(json.dumps({"answer": normalize(args.answer),
                          "in_list": contains(args.answer, args.src)}))


if __name__ == "__main__":
    main()
