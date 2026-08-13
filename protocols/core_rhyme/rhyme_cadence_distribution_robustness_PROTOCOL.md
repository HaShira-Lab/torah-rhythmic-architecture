# Rhyme–Cadence Distribution and Robustness — Protocol v1

## Purpose

This analysis asks whether the rhyme–cadence alignment already established by
`rhyme_burst_architecture.py` is broadly distributed across the Torah or can be
attributed to a small number of rhyme-rich passages.

It does **not** compare the Torah with a modern text. It does not retest whether
Hebrew contains more phonetic recurrence than another language, genre, or
period. Its scope is internal generalizability of the observed relationship
between rhyme-burst endings and independently defined taam boundaries.

The analysis asks four questions:

1. Is rhyme activity represented across all five books, fixed textual blocks,
   and verses?
2. Is the direction of burst-ending alignment reproduced across books and
   fixed blocks?
3. Does the pooled alignment survive exclusion of each book in turn?
4. Does it survive removal of the most rhyme-dense fixed blocks?

This package is downstream of the frozen burst analysis. The primary existence
test for rhyme enrichment, the conditional test for burst clustering, and the
primary boundary-alignment test remain in `rhyme_burst_architecture.py`.

## Runtime dependencies

The analysis imports the frozen implementations:

```text
src/analyses/core_rhyme/rhyme_burst_architecture.py  version 5.0.2
src/shared/rhyme/rhyme_protocol.py                   protocol 4
```

Execution stops if the burst-analysis version is not exactly `5.0.2`.

Input is the five `*_taamim_annotated.txt` files and their mandatory adjacent
`.meta.json` files. Every source SHA256 is verified against `output_sha256`
before analysis.

## Frozen rhyme and hierarchy definitions

No rhyme or taam rule is reimplemented here.

- A rhyme signature begins at the final stressed vowel and extends to word end.
- If the stressed vowel is the final phonetic segment, the signature extends
  exactly one segment to the left.
- `FULL` and non-transitive `BRIDGE` are distinct pairwise match types.
- bridge-to-bridge links are not created through transitive grouping.
- MAIN uses `STRICT` segmental identity.
- MAIN uses the preceding `20` analyzable stressed word tokens.
- MAIN activity threshold is one arrival.
- Minor, major, and verse boundaries are the nested boundaries defined by the
  frozen burst analysis.

## Scientific status of identical words

Exact lexical repetitions are not treated as noise or invalid rhyme. Repeated
words may be constituents of poetic parallelism and may help sustain form.
Therefore MAIN retains them.

For the selected match filter, the code computes two link streams using the
same tokens, window, rhyme rules, and order:

1. all accepted rhyme links;
2. accepted links between different normalized complete word forms.

Their difference is the `exact_word` component. Output reports:

- exact-word arrival links;
- different-word arrival links;
- FULL and BRIDGE link totals before applying the selected match filter;
- their proportions;
- positions active through exact words only;
- positions active through different words only;
- positions where both components occur;
- at thresholds above one, positions activated only by their combined count.

`--exclude-exact` is a diagnostic control. Weakening after exclusion means that
lexical recurrence carries part of the architecture; it does not by itself
invalidate the MAIN result. The control must not be described as separating
“real rhyme” from repetition.

## Observed stream and edge censorship

The thresholded arrival stream is constructed exactly as in the frozen burst
analysis. Active positions form maximal consecutive runs (bursts).

Runs touching the first or last analyzed stream position are observationally
truncated and are censored before location inference. They remain represented
in descriptive rhyme-activity coverage. At most two edge runs are affected,
and their positions and arrival totals are recorded.

## Coverage summaries

Coverage is descriptive; it is not a comparison with an external prose corpus.

Per book, output records:

- eligible analyzed positions, arrivals, active positions, and active rate;
- number of boundary-test burst endings;
- represented verses and the proportions containing activity or a burst end;
- fixed-block activity and arrival density;
- lexical decomposition described above.

The first verse intersected by the left rhyme window is marked as not fully
represented and excluded from verse-coverage denominators. Verse identifiers
are sequential within each book; the input does not contain chapter labels, so
the analysis does not invent chapter divisions.

## Fixed textual blocks

MAIN partitions each book separately into non-overlapping blocks of `1,000`
eligible stream positions. These are analyzable target positions after the
left rhyme-window edge, not unfiltered source words.

The final incomplete block is retained descriptively and enters fixed-block
inference only if it contains at least `50%` of the requested block size.

A block enters the distribution summary only when:

1. it passes the length rule; and
2. at least five observed, edge-censored burst endings fall inside it.

Eligibility depends on activity amount, never on whether the burst endings hit
boundaries.

For each eligible block and boundary level, the response is:

```text
burst endings on the boundary / burst endings in the block
```

The block-specific difference is observed hit rate minus its own circular-null
mean. Distribution summaries report:

- `positive_block_difference_share`;
- `median_block_hit_rate_difference`.

Minor and major summaries are robustness outcomes. Verse summaries are
exploratory because verse boundaries are sparse at this block scale and prior
book-level effects are heterogeneous.

Per-block Z and p-values are diagnostic rows used to construct and inspect the
distribution. Individual blocks are not declared significant and no claim is
based on counting individually significant blocks.

Blocks are not asserted to be independent textual replications. Empirical
inference translates each book independently and recomputes the cross-block
summary under the null.

## Null model

All inferential checks use the frozen null:

```text
run_preserving_circular_translation
```

The complete observed edge-censored thresholded stream is circularly
translated relative to fixed taam boundaries. Only nonzero shifts whose cut
neither splits nor merges an active run are eligible. Shifts are sampled
without replacement; the complete eligible space is used if requested.

This preserves:

- the observed number of rhyme arrivals;
- arrival intensities and their complete order;
- active/zero pattern;
- burst lengths, intensities, and spacing;
- autocorrelation and the entire burst architecture;
- taam hierarchy and textual block locations.

It destroys the observed location of that architecture relative to boundaries.
Thus a positive result cannot be produced merely by having many exact-word or
different-word repetitions: their observed amount and burst organization are
already held fixed.

## Leave-one-book-out robustness

For each boundary level the pooled burst-ending hit rate is recalculated for:

```text
ALL books
ALL except Genesis
ALL except Exodus
ALL except Leviticus
ALL except Numbers
ALL except Deuteronomy
```

Null values pool independent book-specific circular translations at the same
permutation index. These rows are sensitivity estimates, not five independent
confirmatory tests.

## Rhyme-dense-block trimming

Fixed blocks eligible under the `50%` length rule are ranked across the corpus
by observed analyzed arrival density, without reference to boundary hits. The
analysis then removes the top:

```text
0%, 1%, 5%, and 10% of fixed blocks
```

Bursts are defined before trimming. A burst is omitted only when its ending
falls in a selected block; trimming therefore cannot split a run and create an
artificial new ending.

The same fixed omitted block locations are applied to every circular-null
translation. Persistence after trimming shows that a pooled effect is not
confined to the most rhyme-dense passages. Weakening is reported as
concentration, not as automatic invalidation.

## Book-direction audit

The output counts books whose observed burst-ending hit rate exceeds their own
circular-null mean. With only five books this is a descriptive directional
audit. Books are not treated as five statistically independent replications.

## Empirical inference

Every inferential row contains observed value, null mean, difference, fold,
null SD, Z, one-sided enrichment/depletion p-values, and doubled two-sided
p-value. Empirical p-values use the plus-one correction.

## MAIN

```text
window = 20
activity_threshold = 1
match_filter = ALL (FULL + BRIDGE)
exclude_exact = false
equivalence_profile = STRICT
block_size = 1000
minimum_block_fraction = 0.5
minimum_burst_ends_per_block = 5
boundary_permutations = 1000
base_seed = 20260728
jobs = 5
```

Output:

```text
results/core_rhyme/rhyme_cadence_distribution_robustness/main_strict
```

## CONTROLS

All ordinary controls retain `STRICT`:

1. exact lexical repetitions excluded;
2. FULL matches only, exact repetitions retained;
3. FULL matches only, exact repetitions excluded;
4. BRIDGE matches only;
5. activity threshold raised to 2;
6. local rhyme window `L=10`;
7. local rhyme window `L=50`;
8. fixed block size 500;
9. fixed block size 2,000.

The exact-exclusion controls quantify the different-word component. They are
not alternate definitions of legitimate poetry.

## EXPLORE

EXPLORE varies only the named phonetic-equivalence profile while retaining
MAIN geometry, exact-word inclusion, null, seed, and scientific roles:

```text
STRICT, VF, DT, PB, QK, H_KH, TS_S, VOICING, TRADITION,
VOICING_TRADITION, EXPANDED_ALL
```

These are sensitivity conditions, not alternative baselines.

## Outputs

Every run writes:

- per-book fixed-block coverage CSV;
- per-book block-alignment statistics CSV;
- per-book verse-coverage CSV;
- per-book JSON summary;
- aggregate book coverage and lexical decomposition CSVs;
- aggregate fixed-block and verse CSVs;
- fixed-block distribution statistics;
- leave-one-book-out statistics;
- rhyme-dense-block trimming statistics;
- book-direction audit;
- aggregate JSON summary;
- `RUN_METADATA.json`.

The `*_fixed_blocks.csv` and `*_verse_coverage.csv` files are reproducible
row-level inventories.  They should follow the repository's existing policy
for large reconstructable outputs and remain untracked.  Aggregate statistics,
book summaries, metadata, and compact audit tables are the citable results.
Before staging a completed run, add these patterns to `.gitignore` if they are
not already present:

```gitignore
results/**/*_fixed_blocks.csv
results/**/*_verse_coverage.csv
```

Metadata records the full CLI, parameters, scientific roles, seeds,
Python/platform version, verified input hashes, hashes and versions of both
upstream implementations, and hashes of every other output.

Book seeds depend on the canonical book index, never on supplied order or
subset. Parallel execution changes scheduling only. With identical input,
parameters, seed, code, Python environment, and CLI, outputs are expected to be
byte-reproducible.
