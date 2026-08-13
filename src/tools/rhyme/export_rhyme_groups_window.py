#!/usr/bin/env python3
"""Export compact rhyme groups for one ordinal-verse window of a Torah book.

This is a qualitative inspection and example-export utility, not a statistical
analysis. Rhyme signatures and FULL/BRIDGE decisions come from the shared
project rhyme protocol.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import shared.rhyme.rhyme_protocol as shared_rhyme_module  # type: ignore
from shared.rhyme import (  # type: ignore
    ProtocolConfig,
    RhymeProtocolError,
    RhymeSignature,
    available_equivalence_profiles,
    extract_rhyme_signature,
    normalize_profile_name,
)

TOOL_NAME = "export_rhyme_groups_window"
TOOL_VERSION = "1.0.0"
SHARED_RHYME_PROTOCOL_VERSION = "4"

SOF = "sof_pasuq"
MATCH_FILTERS = ("ALL", "FULL", "BRIDGE")
BOOK_FILES = {
    "genesis": "genesis_taamim_annotated.txt",
    "exodus": "exodus_taamim_annotated.txt",
    "leviticus": "leviticus_taamim_annotated.txt",
    "numbers": "numbers_taamim_annotated.txt",
    "deuteronomy": "deuteronomy_taamim_annotated.txt",
}
ALIASES = {
    "gen": "genesis", "genesis": "genesis",
    "ex": "exodus", "exo": "exodus", "exodus": "exodus",
    "lev": "leviticus", "leviticus": "leviticus",
    "num": "numbers", "numbers": "numbers",
    "deut": "deuteronomy", "deuteronomy": "deuteronomy",
}
ANNOT_RE = re.compile(r"^(.*?)(?:\[([^\]]+)\])?$")
MARKER_RE = re.compile(r"^\{([^}]+)\}$")


@dataclass(frozen=True)
class SourceWord:
    verse_ordinal: int
    word_position: int
    source_token: str


@dataclass(frozen=True)
class Occurrence:
    verse_ordinal: int
    word_position: int
    source_token: str
    signature: RhymeSignature

    @property
    def location(self) -> str:
        return f"v{self.verse_ordinal}:w{self.word_position}"


@dataclass(frozen=True)
class GroupRow:
    group_id: str
    group_type: str
    normalized_key: str
    display_rhyme: str
    role: str
    word: str
    count: int
    locations: tuple[str, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_book(value: str) -> str:
    key = value.casefold().strip()
    if key not in ALIASES:
        raise argparse.ArgumentTypeError(f"Unknown book: {value}")
    return ALIASES[key]


def normalize_match_filter(value: str) -> str:
    normalized = value.upper().strip()
    if normalized not in MATCH_FILTERS:
        raise argparse.ArgumentTypeError(
            f"Unknown match filter {value!r}. Allowed: {', '.join(MATCH_FILTERS)}"
        )
    return normalized


def validate_input(source: Path) -> dict[str, object]:
    metadata_path = source.with_name(source.name + ".meta.json")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Missing input metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    expected = metadata.get("output_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError(f"Invalid output_sha256 in {metadata_path}")
    actual = sha256_file(source)
    if actual.casefold() != expected.casefold():
        raise ValueError(
            f"Input SHA256 mismatch for {source}: expected {expected}, got {actual}"
        )
    return {
        "source_file": str(source),
        "source_sha256": actual,
        "metadata_file": str(metadata_path),
        "metadata_sha256": sha256_file(metadata_path),
        "metadata_schema_version": metadata.get("schema_version"),
        "verified_against_output_sha256": True,
    }


def read_verses(path: Path) -> tuple[list[list[SourceWord]], dict[str, int]]:
    verses: list[list[SourceWord]] = []
    current: list[SourceWord] = []
    source_word_tokens = 0
    structural_markers = 0
    orphan_sof_markers = 0
    verse_ordinal = 1

    for source_token in path.read_text(encoding="utf-8-sig").split():
        marker_match = MARKER_RE.fullmatch(source_token)
        if marker_match:
            structural_markers += 1
            marker = marker_match.group(1).strip().casefold()
            if marker == SOF:
                if current:
                    verses.append(current)
                    current = []
                    verse_ordinal += 1
                else:
                    orphan_sof_markers += 1
            continue

        match = ANNOT_RE.fullmatch(source_token)
        if not match or not match.group(1):
            raise ValueError(f"Unparseable source token in {path}: {source_token!r}")
        source_word_tokens += 1
        current.append(SourceWord(
            verse_ordinal=verse_ordinal,
            word_position=len(current) + 1,
            source_token=source_token,
        ))

    trailing_without_sof = int(bool(current))
    if current:
        verses.append(current)

    return verses, {
        "source_word_tokens": source_word_tokens,
        "structural_markers": structural_markers,
        "orphan_sof_markers": orphan_sof_markers,
        "trailing_verse_without_sof_pasuq": trailing_without_sof,
        "verse_ordinals": len(verses),
    }


def build_occurrences(
    verses: Iterable[list[SourceWord]],
    *,
    config: ProtocolConfig,
) -> tuple[list[Occurrence], int]:
    occurrences: list[Occurrence] = []
    missing_stress = 0
    for verse in verses:
        for item in verse:
            try:
                signature = extract_rhyme_signature(item.source_token, config=config)
            except RhymeProtocolError as exc:
                if not str(exc).startswith("No stressed vowel found"):
                    raise
                signature = None
            if signature is None:
                missing_stress += 1
                continue
            occurrences.append(Occurrence(
                verse_ordinal=item.verse_ordinal,
                word_position=item.word_position,
                source_token=item.source_token,
                signature=signature,
            ))
    return occurrences, missing_stress


def stable_counter_display(counter: Counter[str]) -> str:
    return ", ".join(
        word if count == 1 else f"{word} ×{count}"
        for word, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    )


def stable_mode(counter: Counter[str]) -> str:
    if not counter:
        return "-"
    return min(counter, key=lambda value: (-counter[value], value))


def count_total(counter: Counter[str]) -> int:
    return sum(counter.values())


def occurrence_index(
    occurrences: Sequence[Occurrence],
    *,
    role: str,
) -> dict[str, dict[str, list[Occurrence]]]:
    result: dict[str, dict[str, list[Occurrence]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for occurrence in occurrences:
        if role == "primary":
            key = occurrence.signature.primary_key
        elif role == "bridge":
            key = occurrence.signature.bridge_key
            if key is None:
                continue
        else:
            raise ValueError(f"Unknown role: {role}")
        result[key][occurrence.signature.word].append(occurrence)
    return result


def build_groups(
    occurrences: Sequence[Occurrence],
    *,
    match_filter: str,
    min_distinct_words: int,
    include_identical_only: bool,
) -> tuple[
    list[tuple[str, Counter[str]]],
    list[tuple[str, Counter[str], Counter[str]]],
    dict[str, Counter[str]],
    dict[str, Counter[str]],
    dict[str, dict[str, list[Occurrence]]],
    dict[str, dict[str, list[Occurrence]]],
]:
    primary_occurrences = occurrence_index(occurrences, role="primary")
    bridge_occurrences = occurrence_index(occurrences, role="bridge")
    primary_words = {
        key: Counter({word: len(items) for word, items in words.items()})
        for key, words in primary_occurrences.items()
    }
    bridge_words = {
        key: Counter({word: len(items) for word, items in words.items()})
        for key, words in bridge_occurrences.items()
    }
    primary_raws: dict[str, Counter[str]] = defaultdict(Counter)
    bridge_raws: dict[str, Counter[str]] = defaultdict(Counter)
    for occurrence in occurrences:
        signature = occurrence.signature
        primary_raws[signature.primary_key][signature.primary_raw] += 1
        if signature.bridge_key is not None and signature.bridge_raw is not None:
            bridge_raws[signature.bridge_key][signature.bridge_raw] += 1

    full_groups: list[tuple[str, Counter[str]]] = []
    if match_filter in {"ALL", "FULL"}:
        for key, words in primary_words.items():
            qualifies = len(words) >= min_distinct_words
            if include_identical_only and count_total(words) >= 2:
                qualifies = True
            if qualifies:
                full_groups.append((key, words))
        full_groups.sort(
            key=lambda item: (-len(item[1]), -count_total(item[1]), item[0])
        )

    bridge_groups: list[tuple[str, Counter[str], Counter[str]]] = []
    if match_filter in {"ALL", "BRIDGE"}:
        for key in sorted(set(primary_words) & set(bridge_words)):
            open_words = primary_words[key]
            closed_words = bridge_words[key]
            distinct_union = set(open_words) | set(closed_words)
            has_cross_form_relation = any(
                open_word != closed_word
                for open_word in open_words
                for closed_word in closed_words
            )
            if has_cross_form_relation and len(distinct_union) >= min_distinct_words:
                bridge_groups.append((key, open_words, closed_words))
        bridge_groups.sort(key=lambda item: (
            -len(set(item[1]) | set(item[2])),
            -(count_total(item[1]) + count_total(item[2])),
            item[0],
        ))

    return (
        full_groups,
        bridge_groups,
        primary_raws,
        bridge_raws,
        primary_occurrences,
        bridge_occurrences,
    )


def group_rows(
    full_groups: Sequence[tuple[str, Counter[str]]],
    bridge_groups: Sequence[tuple[str, Counter[str], Counter[str]]],
    primary_raws: dict[str, Counter[str]],
    bridge_raws: dict[str, Counter[str]],
    primary_occurrences: dict[str, dict[str, list[Occurrence]]],
    bridge_occurrences: dict[str, dict[str, list[Occurrence]]],
) -> list[GroupRow]:
    rows: list[GroupRow] = []
    for index, (key, words) in enumerate(full_groups, 1):
        raw = stable_mode(primary_raws[key])
        for word, count in sorted(words.items(), key=lambda item: (-item[1], item[0])):
            rows.append(GroupRow(
                group_id=f"F{index:03d}",
                group_type="FULL",
                normalized_key=key,
                display_rhyme=raw,
                role="primary",
                word=word,
                count=count,
                locations=tuple(item.location for item in primary_occurrences[key][word]),
            ))
    for index, (key, open_words, closed_words) in enumerate(bridge_groups, 1):
        display = f"{stable_mode(primary_raws[key])} ↔ {stable_mode(bridge_raws[key])}"
        for role, words, index_map in (
            ("open_primary", open_words, primary_occurrences),
            ("closed_bridge", closed_words, bridge_occurrences),
        ):
            for word, count in sorted(words.items(), key=lambda item: (-item[1], item[0])):
                rows.append(GroupRow(
                    group_id=f"B{index:03d}",
                    group_type="BRIDGE",
                    normalized_key=key,
                    display_rhyme=display,
                    role=role,
                    word=word,
                    count=count,
                    locations=tuple(item.location for item in index_map[key][word]),
                ))
    return rows


def write_text(
    path: Path,
    *,
    book: str,
    start_verse: int,
    end_verse: int,
    profile: str,
    match_filter: str,
    occurrences: Sequence[Occurrence],
    missing_stress: int,
    min_distinct_words: int,
    include_identical_only: bool,
    full_groups: Sequence[tuple[str, Counter[str]]],
    bridge_groups: Sequence[tuple[str, Counter[str], Counter[str]]],
    primary_raws: dict[str, Counter[str]],
    bridge_raws: dict[str, Counter[str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as out:
        out.write("RHYME GROUPS — QUALITATIVE INSPECTION\n")
        out.write(f"tool version: {TOOL_VERSION}\n")
        out.write(f"book: {book}\n")
        out.write(f"ordinal verse window: {start_verse}-{end_verse}\n")
        out.write(f"equivalence profile: {profile}\n")
        out.write(f"match filter: {match_filter}\n")
        out.write(f"minimum distinct written forms: {min_distinct_words}\n")
        out.write(f"identical-only FULL groups included: {str(include_identical_only).lower()}\n")
        out.write(f"analyzable stressed occurrences: {len(occurrences)}\n")
        out.write(f"word tokens without explicit stressed vowel: {missing_stress}\n")
        out.write(f"FULL groups shown: {len(full_groups)}\n")
        out.write(f"BRIDGE groups shown: {len(bridge_groups)}\n")
        out.write("\nThis export is descriptive and is not an inferential analysis.\n")
        out.write("A location such as v12:w7 means ordinal verse 12, source-word 7.\n")
        out.write("FULL = primary↔primary. BRIDGE = primary↔bridge.\n")
        out.write("BRIDGE↔BRIDGE and transitive closure are not counted.\n")
        out.write("word ×N means N occurrences of the same written form.\n")

        if match_filter in {"ALL", "FULL"}:
            out.write("\n\nFULL RHYME GROUPS\n")
            out.write("=" * 96 + "\n")
            if not full_groups:
                out.write("(none)\n")
            for index, (key, words) in enumerate(full_groups, 1):
                out.write(
                    f"F{index:03d}  rhyme={stable_mode(primary_raws[key])}  "
                    f"different_words={len(words)}  occurrences={count_total(words)}\n"
                )
                out.write(f"      {stable_counter_display(words)}\n")

        if match_filter in {"ALL", "BRIDGE"}:
            out.write("\n\nBRIDGE RHYME GROUPS\n")
            out.write("=" * 96 + "\n")
            if not bridge_groups:
                out.write("(none)\n")
            for index, (key, open_words, closed_words) in enumerate(bridge_groups, 1):
                distinct = len(set(open_words) | set(closed_words))
                out.write(
                    f"B{index:03d}  rhyme={stable_mode(primary_raws[key])} ↔ "
                    f"{stable_mode(bridge_raws[key])}  different_words={distinct}  "
                    f"role_memberships={count_total(open_words) + count_total(closed_words)}\n"
                )
                out.write(f"      OPEN:   {stable_counter_display(open_words)}\n")
                out.write(f"      CLOSED: {stable_counter_display(closed_words)}\n")


def write_tsv(path: Path, rows: Sequence[GroupRow], *, profile: str, match_filter: str) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "equivalence_profile", "match_filter", "group_id", "group_type",
            "normalized_key", "display_rhyme", "role", "word", "count",
            "locations",
        ])
        for row in rows:
            writer.writerow([
                profile, match_filter, row.group_id, row.group_type,
                row.normalized_key, row.display_rhyme, row.role, row.word,
                row.count, ",".join(row.locations),
            ])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--book", required=True, type=normalize_book)
    parser.add_argument(
        "--start-verse-ordinal", "--start-verse",
        dest="start_verse_ordinal", type=int, default=1,
        help="One-based ordinal verse within the book (not chapter:verse).",
    )
    parser.add_argument("--verse-count", type=int, default=30)
    parser.add_argument("--min-distinct-words", type=int, default=2)
    parser.add_argument(
        "--include-identical-only",
        action="store_true",
        help="Also show FULL groups containing only one repeated written form.",
    )
    parser.add_argument(
        "--equivalence-profile",
        default="STRICT",
        type=normalize_profile_name,
        choices=available_equivalence_profiles(),
        help="Named shared-protocol segment-equivalence profile.",
    )
    parser.add_argument(
        "--match-filter",
        type=normalize_match_filter,
        default="ALL",
        help="ALL, FULL, or BRIDGE.",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.start_verse_ordinal < 1:
        parser.error("--start-verse-ordinal must be >= 1")
    if args.verse_count < 1:
        parser.error("--verse-count must be >= 1")
    if args.min_distinct_words < 1:
        parser.error("--min-distinct-words must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source = args.source_dir / BOOK_FILES[args.book]
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")
    input_audit = validate_input(source)

    all_verses, source_audit = read_verses(source)
    start_index = args.start_verse_ordinal - 1
    if start_index >= len(all_verses):
        raise ValueError(
            f"--start-verse-ordinal exceeds book length ({len(all_verses)})"
        )
    end_index = min(start_index + args.verse_count, len(all_verses))
    selected = all_verses[start_index:end_index]

    # Missing-stress tokens are never assigned an inferred stress. They are
    # omitted exactly as in the project's stressed-token rhyme analyses.
    profile = normalize_profile_name(args.equivalence_profile)
    config = ProtocolConfig.from_profile(profile, require_stress=False)
    occurrences, missing_stress = build_occurrences(selected, config=config)
    (
        full_groups,
        bridge_groups,
        primary_raws,
        bridge_raws,
        primary_occurrences,
        bridge_occurrences,
    ) = build_groups(
        occurrences,
        match_filter=args.match_filter,
        min_distinct_words=args.min_distinct_words,
        include_identical_only=args.include_identical_only,
    )
    rows = group_rows(
        full_groups,
        bridge_groups,
        primary_raws,
        bridge_raws,
        primary_occurrences,
        bridge_occurrences,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{args.book}_v{args.start_verse_ordinal}-{end_index}"
        f"_{profile}_{args.match_filter}_rhyme_groups"
    )
    txt_path = args.out_dir / f"{stem}.txt"
    tsv_path = args.out_dir / f"{stem}.tsv"
    metadata_path = args.out_dir / f"{stem}.metadata.json"

    write_text(
        txt_path,
        book=args.book,
        start_verse=args.start_verse_ordinal,
        end_verse=end_index,
        profile=profile,
        match_filter=args.match_filter,
        occurrences=occurrences,
        missing_stress=missing_stress,
        min_distinct_words=args.min_distinct_words,
        include_identical_only=args.include_identical_only,
        full_groups=full_groups,
        bridge_groups=bridge_groups,
        primary_raws=primary_raws,
        bridge_raws=bridge_raws,
    )
    write_tsv(tsv_path, rows, profile=profile, match_filter=args.match_filter)

    tool_path = Path(__file__).resolve()
    shared_path = Path(shared_rhyme_module.__file__).resolve()
    metadata = {
        "schema_version": "1.0",
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "classification": "qualitative_inspection_utility_not_statistical_analysis",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "argv": [str(Path(sys.argv[0])), *(sys.argv[1:] if argv is None else argv)],
        },
        "code": {
            "tool_file": str(tool_path),
            "tool_sha256": sha256_file(tool_path),
            "shared_rhyme_file": str(shared_path),
            "shared_rhyme_sha256": sha256_file(shared_path),
            "shared_rhyme_protocol_version": SHARED_RHYME_PROTOCOL_VERSION,
        },
        "input": input_audit,
        "selection": {
            "book": args.book,
            "verse_numbering": "one_based_ordinal_within_book_not_chapter_verse",
            "start_verse_ordinal": args.start_verse_ordinal,
            "end_verse_ordinal": end_index,
            "requested_verse_count": args.verse_count,
            "selected_verse_count": len(selected),
        },
        "rhyme_protocol": {
            "equivalence_profile": profile,
            "equivalences": dict(config.equivalences),
            "multigraphs": list(config.multigraphs),
            "match_filter": args.match_filter,
            "missing_stress_policy": "skip_without_inference",
            "full_relation": "primary_to_primary",
            "bridge_relation": "primary_to_bridge_only_nontransitive",
            "bridge_to_bridge": False,
        },
        "filters": {
            "min_distinct_written_forms": args.min_distinct_words,
            "include_identical_only_full_groups": args.include_identical_only,
        },
        "audit": {
            **source_audit,
            "selected_source_word_tokens": sum(len(verse) for verse in selected),
            "analyzable_stressed_occurrences": len(occurrences),
            "word_tokens_without_explicit_stressed_vowel": missing_stress,
            "full_groups": len(full_groups),
            "bridge_groups": len(bridge_groups),
            "tsv_member_rows": len(rows),
        },
        "outputs": {
            "text": {"file": str(txt_path), "sha256": sha256_file(txt_path)},
            "tsv": {"file": str(tsv_path), "sha256": sha256_file(tsv_path)},
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== RHYME GROUPS WINDOW EXPORT v1 ===")
    print(
        f"book={args.book} ordinal_verses="
        f"{args.start_verse_ordinal}-{end_index}"
    )
    print(f"equivalence_profile={profile} match_filter={args.match_filter}")
    print(f"signatures={len(occurrences)} missing_stress={missing_stress}")
    print(f"full_groups={len(full_groups)} bridge_groups={len(bridge_groups)}")
    print(f"WROTE: {txt_path}")
    print(f"WROTE: {tsv_path}")
    print(f"WROTE: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
