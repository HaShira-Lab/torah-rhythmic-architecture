# Protocol: Taam Hierarchical Structure

## Analysis name
`taam_hierarchical_structure`

## Repository location
- Code: `src/analyses/core_taam/taam_hierarchical_structure.py`
- Runs: `run/`
- Results: `results/core_taam/taam_hierarchical_structure/`

## Purpose
Describe whether the Torah's taamim define a stable nested segmentation hierarchy and characterize the recurrence of segment sizes at each level.

This module unifies the former `taam_hierarchical_composition` and `taam_phrase_size_grammar` analyses. The text is parsed once; one common segment tree supplies both hierarchy and size measurements.

## Input
Annotated transliterated Torah files:
- `word[taam]`
- `word[taam1,taam2]`
- external markers such as `{sof_pasuq}`

External markers are attached to the preceding word before accent-event and boundary calculations.

## Operational units
### Pulse
One Latin vowel group in the transliterated text. This is a syllable-like proxy, not a claim about exact phonetic duration.

### Accent event
One accented word event if the word carries at least one taam other than `paseq`. Multiple taamim on one word count as one accent event. `paseq` can close a segment but does not create an accent event.

## Hierarchical levels
- `verse`: closes at `sof_pasuq`
- `major`: closes at `atnah`, `atnah_hafukh`, or `sof_pasuq`
- `minor`: closes at `revia`, `zaqef_qatan`, `zaqef_gadol`, `shalshelet`, `paseq`, `atnah`, `atnah_hafukh`, or `sof_pasuq`

`atnah_hafukh` is treated as functionally equivalent to `atnah` for boundary and cadence classification, while retaining its own name in outputs. It is absent from the current five canonical inputs, so this rule does not change the frozen results.

The inclusion of enclosing boundaries in the child level ensures exact ordered partitioning:
- verse → major
- major → minor

## Questions
1. How many major segments occur within a verse?
2. How many minor segments occur within a major segment?
3. What are the pulse, accent, and word-size distributions at each level?
4. Is the size vocabulary concentrated in a small number of recurrent classes?
5. Which short size sequences recur within each level?

## Mandatory validation
For every parent segment:
- `child_word_sum == parent_word_count`
- `child_pulse_sum == parent_pulse_count`
- `child_accent_sum == parent_accent_count`
- at least one child is present

The console must report `validation_all_exact: True` for every book. Any `False` invalidates that run.

## Main run
`run/taam_hierarchical_structure_MAIN_all_books.bat`

Parameters:
- reporting limits: words 40, pulses 80, accents 25
- size n-grams: 2–6
- top size n-grams: 50
- jobs: 5

Full CLI:
- `--out_dir`: output directory
- repeatable `--book TAG PATH`: unique book tag and existing annotated input
- `--run_label`: label written to outputs
- `--jobs`: parallel book processes, integer ≥ 1
- `--max_words`, `--max_pulses`, `--max_accents`: positive reporting cutoffs
- `--top_ngram`: positive number of ranked size sequences retained
- `--ngram_ns`: comma-separated sequence lengths, each ≥ 2

Results:
`results/core_taam/taam_hierarchical_structure/main/`

## Controls
`run/taam_hierarchical_structure_CONTROLS_all_books.bat`

These are output-stability controls only:
- `control_large_ranges`: larger reporting ranges
- `control_top200`: larger ranked output

They do not change segmentation or the observations. Main summaries should therefore remain identical.

## Explore
`run/taam_hierarchical_structure_EXPLORE_all_books.bat`

Produces a larger descriptive long-tail list (`top_ngram=500`). It is exploratory and should not be used as a significance test.

## Outputs per book
- `hierarchy_segments.csv`
- `hierarchy_relations.csv`
- `hierarchy_level_summary.csv`
- `hierarchy_relation_summary.csv`
- `hierarchy_size_frequency.csv`
- `hierarchy_size_ngram_top.csv`
- `hierarchy_validation.csv`
- `hierarchy_meta.json`

Equivalent `ALL_*.csv/json` files are written across all five books.

Metadata records the complete parameter set, level definitions, relations, input path, and SHA256 of each input. Before a run, the program removes only its known output filenames for the requested books and combined run directory; unrelated files are preserved. This prevents old outputs from being mistaken for results of a new run.

## Primary article-facing measures
- mean and median major units per verse
- share of verses with exactly two major units
- mean and median minor units per major unit
- pulse and accent medians at minor, major, and verse levels
- top-five size-class coverage
- exact-partition validation

## Interpretation
A stable pattern near:
- minor ≈ 3 accents ≈ 8 pulses
- major ≈ 6 accents ≈ 16 pulses
- verse ≈ 12 accents ≈ 30–32 pulses

combined with verse ≈ 2 major and major ≈ 2 minor supports the claim that cadence marks encode a recurrent nested temporal segmentation architecture.

Size n-grams are descriptive sequences of adjacent segment sizes. They document recurrence but are not a probabilistic test of a bounded or restricted size vocabulary.

## Claims not made
This analysis does not by itself establish:
- a fixed modern meter;
- exact ancient duration values;
- melody or harmony;
- non-randomness under a probabilistic null.

Its role is structural and descriptive. Non-random local ordering is tested separately by `taam_grammar`.

## Validation and failure conditions
The program rejects missing input files, duplicate or empty book tags, jobs below 1, nonpositive reporting/list limits, empty n-gram lists, and n-gram sizes below 2. A successful run must also report `validation_all_exact: True` for all five books.
