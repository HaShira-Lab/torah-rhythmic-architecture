# Export Rhyme Groups Window — Tool v1.0.0

## Status and purpose

`export_rhyme_groups_window.py` is a qualitative inspection and example-export
tool. It is **not a statistical analysis** and does not produce inferential
evidence for the article.

The tool extracts compact, deduplicated rhyme groups from a selected window of
one Torah book. It is useful for:

1. inspecting concrete rhyme examples;
2. manually checking the executable rhyme protocol;
3. exporting traceable examples for notes, figures, or supplementary material;
4. diagnosing why particular written forms enter a `FULL` or `BRIDGE` group.

Recommended repository placement:

```text
src/tools/rhyme/export_rhyme_groups_window.py
run/export_rhyme_groups_window.bat
protocols/tools/EXPORT_RHYME_GROUPS_WINDOW.md
```

Recommended output root:

```text
results/tools/export_rhyme_groups_window
```

## Runtime dependency

The tool imports the frozen shared implementation:

```text
src/shared/rhyme/rhyme_protocol.py    protocol 4
```

The human-readable `RHYME_PROTOCOL_V4.md` is documentation and is not a runtime
dependency.

## Input validation

Input is one frozen `*_taamim_annotated.txt` corpus and its adjacent
`*.txt.meta.json`. The tool refuses to run when:

- the metadata file is absent;
- `output_sha256` is absent or malformed;
- the actual input SHA256 differs from `output_sha256`.

The run metadata records hashes of the corpus, input metadata, tool code,
shared rhyme implementation, and both substantive outputs.

## Verse numbering

The preprocessed corpus does not contain chapter identifiers. Therefore a
window is selected by a **one-based ordinal verse number within the book**, not
by canonical `chapter:verse` notation.

For example:

```text
--book genesis --start-verse-ordinal 1 --verse-count 30
```

means the first 30 sof-pasuq-delimited verses of Genesis. In output, `v12:w7`
means source-word position 7 in ordinal verse 12.

The backward-compatible alias `--start-verse` is accepted, but
`--start-verse-ordinal` is preferred.

## Rhyme protocol

The rhyme signature is extracted by the shared project protocol:

- primary signature: from the final stressed vowel through word end;
- if that vowel is the final segment, extend exactly one segment left;
- `STRICT` is the default and scientific baseline;
- optional equivalence profiles are inspection/sensitivity settings only;
- corpus multigraphs are `kh`, `sh`, and `ts`; `tsh` is `t + sh`.

Only tokens with an explicitly marked stressed vowel receive a rhyme
signature. Tokens lacking one are skipped and counted; the tool never guesses
or supplies stress.

Relations:

- `FULL`: primary↔primary equality;
- `BRIDGE`: primary↔bridge equality in either direction;
- bridge↔bridge equality is excluded;
- no transitive closure is applied across different keys.

`BRIDGE` output uses `OPEN` for primary-signature members and `CLOSED` for
bridge-signature members. These are display roles, not claims that all members
form one transitive equivalence class.

## Group filters

Defaults:

```text
equivalence_profile = STRICT
match_filter = ALL
min_distinct_words = 2
include_identical_only = false
```

`--min-distinct-words` applies to both `FULL` and `BRIDGE` groups. For a bridge
group it is evaluated on the union of OPEN and CLOSED written forms.

By default a `FULL` group containing only repeated occurrences of one written
form is omitted. `--include-identical-only` includes such groups. `BRIDGE`
groups always require at least one cross-written-form primary↔bridge relation.

## Usage

From the repository root on Windows:

```bat
run\export_rhyme_groups_window.bat --book genesis --start-verse-ordinal 1 --verse-count 30
```

The launcher supplies the standard source and output directories. All tool
options follow the launcher command. A more selective example is:

```bat
run\export_rhyme_groups_window.bat --book deuteronomy --start-verse-ordinal 100 --verse-count 20 --match-filter FULL --equivalence-profile STRICT
```

Direct Python use:

```bat
set PYTHONPATH=src
python src\tools\rhyme\export_rhyme_groups_window.py ^
  --source-dir data\data_processed\torah ^
  --out-dir results\tools\export_rhyme_groups_window ^
  --book genesis ^
  --start-verse-ordinal 1 ^
  --verse-count 30
```

Use `--help` for the full CLI.

## Outputs

For each run the tool writes:

1. `*_rhyme_groups.txt` — compact human-readable group list;
2. `*_rhyme_groups.tsv` — machine-readable member rows, counts, and exact
   ordinal-verse/source-word locations;
3. `*_rhyme_groups.metadata.json` — parameters, protocol configuration, input
   verification, audit counts, runtime details, code hashes, and output hashes.

The `.txt` and `.tsv` files are deterministic for a fixed input, shared
protocol, tool version, and CLI. Metadata includes a creation timestamp and
runtime paths, so the metadata file itself is not expected to be byte-identical
across machines.

## Interpretation limits

The exported number or size of groups must not be treated as a significance
test. It depends on the selected book window, window length, lexical repetition,
minimum-group filter, match filter, and equivalence profile.

For inferential claims about local rhyme enrichment, burst clustering, and
alignment with taam boundaries, use `rhyme_burst_architecture.py`. For the
internal positional profile of activity inside taam segments, use
`burst_profile_inside_taam_hierarchy.py`.
