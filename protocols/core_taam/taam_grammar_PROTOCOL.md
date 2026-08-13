# Taam Grammar — Analysis Protocol

## 1. Purpose

This analysis tests whether the Torah's taam-event stream exhibits reproducible local sequential organization beyond that expected from the marginal frequencies of individual signs.

It unifies four formerly separate procedures—transition grammar, n-gram profile, network profile, and core network—into one coordinated analysis built from the same parsed event stream.

## 2. Repository locations

- Code: `src/analyses/core_taam/taam_grammar.py`
- Run files: `run/taam_grammar_*.bat`
- Results: `results/core_taam/taam_grammar/<run>/`
- Inputs: `data/data_processed/torah/<book>_taamim_annotated.txt`

## 3. Event extraction

Each bracketed taam is treated as one ordered event:

`word[taam1,taam2]`

External tokens such as `{sof_pasuq}` and `{paseq}` are included in MAIN. Multiple signs attached to one word remain successive events in their written order.

Square brackets identify signs attached to a word. Curly-braced tokens are external events: they are not words and do not supply word stress. Both forms enter the event stream when external events are enabled.

No rhyme, lexical, semantic, or syntactic information enters this analysis.

## 4. Prespecified runs

### MAIN

- Includes external markers.
- Includes meteg.
- Entropy: k = 2–6.
- Recurrent formulas: k = 3–6.
- Transition permutations: 500 per book.
- Formula/entropy permutations: 200 per book.
- Seed: 1.
- Five books processed in parallel (`--jobs 5`).

### CONTROL: exclude external markers

Identical to MAIN except all `{...}` events are removed. This tests whether the result is driven by explicit external boundary tokens.

### CONTROL: exclude meteg

Identical to MAIN except `meteg` is removed. This tests whether the result is dominated by the most frequent marker.

### EXPLORE

Exploratory only. It extends entropy to k = 7, formulas to k = 3–7, increases the candidate pool, and lowers network-edge thresholds. It does not replace MAIN or the controls.

## 5. Null model

Within each book, the full taam-event stream is randomly permuted. This preserves:

- the number of events;
- the inventory of signs;
- unigram frequencies.

It destroys local sequential order. Therefore observed transition and n-gram concentration is evaluated against a frequency-matched random-order baseline.

## 6. Measures

### 6.1 N-gram entropy

For every requested k, Shannon entropy of the observed k-gram distribution is compared with the permutation distribution.

Primary direction: lower observed entropy than the null.

Reported statistics:

- observed entropy;
- null mean and standard deviation;
- one-sided empirical permutation p-value;
- Z-score only when the null distribution has sufficient variance.

### 6.2 Directed transitions

Observed adjacent pair counts are compared with permutation counts. Candidate transitions are selected by their observed minimum frequency; their p-values are therefore screening statistics rather than selection-adjusted confirmatory tests.

Reported statistics:

- observed count;
- null mean and standard deviation;
- empirical upper-tail permutation p-value;
- Z-score when reliable.

### 6.3 Recurrent formulas

Only formulas of length k ≥ 3 are reported, so pair transitions are not duplicated.

For each k, formulas meeting the observed minimum-count threshold are ranked within the tested candidate pool. Reported fields include observed count, observed share, null mean, enrichment ratio, empirical p-value, and a reliability-qualified Z-score. Because candidates are selected and ranked from the observed data, formula p-values are screening statistics without correction for selection or multiple testing.

### 6.4 Handling degenerate Monte-Carlo nulls

Long formulas may be absent from almost all random permutations. In such cases, a conventional Z-score can become artificially enormous or undefined.

The analysis therefore suppresses Z (`z_reliable = false`) unless both conditions hold:

- null SD ≥ 0.5;
- at least 3 distinct values occur in the null sample.

The empirical one-sided permutation p-value remains the primary statistic in these cases:

`p = (1 + number of null values at least as extreme as observed) / (1 + permutations)`

This prevents misleading values such as `Z = 499.9` while retaining a valid finite-sample significance statement.

### 6.5 Directed-network description

For each taam/node:

- successor and predecessor entropy;
- normalized entropy;
- degree;
- most probable successor and predecessor.

For retained edges:

- conditional probability;
- lift relative to independence;
- reverse count;
- directional asymmetry.

These are descriptive complements to the permutation tests.

### 6.6 Compact core

A prespecified 18-sign core is profiled in two forms:

`atnah`, `atnah_hafukh`, `darga`, `geresh`, `mahapakh`, `merkha`, `meteg`, `munah`, `paseq`, `pashta`, `qadma`, `revia`, `sof_pasuq`, `telisha_qetana`, `tevir`, `tipeha`, `zaqef_gadol`, `zaqef_qatan`.

`atnah_hafukh` is assigned to the same cadence/core functional class as `atnah`, while remaining a separately named event in all outputs.

- `core_projected`: non-core events are removed before connecting retained events;
- `core_adjacent`: only core-to-core pairs already adjacent in the original stream are retained.

Core coverage and both edge profiles are reported. The adjacent profile controls for artifacts introduced by projection.

## 7. Output structure

Each run creates one directory per book and combined `ALL_*.csv` files.

Principal outputs:

- `transition_permutation.csv`
- `ngram_entropy_permutation.csv`
- `ngram_formulas_permutation.csv`
- `transition_nodes.csv`
- `transition_edges.csv`
- `transition_top_successors.csv`
- `transition_top_predecessors.csv`
- `cadence_funnels.csv`
- `core_projected_nodes.csv`
- `core_projected_edges.csv`
- `core_adjacent_edges.csv`
- `taam_grammar_meta.json`

The run root contains the corresponding combined files prefixed by `ALL_` and `ALL_taam_grammar_meta.json`.

Each per-book metadata file records the input path and SHA256 hash, the full parameterization, event counts, core coverage, null-reliability rules, and compact result summaries. Reusing an output directory overwrites the fixed files generated for requested books; run directories must therefore remain uniquely named and must not be used to mix parameterizations.

## 8. Command-line interface

Required arguments:

- `--out_dir PATH`
- `--book TAG PATH` (repeat once per book; tags must be unique)

Run identity and stream controls:

- `--run_label LABEL` (default: `main`)
- `--exclude_external`
- `--exclude_taamim NAME[,NAME...]`
- `--core_nodes default|NAME[,NAME...]`

Permutation and n-gram controls:

- `--entropy_k K[,K...]` (default: `2,3,4,5,6`)
- `--formula_k K[,K...]` (default: `3,4,5,6`)
- `--transition_perm N` (default: `500`)
- `--formula_perm N` (default: `200`)
- `--seed N` (default: `1`)
- `--jobs N` (default: `1`)

Selection and reporting thresholds:

- `--min_transition_count N` (default: `20`)
- `--min_formula_count N` (default: `20`)
- `--formula_candidates N` (default: `250`)
- `--top_k N` (default: `50`)
- `--top_n N` (default: `10`)
- `--min_edge_count N` (default: `5`)
- `--min_prob P` (default: `0.0`)
- `--core_min_edge_count N` (default: `100`)
- `--core_min_prob P` (default: `0.15`)

The program rejects missing inputs, duplicate book tags, empty k-lists, invalid k values, permutation counts below 2, nonpositive count limits, jobs below 1, and probabilities outside `[0,1]`.

## 9. Interpretation rule

The entropy test is the principal confirmatory component. Transition and formula tables identify and quantify candidate structures; because candidates are selected from observed data, they require replication or a separately prespecified test for confirmatory use.

A central claim is supported only when the pattern:

1. appears in all five books;
2. is strong in MAIN;
3. remains qualitatively stable in both prespecified controls.

EXPLORE may identify additional formulas, but exploratory findings are not treated as confirmatory evidence without a separate prespecified test.

## 10. Runtime design

Each book is parsed once. All descriptive analyses use that same stream. Books are processed in parallel. Transition permutations and formula/entropy permutations are separately configurable because long-formula counting is the expensive step.
