# Keynesian Cryptics - Parse Notation Cheat Sheet

This document outlines the notation used to explain the solutions to the cryptic crosswords at Keynesian Cryptics.

A full parse will almost always have one of the following forms:
- `<...> X = Y`
- `X = Y <...>`

This depends on which end of the clue the definition is found.
 
## 0. Definitions

- `<...>` : Straight definition formed from part of the clue, at the beginning or end of the surface (or both, in the case of double definitions). Definitions should generally be written in lowercase, stripping out punctuation or possessives that are not an intrinsic part of the definition. Retain capital letters for proper nouns (e.g., `<Polish area>`).
  - "Record cant" (271-Across-13) is parsed as `<record> LIST <cant>`; "record" and "cant" define senses of "list".
- `{...}` : Cryptic definition explanation, accompanied by the notation `<&cd>` to signify that the whole surface defines the answer, if obliquely.
  - "When two gentlemen's agreements perhaps become legally binding?" (288-Down-6) is parsed as `<&cd> SAME-SEX MARRIAGE {when e.g. two men's "I do"s bind them together legally}`
- `<&lit>` : So-called "and-lit" clue in which the entire clue acts simultaneously as a definition and as wordplay.
  - "Fourth of Persepolis, old king from the East" is parsed as `<&lit> XERXES = ←_S_ EX REX←`; Xerxes II was the fourth Achaemenid Emperor to reign from Persepolis.

## 1. Anagrams & Transpositions

- `*` : Anagram the fodder. The clue will feature an anagram indicator like "bonkers", "somehow", or "rambling". If the fodder is a single continuous word, omit the parentheses (e.g., `GLORIED*`). If the fodder consists of multiple words, is hyphenated, or contains an apostrophe, enclose it in parentheses.
  - "Bonkers semi-rationalist philosophy" (281-Across-1) is parsed as `(SEMI-RATIONALIST)* = ARISTOTELIANISM`.
- `↔` : Swap two letters or strings.
  - "Rogue lascar switching sides" (278-Across-16) is parsed as `LASCAR, L↔R`; the 'L' and 'R' in "LASCAR" trade positions.
- `⭯...⭯` : Cycle the component by moving a string from one end to the other.
  - "Fly with cycling propellers" (273-Down-7) is parsed as `SOAR = ⭯OARS⭯`; the 'S' cycles from the end to the start.

## 2. Deletions & Derivations

- `[-...]` : Delete indicated parts, signalled by constructions like "mostly", "topless" or "endless".
  - "Mischievous kid suddenly going out of bounds" (282-Across-25) is parsed as `URCHIN = [-l]URCHIN[-g]`; the "bounds" of LURCHING are deleted.
- `-, out of` : Delete the indicated strings, signalled by constructions like "without", "losing" or "away from", "quitting" respectively.
  - "Host's mad to snub bishop" (284-Across-9) is parsed as `ARMY = BARMY - B`; 'B' is deleted.
  - "Vinegary wines ultimately thrown out by Spartan" (276-Across-12) is parsed as `ACETIC = _S out of ASCETIC`; 'S' is deleted.

## 3. Extractions, Charades & Hidden Words

- **Letter Extractions** : Use underscores to represent deleted letters. For first or last letters, place the underscore on the side of the deleted letters (e.g., `H_` for the first letter of "heathens", `_Y` for the last letter of "Yankee"). For alternating or regular cuts, replace the deleted letters with underscores to show the extraction pattern (e.g., `_E_N _E_D` from "bEeN hEaD").
- **Charades & Abbreviations** : Standard single-letter substitutions or abbreviations should not have any underscores (e.g., "bishop" = `B`, "loud" = `F`).
- **Hidden Words** : Indicated by showing the exact hidden string with only the single immediately adjacent letter on either side enclosed in parentheses with a dot.
  - "Dress used in panto gag" (1-Down) is parsed as `<dress> TOGA = (.n)TO GA(g.)`.

## 4. Concatenation & Positional Indicators

- ` ` (space) : Join elements in the order they appear by simple juxtaposition using a standard space. Use this when there is no explicit joining word in the surface.
  - "Blacken brown fabric" (290-Across-21) is parsed as `TAR TAN = TARTAN`.
- `+` : Join elements in the order they appear. Use this when the clue contains an explicit joining or link word like "and", "with", "plus", "near", "has", or "having".
  - "Pioneer species and each flightless bird died" (289-Across-15) is parsed as `SP + EA RHEA D = SPEARHEAD`; the + reflects "and".
- `after` : Join elements in the reverse order.
  - "Finished with location for shipping forecast" (288-Down-8) is parsed as `ENDED after PORT = PORTENDED`; ENDED "finished" appears before PORT "location for shipping" (PORT).

## 5. Containment & Insertion

- `inside/outside` : Place one component within another.
  - "Sharpen or dampen hard probes" (289-Down-1) is parsed as `WHET = WET outside H`; the answer is made of the word WET "dampen" which 'H' "hard" goes inside "probes".
  - "Prize is a bunch of cash including rand" (288-Across-17) is parsed as `AWARD = A WAD outside R`; the answer is made of the phrase A WAD "a bunch of cash" outside 'R' "rand".

## 6. Homophones

- `"..."` : Homophone the component. Clues use indicators like "heard", "in speech", or "announced".
  - "Heard salvo's sound" (282-Across-18) is parsed as `"HAIL" = HALE`.

## 7. Reversals

- `←...←` : Reverse the enclosed component.
  - "Aromatic plant is stored in laboratory upside-down" (283-Down-23) is parsed as `←IS inside LAB←`. The result of the inner operation, L(IS)AB, is reversed to get BA(SI)L.

## 8. Replacements & Translations

- `→/←` : Replace one string with another. The arrow's direction depends on the order of presentation in the clue.
  - "Chance to get Oscar instead of a western" (282-Across-22) is parsed as `ACCIDENTAL, O←A = OCCIDENTAL`; an A is replaced by O.
- `🇩🇪...🇫🇷` : Translate the enclosed component into the language indicated by the flags.
  - "Hamburger's good for digestive system" (271-Down-28) is parsed as `🇩🇪GOOD🇩🇪 = GUT <digestive system>`; the English "good" is translated to German.

## 9. Special & Complex Clue Types

- `£*...*£` (letter bank) : Anagram the fodder with repetition. Clues will typically include an anagram indicator and a word suggesting repetition.
  - "Start of soliloquy by Brontë repeatedly flubbed" (273-Across-16) is parsed as `TO BE OR NOT TO BE = £*BRONTE*£`; the answer has only the letters of BRONTE, but many appear multiple times.
- `⇐/⇒` (reverse engineering) : Reverse-engineer a phrase which can be read cryptically to indicate a word or phrase mentioned in the clue; this will be included in the parse within `{...}`.
  - "Cryptic way of saying 'peach' is jibe" (275-Across-10) is parsed as `{peach} CHEAP* ⇐ CHEAP SHOT`; the answer may be read as indicating an anagram of CHEAP, in this case "peach".
- `→"..."←` (Spoonerism) : Spoonerise the components, i.e. swap the onsets of two words in a phrase spoken aloud.
  - "Spooner's gumshoe practically formalwear" (287-Down-3) is parsed as `→"TEC NIGH"← = NECKTIE`.

Examples:
```
Blackmail material to strike down MP with—corruption involving mother (9)
Parse: <blackmail material> KOMPROMAT = KO MP + ROT outside MA
Answer: KOMPROMAT
Explanation: “Blackmail material” is the definition. “To strike down” gives KO, followed by MP. “Corruption” is ROT, which is “involving” MA (meaning mother) to make the letters RO(MA)T.

Rear section of orchestra is euphoniums (5)
Parse: <rear> RAISE = (.t)RA IS E(u.)
Answer: RAISE
Explanation: “Rear” is the definition. This is hidden as a “section” of the string “orchestRA IS Euphoniums”.

Old man not paying a debt moved repeatedly (8,3)
Parse: <old man not paying> DEADBEAT DAD = £A DEBT£
Answer: DEADBEAT DAD
Explanation: “Old man not paying” is the definition. The letters of “A DEBT” are “moved repeatedly” (reused and shuffled).

Leaders in iditarod can ease off (3)
Parse: I_ C_ E_ = ICE <off>
Answer: ICE
Explanation: The leading letters of Iditarod, Can, Ease give I C E. The definition is “off” (as a verb meaning to kill).

Thanks, doll, already in a relationship! (5)
Parse: TA KEN = TAKEN <already in a relationship>
Answer: TAKEN
Explanation: “Thanks” supplies TA; “doll” refers to KEN (Barbie’s partner). The definition is “already in a relationship.”

This minor criminal is forger (9)
Parse: (THIS MINOR)* = IRONSMITH <forger>
Answer: IRONSMITH
Explanation: This is an anagram of “This minor”. The definition is “forger” (one who forges iron).

Cafeteria near houses, say (7)
Parse: <cafeteria> BUTTERY = BY outside UTTER
Answer: BUTTERY
Explanation: The definition is “Cafeteria”; a buttery is a type of pantry or canteen. “Near” provides BY, which “housed” (contains) UTTER, which means “say”.

Awful man beginning to intimidate us in Paris (7)
Parse: <awful> HEINOUS = HE I_ NOUS
Answer: HEINOUS
Explanation: The definition is “awful”. It is made from HE (“man”), I (beginning of Intimidate) and NOUS (“us” in French, hence “in Paris”).

Notice crowds rob secure checkpoint (9)
Parse: AD isnide ROB LOCK = ROADBLOCK <checkpoint>
Answer: ROADBLOCK
Explanation: “Notice” is AD. Insert (“crowds”) AD “inside” ROB LOCK “secure” to get RO(AD)BLOCK. The definition is “checkpoint.”

Tree area nearly used up (5)
Parse: <tree> ASPEN = A SPEN[-t]
Answer: ASPEN
Explanation:  The definition is “tree.” It is made of A for “area” plus all but the last letter “nearly” of SPENT “used up”.

Bob avoids discount beer (3)
Parse: S out of SALE = ALE <beer>
Answer: ALE
Explanation: S (“bob” as slang for a shilling) is removed from “avoids” SALE “discount” from SALE to leave ALE. The definition is “beer.”

Additional editions without covers for delivery abroad (11)
Parse: EXTRA DITION = EXTRADITION <delivery abroad>
Answer: EXTRADITION
Explanation: “Additional” gives EXTRA; “editions without covers” is EDITIONS minus its first and last letters → DITION. The definition is “delivery abroad.”

Flower from a bunch cut by you (5)
Parse: <flower> LOTUS = LOTS outside U
Answer: LOTUS
Explanation: The definition is “flower”. It is made frmo LOTS “a bunch” outside “cut by” U (“you”, as texted).

Wordy rant claims end ruined after regular cuts (9)
Parse: <repetitive> REDUNDANT = RANT outside E_D _U_N_D
Answer: REDUNDANT
Explanation: The definition is “Wordy” (as in repetitive). The word RANT is outside “claims” the letters of “end ruined” after removing every second letter after “regular cuts”.
```