# Rhyme–Cadence Additional Controls — Protocol v1.0.0

## Purpose and status

This companion package adds three targeted sensitivity analyses requested by
the final manuscript audit. It does not replace or redefine the frozen STRICT
MAIN analysis. Every output is labelled as a sensitivity control.

The package requires:

```text
src/analyses/core_rhyme/rhyme_burst_architecture.py                 v5.0.2
src/analyses/core_rhyme/rhyme_cadence_distribution_robustness.py   v1.0.1
src/shared/rhyme/rhyme_protocol.py                                 protocol 4
```

The supplied batch file intentionally runs the patched controls with one job.
This ensures that the local control definition is identical under Windows
`spawn` semantics and under POSIX execution. Random seeds and all permutation
counts are fixed.

## Control 1: operational minor boundary set without `paseq`

The manuscript's MAIN operational minor boundary set contains `revia`,
`zaqef_qatan`, `zaqef_gadol`, `shalshelet`, and `paseq`. The control removes
only `paseq` from that set. Rhyme signatures, link construction, arrival counts,
burst construction, major boundaries, verse boundaries, canonical verse maps,
and randomization rules remain unchanged.

This test addresses the special status of `paseq` as a transmitted separator
rather than an ordinary accent category. A positive result shows that the
minor-level finding is not created by grouping `paseq` with the selected
disjunctive accents.

Output:

```text
results/core_rhyme/rhyme_cadence_additional_controls/boundary_no_paseq/
```

## Control 2: final-stressed-vowel extension sensitivity

Under the frozen rhyme protocol, when the final stressed vowel is the last
phonetic segment of a word, the primary signature extends one segment left.
The control keeps the corpus and signature extraction unchanged but excludes
every pairwise link for which either participating token has an
`extended_left` signature.

This is deliberately conservative. It does not propose a competing definition
of rhyme and does not allow one-vowel signatures. It asks whether the principal
results survive when no accepted link depends on the one-segment extension
heuristic.

The control recomputes:

- token-order enrichment (500 permutations);
- conditional clustering (500 permutations);
- run-preserving boundary alignment (1,000 translations);
- canonical-verse and fixed-block distribution summaries.

It also writes `extended_left_token_counts.csv`, which reports how many
analyzable stressed tokens were affected in every book.

Output:

```text
results/core_rhyme/rhyme_cadence_additional_controls/exclude_extended_left/
```

## Control 3: canonical-verse allocation null

The descriptive verse coverage in MAIN is conditioned on fully represented
canonical verses. For each book and metric, this null preserves:

- the number and eligible-position size of every fully represented verse;
- the observed total number of marked positions;
- the book boundary.

It randomly allocates the observed marked positions without replacement over
all eligible positions in that book and counts the share of verses receiving
at least one mark. Two metrics are evaluated separately:

1. active recurrence positions;
2. edge-censored burst ends.

Five thousand allocations are generated for each book and metric. Pooled
statistics combine the five independently generated book-level null values at
the same permutation index, weighted by the number of fully represented
verses. The output reports observed value, null mean, difference, null SD, Z,
one- and two-sided empirical probabilities, and 2.5/97.5 percentiles.

This is a distribution test, not a boundary-alignment test. It asks whether the
observed marks are spread across canonical verses more broadly than would be
expected from their count and the empirical verse sizes.

Output:

```text
results/core_rhyme/rhyme_cadence_additional_controls/verse_allocation_null/
```

## Reproducible run

From the repository root:

```bat
run\rhyme_cadence_additional_controls_all_books.bat
```

The MAIN distribution run must already exist at:

```text
results/core_rhyme/rhyme_cadence_distribution_robustness/main_strict/
```

The first two controls require the five processed Torah files, adjacent
metadata, and verified canonical verse maps in
`data/data_processed/torah/`.

## Interpretation limits

- Removing `paseq` tests an operational classification choice; it does not
  settle the historical function of every occurrence of the sign.
- Excluding extended-left links is intentionally stricter than MAIN and may
  remove legitimate vowel-final rhymes together with heuristic-dependent ones.
- The verse-allocation null measures spatial coverage only. It does not test
  cantillation alignment, syntax, morphology, genre, or historical intention.
