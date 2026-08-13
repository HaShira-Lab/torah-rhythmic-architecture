# Rhyme Burst Architecture — Protocol v5

## Purpose

This analysis asks three separate questions:

1. Are there more local rhyme arrivals than expected from the same tokens in random order?
2. Given the observed amount and intensity distribution of rhyme activity, are active positions temporally clustered into bursts?
3. Given the observed bursts, do their locations align with the taam hierarchy?

Each question has its own null model. Results from one null must not be used to answer another question.

## Input and analyzed unit

Input files are the five `*_taamim_annotated.txt` files produced by the frozen phonetic/taam preprocessing stage. Their adjacent `.meta.json` files are mandatory. The analysis verifies every input SHA256 against `output_sha256` before computation.

The analyzed stream contains only word tokens with an explicit stressed vowel. Therefore `window = 20` means 20 preceding **analyzable stressed word tokens**, not 20 source words of every kind.

Structural markers are read before stress filtering. A boundary following a word without an explicit stressed vowel necessarily lies between the adjacent retained tokens in the analyzed stream. These rare projections are not hidden: they are counted per book in `parse_audit.boundaries_after_unanalyzable_words`.

## Shared rhyme protocol

The analysis imports the executable implementation:

```text
src/shared/rhyme/rhyme_protocol.py
```

`protocols/RHYME_PROTOCOL_V4.md` is the human-readable methodological
documentation. It is not opened, hashed, or otherwise required by the
analysis at runtime.

The rhyme signature begins at the final stressed vowel and continues to word end. When the stressed vowel is the final phonetic segment, the signature extends exactly one segment to the left. `FULL` and non-transitive `BRIDGE` are distinct match types.

MAIN uses `STRICT`: identical normalized segments only. Named phonetic-correspondence profiles belong to EXPLORE and must not be merged with MAIN.

Segmentation is deterministic and rule-based. It covers the regular consonant and multigraph patterns of the corpus. Rare orthographically ambiguous sequences may admit an alternative lexical segmentation; exceptional forms are not manually corrected. In particular, the shared implementation uses `t + sh` as the deterministic default for `tsh`, while rare lexical forms may permit `ts + h`.

## Observed rhyme-arrival stream

For every analyzable target token `j` after the first `L` analyzable tokens, the raw arrival count is the number of accepted rhyme links from `j` back to tokens `j-L ... j-1`.

Options:

- `match_filter = ALL`: FULL + BRIDGE;
- `match_filter = FULL`: FULL only;
- `match_filter = BRIDGE`: BRIDGE only;
- `exclude_exact`: exclude pairs whose normalized complete word forms are identical;
- `activity_threshold = T`: replace counts below `T` by zero.

An active position has thresholded count greater than zero. A burst is a maximal consecutive run of active positions. One burst may contain arrivals involving different rhyme signatures and different word pairs; it is a temporal activity unit, not one rhyme class.

## Test 1: local rhyme enrichment

Null:

```text
shuffle_tokens_then_recompute
```

The analyzable tokens are shuffled and all windowed rhyme arrivals are recomputed. This preserves token inventory, rhyme signatures, lexical frequencies, stream length, comparison rules, window length, threshold, and exact-word policy while destroying observed token order.

Primary metric:

```text
mean_arrivals
```

`active_rate` is secondary.

## Test 2: conditional burst clustering

Null:

```text
shuffle_observed_thresholded_arrival_stream
```

The already observed thresholded count stream is shuffled. This preserves its exact multiset: total arrivals, count distribution, number of active positions, and thresholded activity rate. It destroys only temporal arrangement. This conditional test distinguishes burst clustering from a simple excess of rhyme arrivals.

Primary metrics:

```text
active_lag1_corr
fano_w10
```

`count_lag1_corr` and other autocorrelation/run/Fano measures are secondary. `max_run_length` is descriptive only because it was not stable across all books under the conditional null.

Fano measures use non-overlapping windows; an incomplete final window is omitted.

## Test 3: taam-boundary alignment

Null:

```text
run_preserving_circular_translation
```

The complete observed thresholded stream is circularly translated relative to fixed taam boundaries. Only nonzero shifts that neither split nor merge a positive run are eligible. Thus every null sample preserves the observed collection of burst lengths and intensities. Eligible shifts are sampled without replacement; if all are requested, the complete eligible shift space is used.

Runs touching the first or last analyzed stream position are observationally truncated. They are retained in enrichment and clustering, but censored from the boundary-location test before translation. At most two edge runs are affected. Their number, positions, and arrivals are recorded in `boundary_edge_audit`, and every burst row states whether it entered the boundary test. This also prevents endpoint runs from merging under circular translation.

Primary metrics:

```text
run_ends_minor_boundary
run_ends_major_boundary
run_ends_verse_boundary
```

Containment and run-start metrics are secondary.

Boundary levels are nested:

- minor: `revia`, `zaqef_qatan`, `zaqef_gadol`, `shalshelet`, `paseq`;
- major: `atnah` or `atnah_hafukh`, and also every verse end;
- verse: `sof_pasuq`.

A major boundary also closes a minor block. A verse boundary also closes major and minor blocks. The three levels are not mutually exclusive.

## Empirical inference

For each metric the output records observed value, null mean, difference, fold, null SD, Z, one-sided enrichment/depletion p-values, and doubled two-sided p-value. Empirical p-values use the plus-one correction.

## MAIN

```text
window = 20
activity_threshold = 1
match_filter = ALL
exclude_exact = false
equivalence_profile = STRICT
enrichment permutations = 500
clustering permutations = 500
boundary permutations = 1000
base seed = 20260728
jobs = 5
```

Output:

```text
results/core_rhyme/rhyme_burst_architecture/main_strict
```

## CONTROLS

All controls retain STRICT:

1. ALL matches with exact word repetitions excluded.
2. FULL only.
3. FULL only with exact word repetitions excluded.
4. BRIDGE only.
5. Activity threshold 2.
6. Window 10.
7. Window 50.

Temporal clustering may be robust even when boundary alignment weakens. In particular, boundary alignment after exact-word exclusion must be reported as heterogeneous across books, not as a universal persistence result.

## EXPLORE

EXPLORE sweeps the named correspondence profiles while retaining MAIN window, threshold, match filter, exact-word policy, null construction, and seed. These are sensitivity conditions, not alternative baselines.

## Reproducibility and metadata

Book seeds depend on the fixed canonical book index, never on the order or subset supplied to `--books`. The three null families use independent per-book RNG seeds.

Every run writes:

- per-book arrival and burst audit CSVs;
- separate per-book and aggregate statistics for all three tests;
- per-book and aggregate JSON summaries;
- `RUN_METADATA.json` containing full CLI, run label/version, parameters, all seeds, Python/platform version, verified input hashes, analysis/shared-code hashes, the shared rhyme protocol version, and hashes of all other outputs.

Runs with the same inputs, parameters, seed, code, Python environment, and CLI are expected to be byte-reproducible. `jobs` changes execution order only; book outputs and statistics must remain identical.
