#!/usr/bin/env python3
"""Test local rhyme enrichment, burst clustering, and taam-boundary alignment.

The three inferential questions use separate null models:

1. LOCAL ENRICHMENT: shuffle tokens and recompute local rhyme arrivals.
2. BURST CLUSTERING: shuffle the observed thresholded arrival stream.
3. BOUNDARY ALIGNMENT: translate the observed stream by circular shifts that
   preserve the complete collection of linear active runs.

MAIN uses STRICT segmental identity from the shared rhyme protocol.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Iterable, MutableMapping, Sequence, TypeAlias

import shared.rhyme.rhyme_protocol as shared_rhyme_module  # type: ignore
from shared.rhyme import (  # type: ignore
    DEFAULT_EQUIVALENCE_PROFILE,
    ProtocolConfig,
    RhymeProtocolError,
    RhymeSignature,
    available_equivalence_profiles,
    compare_rhyme_signatures,
    extract_rhyme_signature,
    normalize_profile_name,
)

ANALYSIS_NAME = "rhyme_burst_architecture"
ANALYSIS_VERSION = "5.0.2"
SHARED_RHYME_PROTOCOL_VERSION = "4"
BOOKS = ("genesis", "exodus", "leviticus", "numbers", "deuteronomy")
BOOK_INDEX = {book: index for index, book in enumerate(BOOKS)}
ANNOT_RE = re.compile(r"^(.*?)(?:\[([^\]]+)\])?$")
MARKER_RE = re.compile(r"^\{([^}]+)\}$")

MINOR_TAAMIM = frozenset(
    {"revia", "zaqef_qatan", "zaqef_gadol", "shalshelet", "paseq"}
)
MAJOR_TAAMIM = frozenset({"atnah", "atnah_hafukh"})
VERSE_TAAMIM = frozenset({"sof_pasuq"})

LOCAL_ENRICHMENT_NULL = "shuffle_tokens_then_recompute"
BURST_CLUSTERING_NULL = "shuffle_observed_thresholded_arrival_stream"
BOUNDARY_ALIGNMENT_NULL = "run_preserving_circular_translation"

SignatureKey: TypeAlias = tuple[str, str | None]
ComparisonKey: TypeAlias = tuple[SignatureKey, SignatureKey]


@dataclass(frozen=True)
class ParsedWord:
    source_token: str
    word: str
    exact_word_key: str
    taamim: tuple[str, ...]
    signature: RhymeSignature | None


@dataclass(frozen=True)
class Token:
    index: int
    source_word_index: int
    verse_id: int
    major_id: int
    minor_id: int
    source_token: str
    word: str
    exact_word_key: str
    taamim: tuple[str, ...]
    signature: RhymeSignature


@dataclass(frozen=True)
class RunConfig:
    source_dir: Path
    out_dir: Path
    window: int
    enrichment_permutations: int
    clustering_permutations: int
    boundary_permutations: int
    base_seed: int
    exclude_exact: bool
    match_filter: str
    threshold: int
    equivalence_profile: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_combining(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if not unicodedata.combining(ch)
    ).casefold()


def unique_ordered(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip().casefold()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def validate_input(source: Path) -> dict[str, object]:
    metadata_path = source.with_name(source.name + ".meta.json")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Missing input metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    expected = metadata.get("output_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
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


def parse_book(path: Path, rhyme_config: ProtocolConfig) -> tuple[list[Token], dict[str, object]]:
    words: list[ParsedWord] = []
    structural_markers = 0
    external_markers_attached = 0
    orphan_structural_markers = 0
    missing_stress_tokens = 0

    for source_token in path.read_text(encoding="utf-8-sig").split():
        marker_match = MARKER_RE.fullmatch(source_token)
        if marker_match:
            structural_markers += 1
            marker = marker_match.group(1).strip().casefold()
            if words and marker in {"sof_pasuq", "paseq"}:
                last = words[-1]
                words[-1] = ParsedWord(
                    source_token=last.source_token,
                    word=last.word,
                    exact_word_key=last.exact_word_key,
                    taamim=unique_ordered((*last.taamim, marker)),
                    signature=last.signature,
                )
                external_markers_attached += 1
            else:
                orphan_structural_markers += 1
            continue

        match = ANNOT_RE.fullmatch(source_token)
        if not match:
            raise ValueError(f"Unparseable source token in {path}: {source_token!r}")
        taamim = unique_ordered((match.group(2) or "").split(","))
        try:
            signature = extract_rhyme_signature(source_token, config=rhyme_config)
        except RhymeProtocolError as exc:
            if not str(exc).startswith("No stressed vowel found"):
                raise
            signature = None
            missing_stress_tokens += 1
        clean = match.group(1)
        words.append(ParsedWord(
            source_token=source_token,
            word=signature.word if signature is not None else clean,
            exact_word_key=strip_combining(signature.word if signature is not None else clean),
            taamim=taamim,
            signature=signature,
        ))

    verse_id = major_id = minor_id = 1
    tokens: list[Token] = []
    projected = Counter()
    source_boundary_counts = Counter()
    for source_word_index, item in enumerate(words):
        if item.signature is not None:
            tokens.append(Token(
                index=len(tokens),
                source_word_index=source_word_index,
                verse_id=verse_id,
                major_id=major_id,
                minor_id=minor_id,
                source_token=item.source_token,
                word=item.word,
                exact_word_key=item.exact_word_key,
                taamim=item.taamim,
                signature=item.signature,
            ))
        signs = set(item.taamim)
        boundary_level: str | None = None
        if signs & VERSE_TAAMIM:
            boundary_level = "verse"
            source_boundary_counts["verse"] += 1
            source_boundary_counts["major"] += 1
            source_boundary_counts["minor"] += 1
            verse_id += 1
            major_id += 1
            minor_id += 1
        elif signs & MAJOR_TAAMIM:
            boundary_level = "major"
            source_boundary_counts["major"] += 1
            source_boundary_counts["minor"] += 1
            major_id += 1
            minor_id += 1
        elif signs & MINOR_TAAMIM:
            boundary_level = "minor"
            source_boundary_counts["minor"] += 1
            minor_id += 1
        if boundary_level is not None and item.signature is None:
            projected[boundary_level] += 1

    if not tokens:
        raise ValueError(f"No analyzable stressed tokens in {path}")
    return tokens, {
        "source_word_tokens": len(words),
        "analyzable_stressed_tokens": len(tokens),
        "missing_stress_tokens": missing_stress_tokens,
        "structural_markers": structural_markers,
        "external_markers_attached": external_markers_attached,
        "orphan_structural_markers": orphan_structural_markers,
        "source_boundary_counts_nested": dict(source_boundary_counts),
        "boundaries_after_unanalyzable_words": dict(projected),
        "boundary_projection_note": (
            "A boundary after an unanalyzable word lies between the adjacent retained "
            "tokens in the stressed-token stream; each such projection is counted here."
        ),
        "verses_in_analyzable_stream": len({token.verse_id for token in tokens}),
        "major_blocks_in_analyzable_stream": len({token.major_id for token in tokens}),
        "minor_blocks_in_analyzable_stream": len({token.minor_id for token in tokens}),
    }


def compact_signature_key(signature: RhymeSignature) -> SignatureKey:
    return (signature.primary_key, signature.bridge_key)


def rhyme_kind(
    source: Token,
    target: Token,
    cache: MutableMapping[ComparisonKey, str | None] | None,
) -> str | None:
    key = (compact_signature_key(source.signature), compact_signature_key(target.signature))
    if cache is not None and key in cache:
        return cache[key]
    result = compare_rhyme_signatures(source.signature, target.signature)
    kind = str(result.match_type) if result.rhymes else None
    if cache is not None:
        cache[key] = kind
        cache[(key[1], key[0])] = kind
    return kind


def build_arrival_stream(
    tokens: Sequence[Token],
    window: int,
    exclude_exact: bool,
    match_filter: str,
    comparison_cache: MutableMapping[ComparisonKey, str | None] | None = None,
    collect_audit: bool = True,
) -> tuple[list[int], list[int], list[int], dict[str, int]]:
    counts: list[int] = []
    full_counts: list[int] = []
    bridge_counts: list[int] = []
    audit = Counter()
    for j in range(window, len(tokens)):
        target = tokens[j]
        full = bridge = 0
        for i in range(j - window, j):
            source = tokens[i]
            exact = source.exact_word_key == target.exact_word_key
            if exclude_exact and exact:
                if collect_audit:
                    audit["exact_word_pairs_excluded"] += 1
                continue
            if collect_audit:
                audit["eligible_pairs"] += 1
            kind = rhyme_kind(source, target, comparison_cache)
            if kind is None:
                continue
            if collect_audit and exact:
                audit["exact_word_rhyme_pairs_included"] += 1
            if kind == "FULL":
                full += 1
                if collect_audit:
                    audit["full_pairs"] += 1
            elif kind == "BRIDGE":
                bridge += 1
                if collect_audit:
                    audit["bridge_pairs"] += 1
        full_counts.append(full)
        bridge_counts.append(bridge)
        if match_filter == "FULL":
            counts.append(full)
        elif match_filter == "BRIDGE":
            counts.append(bridge)
        else:
            counts.append(full + bridge)
    for key in (
        "eligible_pairs", "exact_word_pairs_excluded",
        "exact_word_rhyme_pairs_included", "full_pairs", "bridge_pairs",
    ):
        audit.setdefault(key, 0)
    return counts, full_counts, bridge_counts, dict(audit)


def threshold_stream(values: Sequence[int], threshold: int) -> list[int]:
    return [value if value >= threshold else 0 for value in values]


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def variance(values: Sequence[float], mu: float | None = None) -> float:
    if not values:
        return math.nan
    center = mean(values) if mu is None else mu
    return sum((value - center) ** 2 for value in values) / len(values)


def correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or len(left) != len(right):
        return math.nan
    left_mean, right_mean = mean(left), mean(right)
    left_var, right_var = variance(left, left_mean), variance(right, right_mean)
    if left_var <= 0 or right_var <= 0:
        return 0.0
    covariance = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    ) / len(left)
    return covariance / math.sqrt(left_var * right_var)


def lag_corr(values: Sequence[int], lag: int) -> float:
    return math.nan if len(values) <= lag else correlation(values[:-lag], values[lag:])


def active_runs(values: Sequence[int]) -> list[tuple[int, int, int, int]]:
    """Return (start, end_exclusive, length, intensity) for positive runs."""
    runs: list[tuple[int, int, int, int]] = []
    start: int | None = None
    intensity = 0
    for index, value in enumerate(values):
        if value > 0 and start is None:
            start = index
            intensity = value
        elif value > 0:
            intensity += value
        elif start is not None:
            runs.append((start, index, index - start, intensity))
            start = None
            intensity = 0
    if start is not None:
        runs.append((start, len(values), len(values) - start, intensity))
    return runs


def window_fano(values: Sequence[int], width: int) -> float:
    if width <= 0 or len(values) < width:
        return math.nan
    # Non-overlapping windows avoid treating nearly identical shifted windows
    # as independent observations. An incomplete final window is omitted.
    totals = [
        sum(values[start:start + width])
        for start in range(0, len(values) - width + 1, width)
    ]
    mu = mean(totals)
    return variance(totals, mu) / mu if mu > 0 else 0.0


def temporal_metrics(values: Sequence[int]) -> dict[str, float]:
    active = [int(value > 0) for value in values]
    runs = active_runs(values)
    active_rate = mean(active)
    adjacent = sum(active[index] and active[index + 1] for index in range(len(active) - 1))
    active_predecessors = sum(active[:-1])
    conditional = adjacent / active_predecessors if active_predecessors else 0.0
    return {
        "mean_arrivals": mean(values),
        "active_rate": active_rate,
        "active_lag1_corr": lag_corr(active, 1),
        "active_lag2_corr": lag_corr(active, 2),
        "count_lag1_corr": lag_corr(values, 1),
        "count_lag2_corr": lag_corr(values, 2),
        "count_lag5_corr": lag_corr(values, 5),
        "adjacent_active_ratio": conditional / active_rate if active_rate > 0 else 0.0,
        "run_count": float(len(runs)),
        "mean_run_length": mean([float(run[2]) for run in runs]) if runs else 0.0,
        "max_run_length": float(max((run[2] for run in runs), default=0)),
        "mean_run_intensity": mean([float(run[3]) for run in runs]) if runs else 0.0,
        "fano_w5": window_fano(values, 5),
        "fano_w10": window_fano(values, 10),
        "fano_w20": window_fano(values, 20),
    }


def boundary_metrics(
    values: Sequence[int], positions: Sequence[int], tokens: Sequence[Token]
) -> dict[str, float]:
    metric_names = (
        "run_contained_minor", "run_contained_major", "run_contained_verse",
        "run_ends_minor_boundary", "run_ends_major_boundary", "run_ends_verse_boundary",
        "run_starts_after_minor_boundary", "run_starts_after_major_boundary",
        "run_starts_after_verse_boundary",
    )
    runs = active_runs(values)
    if not runs:
        return {name: 0.0 for name in metric_names}
    totals = Counter()
    for start, end, _, _ in runs:
        absolute = positions[start:end]
        first, last = absolute[0], absolute[-1]
        totals["run_contained_minor"] += len({tokens[pos].minor_id for pos in absolute}) == 1
        totals["run_contained_major"] += len({tokens[pos].major_id for pos in absolute}) == 1
        totals["run_contained_verse"] += len({tokens[pos].verse_id for pos in absolute}) == 1
        if last + 1 < len(tokens):
            totals["run_ends_minor_boundary"] += tokens[last].minor_id != tokens[last + 1].minor_id
            totals["run_ends_major_boundary"] += tokens[last].major_id != tokens[last + 1].major_id
            totals["run_ends_verse_boundary"] += tokens[last].verse_id != tokens[last + 1].verse_id
        if first > 0:
            totals["run_starts_after_minor_boundary"] += tokens[first - 1].minor_id != tokens[first].minor_id
            totals["run_starts_after_major_boundary"] += tokens[first - 1].major_id != tokens[first].major_id
            totals["run_starts_after_verse_boundary"] += tokens[first - 1].verse_id != tokens[first].verse_id
    return {name: totals[name] / len(runs) for name in metric_names}


def circular_shift(values: Sequence[int], shift: int) -> list[int]:
    if not values:
        return []
    normalized = shift % len(values)
    return list(values[-normalized:] + values[:-normalized]) if normalized else list(values)


def eligible_run_preserving_shifts(values: Sequence[int]) -> list[int]:
    """Return nonzero shifts that neither split nor merge a positive run."""
    size = len(values)
    if size < 2:
        return []
    # A rotation makes the original endpoints adjacent. If both are active,
    # every ordinary cut merges those endpoint runs, so no shift is admitted.
    if values[0] > 0 and values[-1] > 0:
        return []
    eligible: list[int] = []
    for shift in range(1, size):
        cut = size - shift
        if not (values[cut - 1] > 0 and values[cut] > 0):
            eligible.append(shift)
    return eligible


def censor_edge_runs(values: Sequence[int]) -> tuple[list[int], dict[str, int]]:
    """Remove runs touching stream edges for the boundary-location test only.

    Such runs are observationally truncated and cannot always be circularly
    translated without merging. Enrichment and clustering retain the full
    stream; only boundary alignment uses this edge-censored copy.
    """
    result = list(values)
    censored_positions: set[int] = set()
    index = 0
    while index < len(result) and result[index] > 0:
        censored_positions.add(index)
        index += 1
    index = len(result) - 1
    while index >= 0 and result[index] > 0:
        censored_positions.add(index)
        index -= 1
    censored_arrivals = sum(result[index] for index in censored_positions)
    for index in censored_positions:
        result[index] = 0
    edge_runs = int(bool(values and values[0] > 0)) + int(
        bool(values and values[-1] > 0)
    )
    # A fully active stream is one run, not two.
    if values and all(value > 0 for value in values):
        edge_runs = 1
    return result, {
        "edge_runs_censored": edge_runs,
        "edge_positions_censored": len(censored_positions),
        "edge_arrivals_censored": censored_arrivals,
    }


def select_boundary_shifts(
    values: Sequence[int], requested: int, rng: Random
) -> tuple[list[int], dict[str, int | str]]:
    eligible = eligible_run_preserving_shifts(values)
    if not eligible:
        raise ValueError("No nonzero run-preserving circular shifts are available")
    if requested >= len(eligible):
        selected = list(eligible)
        rng.shuffle(selected)
        sampling = "complete_eligible_shift_space"
    else:
        selected = rng.sample(eligible, requested)
        sampling = "without_replacement"
    return selected, {
        "requested_permutations": requested,
        "used_permutations": len(selected),
        "eligible_nonzero_shifts": len(eligible),
        "rejected_run_splitting_or_merging_shifts": (len(values) - 1) - len(eligible),
        "sampling": sampling,
    }


def empirical_summary(observed: float, null_values: Sequence[float]) -> dict[str, float]:
    finite = [value for value in null_values if math.isfinite(value)]
    if not math.isfinite(observed) or not finite:
        return {
            "observed": observed, "null_mean": math.nan, "difference": math.nan,
            "fold": math.nan, "null_sd": math.nan, "z": math.nan,
            "p_enrich": math.nan, "p_deplete": math.nan, "p_two_sided": math.nan,
        }
    null_mean = mean(finite)
    sd = math.sqrt(variance(finite, null_mean))
    ge = sum(value >= observed for value in finite)
    le = sum(value <= observed for value in finite)
    p_enrich = (ge + 1) / (len(finite) + 1)
    p_deplete = (le + 1) / (len(finite) + 1)
    return {
        "observed": observed,
        "null_mean": null_mean,
        "difference": observed - null_mean,
        "fold": observed / null_mean if null_mean != 0 else math.nan,
        "null_sd": sd,
        "z": (observed - null_mean) / sd if sd > 0 else math.nan,
        "p_enrich": p_enrich,
        "p_deplete": p_deplete,
        "p_two_sided": min(1.0, 2 * min(p_enrich, p_deplete)),
    }


def metric_role(family: str, metric: str) -> str:
    if family == "local_rhyme_enrichment":
        return "primary" if metric == "mean_arrivals" else "secondary"
    if family == "burst_clustering":
        if metric in {"active_lag1_corr", "fano_w10"}:
            return "primary"
        if metric == "max_run_length":
            return "descriptive"
        return "secondary"
    if family == "boundary_alignment":
        return "primary" if metric.startswith("run_ends_") else "secondary"
    raise ValueError(f"Unknown metric family: {family}")


def statistics_rows(
    book: str,
    profile: str,
    family: str,
    null_name: str,
    observed: dict[str, float],
    nulls: dict[str, list[float]],
    selected_metrics: Sequence[str],
) -> list[dict[str, object]]:
    return [
        {
            "book": book,
            "equivalence_profile": profile,
            "family": family,
            "metric_role": metric_role(family, metric),
            "metric": metric,
            "null": null_name,
            "permutations": len(nulls[metric]),
            **empirical_summary(observed[metric], nulls[metric]),
        }
        for metric in selected_metrics
    ]


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
    """Convert non-finite floats to JSON null and recurse through containers."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def locate_book(source_dir: Path, book: str) -> Path:
    candidates = (
        f"{book}_taamim_annotated.txt",
        f"{book}_taam_annotated.txt",
        f"{book}.txt",
    )
    for name in candidates:
        path = source_dir / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"Could not locate input for {book} under {source_dir}")


def derive_seeds(base_seed: int, book: str) -> dict[str, int]:
    book_offset = BOOK_INDEX[book] * 1_000_003
    return {
        "base_seed": base_seed,
        "book_index": BOOK_INDEX[book],
        "enrichment_seed": base_seed + book_offset + 101,
        "clustering_seed": base_seed + book_offset + 211,
        "boundary_seed": base_seed + book_offset + 307,
    }


def analyze_book(book: str, config: RunConfig) -> dict[str, object]:
    source = locate_book(config.source_dir, book)
    input_audit = validate_input(source)
    rhyme_config = ProtocolConfig.from_profile(config.equivalence_profile)
    tokens, parse_audit = parse_book(source, rhyme_config)
    if len(tokens) <= config.window:
        raise ValueError(f"{book}: only {len(tokens)} analyzable tokens; window={config.window}")

    comparison_cache: dict[ComparisonKey, str | None] = {}
    raw_values, full_values, bridge_values, pair_audit = build_arrival_stream(
        tokens, config.window, config.exclude_exact, config.match_filter,
        comparison_cache, collect_audit=True,
    )
    values = threshold_stream(raw_values, config.threshold)
    positions = list(range(config.window, len(tokens)))
    observed_temporal = temporal_metrics(values)
    boundary_values, boundary_edge_audit = censor_edge_runs(values)
    observed_boundary = boundary_metrics(boundary_values, positions, tokens)
    seeds = derive_seeds(config.base_seed, book)

    enrichment_metrics = ("mean_arrivals", "active_rate")
    clustering_metrics = tuple(
        metric for metric in observed_temporal if metric not in enrichment_metrics
    )
    enrichment_nulls = {metric: [] for metric in enrichment_metrics}
    clustering_nulls = {metric: [] for metric in clustering_metrics}
    boundary_nulls = {metric: [] for metric in observed_boundary}

    enrichment_rng = Random(seeds["enrichment_seed"])
    work_tokens = list(tokens)
    for _ in range(config.enrichment_permutations):
        enrichment_rng.shuffle(work_tokens)
        perm_raw, _, _, _ = build_arrival_stream(
            work_tokens, config.window, config.exclude_exact, config.match_filter,
            comparison_cache, collect_audit=False,
        )
        perm_metrics = temporal_metrics(threshold_stream(perm_raw, config.threshold))
        for metric in enrichment_metrics:
            enrichment_nulls[metric].append(perm_metrics[metric])

    clustering_rng = Random(seeds["clustering_seed"])
    work_values = list(values)
    for _ in range(config.clustering_permutations):
        clustering_rng.shuffle(work_values)
        perm_metrics = temporal_metrics(work_values)
        for metric in clustering_metrics:
            clustering_nulls[metric].append(perm_metrics[metric])

    boundary_rng = Random(seeds["boundary_seed"])
    selected_shifts, boundary_shift_audit = select_boundary_shifts(
        boundary_values, config.boundary_permutations, boundary_rng
    )
    for shift in selected_shifts:
        shifted_metrics = boundary_metrics(
            circular_shift(boundary_values, shift), positions, tokens
        )
        for metric, value in shifted_metrics.items():
            boundary_nulls[metric].append(value)

    enrichment_rows = statistics_rows(
        book, config.equivalence_profile, "local_rhyme_enrichment",
        LOCAL_ENRICHMENT_NULL, observed_temporal, enrichment_nulls,
        enrichment_metrics,
    )
    clustering_rows = statistics_rows(
        book, config.equivalence_profile, "burst_clustering",
        BURST_CLUSTERING_NULL, observed_temporal, clustering_nulls,
        clustering_metrics,
    )
    boundary_rows = statistics_rows(
        book, config.equivalence_profile, "boundary_alignment",
        BOUNDARY_ALIGNMENT_NULL, observed_boundary, boundary_nulls,
        tuple(observed_boundary),
    )

    stream_rows: list[dict[str, object]] = []
    for local_index, position in enumerate(positions):
        token = tokens[position]
        stream_rows.append({
            "book": book,
            "equivalence_profile": config.equivalence_profile,
            "stream_index": local_index + 1,
            "token_index": position + 1,
            "source_word_index": token.source_word_index + 1,
            "word": token.word,
            "raw_arrival_count": raw_values[local_index],
            "analyzed_arrival_count": values[local_index],
            "full_arrivals": full_values[local_index],
            "bridge_arrivals": bridge_values[local_index],
            "active": int(values[local_index] > 0),
            "verse_id": token.verse_id,
            "major_id": token.major_id,
            "minor_id": token.minor_id,
            "taamim": ",".join(token.taamim),
        })

    burst_rows: list[dict[str, object]] = []
    boundary_run_keys = {
        (start, end) for start, end, _, _ in active_runs(boundary_values)
    }
    for run_id, (start, end, length, intensity) in enumerate(active_runs(values), start=1):
        absolute = positions[start:end]
        first, last = absolute[0], absolute[-1]
        burst_rows.append({
            "book": book,
            "equivalence_profile": config.equivalence_profile,
            "run_id": run_id,
            "first_token": first + 1,
            "last_token": last + 1,
            "length": length,
            "intensity": intensity,
            "included_in_boundary_test": int((start, end) in boundary_run_keys),
            "contained_minor": int(len({tokens[pos].minor_id for pos in absolute}) == 1),
            "contained_major": int(len({tokens[pos].major_id for pos in absolute}) == 1),
            "contained_verse": int(len({tokens[pos].verse_id for pos in absolute}) == 1),
            "ends_minor_boundary": int(
                last + 1 < len(tokens) and tokens[last].minor_id != tokens[last + 1].minor_id
            ),
            "ends_major_boundary": int(
                last + 1 < len(tokens) and tokens[last].major_id != tokens[last + 1].major_id
            ),
            "ends_verse_boundary": int(
                last + 1 < len(tokens) and tokens[last].verse_id != tokens[last + 1].verse_id
            ),
            "words": " | ".join(tokens[pos].word for pos in absolute),
        })

    prefix = config.out_dir / book
    output_paths = {
        "arrival_stream": prefix.with_name(f"{book}_arrival_stream.csv"),
        "bursts": prefix.with_name(f"{book}_bursts.csv"),
        "local_enrichment": prefix.with_name(f"{book}_local_enrichment_statistics.csv"),
        "burst_clustering": prefix.with_name(f"{book}_burst_clustering_statistics.csv"),
        "boundary_alignment": prefix.with_name(f"{book}_boundary_alignment_statistics.csv"),
        "summary": prefix.with_name(f"{book}_summary.json"),
    }
    write_csv(output_paths["arrival_stream"], stream_rows)
    write_csv(output_paths["bursts"], burst_rows)
    write_csv(output_paths["local_enrichment"], enrichment_rows)
    write_csv(output_paths["burst_clustering"], clustering_rows)
    write_csv(output_paths["boundary_alignment"], boundary_rows)

    active = [int(value > 0) for value in values]
    summary: dict[str, object] = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "book": book,
        "input": input_audit,
        "tokens": len(tokens),
        "eligible_stream_positions": len(values),
        "equivalence_profile": config.equivalence_profile,
        "raw_total_arrivals": sum(raw_values),
        "analyzed_total_arrivals": sum(values),
        "active_positions": sum(active),
        "active_rate": mean(active),
        "raw_arrival_histogram": dict(sorted(Counter(raw_values).items())),
        "analyzed_arrival_histogram": dict(sorted(Counter(values).items())),
        "parameters": {
            "window_in_analyzable_stressed_tokens": config.window,
            "enrichment_permutations": config.enrichment_permutations,
            "clustering_permutations": config.clustering_permutations,
            "boundary_permutations_requested": config.boundary_permutations,
            "exclude_exact": config.exclude_exact,
            "match_filter": config.match_filter,
            "activity_threshold": config.threshold,
            "equivalence_profile": config.equivalence_profile,
            "equivalence_map": dict(rhyme_config.equivalences),
        },
        "null_models": {
            "local_rhyme_enrichment": LOCAL_ENRICHMENT_NULL,
            "burst_clustering": BURST_CLUSTERING_NULL,
            "boundary_alignment": BOUNDARY_ALIGNMENT_NULL,
        },
        "seeds": seeds,
        "parse_audit": parse_audit,
        "pair_audit": pair_audit,
        "boundary_edge_audit": boundary_edge_audit,
        "boundary_shift_audit": boundary_shift_audit,
        "comparison_cache_entries": len(comparison_cache),
        "local_rhyme_enrichment": {row["metric"]: row for row in enrichment_rows},
        "burst_clustering": {row["metric"]: row for row in clustering_rows},
        "boundary_alignment": {row["metric"]: row for row in boundary_rows},
    }
    output_paths["summary"].write_text(
        json.dumps(json_safe(summary), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "enrichment_rows": enrichment_rows,
        "clustering_rows": clustering_rows,
        "boundary_rows": boundary_rows,
        "output_paths": [str(path) for path in output_paths.values()],
    }


def print_book_result(result: dict[str, object]) -> None:
    summary = result["summary"]
    assert isinstance(summary, dict)
    enrichment = summary["local_rhyme_enrichment"]
    clustering = summary["burst_clustering"]
    boundary = summary["boundary_alignment"]
    assert isinstance(enrichment, dict) and isinstance(clustering, dict) and isinstance(boundary, dict)
    mean_row = enrichment["mean_arrivals"]
    active_row = clustering["active_lag1_corr"]
    fano_row = clustering["fano_w10"]
    print(
        f"\n{summary['book']:<12} tokens={summary['tokens']:6d} "
        f"positions={summary['eligible_stream_positions']:6d} "
        f"arrivals={summary['analyzed_total_arrivals']:6d} "
        f"active_rate={summary['active_rate']:.4f}"
    )
    print(
        "  enrichment: "
        f"mean={mean_row['observed']:.4f} null={mean_row['null_mean']:.4f} "
        f"Z={mean_row['z']:.2f} p={mean_row['p_enrich']:.4g}"
    )
    print(
        "  clustering: "
        f"active_lag1 Z={active_row['z']:.2f} p={active_row['p_enrich']:.4g}; "
        f"Fano-10 Z={fano_row['z']:.2f} p={fano_row['p_enrich']:.4g}"
    )
    endings = []
    for level in ("minor", "major", "verse"):
        row = boundary[f"run_ends_{level}_boundary"]
        endings.append(f"{level}={row['observed']:.3f} Z={row['z']:.2f}")
    print("  run endings: " + "; ".join(endings))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--books", nargs="+", choices=BOOKS, default=list(BOOKS))
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--enrichment-permutations", type=int, default=500)
    parser.add_argument("--clustering-permutations", type=int, default=500)
    parser.add_argument("--boundary-permutations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--exclude-exact", action="store_true")
    parser.add_argument("--match-filter", choices=("ALL", "FULL", "BRIDGE"), default="ALL")
    parser.add_argument("--activity-threshold", type=int, default=1)
    parser.add_argument(
        "--equivalence-profile",
        default=DEFAULT_EQUIVALENCE_PROFILE,
        type=normalize_profile_name,
        choices=available_equivalence_profiles(),
    )
    args = parser.parse_args(argv)
    positive = (
        args.window, args.enrichment_permutations, args.clustering_permutations,
        args.boundary_permutations, args.jobs, args.activity_threshold,
    )
    if any(value < 1 for value in positive):
        parser.error("window, permutation counts, jobs, and activity-threshold must be positive")
    if len(set(args.books)) != len(args.books):
        parser.error("--books must not contain duplicates")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    config = RunConfig(
        source_dir=args.source_dir,
        out_dir=args.out_dir,
        window=args.window,
        enrichment_permutations=args.enrichment_permutations,
        clustering_permutations=args.clustering_permutations,
        boundary_permutations=args.boundary_permutations,
        base_seed=args.seed,
        exclude_exact=args.exclude_exact,
        match_filter=args.match_filter,
        threshold=args.activity_threshold,
        equivalence_profile=args.equivalence_profile,
    )

    print("=== RHYME BURST ARCHITECTURE v5 ===")
    print(f"run_label={args.run_label}")
    print(f"source={args.source_dir}")
    print(f"out={args.out_dir}")
    print(
        f"L={args.window} enrichment_perm={args.enrichment_permutations} "
        f"clustering_perm={args.clustering_permutations} "
        f"boundary_perm={args.boundary_permutations} jobs={args.jobs}"
    )
    print(
        f"profile={args.equivalence_profile} match_filter={args.match_filter} "
        f"exclude_exact={args.exclude_exact} threshold={args.activity_threshold}"
    )

    if args.jobs == 1 or len(args.books) == 1:
        results = [analyze_book(book, config) for book in args.books]
    else:
        worker_count = min(args.jobs, len(args.books))
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(analyze_book, book, config) for book in args.books]
            results = [future.result() for future in futures]

    all_enrichment: list[dict[str, object]] = []
    all_clustering: list[dict[str, object]] = []
    all_boundary: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    created_files: list[Path] = []
    for result in results:
        print_book_result(result)
        summaries.append(result["summary"])  # type: ignore[arg-type]
        all_enrichment.extend(result["enrichment_rows"])  # type: ignore[arg-type]
        all_clustering.extend(result["clustering_rows"])  # type: ignore[arg-type]
        all_boundary.extend(result["boundary_rows"])  # type: ignore[arg-type]
        created_files.extend(Path(path) for path in result["output_paths"])  # type: ignore[arg-type]

    aggregate_paths = {
        "all_local_enrichment": args.out_dir / "ALL_local_enrichment_statistics.csv",
        "all_burst_clustering": args.out_dir / "ALL_burst_clustering_statistics.csv",
        "all_boundary_alignment": args.out_dir / "ALL_boundary_alignment_statistics.csv",
        "all_summary": args.out_dir / "ALL_summary.json",
    }
    write_csv(aggregate_paths["all_local_enrichment"], all_enrichment)
    write_csv(aggregate_paths["all_burst_clustering"], all_clustering)
    write_csv(aggregate_paths["all_boundary_alignment"], all_boundary)
    aggregate_paths["all_summary"].write_text(
        json.dumps(json_safe(summaries), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    created_files.extend(aggregate_paths.values())

    analysis_path = Path(__file__).resolve()
    shared_module_path = Path(shared_rhyme_module.__file__).resolve()
    run_metadata = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "run_label": args.run_label,
        "command_line": [sys.executable, *sys.argv],
        "books": list(args.books),
        "available_equivalence_profiles": list(available_equivalence_profiles()),
        "parameters": {
            "source_dir": str(args.source_dir),
            "out_dir": str(args.out_dir),
            "window_in_analyzable_stressed_tokens": args.window,
            "enrichment_permutations": args.enrichment_permutations,
            "clustering_permutations": args.clustering_permutations,
            "boundary_permutations_requested": args.boundary_permutations,
            "base_seed": args.seed,
            "jobs": args.jobs,
            "exclude_exact": args.exclude_exact,
            "match_filter": args.match_filter,
            "activity_threshold": args.activity_threshold,
            "equivalence_profile": args.equivalence_profile,
        },
        "null_models": {
            "local_rhyme_enrichment": LOCAL_ENRICHMENT_NULL,
            "burst_clustering": BURST_CLUSTERING_NULL,
            "boundary_alignment": BOUNDARY_ALIGNMENT_NULL,
        },
        "primary_metrics": {
            "local_rhyme_enrichment": ["mean_arrivals"],
            "burst_clustering": ["active_lag1_corr", "fano_w10"],
            "boundary_alignment": [
                "run_ends_minor_boundary", "run_ends_major_boundary",
                "run_ends_verse_boundary",
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
            "shared_rhyme_module": str(shared_module_path),
            "shared_rhyme_module_sha256": sha256_file(shared_module_path),
            "shared_rhyme_protocol_version": SHARED_RHYME_PROTOCOL_VERSION,
        },
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
