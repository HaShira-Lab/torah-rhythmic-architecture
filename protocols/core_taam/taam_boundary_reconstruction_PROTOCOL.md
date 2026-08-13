# Protocol: Taam Boundary Reconstruction

## 1. Goal

Test whether hidden minor cadence boundaries can be reconstructed from major-unit geometry and the remaining visible taam context, without rhyme, lexical, or phonetic features.

The scientifically primary taam-only comparison is `adjacent_only` versus `structure`. It tests whether the immediately preceding and following visible taamim predict a hidden boundary without using any feature of the current word.

## 2. Input and parser

Input is the canonical `*_taamim_annotated.txt` produced by preprocessing.

- Internal annotation: `word[taam1,taam2,...]`.
- External annotation: `{paseq}` and `{sof_pasuq}` attach to the preceding word.
- One parser is used by all models, folds, controls, predictions, and metadata.
- Input SHA256 and implementation SHA256 are recorded in every metadata file.

The script uses only the Python standard library.

## 3. Hidden target and major units

Positive class:

- `revia`
- `zaqef_qatan`
- `zaqef_gadol`
- `shalshelet`
- `paseq`

These labels are used only as gold labels. They are removed from the current, previous, and next taam signatures used as predictors.

Major units close at:

- `atnah`
- `atnah_hafukh`
- `sof_pasuq`

Major-cadence words are always excluded from candidate positions. By default the first and terminal non-major positions of a unit are also excluded; `--include_edges` restores those non-major edge positions. In the canonical complete Torah inputs, the terminal word is normally the excluded major cadence itself.

## 4. Canonical feature ladder

| Feature set | Information used |
|---|---|
| `structure` | Major-unit geometry only |
| `current_only` | Current word's remaining visible non-minor/non-major taamim only |
| `adjacent_only` | Immediately previous and next visible taamim only; no current-word features and no geometry |
| `local_taam` | Current + previous + next visible taamim; no geometry |
| `structure_current` | Geometry + current-word visible taamim |
| `structure_local` | Geometry + current + previous + next visible taamim |

`adjacent_only` is the strict neighbor model and the primary evidence for local taam grammar. `local_taam` and `structure_local` are reconstruction models, not pure neighbor tests, because absence of a visible sign on the current word can itself be informative after the hidden minor sign is removed.

No rhyme, word identity, lexical, phonetic, stress, or pulse features are computed or accepted.

## 5. Model

Each feature set is fitted with the same multinomial Naive Bayes implementation:

- class-prior smoothing: additive `alpha`;
- feature-count smoothing: additive `alpha`;
- MAIN: `alpha=1.0`;
- geometry caps in MAIN: `pos_cap=10`, `len_cap=30`.

Feature values are categorical strings. A higher score is a larger log-posterior odds estimate for the hidden-boundary class. Equal scores are resolved deterministically by ascending global word index.

Feature-weight CSV files are deterministic. Rows are sorted by weight and feature name, and a feature cannot occur twice within the same fold even when the requested positive and negative tails overlap.

## 6. Splitting and evaluation

### MAIN

- fixed five-fold cross-validation;
- split unit: complete major unit;
- `seed=1`;
- each eligible candidate is tested exactly once;
- no major unit appears simultaneously in train and test within a fold.

### Top-k reconstruction

Within each test fold, `k` equals the true number of hidden minor boundaries in that fold. The `k` highest-scoring positions are predicted as boundaries. Consequently:

`precision = recall = F1`

by design. This is an oracle-prevalence ranking evaluation: it tests placement of a known number of boundaries and does not estimate a deployable probability threshold.

Cross-validated F1 is computed from total true positives divided by total gold boundaries across folds. Fold mean, SD, minimum, and maximum are also reported.

## 7. Statistical tests

### Model versus random top-k

The null independently samples a matched random top-k prediction in every test fold and aggregates F1 across folds. Report:

- random F1 mean and SD;
- Z relative to the permutation distribution;
- one-sided empirical p-value with add-one correction.

MAIN uses `1,000` random permutations, so the smallest possible value is `1/1001 = .000999`.

### Direct paired model comparisons

Direct tests compare predictions on exactly the same held-out candidates. The observed statistic is:

`F1(model) - F1(comparator)`

For major-unit splits, true-positive contributions are clustered by major unit and their model/comparator signs are randomly exchanged. For random-word control, the cluster is the candidate word. Tests are one-sided for model improvement and use add-one empirical p-values.

MAIN uses `10,000` paired permutations. Prespecified comparisons include:

- `adjacent_only` versus `structure` — primary strict-neighbor test;
- `structure_local` versus `structure` — maximal combined reconstruction versus geometry;
- current-word and incremental ablations listed in the paired-comparison CSV.

## 8. Outputs

Per book:

- `boundary_reconstruction_summary.csv`
- `boundary_reconstruction_predictions.csv`
- `boundary_reconstruction_paired_comparisons.csv`
- `feature_weights_<feature_set>.csv`
- `boundary_reconstruction_meta.json`

All books:

- `ALL_boundary_reconstruction_summary.csv`
- `ALL_boundary_reconstruction_paired_comparisons.csv`
- `ALL_boundary_reconstruction_meta.json`

Predictions contain both score and selected/not-selected columns for every feature set. Metadata record the input hash, implementation hash, normalized full analysis command, alpha, caps, feature definitions, candidate policy, fold counts, output hashes, summary rows, and paired tests.

## 9. Launchers

- `MAIN`: five-fold major-unit cross-validation; 1,000 random and 10,000 paired permutations.
- `CONTROLS`:
  - five-fold random-word split;
  - inclusion of non-major edge positions;
  - wider geometry caps (`16/40`).
- `EXPLORE`: legacy-comparable 30% major-unit holdout with enlarged feature-weight output.

Every launcher changes to the repository root relative to its own location and exits immediately with a non-zero status if a Python run fails.

## 10. Interpretation boundary

A significant `adjacent_only - structure` contrast supports local sequential organization in the taam system beyond simple location inside a major unit. It does not by itself prove melody, meter, authorial intent, historical origin, or deterministic recovery of every boundary. Models containing current-word features answer the broader reconstruction question and must not be described as strictly neighbor-only evidence.
