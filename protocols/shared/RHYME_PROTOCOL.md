# Rhyme protocol v4: strict baseline and sensitivity profiles

## Baseline

The scientific baseline is `STRICT`. Two rhyme signatures match only when
their normalized transliteration segments are identical. No cross-segment
phonetic equivalences are active by default.

The rhyme signature itself is still defined from the final stressed vowel to
the end of the word. If the stressed vowel is the final segment, exactly one
preceding segment is included. FULL and non-transitive BRIDGE matching are
structural comparison rules and are not phonetic equivalence classes.

## Corpus-derived segment inventory

Inspection of all five supplied annotated Torah files found only the following
multigraphs that function as single transliteration segments:

- `kh`
- `sh`
- `ts`

The previous generic entries `dzh`, `zh`, and `ch` do not occur. The sequence
`tsh` occurs five times and is explicitly segmented as `t` + `sh`; neither treating
`tsh` as one segment nor greedily reading it as `ts` + `h` is correct. The symbol `ḥ` does not occur
anywhere in the supplied corpus.

## Optional sensitivity profiles

The following named profiles can be selected explicitly:

- `STRICT`: no equivalences
- `VF`: v~f
- `DT`: d~t
- `PB`: p~b
- `QK`: q~k
- `H_KH`: h~kh
- `TS_S`: ts~s
- `VOICING`: v~f, d~t, p~b
- `TRADITION`: q~k, h~kh
- `VOICING_TRADITION`: VOICING + TRADITION
- `EXPANDED_ALL`: all six optional groups

These profiles are computational sensitivity conditions. Their labels do not
assert historical identity or identical pronunciation.

## Important source-specific observations

- `sin` and `samekh` are already both represented as `s` by preprocessing;
  they cannot be toggled later by the rhyme protocol.
- `het` is represented as `h`, not `ḥ`. Therefore an optional het/khaf-like
  sensitivity condition must be implemented as `h~kh`, although this also
  merges other source occurrences represented by `h`. It should be interpreted
  cautiously.
- The former code's `ḥ~kh` mapping had no effect on this corpus because `ḥ`
  never occurs.

## CLI examples

```bat
python rhyme_protocol.py profiles
python rhyme_protocol.py compare "davár" "atár" --equivalence-profile STRICT
python rhyme_protocol.py compare "davád" "davát" --equivalence-profile DT
python rhyme_protocol.py audit genesis_taamim_annotated.txt --equivalence-profile STRICT
```

## Analysis requirement

Every rhyme-based analysis must record the selected `equivalence_profile` in
its console header, CSV/JSON metadata, and output directory or run label.
`STRICT` should be used for MAIN. Expanded profiles belong in robustness runs.
