# OED "isolated use" theme list

Source: four OED advanced-search exports (`textTermOpt0=Definition`, phrase `"isolated use"`,
sliced by first-use date to stay under the export cap). The footers confirm the exports are
complete — 997 + 991 + 997 + 922 = **3,907 entries**, no truncation.

The exports say *that* an entry contains the phrase "isolated use" somewhere in its definition
text, but not *where* — and the `DEFINITION` column is capped at about 50 characters, so the
note itself never survives into the CSV. The filtering below infers it from the metadata.

## The main signal: `DATE OF USE`

The OED prints an entry's date span as first quotation → last quotation:

| Shape | Meaning | Count |
|---|---|---|
| `1621` | all evidence falls in one year | 1,559 |
| `1623-1799` | evidence at two or more separated dates | 81 |
| `1922-` | **not marked obsolete — the last-quotation year is hidden** | 2,267 |

The third row is the trap. An open-ended date does **not** mean many quotations: `demi-world`
prints as `1862-`, band 2, "In current use", on a single 1862 source, with the whole note
reading "= demimonde. Apparently an isolated use". Frequency band is no help either — it is
computed from a modern corpus on the letter-string, not from the OED's own quotations.

So the single-year test is **sufficient but not necessary**. Tier 1 is sound; the 2,267
open-ended entries are *unresolved*, not excluded, and an unknown number of them qualify.

## Second filter: is the letter-string also an ordinary word?

Many hits are one-off *conversions* — a familiar word pressed into a new part of speech
(`his, v.`, `rat, v.`, `pie, v.`). One source for the entry, but not for the word.
Three independent tests catch these:

1. another **still-current OED entry** shares the crossword form (checked against
   `../Word List - OED.csv`, which is current-use-only, so it is a good "is this a live word?"
   test — though it has gaps, e.g. `port` and `point` are missing);
2. the **OED URL carries a homograph number** (`bullish_adj1`, `port_v5`) — proof of a sibling entry;
3. `TYPE OF FORMATION` is **`conversion`** — by definition built on an existing English word.

## Tiers (in `Isolated uses - annotated.csv`)

| Tier | Count | |
|---|---|---|
| **1** single year of evidence, form unique | **1,407** | the theme list |
| 2 single year of evidence, but form is another word too | 152 | `HIS`, `RAT`, `PIE`, `NOW` — a separate theme in its own right |
| 3 evidence at two or more separated dates | 81 | two sources, not one |
| 4 unresolved | 2,267 | contains both `by`/`do`/`so` (sense-level) and `demi-world` (genuine) |

## Closing tier 4

`build.py` will resolve tier 4 automatically if given last-use-filtered exports. Re-run the
same search with the date-of-use filter set to **last use** instead of first use (the current
export URLs carry `dateOfUseFirstUse=true`, so check what else that dropdown offers), slice it,
and drop the files in this folder named `OED Search Export - Last use <from>-<to>.csv`.
The script reads the slice bounds straight out of each file's footer, so the names only need
the words "Last use" in them.

Given last use ∈ `[lo, hi]` and the first-use year already known per entry:

- `lo > first_year` → there is later evidence → **not** a one-source word;
- `hi <= first_year` → last equals first → all evidence in a single year → **qualifies**.

Century slices (~6 exports) should clear most of the 2,267 by the first rule; decade slices
over whatever survives would settle the rest. Nothing else needs changing — re-run `build.py`.

## Files

- `Isolated uses - theme list.txt` — tier 1, one form per line, A–Z only, sorted by length
- `Isolated uses - theme list (CC).txt` — same, `WORD,50` for Crossword Compiler
- `Isolated uses - glossary.csv` — tier 1 with definition, date and OED link, for clueing
- `Isolated uses - unresolved.csv` — the 2,267 still open, sorted by first-use year
- `Isolated uses - annotated.csv` — all 3,907 with tier and every signal used
- `build.py` — regenerates all of the above

## Known limits

- A single-year date means one *year*, not strictly one *quotation*; an entry with two
  quotations from the same year would look identical. Rare for nonce-words, but not impossible.
- Tier 1 includes 31 entries whose formation is `variant` — a one-off *spelling* of an
  existing word rather than a one-off word. Filter on the `formation` column to drop them.
- Inflections are not checked: `LABRA` is a distinct OED headword but also the plural of *labrum*.
- 70 tier-1 lemmas are multi-word and 327 hyphenated; both are flattened in the crossword form.
