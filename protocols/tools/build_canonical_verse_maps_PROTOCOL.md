# Protocol: Canonical Torah Verse Maps

## Purpose

Create verified sidecar maps that connect the frozen processed Torah word stream to canonical Sefaria chapter-and-verse references.

The processed `*_taamim_annotated.txt` files preserve the performance boundary marker `{sof_pasuq}`, but they do not retain the nested chapter/verse structure of the Sefaria API response. A `{sof_pasuq}` marker identifies a verse ending; by itself it does not encode the canonical chapter and verse number. This tool restores that reference layer without changing the processed corpus.

The maps are required only for outputs that report canonical verse coverage or canonical verse identifiers. Rhyme detection, burst construction, cadence alignment, permutations, and other inferential calculations do not derive their boundaries from these maps.

## Files and locations

Recommended repository locations:

```text
src/tools/build_canonical_verse_maps.py
run/build_canonical_verse_maps.bat
protocols/tools/build_canonical_verse_maps_PROTOCOL.md
data/data_processed/torah/*_taamim_annotated.txt.verse_map.json
```

The five generated maps are written next to their corresponding processed files. No `canonical_verse_maps` subdirectory is used in the repository.

## Required inputs

For each requested book, the generator requires:

1. the frozen processed file
   `data/data_processed/torah/{book}_taamim_annotated.txt`;
2. the frozen preprocessing implementation
   `src/preprocessing/preprocessing_phonetic_taamim_annotated.py`, exposing `build_torah(text)`;
3. a nested Sefaria response containing a Hebrew `he` chapter/verse array.

The nested response can be obtained in either of two ways:

- live retrieval from Sefaria when `--api-dir` is omitted; or
- a frozen `sefaria_{book}.json` response supplied through `--api-dir`.

## Source

- Provider: Sefaria API
- Endpoint: `https://www.sefaria.org/api/texts/{book}`
- Language parameter: `lang=he`
- Default requested Hebrew version: `Tanach_with_Ta'amei_Hamikra`
- Context, padding, and commentary: disabled

Chapter and verse numbers are the one-based positions of the corresponding arrays in the returned Hebrew `he` field. They are reference identifiers derived from the source structure, not inferred from `{sof_pasuq}` counts.

## Procedure

For each book, the generator:

1. loads the nested Sefaria response;
2. visits chapters and verses in source order;
3. processes each verse independently with the same `build_torah()` function used to produce the frozen corpus;
4. concatenates the processed verse token streams;
5. compares the complete reconstruction with the frozen processed book token for token;
6. stops for that book if any token or total stream length differs;
7. counts source words while excluding structural `{...}` markers;
8. records the zero-based half-open source-word span `[first, last)` for every canonical verse;
9. records source, version, integrity, and verification metadata;
10. writes `{book}_taamim_annotated.txt.verse_map.json` only after that book passes reconstruction validation.

The comparison includes lexical tokens and structural markers. It uses whitespace tokenization of the two streams; it is therefore a token-for-token identity check, not a claim of byte-for-byte identity between the Sefaria response and the processed file.

## Standard Windows run

From the repository root:

```bat
run\build_canonical_verse_maps.bat
```

The BAT invokes the equivalent of:

```text
py -3 src/tools/build_canonical_verse_maps.py \
  --processed-dir data/data_processed/torah \
  --preprocessor src/preprocessing/preprocessing_phonetic_taamim_annotated.py
```

This standard invocation downloads the nested responses from Sefaria and generates all five maps in `data/data_processed/torah`.

## Offline or frozen-source run

For stricter future reconstruction, preserve the complete nested API responses as:

```text
sefaria_genesis.json
sefaria_exodus.json
sefaria_leviticus.json
sefaria_numbers.json
sefaria_deuteronomy.json
```

Then run:

```text
py -3 src/tools/build_canonical_verse_maps.py \
  --api-dir PATH/TO/FROZEN_API_RESPONSES \
  --processed-dir data/data_processed/torah \
  --preprocessor src/preprocessing/preprocessing_phonetic_taamim_annotated.py
```

The ordinary rhyme-cadence analyses do not contact Sefaria. They read the committed, verified map sidecars offline.

## Output schema

Each map contains:

- schema version and book name;
- canonical reference system;
- requested and returned Hebrew-version metadata;
- API reference and response source;
- canonicalized SHA-256 of the complete API payload;
- processed filename and SHA-256 of its exact stored bytes;
- the reconstruction-verification flag;
- total canonical verse and source-word counts;
- one span record per canonical verse.

Each span record contains:

- `canonical_verse_ordinal` — one-based ordinal within the book;
- `chapter` and `verse` — one-based Sefaria array positions;
- `first_source_word_index` — zero-based inclusive word index;
- `last_source_word_index_exclusive` — zero-based exclusive word index;
- `source_word_count` — number of non-structural tokens in the verse.

## Frozen-corpus validation values

The verified corpus used for the current analysis produced:

| Book | Canonical verses | Source words |
|---|---:|---:|
| Genesis | 1,533 | 20,596 |
| Exodus | 1,210 | 16,701 |
| Leviticus | 859 | 11,945 |
| Numbers | 1,288 | 16,404 |
| Deuteronomy | 956 | 14,269 |

These are total map counts. Analysis-specific canonical-coverage denominators may be smaller because an analysis can exclude verses that are not fully represented after a left context window or another eligibility restriction.

## Failure behavior

The generator returns a non-zero exit status when:

- the preprocessor or a processed file is missing;
- a frozen API response is missing or malformed;
- a live request fails;
- the `he` field is not a chapter/verse array;
- a verse is not a string;
- reconstructed and frozen token streams differ.

Books are processed sequentially. If a later book fails, maps already validated and written for earlier books may remain; the entire run must not be treated as complete unless all five success lines and the BAT's final `DONE` message are present.

## Reproducibility and limitations

Sefaria is an external, mutable service. A successful live rerun proves that the retrieved nested response, the selected preprocessor, and the frozen processed corpus are mutually consistent at that time. It does not guarantee that the same API payload will remain available indefinitely.

For the research freeze, commit the five verified map sidecars together with the generator, BAT, processed files, preprocessing code, and this protocol. The committed maps make the published analysis repeatable without network access. Preserving the corresponding nested API JSON responses as immutable source artifacts would additionally permit exact regeneration of the maps if Sefaria later changes.

The maps identify canonical textual segments. They do not claim that canonical chapter/verse numbering is an original compositional division, and they do not replace cadence boundaries used by the analysis.

## Dependencies

- Python 3.9 or later
- `requests` for live Sefaria retrieval
- the repository's frozen phonetic/taamim preprocessor and processed Torah corpus
