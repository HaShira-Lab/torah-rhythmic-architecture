# Rhyme–cadence article figures protocol

## Purpose

This utility produces the manuscript figures for the rhyme–cadence distribution
and robustness analysis. It is a presentation layer only: it reads frozen
outputs of `rhyme_cadence_distribution_robustness` v1.0.1 and does not recompute,
modify, or replace any statistical result.

## Repository locations

- Builder: `src/figures/build_rhyme_cadence_article_figures.py`
- Windows runner: `run/build_rhyme_cadence_article_figures.bat`
- Default output: `figures/rhyme_cadence_distribution_robustness/`
- This protocol: `protocols/figures/rhyme_cadence_article_figures_PROTOCOL.md`

## Required inputs

The default runner expects:

1. MAIN STRICT v1.0.1 results in
   `results/core_rhyme/rhyme_cadence_distribution_robustness/main_strict/`,
   including five `<book>_summary.json` files,
   `ALL_block_distribution_statistics.csv`, and `ALL_verse_coverage.csv`.
2. Exact-word exclusion block statistics in
   `results/core_rhyme/rhyme_cadence_distribution_robustness/control_strict_exclude_exact/ALL_block_distribution_statistics.csv`.

The builder rejects book summaries whose `analysis_version` is not `1.0.1`.

## Run

From the repository root:

```bat
run\build_rhyme_cadence_article_figures.bat
```

Optional positional arguments override, in order, the MAIN result directory,
the exact-word-control statistics file, and the output directory:

```bat
run\build_rhyme_cadence_article_figures.bat MAIN_DIR EXACT_CSV OUT_DIR
```

## Outputs

The builder writes each figure independently as 600-dpi PNG, LZW-compressed
TIFF, vector PDF, and editable SVG:

- `Figure1_book_alignment.*`
- `Figure2_block_robustness.*`
- `Figure3_verse_coverage.*`

The build fails if any requested export is absent or empty.

## Figure definitions

### Figure 1: book-level alignment

For each Torah book, the figure plots the observed-minus-translation-null
burst-end hit-rate difference at minor and major cantillation boundaries under
the MAIN STRICT specification.

### Figure 2: fixed-block robustness

Panel A compares the share of eligible fixed blocks with a positive difference.
Panel B compares the median block-level hit-rate difference. Open circles retain
all accepted links; filled squares exclude links between identical word forms.
The dashed reference represents the applicable null expectation.

### Figure 3: verse-scale distribution and coverage

Panel A displays, without smoothing, the proportion of eligible positions that
are active in every canonical verse, preserving received verse order within
each book. Grey marks verses not fully represented after the initial left
window. Panel B reports the percentage of fully represented verses containing
any recurrence activity and the percentage containing at least one
edge-censored burst end.

These percentages describe the distribution of recurrence across the corpus.
They are not verse-by-verse tests of cantillation-boundary enrichment and must
not be described as the percentage of verses in which the boundary effect is
statistically significant.

## Suggested captions

**Figure 1. Book-level enrichment of rhyme-burst endpoints at cantillation
boundaries.** Points show the observed-minus-null difference in burst-end hit
rate for minor and major disjunctive boundaries in each Torah book under the
STRICT MAIN specification. The null distribution preserves observed recurrence
runs while circularly translating them relative to the fixed boundary sequence.

**Figure 2. Fixed-block robustness and the contribution of exact-word
recurrence.** Panel A shows the share of eligible 1,000-position blocks with a
positive observed-minus-null difference; the dashed line is the corresponding
permutation-null mean. Panel B shows the median block-level hit-rate difference,
with zero indicating no enrichment. Open circles include all accepted links;
filled squares exclude links between identical word forms. Lines connect paired
specifications for the same boundary level.

**Figure 3. Verse-scale distribution of rhyme-like recurrence under STRICT
MAIN.** Panel A shows the unsmoothed proportion of eligible positions active in
each fully represented canonical verse, ordered separately within each Torah
book; grey marks verses not fully represented after the initial analysis
window. Panel B shows the percentage of fully represented verses containing at
least one active position and at least one edge-censored burst end. The expanded
axis resolves values between 96.5% and 99%; exact percentages are printed beside
the points. Coverage is descriptive and should not be interpreted as a
verse-by-verse test of cantillation-boundary enrichment.

## Software requirements

- Python 3
- NumPy
- Matplotlib
