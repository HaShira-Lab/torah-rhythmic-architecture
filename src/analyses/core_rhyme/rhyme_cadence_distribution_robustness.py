#!/usr/bin/env python3
"""Audit corpus distribution and robustness of rhyme-cadence alignment.

This analysis is downstream of rhyme_burst_architecture.py.  It does not use
an external comparison text and does not redefine rhyme or taam boundaries.
It asks whether the already defined burst-ending alignment is broadly
distributed across books and fixed textual blocks, and whether it survives
leave-one-book-out and rhyme-dense-block trimming checks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from random import Random
from statistics import median
from typing import Iterable, Sequence

import analyses.core_rhyme.rhyme_burst_architecture as burst  # type: ignore
import shared.rhyme.rhyme_protocol as shared_rhyme_module  # type: ignore
from shared.rhyme import (  # type: ignore
    DEFAULT_EQUIVALENCE_PROFILE,
    ProtocolConfig,
    available_equivalence_profiles,
    normalize_profile_name,
)

ANALYSIS_NAME = "rhyme_cadence_distribution_robustness"
ANALYSIS_VERSION = "1.0.1"
REQUIRED_BURST_VERSION = "5.0.2"
SHARED_RHYME_PROTOCOL_VERSION = "4"
CANONICAL_VERSE_MAP_SCHEMA_VERSION = "1.0"
BOOKS = burst.BOOKS
BOOK_INDEX = burst.BOOK_INDEX
LEVELS = ("minor", "major", "verse")
NULL_NAME = "run_preserving_circular_translation"


@dataclass(frozen=True)
class RunConfig:
    source_dir: Path
    out_dir: Path
    window: int
    threshold: int
    match_filter: str
    exclude_exact: bool
    equivalence_profile: str
    block_size: int
    minimum_block_fraction: float
    minimum_burst_ends_per_block: int
    boundary_permutations: int
    base_seed: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else math.nan


def finite_median(values: Iterable[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return median(finite) if finite else math.nan


def derive_seed(base_seed: int, book: str) -> int:
    return base_seed + BOOK_INDEX[book] * 1_000_003 + 401


def load_canonical_verse_map(
    source: Path,
    tokens: Sequence[burst.Token],
    source_word_count: int,
) -> tuple[list[dict[str, int]], dict[int, int], dict[str, object]]:
    """Load and validate canonical chapter/verse spans adjacent to ``source``.

    The taam hierarchy retains its existing ``sof_pasuq``-defined verse units.
    This independent map is used only for canonical chapter/verse coverage and
    labels, because a few Masoretic double-accentuation passages do not have a
    one-to-one relation between API segments and ``sof_pasuq`` units.
    """
    path = source.with_name(source.name + ".verse_map.json")
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing canonical verse map: {path}. "
            "Coverage cannot be labelled as canonical chapter/verse coverage "
            "without this verified sidecar."
        )
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != CANONICAL_VERSE_MAP_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported canonical verse-map schema in {path}: "
            f"{payload.get('schema_version')!r}"
        )
    expected_source_hash = payload.get("processed_file_sha256")
    actual_source_hash = sha256_file(source)
    if expected_source_hash != actual_source_hash:
        raise ValueError(
            f"Canonical verse map does not match {source}: "
            f"expected {expected_source_hash}, got {actual_source_hash}"
        )
    if int(payload.get("source_word_count", -1)) != source_word_count:
        raise ValueError(
            f"Canonical verse-map source-word count mismatch for {source}: "
            f"map={payload.get('source_word_count')}, parsed={source_word_count}"
        )

    raw_spans = payload.get("spans")
    if not isinstance(raw_spans, list) or not raw_spans:
        raise ValueError(f"Canonical verse map contains no spans: {path}")
    spans: list[dict[str, int]] = []
    word_to_ordinal: dict[int, int] = {}
    expected_first = 0
    for raw in raw_spans:
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid span in {path}: {raw!r}")
        span = {
            key: int(raw[key])
            for key in (
                "canonical_verse_ordinal", "chapter", "verse",
                "first_source_word_index", "last_source_word_index_exclusive",
                "source_word_count",
            )
        }
        first = span["first_source_word_index"]
        last = span["last_source_word_index_exclusive"]
        if first != expected_first or last <= first or last - first != span["source_word_count"]:
            raise ValueError(f"Non-contiguous or invalid canonical span in {path}: {span}")
        ordinal = span["canonical_verse_ordinal"]
        if ordinal != len(spans) + 1 or span["chapter"] < 1 or span["verse"] < 1:
            raise ValueError(f"Invalid canonical identifiers in {path}: {span}")
        for source_word_index in range(first, last):
            word_to_ordinal[source_word_index] = ordinal
        expected_first = last
        spans.append(span)
    if expected_first != source_word_count:
        raise ValueError(
            f"Canonical spans end at source word {expected_first}, expected {source_word_count}"
        )
    unmapped = [token.source_word_index for token in tokens if token.source_word_index not in word_to_ordinal]
    if unmapped:
        raise ValueError(f"Analyzable tokens missing from canonical verse map: {unmapped[:5]}")

    audit = {
        "map_file": str(path),
        "map_sha256": sha256_file(path),
        "schema_version": payload.get("schema_version"),
        "canonical_reference_system": payload.get("canonical_reference_system"),
        "canonical_verse_count": len(spans),
        "source_word_count": source_word_count,
        "processed_file_sha256_verified": True,
        "reconstruction_verified_token_for_token": payload.get(
            "reconstruction_verified_token_for_token"
        ),
        "api_payload_canonical_json_sha256": payload.get(
            "api_payload_canonical_json_sha256"
        ),
        "hebrew_version_title": payload.get("hebrew_version_title"),
        "hebrew_version_source": payload.get("hebrew_version_source"),
    }
    return spans, word_to_ordinal, audit


def make_blocks(size: int, block_size: int, minimum_fraction: float) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    minimum_size = max(1, math.ceil(block_size * minimum_fraction))
    for block_id, start in enumerate(range(0, size, block_size), start=1):
        end = min(size, start + block_size)
        length = end - start
        blocks.append({
            "block_id": block_id,
            "start": start,
            "end": end,
            "length": length,
            "included": length >= minimum_size,
        })
    return blocks


def block_index_map(blocks: Sequence[dict[str, object]], size: int) -> list[int]:
    mapping = [0] * size
    for block in blocks:
        block_id = int(block["block_id"])
        for index in range(int(block["start"]), int(block["end"])):
            mapping[index] = block_id
    return mapping


def run_end_records(
    values: Sequence[int],
    positions: Sequence[int],
    tokens: Sequence[burst.Token],
    block_map: Sequence[int],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for run_id, (start, end, length, intensity) in enumerate(
        burst.active_runs(values), start=1
    ):
        local_end = end - 1
        absolute_end = positions[local_end]
        records.append({
            "run_id": run_id,
            "local_start": start,
            "local_end": local_end,
            "absolute_end": absolute_end,
            "block_id": block_map[local_end],
            "length": length,
            "intensity": intensity,
            "minor": int(
                absolute_end + 1 < len(tokens)
                and tokens[absolute_end].minor_id != tokens[absolute_end + 1].minor_id
            ),
            "major": int(
                absolute_end + 1 < len(tokens)
                and tokens[absolute_end].major_id != tokens[absolute_end + 1].major_id
            ),
            "verse": int(
                absolute_end + 1 < len(tokens)
                and tokens[absolute_end].verse_id != tokens[absolute_end + 1].verse_id
            ),
        })
    return records


def count_hits(
    records: Sequence[dict[str, object]],
    level: str,
    excluded_blocks: set[int] | None = None,
) -> tuple[int, int]:
    accepted = (
        records if excluded_blocks is None
        else [row for row in records if int(row["block_id"]) not in excluded_blocks]
    )
    return sum(int(row[level]) for row in accepted), len(accepted)


def category_counts(
    all_raw: Sequence[int], nonexact_raw: Sequence[int], threshold: int
) -> dict[str, int | float]:
    exact_raw = [all_value - other for all_value, other in zip(all_raw, nonexact_raw)]
    if any(value < 0 for value in exact_raw):
        raise AssertionError("Exact-arrival decomposition produced a negative count")
    result: dict[str, int | float] = {
        "all_arrival_links": sum(all_raw),
        "different_word_arrival_links": sum(nonexact_raw),
        "exact_word_arrival_links": sum(exact_raw),
        "exact_word_arrival_share": safe_rate(sum(exact_raw), sum(all_raw)),
        "eligible_positions": len(all_raw),
    }
    counts = {
        "inactive": 0,
        "exact_only": 0,
        "different_word_only": 0,
        "mixed": 0,
        "combined_only_at_threshold": 0,
    }
    for total, exact, different in zip(all_raw, exact_raw, nonexact_raw):
        total_active = total >= threshold
        exact_active = exact >= threshold
        different_active = different >= threshold
        if not total_active:
            counts["inactive"] += 1
        elif exact_active and different_active:
            counts["mixed"] += 1
        elif exact_active:
            counts["exact_only"] += 1
        elif different_active:
            counts["different_word_only"] += 1
        else:
            counts["combined_only_at_threshold"] += 1
    result.update({f"positions_{key}": value for key, value in counts.items()})
    return result


def block_hit_rates(
    records: Sequence[dict[str, object]], blocks: Sequence[dict[str, object]], level: str
) -> dict[int, float]:
    result: dict[int, float] = {}
    for block in blocks:
        block_id = int(block["block_id"])
        subset = [row for row in records if int(row["block_id"]) == block_id]
        result[block_id] = safe_rate(sum(int(row[level]) for row in subset), len(subset))
    return result


def analyze_book(book: str, config: RunConfig) -> dict[str, object]:
    source = burst.locate_book(config.source_dir, book)
    input_audit = burst.validate_input(source)
    rhyme_config = ProtocolConfig.from_profile(config.equivalence_profile)
    tokens, parse_audit = burst.parse_book(source, rhyme_config)
    canonical_spans, word_to_canonical_ordinal, canonical_map_audit = (
        load_canonical_verse_map(
            source, tokens, int(parse_audit["source_word_tokens"])
        )
    )
    if len(tokens) <= config.window:
        raise ValueError(f"{book}: only {len(tokens)} analyzable tokens; window={config.window}")

    comparison_cache: dict[burst.ComparisonKey, str | None] = {}
    all_raw, all_full, all_bridge, all_pair_audit = burst.build_arrival_stream(
        tokens, config.window, False, config.match_filter,
        comparison_cache, collect_audit=True,
    )
    nonexact_raw, _, _, nonexact_pair_audit = burst.build_arrival_stream(
        tokens, config.window, True, config.match_filter,
        comparison_cache, collect_audit=True,
    )
    selected_raw = nonexact_raw if config.exclude_exact else all_raw
    values = burst.threshold_stream(selected_raw, config.threshold)
    positions = list(range(config.window, len(tokens)))
    boundary_values, edge_audit = burst.censor_edge_runs(values)

    blocks = make_blocks(len(values), config.block_size, config.minimum_block_fraction)
    block_map = block_index_map(blocks, len(values))
    observed_records = run_end_records(boundary_values, positions, tokens, block_map)

    seed = derive_seed(config.base_seed, book)
    selected_shifts, shift_audit = burst.select_boundary_shifts(
        boundary_values, config.boundary_permutations, Random(seed)
    )
    null_records = [
        run_end_records(
            burst.circular_shift(boundary_values, shift), positions, tokens, block_map
        )
        for shift in selected_shifts
    ]

    # Fixed-block coverage and alignment.  Selection uses observed burst-end
    # count only, never whether an end happens to hit a boundary.
    block_rows: list[dict[str, object]] = []
    block_alignment_rows: list[dict[str, object]] = []
    block_null_rates: dict[str, dict[int, list[float]]] = {
        level: {int(block["block_id"]): [] for block in blocks} for level in LEVELS
    }
    for level in LEVELS:
        for perm_records in null_records:
            rates = block_hit_rates(perm_records, blocks, level)
            for block_id, rate in rates.items():
                block_null_rates[level][block_id].append(rate)

    exact_raw = [a - b for a, b in zip(all_raw, nonexact_raw)]
    observed_runs_by_block = {
        int(block["block_id"]): [
            row for row in observed_records
            if int(row["block_id"]) == int(block["block_id"])
        ]
        for block in blocks
    }
    for block in blocks:
        block_id = int(block["block_id"])
        start, end = int(block["start"]), int(block["end"])
        subset = observed_runs_by_block[block_id]
        active_positions = sum(value > 0 for value in values[start:end])
        block_rows.append({
            "book": book,
            "block_id": block_id,
            "first_stream_position": start + 1,
            "last_stream_position": end,
            "first_token_index": positions[start] + 1,
            "last_token_index": positions[end - 1] + 1,
            "block_length": end - start,
            "included_in_fixed_block_inference": int(bool(block["included"])),
            "analyzed_arrivals": sum(values[start:end]),
            "arrival_density": safe_rate(sum(values[start:end]), end - start),
            "active_positions": active_positions,
            "active_rate": safe_rate(active_positions, end - start),
            "burst_ends": len(subset),
            "exact_word_arrival_links": sum(exact_raw[start:end]),
            "different_word_arrival_links": sum(nonexact_raw[start:end]),
            "minor_boundary_hits": sum(int(row["minor"]) for row in subset),
            "major_boundary_hits": sum(int(row["major"]) for row in subset),
            "verse_boundary_hits": sum(int(row["verse"]) for row in subset),
        })
        for level in LEVELS:
            observed_rate = safe_rate(sum(int(row[level]) for row in subset), len(subset))
            summary = burst.empirical_summary(
                observed_rate, block_null_rates[level][block_id]
            )
            eligible = bool(block["included"]) and len(subset) >= config.minimum_burst_ends_per_block
            block_alignment_rows.append({
                "book": book,
                "block_id": block_id,
                "level": level,
                "metric_role": "exploratory" if level == "verse" else "robustness",
                "eligible_for_distribution_summary": int(eligible),
                "observed_burst_ends": len(subset),
                "observed_boundary_hits": sum(int(row[level]) for row in subset),
                "null": NULL_NAME,
                "permutations": len(selected_shifts),
                **summary,
            })

    verse_rows: list[dict[str, object]] = []
    token_indices_by_verse: dict[int, list[int]] = {}
    local_indices_by_verse: dict[int, list[int]] = {}
    for token_index, token in enumerate(tokens):
        canonical_ordinal = word_to_canonical_ordinal[token.source_word_index]
        token_indices_by_verse.setdefault(canonical_ordinal, []).append(token_index)
    for local_index, token_index in enumerate(positions):
        canonical_ordinal = word_to_canonical_ordinal[tokens[token_index].source_word_index]
        local_indices_by_verse.setdefault(canonical_ordinal, []).append(local_index)
    span_by_ordinal = {
        span["canonical_verse_ordinal"]: span for span in canonical_spans
    }
    for canonical_ordinal in sorted(token_indices_by_verse):
        span = span_by_ordinal[canonical_ordinal]
        local = local_indices_by_verse.get(canonical_ordinal, [])
        complete = min(token_indices_by_verse[canonical_ordinal]) >= config.window
        verse_run_ends = [
            row for row in observed_records
            if word_to_canonical_ordinal[
                tokens[int(row["absolute_end"])].source_word_index
            ] == canonical_ordinal
        ]
        sof_pasuq_unit_ids = sorted({
            tokens[token_index].verse_id
            for token_index in token_indices_by_verse[canonical_ordinal]
        })
        verse_rows.append({
            "book": book,
            "canonical_verse_ordinal": canonical_ordinal,
            "chapter": span["chapter"],
            "verse": span["verse"],
            "canonical_reference": f"{book.title()} {span['chapter']}:{span['verse']}",
            "first_source_word_index": span["first_source_word_index"],
            "last_source_word_index_exclusive": span["last_source_word_index_exclusive"],
            "sof_pasuq_unit_ids": "|".join(str(value) for value in sof_pasuq_unit_ids),
            "sof_pasuq_unit_count": len(sof_pasuq_unit_ids),
            "fully_represented_after_left_window": int(complete),
            "eligible_positions": len(local),
            "analyzed_arrivals": sum(values[index] for index in local),
            "active_positions": sum(values[index] > 0 for index in local),
            "has_rhyme_activity": int(any(values[index] > 0 for index in local)),
            "burst_ends": len(verse_run_ends),
            "has_burst_end": int(bool(verse_run_ends)),
            "minor_boundary_hits": sum(int(row["minor"]) for row in verse_run_ends),
            "major_boundary_hits": sum(int(row["major"]) for row in verse_run_ends),
            "verse_boundary_hits": sum(int(row["verse"]) for row in verse_run_ends),
        })

    lexical = {
        "book": book,
        "match_filter": config.match_filter,
        "activity_threshold": config.threshold,
        "full_arrival_links_before_match_filter": sum(all_full),
        "bridge_arrival_links_before_match_filter": sum(all_bridge),
        **category_counts(all_raw, nonexact_raw, config.threshold),
    }
    complete_verses = [row for row in verse_rows if row["fully_represented_after_left_window"]]
    coverage = {
        "book": book,
        "coverage_unit": "canonical_chapter_verse",
        "tokens": len(tokens),
        "eligible_stream_positions": len(values),
        "analyzed_total_arrivals": sum(values),
        "active_positions": sum(value > 0 for value in values),
        "active_rate": safe_rate(sum(value > 0 for value in values), len(values)),
        "boundary_test_burst_ends": len(observed_records),
        "fixed_blocks_total": len(blocks),
        "fixed_blocks_included": sum(bool(block["included"]) for block in blocks),
        "included_blocks_with_activity": sum(
            bool(row["included_in_fixed_block_inference"]) and int(row["active_positions"]) > 0
            for row in block_rows
        ),
        "canonical_verses_total": len(canonical_spans),
        "canonical_verses_with_analyzable_tokens": len(token_indices_by_verse),
        "complete_represented_canonical_verses": len(complete_verses),
        "complete_canonical_verses_with_activity": sum(
            int(row["has_rhyme_activity"]) for row in complete_verses
        ),
        "complete_canonical_verse_activity_coverage": safe_rate(
            sum(int(row["has_rhyme_activity"]) for row in complete_verses), len(complete_verses)
        ),
        "complete_canonical_verses_with_burst_end": sum(
            int(row["has_burst_end"]) for row in complete_verses
        ),
        "complete_canonical_verse_burst_end_coverage": safe_rate(
            sum(int(row["has_burst_end"]) for row in complete_verses), len(complete_verses)
        ),
    }

    book_alignment: dict[str, dict[str, object]] = {}
    block_support: dict[str, dict[str, object]] = {}
    for level in LEVELS:
        observed_hits, observed_total = count_hits(observed_records, level)
        null_rates = [safe_rate(*count_hits(records, level)) for records in null_records]
        book_alignment[level] = {
            "hits": observed_hits,
            "burst_ends": observed_total,
            "summary": burst.empirical_summary(
                safe_rate(observed_hits, observed_total), null_rates
            ),
            "null_rates": null_rates,
        }

        eligible_rows = [
            row for row in block_alignment_rows
            if row["level"] == level and row["eligible_for_distribution_summary"]
        ]
        eligible_ids = [int(row["block_id"]) for row in eligible_rows]
        null_means = {int(row["block_id"]): float(row["null_mean"]) for row in eligible_rows}
        observed_differences = [float(row["difference"]) for row in eligible_rows]
        observed_positive_share = safe_rate(
            sum(value > 0 for value in observed_differences), len(observed_differences)
        )
        observed_median_difference = finite_median(observed_differences)
        null_positive_shares: list[float] = []
        null_medians: list[float] = []
        for permutation_index in range(len(selected_shifts)):
            differences = []
            for block_id in eligible_ids:
                rate = block_null_rates[level][block_id][permutation_index]
                if math.isfinite(rate) and math.isfinite(null_means[block_id]):
                    differences.append(rate - null_means[block_id])
            null_positive_shares.append(
                safe_rate(sum(value > 0 for value in differences), len(differences))
            )
            null_medians.append(finite_median(differences))
        block_support[level] = {
            "eligible_blocks": len(eligible_rows),
            "positive_share": burst.empirical_summary(
                observed_positive_share, null_positive_shares
            ),
            "median_difference": burst.empirical_summary(
                observed_median_difference, null_medians
            ),
            "null_positive_shares": null_positive_shares,
            "null_medians": null_medians,
        }

    prefix = config.out_dir / book
    paths = {
        "blocks": prefix.with_name(f"{book}_fixed_blocks.csv"),
        "block_alignment": prefix.with_name(f"{book}_block_alignment_statistics.csv"),
        "verses": prefix.with_name(f"{book}_verse_coverage.csv"),
        "summary": prefix.with_name(f"{book}_summary.json"),
    }
    write_csv(paths["blocks"], block_rows)
    write_csv(paths["block_alignment"], block_alignment_rows)
    write_csv(paths["verses"], verse_rows)
    public_summary = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "book": book,
        "input": input_audit,
        "parameters": {
            "window_in_analyzable_stressed_tokens": config.window,
            "activity_threshold": config.threshold,
            "match_filter": config.match_filter,
            "exclude_exact": config.exclude_exact,
            "equivalence_profile": config.equivalence_profile,
            "block_size_in_eligible_stream_positions": config.block_size,
            "minimum_block_fraction": config.minimum_block_fraction,
            "minimum_burst_ends_per_block": config.minimum_burst_ends_per_block,
            "boundary_permutations_requested": config.boundary_permutations,
        },
        "seed": seed,
        "parse_audit": parse_audit,
        "canonical_verse_map_audit": canonical_map_audit,
        "all_pair_audit": all_pair_audit,
        "nonexact_pair_audit": nonexact_pair_audit,
        "edge_audit": edge_audit,
        "shift_audit": shift_audit,
        "coverage": coverage,
        "lexical_decomposition": lexical,
        "book_alignment": {
            level: {key: value for key, value in payload.items() if key != "null_rates"}
            for level, payload in book_alignment.items()
        },
        "block_support": {
            level: {
                key: value for key, value in payload.items()
                if not key.startswith("null_")
            }
            for level, payload in block_support.items()
        },
    }
    paths["summary"].write_text(
        json.dumps(json_safe(public_summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return {
        "book": book,
        "input": input_audit,
        "canonical_verse_map_audit": canonical_map_audit,
        "seed": seed,
        "coverage": coverage,
        "lexical": lexical,
        "block_rows": block_rows,
        "block_alignment_rows": block_alignment_rows,
        "verse_rows": verse_rows,
        "observed_records": observed_records,
        "null_records": null_records,
        "book_alignment": book_alignment,
        "block_support": block_support,
        "paths": [str(path) for path in paths.values()],
    }


def pooled_rate(
    results: Sequence[dict[str, object]],
    level: str,
    permutation_index: int | None = None,
    excluded_book: str | None = None,
    excluded_blocks: dict[str, set[int]] | None = None,
) -> tuple[int, int, float]:
    hits = total = 0
    for result in results:
        book = str(result["book"])
        if book == excluded_book:
            continue
        records = (
            result["observed_records"] if permutation_index is None
            else result["null_records"][permutation_index]  # type: ignore[index]
        )
        excluded = None if excluded_blocks is None else excluded_blocks.get(book, set())
        book_hits, book_total = count_hits(records, level, excluded)  # type: ignore[arg-type]
        hits += book_hits
        total += book_total
    return hits, total, safe_rate(hits, total)


def aggregate_results(
    results: Sequence[dict[str, object]], config: RunConfig
) -> tuple[dict[str, object], list[Path]]:
    results = sorted(results, key=lambda result: BOOK_INDEX[str(result["book"])])
    permutation_count = min(len(result["null_records"]) for result in results)  # type: ignore[arg-type]
    created: list[Path] = []

    all_blocks = [row for result in results for row in result["block_rows"]]  # type: ignore[misc]
    all_block_alignment = [
        row for result in results for row in result["block_alignment_rows"]  # type: ignore[misc]
    ]
    all_verses = [row for result in results for row in result["verse_rows"]]  # type: ignore[misc]
    coverages = [result["coverage"] for result in results]
    lexicals = [result["lexical"] for result in results]

    aggregate_files = {
        "book_coverage": config.out_dir / "ALL_book_coverage.csv",
        "lexical": config.out_dir / "ALL_lexical_decomposition.csv",
        "blocks": config.out_dir / "ALL_fixed_blocks.csv",
        "block_alignment": config.out_dir / "ALL_block_alignment_statistics.csv",
        "verses": config.out_dir / "ALL_verse_coverage.csv",
    }
    write_csv(aggregate_files["book_coverage"], coverages)  # type: ignore[arg-type]
    write_csv(aggregate_files["lexical"], lexicals)  # type: ignore[arg-type]
    write_csv(aggregate_files["blocks"], all_blocks)
    write_csv(aggregate_files["block_alignment"], all_block_alignment)
    write_csv(aggregate_files["verses"], all_verses)
    created.extend(aggregate_files.values())

    # Distribution summary over all eligible fixed blocks, with book-specific
    # null expectations and paired independent circular translations.
    distribution_rows: list[dict[str, object]] = []
    for scope in ["ALL", *[str(result["book"]) for result in results]]:
        scoped_results = results if scope == "ALL" else [
            result for result in results if result["book"] == scope
        ]
        for level in LEVELS:
            eligible_rows = [
                row for result in scoped_results
                for row in result["block_alignment_rows"]  # type: ignore[misc]
                if row["level"] == level and row["eligible_for_distribution_summary"]
            ]
            observed_differences = [float(row["difference"]) for row in eligible_rows]
            observed_positive = safe_rate(
                sum(value > 0 for value in observed_differences), len(observed_differences)
            )
            observed_median = finite_median(observed_differences)
            null_positive: list[float] = []
            null_medians: list[float] = []
            for permutation_index in range(permutation_count):
                differences: list[float] = []
                for result in scoped_results:
                    book_rows = [
                        row for row in result["block_alignment_rows"]  # type: ignore[misc]
                        if row["level"] == level and row["eligible_for_distribution_summary"]
                    ]
                    rates = block_hit_rates(
                        result["null_records"][permutation_index],  # type: ignore[index]
                        result["block_rows"],  # type: ignore[arg-type]
                        level,
                    )
                    for row in book_rows:
                        rate = rates[int(row["block_id"])]
                        null_mean = float(row["null_mean"])
                        if math.isfinite(rate) and math.isfinite(null_mean):
                            differences.append(rate - null_mean)
                null_positive.append(
                    safe_rate(sum(value > 0 for value in differences), len(differences))
                )
                null_medians.append(finite_median(differences))
            for metric, observed, null_values in (
                ("positive_block_difference_share", observed_positive, null_positive),
                ("median_block_hit_rate_difference", observed_median, null_medians),
            ):
                distribution_rows.append({
                    "scope": scope,
                    "level": level,
                    "metric_role": "exploratory" if level == "verse" else "robustness",
                    "metric": metric,
                    "eligible_blocks": len(eligible_rows),
                    "null": NULL_NAME,
                    "permutations": permutation_count,
                    **burst.empirical_summary(observed, null_values),
                })
    distribution_path = config.out_dir / "ALL_block_distribution_statistics.csv"
    write_csv(distribution_path, distribution_rows)
    created.append(distribution_path)

    # Pooled base and leave-one-book-out estimates.  The LOO rows are
    # robustness estimates, not five independent confirmatory tests.
    leave_out_rows: list[dict[str, object]] = []
    for excluded in [None, *[str(result["book"]) for result in results]]:
        for level in LEVELS:
            hits, total, observed = pooled_rate(results, level, excluded_book=excluded)
            null_values = [
                pooled_rate(
                    results, level, permutation_index=index, excluded_book=excluded
                )[2]
                for index in range(permutation_count)
            ]
            leave_out_rows.append({
                "excluded_book": excluded or "NONE",
                "level": level,
                "metric_role": "exploratory" if level == "verse" else "robustness",
                "observed_boundary_hits": hits,
                "observed_burst_ends": total,
                "null": NULL_NAME,
                "permutations": permutation_count,
                **burst.empirical_summary(observed, null_values),
            })
    leave_out_path = config.out_dir / "ALL_leave_one_book_out_statistics.csv"
    write_csv(leave_out_path, leave_out_rows)
    created.append(leave_out_path)

    # Remove blocks ranked by observed rhyme-arrival density, never by whether
    # they align with a boundary.  Runs are defined before trimming; only runs
    # ending in selected blocks are omitted, so trimming cannot split bursts.
    ranked = sorted(
        [row for row in all_blocks if row["included_in_fixed_block_inference"]],
        key=lambda row: (
            -float(row["arrival_density"]),
            BOOK_INDEX[str(row["book"])],
            int(row["block_id"]),
        ),
    )
    trim_rows: list[dict[str, object]] = []
    for fraction in (0.0, 0.01, 0.05, 0.10):
        remove_count = 0 if fraction == 0 else max(1, math.ceil(len(ranked) * fraction))
        selected = ranked[:remove_count]
        excluded_blocks: dict[str, set[int]] = {}
        for row in selected:
            excluded_blocks.setdefault(str(row["book"]), set()).add(int(row["block_id"]))
        for level in LEVELS:
            hits, total, observed = pooled_rate(
                results, level, excluded_blocks=excluded_blocks
            )
            null_values = [
                pooled_rate(
                    results, level, permutation_index=index,
                    excluded_blocks=excluded_blocks,
                )[2]
                for index in range(permutation_count)
            ]
            trim_rows.append({
                "trim_fraction_of_fixed_blocks": fraction,
                "blocks_removed": remove_count,
                "selection_rule": "highest_observed_analyzed_arrival_density",
                "level": level,
                "metric_role": "exploratory" if level == "verse" else "robustness",
                "observed_boundary_hits": hits,
                "observed_burst_ends": total,
                "null": NULL_NAME,
                "permutations": permutation_count,
                **burst.empirical_summary(observed, null_values),
            })
    trim_path = config.out_dir / "ALL_rhyme_dense_block_trim_statistics.csv"
    write_csv(trim_path, trim_rows)
    created.append(trim_path)

    # Book-direction audit: exact equality to the null mean is not counted as
    # positive.  With five books this is descriptive, not a significance test.
    direction_rows: list[dict[str, object]] = []
    for level in LEVELS:
        book_differences = [
            float(result["book_alignment"][level]["summary"]["difference"])  # type: ignore[index]
            for result in results
        ]
        direction_rows.append({
            "level": level,
            "metric_role": "exploratory" if level == "verse" else "descriptive_robustness",
            "books": len(results),
            "books_positive_difference": sum(value > 0 for value in book_differences),
            "positive_book_share": safe_rate(
                sum(value > 0 for value in book_differences), len(book_differences)
            ),
            "median_book_difference": finite_median(book_differences),
            "interpretation": "directional audit; books are not treated as independent replications",
        })
    direction_path = config.out_dir / "ALL_book_direction_audit.csv"
    write_csv(direction_path, direction_rows)
    created.append(direction_path)

    summary = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "books": [result["book"] for result in results],
        "book_coverage": coverages,
        "lexical_decomposition": lexicals,
        "block_distribution_statistics": distribution_rows,
        "leave_one_book_out_statistics": leave_out_rows,
        "rhyme_dense_block_trim_statistics": trim_rows,
        "book_direction_audit": direction_rows,
    }
    summary_path = config.out_dir / "ALL_summary.json"
    summary_path.write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    created.append(summary_path)
    return summary, created


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--books", nargs="+", choices=BOOKS, default=list(BOOKS))
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--activity-threshold", type=int, default=1)
    parser.add_argument("--match-filter", choices=("ALL", "FULL", "BRIDGE"), default="ALL")
    parser.add_argument("--exclude-exact", action="store_true")
    parser.add_argument("--block-size", type=int, default=1000)
    parser.add_argument("--minimum-block-fraction", type=float, default=0.5)
    parser.add_argument("--minimum-burst-ends-per-block", type=int, default=5)
    parser.add_argument("--boundary-permutations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--equivalence-profile",
        default=DEFAULT_EQUIVALENCE_PROFILE,
        type=normalize_profile_name,
        choices=available_equivalence_profiles(),
    )
    args = parser.parse_args(argv)
    positive = (
        args.window, args.activity_threshold, args.block_size,
        args.minimum_burst_ends_per_block, args.boundary_permutations, args.jobs,
    )
    if any(value < 1 for value in positive):
        parser.error("window, threshold, block size, minimum burst ends, permutations, and jobs must be positive")
    if not 0 < args.minimum_block_fraction <= 1:
        parser.error("--minimum-block-fraction must be in (0, 1]")
    if len(set(args.books)) != len(args.books):
        parser.error("--books must not contain duplicates")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if burst.ANALYSIS_VERSION != REQUIRED_BURST_VERSION:
        raise RuntimeError(
            f"This analysis requires rhyme_burst_architecture.py {REQUIRED_BURST_VERSION}; "
            f"found {burst.ANALYSIS_VERSION}"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    config = RunConfig(
        source_dir=args.source_dir,
        out_dir=args.out_dir,
        window=args.window,
        threshold=args.activity_threshold,
        match_filter=args.match_filter,
        exclude_exact=args.exclude_exact,
        equivalence_profile=args.equivalence_profile,
        block_size=args.block_size,
        minimum_block_fraction=args.minimum_block_fraction,
        minimum_burst_ends_per_block=args.minimum_burst_ends_per_block,
        boundary_permutations=args.boundary_permutations,
        base_seed=args.seed,
    )

    print(
        f"=== RHYME-CADENCE DISTRIBUTION AND ROBUSTNESS "
        f"v{ANALYSIS_VERSION} ==="
    )
    print(f"run_label={args.run_label}")
    print(f"source={args.source_dir}")
    print(f"out={args.out_dir}")
    print(
        f"L={args.window} threshold={args.activity_threshold} "
        f"filter={args.match_filter} exclude_exact={args.exclude_exact} "
        f"profile={args.equivalence_profile}"
    )
    print(
        f"block_size={args.block_size} min_block_fraction={args.minimum_block_fraction} "
        f"min_burst_ends={args.minimum_burst_ends_per_block} "
        f"boundary_perm={args.boundary_permutations} jobs={args.jobs}"
    )

    if args.jobs == 1 or len(args.books) == 1:
        results = [analyze_book(book, config) for book in args.books]
    else:
        with ProcessPoolExecutor(max_workers=min(args.jobs, len(args.books))) as executor:
            futures = [executor.submit(analyze_book, book, config) for book in args.books]
            results = [future.result() for future in futures]
    results = sorted(results, key=lambda result: BOOK_INDEX[str(result["book"])])
    for result in results:
        coverage = result["coverage"]
        lexical = result["lexical"]
        print(
            f"\n{result['book']:<12} positions={coverage['eligible_stream_positions']:6d} "
            f"active={coverage['active_rate']:.4f} "
            f"canonical_verse_coverage="
            f"{coverage['complete_canonical_verse_activity_coverage']:.4f} "
            f"exact_arrival_share={lexical['exact_word_arrival_share']:.4f}"
        )
        for level in LEVELS:
            summary = result["book_alignment"][level]["summary"]
            print(
                f"  {level:<5} end-hit={summary['observed']:.4f} "
                f"null={summary['null_mean']:.4f} diff={summary['difference']:.4f} "
                f"Z={summary['z']:.2f}"
            )

    _, aggregate_paths = aggregate_results(results, config)
    created_files = [
        Path(path) for result in results for path in result["paths"]  # type: ignore[misc]
    ] + aggregate_paths

    analysis_path = Path(__file__).resolve()
    burst_path = Path(burst.__file__).resolve()
    shared_path = Path(shared_rhyme_module.__file__).resolve()
    metadata = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "run_label": args.run_label,
        "command_line": [sys.executable, *sys.argv],
        "books": list(args.books),
        "parameters": {
            "source_dir": str(args.source_dir),
            "out_dir": str(args.out_dir),
            "window_in_analyzable_stressed_tokens": args.window,
            "activity_threshold": args.activity_threshold,
            "match_filter": args.match_filter,
            "exclude_exact": args.exclude_exact,
            "equivalence_profile": args.equivalence_profile,
            "block_size_in_eligible_stream_positions": args.block_size,
            "minimum_block_fraction": args.minimum_block_fraction,
            "minimum_burst_ends_per_block": args.minimum_burst_ends_per_block,
            "boundary_permutations_requested": args.boundary_permutations,
            "base_seed": args.seed,
            "jobs": args.jobs,
            "rhyme_dense_block_trim_fractions": [0, 0.01, 0.05, 0.10],
        },
        "scientific_roles": {
            "main_observed_stream": "ALL matches including exact lexical repetitions",
            "exact_word_policy": (
                "Exact repetitions are retained as potentially structural; exact/different/mixed "
                "components are reported. Exclusion is a diagnostic control, not a validity criterion."
            ),
            "minor_and_major_fixed_block_distribution": "robustness",
            "verse_fixed_block_distribution": "exploratory",
            "leave_one_book_out": "robustness",
            "rhyme_dense_block_trimming": "robustness",
            "book_direction_count": "descriptive_robustness",
        },
        "null_model": NULL_NAME,
        "software": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "code_and_protocol": {
            "analysis_file": str(analysis_path),
            "analysis_sha256": sha256_file(analysis_path),
            "rhyme_burst_architecture_file": str(burst_path),
            "rhyme_burst_architecture_version": burst.ANALYSIS_VERSION,
            "rhyme_burst_architecture_sha256": sha256_file(burst_path),
            "shared_rhyme_module": str(shared_path),
            "shared_rhyme_module_sha256": sha256_file(shared_path),
            "shared_rhyme_protocol_version": SHARED_RHYME_PROTOCOL_VERSION,
        },
        "inputs": [result["input"] for result in results],
        "canonical_verse_maps": [
            result["canonical_verse_map_audit"] for result in results
        ],
        "book_seeds": {result["book"]: result["seed"] for result in results},
        "output_sha256": {
            str(path.relative_to(args.out_dir)): sha256_file(path)
            for path in sorted(created_files, key=lambda item: str(item))
        },
    }
    metadata_path = args.out_dir / "RUN_METADATA.json"
    metadata_path.write_text(
        json.dumps(json_safe(metadata), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"\nWROTE: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
