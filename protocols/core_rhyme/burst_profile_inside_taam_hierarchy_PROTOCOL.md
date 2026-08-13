# Burst Profile inside the Taam Hierarchy — Protocol v5

## Purpose

This analysis asks how an already observed, thresholded local rhyme-arrival
stream is distributed from the beginning toward the end of taam-defined
segments.

It is downstream of `rhyme_burst_architecture.py` and does **not** retest:

1. whether local rhyme is enriched;
2. whether rhyme activity forms temporal bursts;
3. whether burst endings coincide with taam boundaries.

The third question is the boundary-alignment test already contained in
`rhyme_burst_architecture.py`. The present analysis instead tests the average
position of rhyme activity *inside* minor, major, and verse segments.

## Runtime dependencies

The analysis imports:

```text
src/analyses/core_rhyme/rhyme_burst_architecture.py  version 5.0.2
src/shared/rhyme/rhyme_protocol.py                   protocol 4
```

`protocols/RHYME_PROTOCOL_V4.md` is human-readable documentation. It is not
opened, hashed, or required at runtime.

## Input and analyzed stream

Input consists of the five `*_taamim_annotated.txt` files produced by frozen
preprocessing. An adjacent `.meta.json` file is mandatory. Before computation,
the code verifies the input file's SHA256 against `output_sha256` in metadata.

As in `rhyme_burst_architecture.py`, only word tokens with an explicit stressed
vowel enter the analyzed stream. Therefore `window = 20` means 20 preceding
**analyzable stressed words**, not 20 unfiltered source words.

The local rhyme signature and `FULL`/`BRIDGE` classification come entirely from
the shared executable rhyme protocol. MAIN uses `STRICT`, with no optional
cross-segment equivalences.

For every target after the first `L` analyzable words, the arrival count is the
number of accepted links to the preceding `L` analyzable words. Counts below
the activity threshold are replaced by zero; retained counts preserve their
original intensity.

Active runs touching the beginning or end of this finite stream are
observationally truncated. They remain in the complete arrival-stream audit but
are censored from profile inference before either null is applied. At most two
edge runs are affected; their positions and arrival totals are recorded. This
guarantees that the circular null can preserve the complete collection of
linear runs used by the profile test, including in long-window controls.

## Hierarchy segments

Segments are defined by the `minor_id`, `major_id`, and `verse_id` values
constructed upstream from taam boundaries. Boundary levels are nested.

Only segments whose beginning and end are completely represented after the
left rhyme-window edge are eligible. The first truncated segment at each level
is excluded.

MAIN requires at least three represented analyzable words per segment. Length
eligibility is evaluated **before** optional cadence-word removal, so the
cadence-word control retains the same eligible segment inventory as MAIN.

Every run records:

- represented, complete, and eligible segment counts;
- eligible share of complete segments;
- length distributions and exclusion reasons;
- a complete segment-inventory CSV.

This coverage matters especially at the minor level: MAIN describes the subset
of complete minor segments with length at least three, not every minor segment.
Minimum-length controls at 5 and 8 test dependence on short phrases.

## Positional profile

MAIN maps every eligible segment to five normalized bins ordered from segment
beginning toward cadence. Token positions are assigned by midpoint rank:

```text
(rank + 0.5) / segment_length
```

MAIN uses equal segment weighting. Values are first averaged within each
segment-bin and then across segments, preventing long segments from dominating
the profile. Empty segment-bins make no contribution to that bin; output records
the number of contributing segments and tokens for every bin.

Two response profiles are reported:

1. `mean_count`: mean thresholded arrival intensity;
2. `active_rate`: proportion of positions with positive thresholded activity.

## Metrics and inferential roles

For a five-bin profile:

- `terminal_contrast`: last bin minus first bin;
- `linear_slope`: least-squares slope across ordered bin midpoints;
- `cadence_peak`: last bin minus the mean of all earlier bins;
- `profile_energy`: scale-normalized deviation from a flat profile;
- `profile_amplitude`: maximum minus minimum bin value.

The frozen roles are:

- **primary:** `mean_count terminal_contrast` at minor and major levels;
- **secondary:** `mean_count linear_slope` at minor and major levels;
- **robustness:** `active_rate` metrics;
- **exploratory:** every verse-level result;
- **descriptive:** cadence peak, energy, and amplitude.

The primary interpretation is a terminal-over-initial contrast. A positive
result means relatively low activity at segment beginnings and higher activity
in the later part. It must not be described as a universal monotonic rise or a
universal peak on the cadence word.

## Null model 1: run-preserving circular translation

Name:

```text
run_preserving_circular_translation
```

The edge-censored observed thresholded stream is circularly translated relative
to the fixed hierarchy. Only nonzero shifts whose cut does not split or merge a
positive run are eligible.

Preserved:

- exact arrival values and their order;
- active/zero pattern;
- burst lengths, intensities, and spacing;
- autocorrelation;
- stream length;
- complete hierarchy and segment inventory.

Destroyed:

- observed alignment between rhyme activity and position inside taam segments.

Eligible shifts are sampled without replacement. If the requested count is at
least the eligible count, the complete eligible shift space is used. The number
of accepted and rejected shifts is recorded for every book and level.

This is the primary alignment null. Ordinary unrestricted rotation is not used,
because a cut inside an active run would change the linear burst collection.

## Null model 2: within-segment value permutation

Name:

```text
within_segment_value_permutation
```

Values are independently permuted inside every eligible segment at one
hierarchy level.

Preserved within each segment:

- analyzed length;
- total arrival intensity;
- active-position count;
- complete value multiset.

Destroyed:

- internal ordering of activity from segment beginning toward cadence.

This is a secondary internal-position null. It answers a different question
from global circular alignment, so the two null results are reported separately.

## Empirical inference

For every metric and null, output contains observed value, null mean,
difference, fold, null SD, Z, one-sided enrichment/depletion p-values, and a
doubled two-sided p-value. Empirical p-values use plus-one correction.

Positive one-sided inference is primary for terminal contrast and slope. Negative
values remain visible through `p_deplete` and must not be reinterpreted as
support for terminal enhancement.

## MAIN

```text
window = 20
match_filter = ALL (FULL + BRIDGE)
exclude_exact = false
activity_threshold = 1
equivalence_profile = STRICT
coordinate_mode = normalized
bins = 5
aggregation = segment
value_mode = raw
exclude_cadence_word = false
minimum segment length = 3
maximum segment length = none
circular permutations = 1000
within-segment permutations = 1000
base seed = 20260728
jobs = 5
```

Output:

```text
results/core_rhyme/burst_profile_inside_taam_hierarchy/main_strict
```

Minor and major are confirmatory levels. Verse is retained for comparison but
is exploratory because previous audit found heterogeneous book-level profiles.

## CONTROLS

Every ordinary control retains `STRICT` segmental identity:

1. exact lexical repetitions excluded;
2. FULL matches only;
3. FULL only with exact lexical repetitions excluded;
4. BRIDGE matches only;
5. activity threshold raised to 2;
6. window `L=10`;
7. window `L=50`;
8. cadence word removed while retaining MAIN's eligible segment inventory;
9. token-pooled rather than segment-equal aggregation;
10. minimum segment length 5;
11. minimum segment length 8;
12. absolute distance to cadence through distance 7;
13. within-segment share normalization.

These controls distinguish several possible sources of the profile. In
particular, FULL and BRIDGE must be reported separately; prior audit found the
positive pattern concentrated in FULL, while BRIDGE was weak or negative.
Excluding exact repetitions and restricting longer minor segments may weaken
the effect and must be reported as heterogeneous if that result recurs.

## EXPLORE

EXPLORE holds the MAIN geometry and null construction fixed while sweeping:

```text
STRICT, VF, DT, PB, QK, H_KH, TS_S, VOICING, TRADITION,
VOICING_TRADITION, EXPANDED_ALL
```

These are equivalence-sensitivity conditions, not alternative baselines.

## Reproducibility and metadata

Book and null seeds derive from the canonical book and hierarchy-level indices,
never from the order or subset supplied to `--books`. Circular and
within-segment nulls use independent RNG streams. Parallel execution changes
only scheduling.

Every run writes per-book and aggregate:

- arrival-stream CSVs;
- segment-inventory CSVs;
- five-bin profile CSVs;
- statistics CSVs;
- JSON summaries;
- `RUN_METADATA.json`.

Metadata records full CLI, parameters, software environment, all seeds,
verified input hashes, hashes and versions of the analysis, upstream burst code,
and executable rhyme module, the shared rhyme-protocol version, and hashes of
all other outputs. The Markdown protocols are not runtime dependencies.

## Interpretation boundary

Evidence for a positive minor/major terminal contrast supports coordination of
local rhyme activity with position inside the taam hierarchy. It does not by
itself prove a fixed musical meter, a cadence-word peak, intentional authorship,
or exact burst-boundary coincidence.
