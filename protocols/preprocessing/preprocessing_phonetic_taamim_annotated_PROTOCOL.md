# Protocol: Phonetic Transliteration with Taam Annotation

## Purpose

Convert pointed Hebrew Torah source files into the canonical phonetic stream used by the `torah-rhythmic-architecture` analyses. The output preserves word order, phonetic vowels, accent placement, in-word taamim, and the external separators `paseq` and `sof_pasuq`.

This is deterministic preprocessing, not an analysis.

## Inputs

- Directory: `data/data_raw/torah/`
- File pattern: `*_raw.txt`
- Encoding: UTF-8 (a BOM is accepted)
- Expected content: fully pointed Hebrew Torah text with cantillation marks

The batch launcher processes every `.txt` file in the input directory. The downloader's chapter/verse numbers and bracketed or parenthetical reference labels are treated as source scaffolding, not textual content.

## Cleaning and tokenization

The script performs these operations in order:

1. Normalize the input to Unicode NFC and remove an initial BOM.
2. Replace maqaf (`־`, U+05BE) with a word boundary.
3. Remove bracketed text `[...]` and parenthetical text `(...)`.
4. Remove decimal digits.
5. Collapse whitespace.
6. Transliterate each remaining pointed Hebrew token.

Unpointed Hebrew tokens are not emitted. The following non-phonemic masoretic marks are ignored and counted separately in metadata: `MASORA CIRCLE` (`֯`, U+05AF), `RAFE` (`ֿ`, U+05BF), and `UPPER DOT` (`ׄ`, U+05C4). Rafe confirms the absence of dagesh but creates no additional segment. Upper dot is an extraordinary masoretic annotation, not a taam or stress mark. Any other unsupported Hebrew combining mark stops the run instead of disappearing silently.

## Canonical phonetic model

### Vowels

| Hebrew sign | Unicode | Output |
|---|---:|---|
| ֱ hataf segol | U+05B1 | `e` |
| ֲ hataf patah | U+05B2 | `a` |
| ֳ hataf qamats | U+05B3 | `a` |
| ִ hiriq | U+05B4 | `i` |
| ֵ tsere | U+05B5 | `e` |
| ֶ segol | U+05B6 | `e` |
| ַ patah | U+05B7 | `a` |
| ָ qamats | U+05B8 | `a` |
| ֹ holam | U+05B9 | `o` |
| ֺ holam haser for vav | U+05BA | `o` |
| ֻ qubuts | U+05BB | `u` |
| ׇ qamats qatan | U+05C7 | `o` |

Shureq is `u`. Consonantal vav is `v`; mater vav with holam or shureq has no additional `v`. Yod is `y` when consonantal and may act as a vowel carrier. The script applies the project's established contextual sheva rules; it does not claim to reconstruct every historical Tiberian phonetic distinction.

### Consonants and special forms

Begadkefat distinctions retained by the model are `b/v`, `k/kh`, and `p/f`. Shin is `sh`; sin is `s`; tsadi is `ts`; qof is `q`; het is `h`; tav is `t`. Alef and ayin are vowel carriers and are not independently written. Word-final he is silent. Final letters are normalized to their base letters internally.

The Divine Names are normalized as follows when their consonantal spelling matches:

- יהוה → `adonai`
- אלהים / אלוהים → `elohim`

If an accent is present, the acute mark is assigned to the final vowel of these normalized forms.

## Stress assignment

Every in-word taam and meteg creates an accent event. Stress is encoded by COMBINING ACUTE ACCENT (`◌́`, U+0301) after the selected Latin vowel.

For a taam attached to Hebrew unit `i`, the target nucleus is selected in this order:

1. a vowel preceding the taam on the same Hebrew letter;
2. the following vocalic carrier (`א`, `ע`, `י`, or `ו`) when it bears the relevant vowel;
3. the next vocalic unit when the sign is attached to a silent carrier;
4. the nearest preceding vowel;
5. the next available vocalic unit.

If several accent marks resolve to the same Latin segment, only one acute mark is emitted. `ATNAH HAFUKH` follows exactly the same stress-targeting logic as ordinary `ATNAH`.

## Taam annotation

In-word signs are appended to the word in square brackets, in source order:

`phonetic_word[taam1,taam2,...]`

External signs are emitted as separate tokens in braces and do not create stress:

- `{paseq}`
- `{sof_pasuq}`

These brace tokens are boundaries, not words. No commas, periods, or other visible punctuation are generated.

### Complete sign inventory

| Sign | Unicode | Data name | Treatment |
|---|---:|---|---|
| ֑ | U+0591 | `atnah` | in-word accent |
| ֒ | U+0592 | `segol` | in-word accent |
| ֓ | U+0593 | `shalshelet` | in-word accent |
| ֔ | U+0594 | `zaqef_qatan` | in-word accent |
| ֕ | U+0595 | `zaqef_gadol` | in-word accent |
| ֖ | U+0596 | `tipeha` | in-word accent |
| ֗ | U+0597 | `revia` | in-word accent |
| ֘ | U+0598 | `zarqa` | in-word accent |
| ֙ | U+0599 | `pashta` | in-word accent |
| ֚ | U+059A | `yetiv` | in-word accent |
| ֛ | U+059B | `tevir` | in-word accent |
| ֜ | U+059C | `geresh` | in-word accent |
| ֝ | U+059D | `geresh_muqdam` | in-word accent |
| ֞ | U+059E | `gershayim` | in-word accent |
| ֟ | U+059F | `qarney_para` | in-word accent |
| ֠ | U+05A0 | `telisha_gedola` | in-word accent |
| ֡ | U+05A1 | `pazer` | in-word accent |
| ֢ | U+05A2 | `atnah_hafukh` | in-word accent; same stress function as `atnah` |
| ֣ | U+05A3 | `munah` | in-word accent |
| ֤ | U+05A4 | `mahapakh` | in-word accent |
| ֥ | U+05A5 | `merkha` | in-word accent |
| ֦ | U+05A6 | `merkha_kefula` | in-word accent |
| ֧ | U+05A7 | `darga` | in-word accent |
| ֨ | U+05A8 | `qadma` | in-word accent |
| ֩ | U+05A9 | `telisha_qetana` | in-word accent |
| ֪ | U+05AA | `yerah_ben_yomo` | in-word accent |
| ֫ | U+05AB | `ole` | in-word accent |
| ֬ | U+05AC | `iluy` | in-word accent |
| ֭ | U+05AD | `dehi` | in-word accent |
| ֮ | U+05AE | `zinor` | in-word accent |
| ֽ | U+05BD | `meteg` | in-word accent |
| ׀ | U+05C0 | `paseq` | external separator; no stress |
| ׃ | U+05C3 | `sof_pasuq` | external verse boundary; no stress |

U+05AF is intentionally absent from the taam inventory because it is `MASORA CIRCLE`, not a cantillation sign.

## CLI and batch run

Direct invocation:

```bat
py -3 src\preprocessing\preprocessing_phonetic_taamim_annotated.py INPUT.txt OUTPUT.txt
```

Standard repository run:

```bat
run\preprocessing_phonetic_taamim_annotated.bat
```

The launcher resolves all paths relative to its own location, so it may be called from any current directory.

## Outputs

For each input book:

- `data/data_processed/torah/<book>_taamim_annotated.txt`
- `data/data_processed/torah/<book>_taamim_annotated.txt.meta.json`

The text output is a single UTF-8-with-BOM whitespace-delimited stream. Metadata records the schema version, vowel policy, annotation format, validation counts, UTC timestamp, and SHA-256 hashes of both input and output.

Console `WORDS` excludes all brace-delimited external tokens.

## Reproducibility constraints

- The five raw source files and their hashes define the textual source snapshot.
- The output depends on this exact protocol and script version.
- Regenerating processed files after a code or source change requires regenerating their metadata as well.
- Downstream parsers must distinguish square-bracket in-word annotations from brace-delimited external events.

## Dependencies

Only the Python standard library is used. No line is added to `requirements.txt` for this package.

## Limitations

The transliteration is a declared project model designed for consistent computational comparison. It is not a full diplomatic transcription, a complete reconstruction of Tiberian pronunciation, or a melodic interpretation of the taamim.
