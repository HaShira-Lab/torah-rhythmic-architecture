#!/usr/bin/env python3
"""Additional robustness controls for the rhyme-cadence study.

This companion analysis leaves the frozen MAIN definitions unchanged and runs
three explicitly labelled sensitivity checks:

1. boundary_no_paseq: remove paseq only from the operational MINOR boundary
   set and recompute the distribution/alignment analysis;
2. exclude_extended_left: exclude every rhyme link involving a token whose
   primary signature was extended one segment left because stress fell on the
   final phonetic segment, then recompute both the burst and distribution
   analyses;
3. verse_allocation_null: condition on the observed number of marked positions
   and the canonical verse sizes, and randomly allocate activity marks or burst
   ends among eligible positions within each book.

The wrapper requires the frozen core versions used by the manuscript and runs
patched controls with jobs=1 so that the declared modifications remain local
and deterministic on Windows as well as POSIX systems.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

import analyses.core_rhyme.rhyme_burst_architecture as burst  # type: ignore
import analyses.core_rhyme.rhyme_cadence_distribution_robustness as dist  # type: ignore


ANALYSIS_NAME = "rhyme_cadence_additional_controls"
ANALYSIS_VERSION = "1.0.0"
REQUIRED_BURST_VERSION = "5.0.2"
REQUIRED_DISTRIBUTION_VERSION = "1.0.1"
BOOKS = tuple(burst.BOOKS)
BOOK_INDEX = dict(burst.BOOK_INDEX)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not rows:
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def empirical_summary(observed: float, null: np.ndarray) -> dict[str, float]:
    mean = float(null.mean())
    sd = float(null.std(ddof=1)) if len(null) > 1 else math.nan
    z = (observed - mean) / sd if sd > 0 else math.nan
    ge = int(np.count_nonzero(null >= observed))
    le = int(np.count_nonzero(null <= observed))
    p_enrich = (ge + 1.0) / (len(null) + 1.0)
    p_deplete = (le + 1.0) / (len(null) + 1.0)
    return {
        "observed": observed,
        "null_mean": mean,
        "difference": observed - mean,
        "null_sd": sd,
        "z": z,
        "p_enrich": p_enrich,
        "p_deplete": p_deplete,
        "p_two_sided": min(1.0, 2.0 * min(p_enrich, p_deplete)),
        "null_q025": float(np.quantile(null, 0.025)),
        "null_q975": float(np.quantile(null, 0.975)),
    }


def distribution_args(source_dir: Path, out_dir: Path, label: str,
                      permutations: int, seed: int) -> list[str]:
    return [
        "--source-dir", str(source_dir),
        "--out-dir", str(out_dir),
        "--run-label", label,
        "--window", "20",
        "--activity-threshold", "1",
        "--match-filter", "ALL",
        "--equivalence-profile", "STRICT",
        "--block-size", "1000",
        "--minimum-block-fraction", "0.5",
        "--minimum-burst-ends-per-block", "5",
        "--boundary-permutations", str(permutations),
        "--seed", str(seed),
        "--jobs", "1",
    ]


def burst_args(source_dir: Path, out_dir: Path, label: str,
               enrichment_permutations: int, clustering_permutations: int,
               boundary_permutations: int, seed: int) -> list[str]:
    return [
        "--source-dir", str(source_dir),
        "--out-dir", str(out_dir),
        "--run-label", label,
        "--window", "20",
        "--activity-threshold", "1",
        "--match-filter", "ALL",
        "--equivalence-profile", "STRICT",
        "--enrichment-permutations", str(enrichment_permutations),
        "--clustering-permutations", str(clustering_permutations),
        "--boundary-permutations", str(boundary_permutations),
        "--seed", str(seed),
        "--jobs", "1",
    ]


def write_control_metadata(out_dir: Path, mode: str, parameters: dict[str, object],
                           generated_dirs: list[Path]) -> None:
    script = Path(__file__).resolve()
    metadata = {
        "analysis": ANALYSIS_NAME,
        "analysis_version": ANALYSIS_VERSION,
        "mode": mode,
        "scientific_status": "sensitivity_control",
        "parameters": parameters,
        "required_versions": {
            "rhyme_burst_architecture": REQUIRED_BURST_VERSION,
            "rhyme_cadence_distribution_robustness": REQUIRED_DISTRIBUTION_VERSION,
        },
        "software": {
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "platform": platform.platform(),
        },
        "code": {"file": str(script), "sha256": sha256_file(script)},
        "generated_directories": [str(path) for path in generated_dirs],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CONTROL_METADATA.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_no_paseq(args: argparse.Namespace) -> int:
    original = burst.MINOR_TAAMIM
    try:
        burst.MINOR_TAAMIM = frozenset(
            {"revia", "zaqef_qatan", "zaqef_gadol", "shalshelet"}
        )
        target = args.out_dir / "boundary_no_paseq"
        rc = dist.main(distribution_args(
            args.source_dir, target, "control_boundary_no_paseq",
            args.boundary_permutations, args.seed,
        ))
    finally:
        burst.MINOR_TAAMIM = original
    write_control_metadata(
        target, "boundary_no_paseq",
        {
            "minor_boundary_set": ["revia", "zaqef_qatan", "zaqef_gadol", "shalshelet"],
            "paseq_treatment": "excluded_from_minor_boundary_set_only",
            "boundary_permutations": args.boundary_permutations,
            "base_seed": args.seed,
            "jobs": 1,
        },
        [target],
    )
    return rc


def run_exclude_extended_left(args: argparse.Namespace) -> int:
    original: Callable[..., str | None] = burst.rhyme_kind

    def controlled_rhyme_kind(source: burst.Token, target: burst.Token, cache):
        if source.signature.extended_left or target.signature.extended_left:
            return None
        return original(source, target, cache)

    burst_target = args.out_dir / "exclude_extended_left" / "burst"
    dist_target = args.out_dir / "exclude_extended_left" / "distribution"
    try:
        burst.rhyme_kind = controlled_rhyme_kind
        rc1 = burst.main(burst_args(
            args.source_dir, burst_target, "control_exclude_extended_left",
            args.enrichment_permutations, args.clustering_permutations,
            args.boundary_permutations, args.seed,
        ))
        if rc1:
            return rc1
        rc2 = dist.main(distribution_args(
            args.source_dir, dist_target, "control_exclude_extended_left",
            args.boundary_permutations, args.seed,
        ))
    finally:
        burst.rhyme_kind = original

    # Auditable token counts for the controlled heuristic.
    rows: list[dict[str, object]] = []
    rhyme_config = burst.ProtocolConfig.from_profile("STRICT")
    for book in BOOKS:
        tokens, audit = burst.parse_book(
            args.source_dir / f"{book}_taamim_annotated.txt", rhyme_config
        )
        affected = sum(token.signature.extended_left for token in tokens)
        rows.append({
            "book": book,
            "analyzable_stressed_tokens": len(tokens),
            "extended_left_tokens": affected,
            "extended_left_token_share": affected / len(tokens),
            "source_word_tokens": audit["source_word_tokens"],
        })
    write_csv(args.out_dir / "exclude_extended_left" / "extended_left_token_counts.csv", rows)
    write_control_metadata(
        args.out_dir / "exclude_extended_left", "exclude_extended_left",
        {
            "link_policy": "exclude_link_if_either_token_signature_extended_left",
            "window": 20,
            "threshold": 1,
            "match_filter": "ALL",
            "equivalence_profile": "STRICT",
            "enrichment_permutations": args.enrichment_permutations,
            "clustering_permutations": args.clustering_permutations,
            "boundary_permutations": args.boundary_permutations,
            "base_seed": args.seed,
            "jobs": 1,
        },
        [burst_target, dist_target],
    )
    return rc2


def run_verse_null(args: argparse.Namespace) -> int:
    per_book: list[dict[str, object]] = []
    simulated_by_metric: dict[str, list[tuple[int, np.ndarray]]] = {
        "activity_coverage": [], "burst_end_coverage": []
    }
    for book in BOOKS:
        rows = [row for row in read_csv(args.main_dir / f"{book}_verse_coverage.csv")
                if int(row["fully_represented_after_left_window"]) == 1]
        sizes = np.asarray([int(row["eligible_positions"]) for row in rows], dtype=np.int64)
        if len(sizes) == 0:
            raise ValueError(f"No fully represented verses for {book}")
        for metric, column in (
            ("activity_coverage", "active_positions"),
            ("burst_end_coverage", "burst_ends"),
        ):
            marks = np.asarray([int(row[column]) for row in rows], dtype=np.int64)
            total_marks = int(marks.sum())
            observed = float(np.count_nonzero(marks) / len(marks))
            metric_offset = 101 if metric == "activity_coverage" else 211
            rng = np.random.default_rng(
                args.seed + BOOK_INDEX[book] * 1_000_003 + metric_offset
            )
            allocations = rng.multivariate_hypergeometric(
                sizes, total_marks, size=args.verse_permutations
            )
            null = np.count_nonzero(allocations, axis=1) / len(sizes)
            summary = empirical_summary(observed, null)
            per_book.append({
                "scope": book,
                "metric": metric,
                "fully_represented_verses": len(rows),
                "eligible_positions": int(sizes.sum()),
                "marked_positions": total_marks,
                "permutations": args.verse_permutations,
                **summary,
            })
            simulated_by_metric[metric].append((len(rows), null))

    pooled_rows: list[dict[str, object]] = []
    for metric, book_nulls in simulated_by_metric.items():
        total_verses = sum(weight for weight, _ in book_nulls)
        pooled_null = sum(weight * null for weight, null in book_nulls) / total_verses
        source_rows = [row for row in per_book if row["metric"] == metric]
        pooled_observed = sum(
            int(row["fully_represented_verses"]) * float(row["observed"])
            for row in source_rows
        ) / total_verses
        pooled_rows.append({
            "scope": "ALL",
            "metric": metric,
            "fully_represented_verses": total_verses,
            "eligible_positions": sum(int(row["eligible_positions"]) for row in source_rows),
            "marked_positions": sum(int(row["marked_positions"]) for row in source_rows),
            "permutations": args.verse_permutations,
            **empirical_summary(pooled_observed, pooled_null),
        })

    target = args.out_dir / "verse_allocation_null"
    all_rows = per_book + pooled_rows
    write_csv(target / "ALL_verse_coverage_null_statistics.csv", all_rows)
    (target / "ALL_verse_coverage_null_summary.json").write_text(
        json.dumps(all_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_control_metadata(
        target, "verse_allocation_null",
        {
            "main_distribution_directory": str(args.main_dir),
            "allocation": "within_book_without_replacement_over_fully_represented_eligible_positions",
            "preserved": ["verse_sizes", "marked_position_count", "book"],
            "metrics": ["activity_coverage", "burst_end_coverage"],
            "permutations": args.verse_permutations,
            "base_seed": args.seed,
        },
        [target],
    )
    for row in all_rows:
        print(
            f"{str(row['scope']):<12} {str(row['metric']):<20} "
            f"obs={float(row['observed']):.4f} null={float(row['null_mean']):.4f} "
            f"diff={float(row['difference']):+.4f} Z={float(row['z']):+.2f}"
        )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("boundary_no_paseq", "exclude_extended_left", "verse_allocation_null")
    )
    parser.add_argument("--source-dir", type=Path, default=Path("data/data_processed/torah"))
    parser.add_argument("--main-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--enrichment-permutations", type=int, default=500)
    parser.add_argument("--clustering-permutations", type=int, default=500)
    parser.add_argument("--boundary-permutations", type=int, default=1000)
    parser.add_argument("--verse-permutations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260728)
    args = parser.parse_args(argv)
    if args.mode == "verse_allocation_null" and args.main_dir is None:
        parser.error("--main-dir is required for verse_allocation_null")
    for name in (
        "enrichment_permutations", "clustering_permutations",
        "boundary_permutations", "verse_permutations",
    ):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if burst.ANALYSIS_VERSION != REQUIRED_BURST_VERSION:
        raise RuntimeError(
            f"Expected rhyme_burst_architecture {REQUIRED_BURST_VERSION}; "
            f"found {burst.ANALYSIS_VERSION}"
        )
    if dist.ANALYSIS_VERSION != REQUIRED_DISTRIBUTION_VERSION:
        raise RuntimeError(
            f"Expected rhyme_cadence_distribution_robustness "
            f"{REQUIRED_DISTRIBUTION_VERSION}; found {dist.ANALYSIS_VERSION}"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.mode == "boundary_no_paseq":
        return run_no_paseq(args)
    if args.mode == "exclude_extended_left":
        return run_exclude_extended_left(args)
    return run_verse_null(args)


if __name__ == "__main__":
    raise SystemExit(main())
