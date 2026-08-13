# Protocol: Taam Temporal Structure

## Analysis name
`taam_temporal_structure`

## Repository location
- Code: `src/analyses/core_taam/taam_temporal_structure.py`
- Runs: `run/`
- Results: `results/core_taam/taam_temporal_structure/`

## Goal
Test whether the Torah's taam system organizes local performance time through:

1. a compact inventory of pulse intervals between adjacent accent events;
2. systematic differences between intervals inside segments and across cadence boundaries;
3. a restricted cross-book vocabulary of cadence-defined segment shapes;
4. non-random transitions between segment-shape classes.

The analysis does not claim reconstruction of melody, exact duration, or modern meter.

## Input
Annotated transliterated Torah files:

`data/data_processed/torah/*_taamim_annotated.txt`

Expected forms:
- `word[taam]`
- `word[taam1,taam2]`
- external markers such as `{sof_pasuq}`

External markers are attached to the preceding word before accent-event fields are finalized.

## Shared operational definitions

### Pulse
A pulse is one Latin-vowel group in the transliterated input. It is a syllable-like operational proxy.

### Accent event
A word contributes one accent event when it carries at least one non-accentless taam. `paseq` is a boundary marker but is not counted as an accent event.

### Segment levels
- `verse`: closes at `sof_pasuq`
- `major`: closes at `atnah`, `atnah_hafukh`, or `sof_pasuq`
- `minor`: closes at any major boundary or at `revia`, `zaqef_qatan`, `zaqef_gadol`, `shalshelet`, `paseq`

`atnah_hafukh` is treated operationally as a variant of `atnah` throughout reset and segmentation models.

## Part 1: Accent-interval inventory
For every pair of adjacent accent events, the script measures their distance in pulses.

Reported metrics:
- mean and median interval;
- top1/top3/top5 interval identities and shares;
- normalized entropy;
- frequency table;
- descriptive interval n-grams.

Reset models:
- `continuous`
- `sof_only`
- `major`
- `major_minor`

## Part 2: Boundary-aligned interval grammar
For segmented models, intervals are classified as:
- `within`
- `cross_reset`
- `all`

The article-facing contrasts are:
- `delta_top3_within_minus_cross`
- `delta_entropy_within_minus_cross`

Each contrast is tested directly in every permutation by recomputing
`within − cross_reset`; significance is not inferred from two separate tests.

Empirical p-value directions are fixed in advance:
- upper tail for top3 concentration and `delta_top3`;
- lower tail for entropy and `delta_entropy`.

Main null: `global_interval_shuffle`. It preserves the observed interval multiset while randomizing its alignment with real within/cross positions.

Control null: `cyclic_shift`. It preserves local interval order while changing alignment to boundaries.

No interval null is run for `continuous` or `all`: shuffling preserves their
complete interval multiset and therefore cannot change concentration or entropy.
Their null fields are marked `not_applicable_distribution_preserved`.

## Part 3: Segment-shape vocabulary
Each complete segment is described by:
- word count;
- pulse count;
- accent-word count;
- taam-event count;
- internal minor-boundary count.

Article-facing shape fields:
- `shape_PA = P{pulses}_A{accent_words}`
- `bucket_PA`

Additional reproducibility fields:
- `shape_PAW`
- `bucket_PAW`

## Part 4: Segment-transition grammar
To reproduce the earlier transition analysis, transition shapes preserve its original operational definition:
- P = word count;
- A = taam-event count in the main run;
- C = internal minor-boundary count.

Fields:
- `transition_exact_shape`
- `transition_bucket_shape`

Tests:
- unigram entropy;
- conditional entropy;
- entropy reduction;
- in-sample next-shape accuracy;
- train/test Markov accuracy;
- transition count, conditional probability, lift, and permutation Z.

Empirical p-values are lower-tailed for conditional entropy and upper-tailed
for entropy reduction and prediction accuracy. P-values for individual
reported transitions are screening indicators over selected frequent
transitions; the global entropy/accuracy results are primary.

The `accent_words` control replaces taam-event count with accent-word count. The chronological control tests ordered rather than randomly mixed train/test pairs.

## Main run
- interval permutations: 500
- transition permutations: 500
- interval null: `global_interval_shuffle`
- transition split: `random`
- transition accent mode: `taam_events`
- random seed: `1`
- five books processed in parallel with `--jobs 5`

The fixed seed controls interval permutations, transition permutations, and
the random train/test split. Identical inputs and parameters therefore produce
identical results regardless of book-level parallel execution.

## Controls
1. `control_cyclic_shift`
2. `control_accent_words_chronological`
3. `control_descriptive_none`

The third control uses no interval null, wider interval output, and `min_transition_count=20`.

## Explore
`explore_large_output` increases interval n-gram, shape, and transition output. It is exploratory and not intended as the main article result.

## Outputs
Per book and all-books:
- `interval_summary.csv`
- `interval_frequency.csv`
- `interval_ngram_top.csv`
- `interval_examples.csv`
- `interval_within_cross_contrast.csv`
- `segment_shapes.csv`
- `segment_shape_summary.csv`
- `segment_shape_frequency.csv`
- `segment_transition_summary.csv`
- `segment_transitions.csv`
- `segment_transition_z.csv`
- `temporal_structure_meta.json`

All-books files are prefixed with `ALL_`.

Metadata records the run label, complete CLI invocation, operational level
definitions, all parameters, and the SHA256 hash of every input file. Before a
run, the program removes only its own known output files in that run's target
directory; unrelated files are left untouched. Book tags must be unique, all
inputs must exist, and numeric parameters are validated before analysis begins.

## Interpretation
The strongest defensible claim is:

> Accent timing is governed by a compact interval inventory whose distribution changes systematically at taam-defined boundaries; those same boundaries generate a restricted vocabulary of recurrent segment shapes, with weaker but reproducible sequential dependencies between shape classes.

The shape-transition component is supporting evidence. The interval contrast and cross-book shape vocabulary are the principal results.

## Limitations
- Pulse counting is based on transliterated vowel groups.
- Interval n-grams are descriptive motifs, not proof of meter.
- The segment-transition effect is moderate and should not be described as deterministic prediction.
- No independent unaccented prose control is available.
