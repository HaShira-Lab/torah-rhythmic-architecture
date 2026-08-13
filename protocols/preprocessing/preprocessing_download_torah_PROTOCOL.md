# Protocol: Torah Source Download

## Purpose

Download the Hebrew text of the five Torah books from one explicitly requested Sefaria version and preserve basic provenance and integrity metadata for the raw dataset.

This is a source-acquisition tool. It does not perform phonetic preprocessing, transliteration, taam parsing, or textual normalization beyond the whitespace handling specified below.

## Source

- Provider: Sefaria API
- Endpoint: `https://www.sefaria.org/api/texts/{book}`
- Language parameter: `lang=he`
- Default Hebrew version: `Tanach_with_Ta'amei_Hamikra`
- Context, padding, and commentary: disabled

The requested version is sent through the API parameter `vhe`. The manifest records both the requested version and, when exposed by the API response, the returned Hebrew version title. `version_check` is recorded as `match`, `mismatch`, or `not_reported`; comparison ignores case, spaces, underscores, and punctuation. `not_reported` is not treated as proof of a version mismatch.

## Books

The default corpus is:

- Genesis
- Exodus
- Leviticus
- Numbers
- Deuteronomy

`--books` may be used to run a specified subset or ordering.

## Procedure

For each requested book, the script:

1. sends an independent API request;
2. requires a Hebrew `he` field in the JSON response;
3. recursively flattens nested arrays while preserving source order;
4. retains string leaves only;
5. removes leading and trailing whitespace from each segment;
6. omits segments that are empty after this cleanup;
7. joins the retained segments with one LF newline;
8. writes UTF-8 text without a byte-order mark;
9. computes SHA-256 over the exact UTF-8 bytes represented by the written text.

No Unicode normalization, niqqud removal, taam removal, punctuation filtering, tokenization, or orthographic correction is performed.

## Command-line interface

```text
python download_torah.py \
  --books Genesis Exodus Leviticus Numbers Deuteronomy \
  --version-name "Tanach_with_Ta'amei_Hamikra" \
  --outdir data/data_raw/torah
```

Arguments:

- `--outdir DIR` — required output directory.
- `--books BOOK [BOOK ...]` — requested books; defaults to all five Torah books.
- `--version-name NAME` — Sefaria Hebrew version title or slug; defaults to `Tanach_with_Ta'amei_Hamikra`.

## Outputs

The output directory contains:

- `{book}_raw.txt` — one UTF-8 source file per successfully downloaded book;
- `download_summary.csv` — one compact result row per requested book;
- `download_manifest.json` — run-level provenance plus the complete per-book result records.

Per-book metadata include status, filename, retained segment count, character count, SHA-256, requested version, returned version when reported, version-reporting status, final request URL, and any error.

Run-level metadata include schema version, script name, source and endpoint, requested version, UTC start and finish times, resolved output directory, requested books, and success/error totals.

The CSV uses UTF-8 with BOM for convenient opening in spreadsheet software. JSON and raw text use UTF-8 without BOM.

## Failure behavior

A failed book is recorded with `status=error`; processing continues with the remaining books. The script writes both metadata files after all attempts and returns exit code `1` if any requested book failed. It returns `0` only when every requested book succeeded.

HTTP failures, invalid JSON, a missing `he` field, and empty Hebrew content are treated as failures. Existing output files with the same names are overwritten; unrelated files in the output directory are left unchanged.

## Reproducibility and limitations

Sefaria is an external, mutable service. The requested version name, returned version title when available, final source URL, retrieval timestamps, and SHA-256 hashes provide an audit trail but do not make a later download intrinsically immutable. Freeze releases should retain the downloaded raw files together with their manifest and summary.

The API's flattened segment structure is preserved only as ordered line-separated text; chapter/verse nesting is not retained as separate metadata by this downloader.

## Dependency

- Python 3.9 or later
- `requests`
