# Torah Rhythmic Architecture

Reproducible computational analyses of *taamim*, temporal organization, hierarchical segmentation, and rhyme architecture in the Torah.

This repository contains the frozen computational core of an ongoing HaShira-Lab research project. It provides source acquisition, deterministic phonetic/taam preprocessing, analysis code, human-readable protocols, Windows launchers, integrity metadata, and selected results. Article-specific figures and their generation scripts will be added separately.

## Scope

The project investigates whether the Torah's accentual and phonetic streams exhibit recurrent local and hierarchical organization that can be measured computationally. The repository does not attempt to reconstruct a melody, and its transliteration is a declared computational model rather than a complete reconstruction of historical Tiberian pronunciation.

The frozen analyses currently cover:

| Analysis | Question | Standard launcher |
|---|---|---|
| Taam grammar | Which transitions and longer taam formulas recur beyond shuffled-order expectations? | `run/taam_grammar_MAIN_all_books.bat` |
| Taam temporal structure | How are accent events and interval/segment shapes organized in local temporal units? | `run/taam_temporal_structure_MAIN_all_books.bat` |
| Taam hierarchical structure | What compositional relations hold among minor, major, and verse units? | `run/taam_hierarchical_structure_MAIN_all_books.bat` |
| Taam boundary reconstruction | Can hidden minor boundaries be reconstructed from taam context and major-unit geometry? | `run/taam_boundary_reconstruction_MAIN_all_books.bat` |
| Rhyme burst architecture | Are local rhyme arrivals enriched, temporally clustered, and aligned with taam boundaries? | `run/rhyme_burst_architecture_MAIN_all_books.bat` |
| Burst profile inside the taam hierarchy | How is rhyme-arrival activity distributed inside minor, major, and verse segments? | `run/burst_profile_inside_taam_hierarchy_MAIN_all_books.bat` |

Each analysis also has `CONTROLS` and `EXPLORE` launchers. The corresponding protocol defines which run is confirmatory, which controls are required, and which exploratory settings must not be merged with the main result.

## Repository layout

```text
data/
  data_raw/torah/          downloaded pointed Hebrew source snapshot
  data_processed/torah/    canonical phonetic stream with taam annotations
protocols/                 preprocessing, shared, analysis, and tool protocols
results/                   tracked compact outputs and run metadata
run/                       Windows launchers
src/
  preprocessing/           source acquisition and deterministic preprocessing
  shared/rhyme/            executable shared rhyme protocol
  analyses/core_taam/      taam analyses
  analyses/core_rhyme/     rhyme analyses
  tools/rhyme/             qualitative example-export utility
```

## Corpus and provenance

The raw corpus was retrieved through the Sefaria API using the Hebrew version `Tanach_with_Ta'amei_Hamikra`. Sefaria identifies this version as **Tanach with Ta'amei Hamikra**, gives `tanach.us` as its source, credits Sefaria for digitization, and marks the version **Public Domain**.

The exact request information, returned version title, source URLs, retrieval timestamps, and SHA-256 hashes are retained in:

```text
data/data_raw/torah/download_manifest.json
data/data_raw/torah/download_summary.csv
```

Every processed book has an adjacent `.meta.json` file recording its input and output SHA-256. Downstream analyses verify the processed input hash before computation. See [`NOTICE`](NOTICE) for attribution and licensing boundaries.

## Requirements

- Windows for the supplied `.bat` launchers
- Python 3.9 or later
- `requests` for source download

Install the declared dependency from the repository root:

```bat
python -m pip install -r requirements.txt
```

All frozen analyses and phonetic preprocessing use only the Python standard library; `requests` is needed only by `src/preprocessing/download_torah.py`.

## Reproducing the workflow

Run commands from the repository root. The launchers resolve repository-relative paths themselves.

To reacquire the raw source and regenerate the canonical processed corpus:

```bat
run\preprocessing_download_torah.bat
run\preprocessing_phonetic_taamim_annotated.bat
```

Reacquisition is not guaranteed to reproduce the frozen raw bytes because Sefaria is an external mutable service. Compare all regenerated hashes with the retained manifest and metadata before replacing the frozen corpus.

Run an analysis using its `MAIN` launcher, for example:

```bat
run\taam_grammar_MAIN_all_books.bat
run\rhyme_burst_architecture_MAIN_all_books.bat
```

Read the matching file under `protocols/` before interpreting any output. Main, control, and exploratory results have distinct inferential roles.

## Results policy

The repository tracks run metadata and compact scientific outputs, including summaries, statistics, profiles, frequency tables, transition/ngram tables, and validation tables.

Large row-level inventories and streams are reproducible and intentionally excluded from Git by `.gitignore`, including arrival streams, segment inventories, complete segment/relationship tables, interval examples, per-position reconstruction predictions, and burst inventories. Running the launchers locally regenerates them in their normal `results/` locations. Full frozen outputs may later be deposited as a versioned external research archive.

Because result metadata can record hashes for both tracked and intentionally untracked outputs, absence of a row-level file from Git does not mean that it was absent from the original run.

## Rhyme protocol

The executable shared rhyme implementation is:

```text
src/shared/rhyme/rhyme_protocol.py
```

The human-readable specification is:

```text
protocols/shared/RHYME_PROTOCOL.md
```

In brief, a rhyme signature begins at the final stressed vowel and continues to word end. If that vowel is the final phonetic segment, the signature extends one segment to the left. `FULL` and non-transitive `BRIDGE` matches remain distinct, and optional equivalence profiles are exploratory unless a protocol explicitly states otherwise.

## Citation

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). Until a versioned archival release and article are available, cite the repository and the specific commit used.

## Licensing

- Code under `src/` and `run/`: [MIT License](LICENSE).
- Project-authored protocols and generated result tables: [CC BY 4.0](LICENSE-DATA).
- Source Torah text: Public Domain according to the Sefaria version record; provenance is preserved in [`NOTICE`](NOTICE) and the download metadata.

Third-party names and trademarks are not covered by these grants. No affiliation with or endorsement by Sefaria or `tanach.us` is implied.
