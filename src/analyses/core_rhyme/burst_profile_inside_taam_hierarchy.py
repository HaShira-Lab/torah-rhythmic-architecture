#!/usr/bin/env python3
"""Profile local rhyme-arrival activity inside the taam hierarchy.

This analysis starts from the observed local rhyme-arrival stream constructed
by rhyme_burst_architecture.py.  It asks whether activity is relatively
depleted near the beginnings of taam-defined segments and higher in their later
part.  It does not test whether local rhyme enrichment or bursts exist, and it
does not test whether burst endings coincide with boundaries.

Primary metric
--------------
For mean arrival count in minor and major segments, the primary metric is the
last normalized position bin minus the first (terminal_contrast).  Verse-level
results are exploratory.

Null models
-----------
1. Run-preserving circular translation of the edge-censored observed
   thresholded stream relative to the fixed hierarchy.
2. Independent permutation of observed values inside each eligible segment.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Mapping, MutableMapping, Sequence

HERE = Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import shared.rhyme.rhyme_protocol as shared_rhyme_module  # type: ignore
from shared.rhyme import (  # type: ignore
    DEFAULT_EQUIVALENCE_PROFILE,
    EQUIVALENCE_GROUPS,
    ProtocolConfig,
    available_equivalence_profiles,
    normalize_profile_name,
)

import rhyme_burst_architecture as upstream_module  # type: ignore
from rhyme_burst_architecture import (  # type: ignore
    ANALYSIS_VERSION as UPSTREAM_ANALYSIS_VERSION,
    BOOKS,
    BOOK_INDEX,
    ComparisonKey,
    Token,
    build_arrival_stream,
    censor_edge_runs,
    circular_shift,
    eligible_run_preserving_shifts,
    empirical_summary,
    json_safe,
    locate_book,
    mean,
    parse_book,
    sha256_file,
    threshold_stream,
    validate_input,
    write_csv,
)

ANALYSIS_NAME = "burst_profile_inside_taam_hierarchy"
ANALYSIS_VERSION = "5.0.0"
ANALYSIS_PROTOCOL_VERSION = "5"
REQUIRED_UPSTREAM_VERSION = "5.0.2"
SHARED_RHYME_PROTOCOL_VERSION = "4"

LEVELS = ("minor", "major", "verse")
LEVEL_INDEX = {level: index for index, level in enumerate(LEVELS)}
RESPONSES = ("mean_count", "active_rate")
PROFILE_METRICS = (
    "terminal_contrast",
    "linear_slope",
    "cadence_peak",
    "profile_energy",
    "profile_amplitude",
)

RUN_PRESERVING_NULL = "run_preserving_circular_translation"
WITHIN_SEGMENT_NULL = "within_segment_value_permutation"


@dataclass(frozen=True)
class Segment:
    level: str
    segment_id: int
    stream_indices: tuple[int, ...]
    token_indices: tuple[int, ...]
    original_stream_indices: tuple[int, ...]
    original_token_indices: tuple[int, ...]

    @property
    def length(self) -> int:
        return len(self.stream_indices)

    @property
    def original_length(self) -> int:
        return len(self.original_stream_indices)


@dataclass(frozen=True)
class RunConfig:
    source_dir: Path
    out_dir: Path
    window: int
    circular_permutations: int
    within_permutations: int
    base_seed: int
    exclude_exact: bool
    match_filter: str
    threshold: int
    equivalence_profile: str
    bins: int
    coordinate_mode: str
    max_distance: int
    aggregation: str
    value_mode: str
    exclude_cadence_word: bool
    min_segment_length: int
    max_segment_length: int


def level_id(token: Token, level: str) -> int:
    if level == "minor":
        return token.minor_id
    if level == "major":
        return token.major_id
    if level == "verse":
        return token.verse_id
    raise ValueError(f"Unknown hierarchy level: {level}")


def derive_seeds(base_seed: int, book: str) -> dict[str, object]:
    """Derive order-independent RNG seeds from canonical book/level indices."""
    book_offset = BOOK_INDEX[book] * 1_000_003
    levels: dict[str, dict[str, int]] = {}
    for level in LEVELS:
        level_offset = LEVEL_INDEX[level] * 10_007
        levels[level] = {
            "circular_seed": base_seed + book_offset + level_offset + 101,
            "within_segment_seed": base_seed + book_offset + level_offset + 211,
        }
    return {
        "base_seed": base_seed,
        "book_index": BOOK_INDEX[book],
        "levels": levels,
    }


def segment_inventory(
    tokens: Sequence[Token],
    positions: Sequence[int],
    level: str,
    min_length: int,
    max_length: int,
    exclude_cadence_word: bool,
) -> tuple[list[Segment], list[dict[str, object]], dict[str, object]]:
    """Build complete eligible segments and a full represented-segment audit.

    Length eligibility is evaluated before optional cadence-word removal.  This
    keeps the segment inventory fixed when the cadence-word control is compared
    with MAIN.
    """
    grouped: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for stream_i, token_i in enumerate(positions):
        grouped[level_id(tokens[token_i], level)].append((stream_i, token_i))

    eligible: list[Segment] = []
    rows: list[dict[str, object]] = []
    reasons: Counter[str] = Counter()
    complete_count = 0
    complete_lengths: list[int] = []

    for seg_id, pairs in sorted(grouped.items()):
        original_stream = tuple(pair[0] for pair in pairs)
        original_tokens = tuple(pair[1] for pair in pairs)
        first_token = original_tokens[0]
        last_token = original_tokens[-1]
        starts_complete = (
            first_token == 0
            or level_id(tokens[first_token - 1], level) != seg_id
        )
        ends_complete = (
            last_token == len(tokens) - 1
            or level_id(tokens[last_token + 1], level) != seg_id
        )
        original_length = len(original_stream)

        if not starts_complete:
            reason = "truncated_by_left_window_edge"
        elif not ends_complete:
            reason = "truncated_by_corpus_edge"
        elif original_length < min_length:
            reason = "below_minimum_length"
        elif max_length > 0 and original_length > max_length:
            reason = "above_maximum_length"
        else:
            reason = "eligible"

        if starts_complete and ends_complete:
            complete_count += 1
            complete_lengths.append(original_length)

        used_stream = original_stream[:-1] if exclude_cadence_word else original_stream
        used_tokens = original_tokens[:-1] if exclude_cadence_word else original_tokens
        if reason == "eligible" and not used_stream:
            reason = "empty_after_cadence_exclusion"

        included = reason == "eligible"
        if included:
            eligible.append(
                Segment(
                    level=level,
                    segment_id=seg_id,
                    stream_indices=used_stream,
                    token_indices=used_tokens,
                    original_stream_indices=original_stream,
                    original_token_indices=original_tokens,
                )
            )
        reasons[reason] += 1
        cadence_token = tokens[last_token]
        rows.append({
            "level": level,
            "segment_id": seg_id,
            "included": included,
            "exclusion_reason": "" if included else reason,
            "starts_complete": starts_complete,
            "ends_complete": ends_complete,
            "original_length": original_length,
            "analyzed_length": len(used_stream) if included else 0,
            "start_stream_index": original_stream[0] + 1,
            "end_stream_index": original_stream[-1] + 1,
            "start_token_index": first_token + 1,
            "end_token_index": last_token + 1,
            "cadence_word": cadence_token.word,
            "cadence_taamim": ",".join(cadence_token.taamim),
            "cadence_word_removed": bool(exclude_cadence_word and included),
        })

    eligible_lengths = [segment.original_length for segment in eligible]
    coverage = {
        "represented_segments": len(grouped),
        "complete_segments": complete_count,
        "eligible_segments": len(eligible),
        "eligible_share_of_complete": (
            len(eligible) / complete_count if complete_count else math.nan
        ),
        "complete_length_min": min(complete_lengths) if complete_lengths else math.nan,
        "complete_length_mean": (
            mean([float(value) for value in complete_lengths])
            if complete_lengths else math.nan
        ),
        "complete_length_max": max(complete_lengths) if complete_lengths else math.nan,
        "eligible_length_min": min(eligible_lengths) if eligible_lengths else math.nan,
        "eligible_length_mean": (
            mean([float(value) for value in eligible_lengths])
            if eligible_lengths else math.nan
        ),
        "eligible_length_max": max(eligible_lengths) if eligible_lengths else math.nan,
        "inventory_counts": dict(sorted(reasons.items())),
    }
    return eligible, rows, coverage


def coordinate_bin(
    rank: int,
    length: int,
    bins: int,
    mode: str,
    max_distance: int,
) -> int | None:
    if mode == "normalized":
        return min(bins - 1, int(((rank + 0.5) / length) * bins))
    distance = length - 1 - rank
    if distance > max_distance:
        return None
    return max_distance - distance


def transformed_values(
    values: Sequence[int], segment: Segment, value_mode: str
) -> list[float]:
    raw = [float(values[index]) for index in segment.stream_indices]
    if value_mode == "raw":
        return raw
    total = sum(raw)
    if total <= 0:
        return [0.0 for _ in raw]
    return [value / total for value in raw]


def build_profile(
    values: Sequence[int],
    segments: Sequence[Segment],
    bins: int,
    coordinate_mode: str,
    max_distance: int,
    aggregation: str,
    value_mode: str,
) -> list[dict[str, object]]:
    bin_values: list[list[float]] = [[] for _ in range(bins)]
    bin_active: list[list[float]] = [[] for _ in range(bins)]
    bin_tokens = [0 for _ in range(bins)]
    bin_segment_ids: list[set[int]] = [set() for _ in range(bins)]

    for segment in segments:
        segment_values = transformed_values(values, segment, value_mode)
        local_values: list[list[float]] = [[] for _ in range(bins)]
        for rank, value in enumerate(segment_values):
            bin_index = coordinate_bin(
                rank, segment.length, bins, coordinate_mode, max_distance
            )
            if bin_index is None:
                continue
            local_values[bin_index].append(value)
            bin_tokens[bin_index] += 1
            bin_segment_ids[bin_index].add(segment.segment_id)
            if aggregation == "token":
                bin_values[bin_index].append(value)
                bin_active[bin_index].append(float(value > 0))

        if aggregation == "segment":
            for bin_index, local in enumerate(local_values):
                if local:
                    bin_values[bin_index].append(mean(local))
                    bin_active[bin_index].append(
                        mean([float(value > 0) for value in local])
                    )

    rows: list[dict[str, object]] = []
    for bin_index in range(bins):
        if coordinate_mode == "normalized":
            midpoint: float | None = (bin_index + 0.5) / bins
            distance: int | None = None
        else:
            midpoint = None
            distance = max_distance - bin_index
        rows.append({
            "bin": bin_index + 1,
            "normalized_position_midpoint": midpoint,
            "distance_to_cadence": distance,
            "mean_count": (
                mean(bin_values[bin_index]) if bin_values[bin_index] else math.nan
            ),
            "active_rate": (
                mean(bin_active[bin_index]) if bin_active[bin_index] else math.nan
            ),
            "n_contributions": len(bin_values[bin_index]),
            "n_segments_contributing": len(bin_segment_ids[bin_index]),
            "n_tokens": bin_tokens[bin_index],
        })
    return rows


def finite_profile(
    profile: Sequence[Mapping[str, object]], response: str
) -> list[float]:
    result: list[float] = []
    for row in profile:
        value = row[response]
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            result.append(float(value))
    return result


def linear_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return math.nan
    xs = [(index + 0.5) / len(values) for index in range(len(values))]
    mean_x = mean(xs)
    mean_y = mean(values)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator == 0:
        return 0.0
    return sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, values)
    ) / denominator


def profile_metrics(
    profile: Sequence[Mapping[str, object]], response: str
) -> dict[str, float]:
    values = finite_profile(profile, response)
    if len(values) < 2:
        return {metric: math.nan for metric in PROFILE_METRICS}
    average = mean(values)
    energy = mean([(value - average) ** 2 for value in values])
    if abs(average) > 1e-15:
        energy /= average * average
    return {
        "terminal_contrast": values[-1] - values[0],
        "linear_slope": linear_slope(values),
        "cadence_peak": values[-1] - mean(values[:-1]),
        "profile_energy": energy,
        "profile_amplitude": max(values) - min(values),
    }


def shuffle_within_segments(
    values: Sequence[int], segments: Sequence[Segment], rng: Random
) -> list[int]:
    result = list(values)
    for segment in segments:
        shuffled = [result[index] for index in segment.stream_indices]
        rng.shuffle(shuffled)
        for index, value in zip(segment.stream_indices, shuffled):
            result[index] = value
    return result


def select_run_preserving_shifts(
    values: Sequence[int], requested: int, rng: Random
) -> tuple[list[int], dict[str, object]]:
    eligible = eligible_run_preserving_shifts(values)
    if not eligible:
        raise ValueError(
            "No nonzero run-preserving circular shifts are available. "
            "This can occur when both stream endpoints are active."
        )
    if requested >= len(eligible):
        selected = list(eligible)
        sampling = "complete_eligible_shift_space"
    else:
        selected = rng.sample(eligible, requested)
        sampling = "without_replacement"
    return selected, {
        "requested_permutations": requested,
        "used_permutations": len(selected),
        "eligible_nonzero_shifts": len(eligible),
        "rejected_run_splitting_or_merging_shifts": (
            len(values) - 1 - len(eligible)
        ),
        "sampling": sampling,
    }


def null_metrics_for_level(
    values: Sequence[int],
    segments: Sequence[Segment],
    config: RunConfig,
    seeds: Mapping[str, int],
) -> tuple[
    dict[str, dict[str, dict[str, list[float]]]],
    dict[str, object],
]:
    store: dict[str, dict[str, dict[str, list[float]]]] = {
        response: {
            RUN_PRESERVING_NULL: {metric: [] for metric in PROFILE_METRICS},
            WITHIN_SEGMENT_NULL: {metric: [] for metric in PROFILE_METRICS},
        }
        for response in RESPONSES
    }

    circular_rng = Random(seeds["circular_seed"])
    shifts, shift_audit = select_run_preserving_shifts(
        values, config.circular_permutations, circular_rng
    )
    for shift in shifts:
        shifted_profile = build_profile(
            circular_shift(values, shift),
            segments,
            config.bins,
            config.coordinate_mode,
            config.max_distance,
            config.aggregation,
            config.value_mode,
        )
        for response in RESPONSES:
            metrics = profile_metrics(shifted_profile, response)
            for metric in PROFILE_METRICS:
                store[response][RUN_PRESERVING_NULL][metric].append(metrics[metric])

    within_rng = Random(seeds["within_segment_seed"])
    for _ in range(config.within_permutations):
        shuffled_profile = build_profile(
            shuffle_within_segments(values, segments, within_rng),
            segments,
            config.bins,
            config.coordinate_mode,
            config.max_distance,
            config.aggregation,
            config.value_mode,
        )
        for response in RESPONSES:
            metrics = profile_metrics(shuffled_profile, response)
            for metric in PROFILE_METRICS:
                store[response][WITHIN_SEGMENT_NULL][metric].append(metrics[metric])

    return store, shift_audit


def metric_role(level: str, response: str, metric: str) -> str:
    if level == "verse":
        return "exploratory"
    if response == "mean_count" and metric == "terminal_contrast":
        return "primary"
    if response == "mean_count" and metric == "linear_slope":
        return "secondary"
    if response == "active_rate":
        return "robustness"
    return "descriptive"


def statistics_rows(
    book: str,
    level: str,
    response: str,
    observed: Mapping[str, float],
    nulls: Mapping[str, Mapping[str, Sequence[float]]],
    equivalence_profile: str,
    aggregation: str,
    value_mode: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for null_name in (RUN_PRESERVING_NULL, WITHIN_SEGMENT_NULL):
        for metric in PROFILE_METRICS:
            rows.append({
                "book": book,
                "level": level,
                "response": response,
                "metric_role": metric_role(level, response, metric),
                "metric": metric,
                "null": null_name,
                "permutations": len(nulls[null_name][metric]),
                "aggregation": aggregation,
                "value_mode": value_mode,
                "equivalence_profile": equivalence_profile,
                **empirical_summary(observed[metric], nulls[null_name][metric]),
            })
    return rows


def profile_rows(
    book: str,
    level: str,
    profile: Sequence[Mapping[str, object]],
    config: RunConfig,
    segment_count: int,
) -> list[dict[str, object]]:
    return [{
        "book": book,
        "level": level,
        "coordinate_mode": config.coordinate_mode,
        "aggregation": config.aggregation,
        "value_mode": config.value_mode,
        "equivalence_profile": config.equivalence_profile,
        "eligible_segments": segment_count,
        **row,
    } for row in profile]


def stat_lookup(
    rows: Sequence[Mapping[str, object]],
    level: str,
    response: str,
    metric: str,
    null_name: str,
) -> Mapping[str, object]:
    for row in rows:
        if (
            row["level"] == level
            and row["response"] == response
            and row["metric"] == metric
            and row["null"] == null_name
        ):
            return row
    raise KeyError((level, response, metric, null_name))


def analyze_book(book: str, config: RunConfig) -> dict[str, object]:
    source = locate_book(config.source_dir, book)
    input_audit = validate_input(source)
    rhyme_config = ProtocolConfig.from_profile(config.equivalence_profile)
    tokens, parse_audit = parse_book(source, rhyme_config)
    if len(tokens) <= config.window:
        raise ValueError(
            f"{book}: only {len(tokens)} analyzable tokens; window={config.window}"
        )

    comparison_cache: MutableMapping[ComparisonKey, str | None] = {}
    raw_values, full_values, bridge_values, pair_audit = build_arrival_stream(
        tokens,
        config.window,
        config.exclude_exact,
        config.match_filter,
        comparison_cache,
        collect_audit=True,
    )
    values = threshold_stream(raw_values, config.threshold)
    # Active runs touching a finite stream edge are observationally truncated.
    # Remove at most those two runs from profile inference so every circular
    # null shift preserves the complete collection of analyzed linear runs.
    profile_values, profile_edge_audit = censor_edge_runs(values)
    positions = list(range(config.window, len(tokens)))
    seeds = derive_seeds(config.base_seed, book)
    level_seeds = seeds["levels"]
    assert isinstance(level_seeds, dict)

    all_profiles: list[dict[str, object]] = []
    all_statistics: list[dict[str, object]] = []
    all_inventory: list[dict[str, object]] = []
    level_summaries: dict[str, object] = {}

    for level in LEVELS:
        segments, inventory_rows, coverage = segment_inventory(
            tokens,
            positions,
            level,
            config.min_segment_length,
            config.max_segment_length,
            config.exclude_cadence_word,
        )
        if not segments:
            raise ValueError(f"{book}/{level}: no complete eligible segments")
        for row in inventory_rows:
            all_inventory.append({"book": book, **row})

        profile = build_profile(
            profile_values,
            segments,
            config.bins,
            config.coordinate_mode,
            config.max_distance,
            config.aggregation,
            config.value_mode,
        )
        all_profiles.extend(
            profile_rows(book, level, profile, config, len(segments))
        )
        observed = {
            response: profile_metrics(profile, response) for response in RESPONSES
        }
        level_seed_values = level_seeds[level]
        assert isinstance(level_seed_values, dict)
        nulls, shift_audit = null_metrics_for_level(
            profile_values, segments, config, level_seed_values
        )
        for response in RESPONSES:
            all_statistics.extend(
                statistics_rows(
                    book,
                    level,
                    response,
                    observed[response],
                    nulls[response],
                    config.equivalence_profile,
                    config.aggregation,
                    config.value_mode,
                )
            )
        level_summaries[level] = {
            "coverage": coverage,
            "observed_profiles": observed,
            "run_preserving_shift_audit": shift_audit,
            "seeds": level_seed_values,
        }

    output_paths = {
        "arrival_stream": config.out_dir / f"{book}_arrival_stream.csv",
        "segment_inventory": config.out_dir / f"{book}_segment_inventory.csv",
        "profiles": config.out_dir / f"{book}_profiles.csv",
        "statistics": config.out_dir / f"{book}_statistics.csv",
        "summary": config.out_dir / f"{book}_summary.json",
    }
    stream_rows: list[dict[str, object]] = []
    for stream_i, (token_i, raw, analyzed, profile_value, full, bridge) in enumerate(
        zip(
            positions,
            raw_values,
            values,
            profile_values,
            full_values,
            bridge_values,
        ),
        start=1,
    ):
        token = tokens[token_i]
        stream_rows.append({
            "book": book,
            "equivalence_profile": config.equivalence_profile,
            "stream_index": stream_i,
            "token_index": token_i + 1,
            "source_word_index": token.source_word_index + 1,
            "word": token.word,
            "raw_arrival_count": raw,
            "analyzed_arrival_count": analyzed,
            "profile_inference_arrival_count": profile_value,
            "full_arrivals": full,
            "bridge_arrivals": bridge,
            "active": analyzed > 0,
            "edge_censored_for_profile": analyzed > 0 and profile_value == 0,
            "minor_id": token.minor_id,
            "major_id": token.major_id,
            "verse_id": token.verse_id,
            "taamim": ",".join(token.taamim),
        })
    write_csv(output_paths["arrival_stream"], stream_rows)
    write_csv(output_paths["segment_inventory"], all_inventory)
    write_csv(output_paths["profiles"], all_profiles)
    write_csv(output_paths["statistics"], all_statistics)

    summary: dict[str, object] = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "book": book,
        "input": input_audit,
        "tokens": len(tokens),
        "eligible_stream_positions": len(values),
        "raw_total_arrivals": sum(raw_values),
        "analyzed_total_arrivals": sum(values),
        "active_positions": sum(value > 0 for value in values),
        "active_rate": mean([float(value > 0) for value in values]),
        "profile_inference_total_arrivals": sum(profile_values),
        "profile_inference_active_positions": sum(
            value > 0 for value in profile_values
        ),
        "profile_inference_active_rate": mean(
            [float(value > 0) for value in profile_values]
        ),
        "profile_edge_audit": profile_edge_audit,
        "parameters": {
            "window_in_analyzable_stressed_tokens": config.window,
            "circular_permutations_requested": config.circular_permutations,
            "within_segment_permutations": config.within_permutations,
            "exclude_exact": config.exclude_exact,
            "match_filter": config.match_filter,
            "activity_threshold": config.threshold,
            "equivalence_profile": config.equivalence_profile,
            "equivalence_groups": [
                list(group)
                for group in EQUIVALENCE_GROUPS[config.equivalence_profile]
            ],
            "multigraphs": list(rhyme_config.multigraphs),
            "bins": config.bins,
            "coordinate_mode": config.coordinate_mode,
            "max_distance": config.max_distance,
            "aggregation": config.aggregation,
            "value_mode": config.value_mode,
            "exclude_cadence_word": config.exclude_cadence_word,
            "min_segment_length_before_cadence_exclusion": (
                config.min_segment_length
            ),
            "max_segment_length_before_cadence_exclusion": (
                config.max_segment_length
            ),
        },
        "seeds": seeds,
        "parse_audit": parse_audit,
        "pair_audit": pair_audit,
        "comparison_cache_entries": len(comparison_cache),
        "raw_arrival_histogram": dict(sorted(Counter(raw_values).items())),
        "analyzed_arrival_histogram": dict(sorted(Counter(values).items())),
        "levels": level_summaries,
    }
    output_paths["summary"].write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "profiles": all_profiles,
        "statistics": all_statistics,
        "inventory": all_inventory,
        "output_paths": [str(path) for path in output_paths.values()],
    }


def print_book_result(result: Mapping[str, object]) -> None:
    summary = result["summary"]
    statistics = result["statistics"]
    assert isinstance(summary, dict) and isinstance(statistics, list)
    print(
        f"\n{summary['book']:<12} stream={summary['eligible_stream_positions']:6d} "
        f"arrivals={summary['analyzed_total_arrivals']:6d} "
        f"profile_active_rate={summary['profile_inference_active_rate']:.4f}"
    )
    levels = summary["levels"]
    assert isinstance(levels, dict)
    for level in LEVELS:
        terminal = stat_lookup(
            statistics,
            level,
            "mean_count",
            "terminal_contrast",
            RUN_PRESERVING_NULL,
        )
        slope = stat_lookup(
            statistics,
            level,
            "mean_count",
            "linear_slope",
            RUN_PRESERVING_NULL,
        )
        level_summary = levels[level]
        assert isinstance(level_summary, dict)
        coverage = level_summary["coverage"]
        assert isinstance(coverage, dict)
        qualifier = " exploratory" if level == "verse" else ""
        print(
            f"  {level:<5}{qualifier:<12} "
            f"n={coverage['eligible_segments']:4d} "
            f"coverage={coverage['eligible_share_of_complete']:.3f} "
            f"terminal={terminal['observed']:+.4f} "
            f"Z={terminal['z']:+.2f} p={terminal['p_enrich']:.4g}; "
            f"slope={slope['observed']:+.4f} Z={slope['z']:+.2f}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--books", nargs="+", choices=BOOKS, default=list(BOOKS))
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--circular-permutations", type=int, default=1000)
    parser.add_argument("--within-permutations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--exclude-exact", action="store_true")
    parser.add_argument(
        "--match-filter", choices=("ALL", "FULL", "BRIDGE"), default="ALL"
    )
    parser.add_argument("--activity-threshold", type=int, default=1)
    parser.add_argument(
        "--equivalence-profile",
        default=DEFAULT_EQUIVALENCE_PROFILE,
        type=normalize_profile_name,
        choices=available_equivalence_profiles(),
    )
    parser.add_argument("--bins", type=int, default=5)
    parser.add_argument(
        "--coordinate-mode", choices=("normalized", "distance"), default="normalized"
    )
    parser.add_argument("--max-distance", type=int, default=7)
    parser.add_argument(
        "--aggregation", choices=("segment", "token"), default="segment"
    )
    parser.add_argument("--value-mode", choices=("raw", "share"), default="raw")
    parser.add_argument("--exclude-cadence-word", action="store_true")
    parser.add_argument("--min-segment-length", type=int, default=3)
    parser.add_argument("--max-segment-length", type=int, default=0)
    args = parser.parse_args(argv)

    positive = (
        args.window,
        args.circular_permutations,
        args.within_permutations,
        args.jobs,
        args.activity_threshold,
        args.bins,
        args.min_segment_length,
    )
    if any(value < 1 for value in positive):
        parser.error(
            "window, permutation counts, jobs, threshold, bins, and minimum "
            "segment length must be positive"
        )
    if args.max_distance < 0:
        parser.error("max-distance must be nonnegative")
    if args.max_segment_length < 0:
        parser.error("max-segment-length must be nonnegative")
    if (
        args.max_segment_length > 0
        and args.max_segment_length < args.min_segment_length
    ):
        parser.error("max-segment-length must be 0 or >= min-segment-length")
    if len(set(args.books)) != len(args.books):
        parser.error("--books must not contain duplicates")
    if args.coordinate_mode == "distance":
        args.bins = args.max_distance + 1
    return args


def main(argv: Sequence[str] | None = None) -> int:
    if UPSTREAM_ANALYSIS_VERSION != REQUIRED_UPSTREAM_VERSION:
        raise RuntimeError(
            f"{ANALYSIS_NAME} {ANALYSIS_VERSION} requires "
            f"rhyme_burst_architecture.py {REQUIRED_UPSTREAM_VERSION}; found "
            f"{UPSTREAM_ANALYSIS_VERSION}"
        )
    args = parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    config = RunConfig(
        source_dir=args.source_dir,
        out_dir=args.out_dir,
        window=args.window,
        circular_permutations=args.circular_permutations,
        within_permutations=args.within_permutations,
        base_seed=args.seed,
        exclude_exact=args.exclude_exact,
        match_filter=args.match_filter,
        threshold=args.activity_threshold,
        equivalence_profile=args.equivalence_profile,
        bins=args.bins,
        coordinate_mode=args.coordinate_mode,
        max_distance=args.max_distance,
        aggregation=args.aggregation,
        value_mode=args.value_mode,
        exclude_cadence_word=args.exclude_cadence_word,
        min_segment_length=args.min_segment_length,
        max_segment_length=args.max_segment_length,
    )

    print("=== BURST PROFILE INSIDE TAAM HIERARCHY v5 ===")
    print(f"run_label={args.run_label}")
    print(f"source={args.source_dir}")
    print(f"out={args.out_dir}")
    print(
        f"L={args.window} circular_perm={args.circular_permutations} "
        f"within_perm={args.within_permutations} jobs={args.jobs}"
    )
    print(
        f"profile={args.equivalence_profile} match_filter={args.match_filter} "
        f"exclude_exact={args.exclude_exact} threshold={args.activity_threshold}"
    )
    print(
        f"coordinate={args.coordinate_mode} bins={args.bins} "
        f"aggregation={args.aggregation} value_mode={args.value_mode} "
        f"exclude_cadence_word={args.exclude_cadence_word} "
        f"min_length={args.min_segment_length} max_length={args.max_segment_length}"
    )

    if args.jobs == 1 or len(args.books) == 1:
        results = [analyze_book(book, config) for book in args.books]
    else:
        workers = min(args.jobs, len(args.books))
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(analyze_book, book, config) for book in args.books]
            results = [future.result() for future in futures]

    results.sort(key=lambda result: BOOK_INDEX[result["summary"]["book"]])  # type: ignore[index]
    all_profiles: list[dict[str, object]] = []
    all_statistics: list[dict[str, object]] = []
    all_inventory: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    created_files: list[Path] = []
    for result in results:
        print_book_result(result)
        summaries.append(result["summary"])  # type: ignore[arg-type]
        all_profiles.extend(result["profiles"])  # type: ignore[arg-type]
        all_statistics.extend(result["statistics"])  # type: ignore[arg-type]
        all_inventory.extend(result["inventory"])  # type: ignore[arg-type]
        created_files.extend(
            Path(path) for path in result["output_paths"]  # type: ignore[arg-type]
        )

    aggregate_paths = {
        "profiles": args.out_dir / "ALL_profiles.csv",
        "statistics": args.out_dir / "ALL_statistics.csv",
        "segment_inventory": args.out_dir / "ALL_segment_inventory.csv",
        "summary": args.out_dir / "ALL_summary.json",
    }
    write_csv(aggregate_paths["profiles"], all_profiles)
    write_csv(aggregate_paths["statistics"], all_statistics)
    write_csv(aggregate_paths["segment_inventory"], all_inventory)
    aggregate_paths["summary"].write_text(
        json.dumps(json_safe(summaries), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    created_files.extend(aggregate_paths.values())

    analysis_path = Path(__file__).resolve()
    upstream_path = Path(upstream_module.__file__).resolve()
    shared_path = Path(shared_rhyme_module.__file__).resolve()
    run_metadata = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_protocol_version": ANALYSIS_PROTOCOL_VERSION,
        "run_label": args.run_label,
        "command_line": [sys.executable, *sys.argv],
        "books": [summary["book"] for summary in summaries],
        "parameters": {
            "source_dir": str(args.source_dir),
            "out_dir": str(args.out_dir),
            "window_in_analyzable_stressed_tokens": args.window,
            "circular_permutations_requested": args.circular_permutations,
            "within_segment_permutations": args.within_permutations,
            "base_seed": args.seed,
            "jobs": args.jobs,
            "exclude_exact": args.exclude_exact,
            "match_filter": args.match_filter,
            "activity_threshold": args.activity_threshold,
            "equivalence_profile": args.equivalence_profile,
            "bins": args.bins,
            "coordinate_mode": args.coordinate_mode,
            "max_distance": args.max_distance,
            "aggregation": args.aggregation,
            "value_mode": args.value_mode,
            "exclude_cadence_word": args.exclude_cadence_word,
            "min_segment_length_before_cadence_exclusion": (
                args.min_segment_length
            ),
            "max_segment_length_before_cadence_exclusion": (
                args.max_segment_length
            ),
        },
        "null_models": {
            "primary_alignment": RUN_PRESERVING_NULL,
            "secondary_internal_position": WITHIN_SEGMENT_NULL,
            "profile_edge_policy": (
                "censor active runs touching either finite stream edge before "
                "both profile nulls; retain them in arrival-stream audit"
            ),
        },
        "metric_roles": {
            "primary": (
                "mean_count terminal_contrast at minor and major levels"
            ),
            "secondary": "mean_count linear_slope at minor and major levels",
            "robustness": "active_rate profile metrics",
            "exploratory": "all verse-level inference",
            "descriptive": [
                "cadence_peak", "profile_energy", "profile_amplitude"
            ],
        },
        "software": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "code_and_protocol": {
            "analysis_file": str(analysis_path),
            "analysis_sha256": sha256_file(analysis_path),
            "upstream_analysis_file": str(upstream_path),
            "upstream_analysis_version": UPSTREAM_ANALYSIS_VERSION,
            "upstream_analysis_sha256": sha256_file(upstream_path),
            "shared_rhyme_module": str(shared_path),
            "shared_rhyme_module_sha256": sha256_file(shared_path),
            "shared_rhyme_protocol_version": SHARED_RHYME_PROTOCOL_VERSION,
            "markdown_protocol_runtime_dependency": False,
        },
        "available_equivalence_profiles": list(available_equivalence_profiles()),
        "inputs": [summary["input"] for summary in summaries],
        "book_seeds": {
            summary["book"]: summary["seeds"] for summary in summaries
        },
        "output_sha256": {
            str(path.relative_to(args.out_dir)): sha256_file(path)
            for path in sorted(created_files, key=lambda item: str(item))
        },
    }
    metadata_path = args.out_dir / "RUN_METADATA.json"
    metadata_path.write_text(
        json.dumps(json_safe(run_metadata), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"\nWROTE: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
