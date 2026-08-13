# -*- coding: utf-8 -*-
"""
Taam Grammar analysis.

One unified analysis of local taam-event organization:
  1. transition and n-gram entropy under a unigram-preserving permutation null;
  2. enriched directed transitions;
  3. recurrent multi-event formulas;
  4. descriptive directed-network constraints;
  5. compact-core coverage with projected and adjacent controls.

Input format:
    word[taam1,taam2] {sof_pasuq}

The program is designed for repository use: one parse per book, coordinated
permutations, parallel books, stable output paths, empirical p-values, and
explicit handling of degenerate/near-degenerate Monte-Carlo nulls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Sequence

WORD_RE = re.compile(r"\[([^\]]+)\]")
EXT_RE = re.compile(r"^\{([^}]+)\}$")

DEFAULT_CORE = {
    "meteg", "munah", "merkha", "tipeha", "mahapakh", "pashta",
    "tevir", "darga", "revia", "zaqef_qatan", "zaqef_gadol",
    "atnah", "atnah_hafukh", "sof_pasuq", "paseq", "qadma", "geresh",
    "telisha_qetana",
}
CADENCE_NODES = {
    "revia", "zaqef_qatan", "zaqef_gadol", "atnah", "atnah_hafukh",
    "sof_pasuq", "paseq",
}
NULL_SD_MIN_FOR_Z = 0.5
NULL_UNIQUE_MIN_FOR_Z = 3


def parse_csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def parse_int_csv(value: str) -> list[int]:
    return [int(x) for x in parse_csv(value)]


def parse_core_nodes(value: str) -> set[str]:
    return set(DEFAULT_CORE) if not value or value.lower() in {"default", "core"} else set(parse_csv(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_stream(text: str, include_external: bool, exclude_taamim: Iterable[str]) -> tuple[list[str], dict]:
    exclude = set(exclude_taamim)
    stream: list[str] = []
    word_tokens = 0
    external_seen = 0
    for token in text.replace("\ufeff", "").split():
        ext = EXT_RE.match(token)
        if ext:
            values = parse_csv(ext.group(1))
            external_seen += len(values)
            if include_external:
                stream.extend(x for x in values if x not in exclude)
            continue
        word = WORD_RE.search(token)
        if word:
            word_tokens += 1
            stream.extend(x for x in parse_csv(word.group(1)) if x not in exclude)
    return stream, {
        "n_word_tokens_with_taam": word_tokens,
        "n_external_taam_tokens_seen": external_seen,
    }


def iter_ngrams(seq: Sequence[str], k: int):
    return zip(*(seq[i:] for i in range(k))) if len(seq) >= k else iter(())


def entropy(counter: Counter) -> float:
    total = sum(counter.values())
    return 0.0 if not total else -sum((c / total) * math.log2(c / total) for c in counter.values())


def norm_entropy(counter: Counter) -> float:
    return 0.0 if len(counter) <= 1 else entropy(counter) / math.log2(len(counter))


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sample_sd(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((x - mu) ** 2 for x in values) / (len(values) - 1))


def empirical_upper_p(observed: float, null: Sequence[float]) -> tuple[float, int]:
    exceedances = sum(1 for x in null if x >= observed)
    return ((exceedances + 1) / (len(null) + 1), exceedances)


def empirical_lower_p(observed: float, null: Sequence[float]) -> tuple[float, int]:
    exceedances = sum(1 for x in null if x <= observed)
    return ((exceedances + 1) / (len(null) + 1), exceedances)


def null_summary(observed: float, null: Sequence[float], tail: str, discrete_count: bool = True) -> dict:
    mu = mean(null)
    sd = sample_sd(null)
    unique = len(set(null))
    if discrete_count:
        reliable = sd >= NULL_SD_MIN_FOR_Z and unique >= NULL_UNIQUE_MIN_FOR_Z
    else:
        reliable = sd > 0.0 and unique >= NULL_UNIQUE_MIN_FOR_Z
    z = (observed - mu) / sd if reliable else None
    if tail == "upper":
        p, exceed = empirical_upper_p(observed, null)
    elif tail == "lower":
        p, exceed = empirical_lower_p(observed, null)
    else:
        raise ValueError("tail must be upper or lower")
    return {
        "null_mean": round(mu, 8),
        "null_sd": round(sd, 8),
        "null_unique_values": unique,
        "z": round(z, 6) if z is not None else "",
        "z_reliable": reliable,
        "empirical_p": round(p, 8),
        "null_exceedances": exceed,
        "permutations": len(null),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def add_context(rows: list[dict], book: str, run_label: str, stream_type: str = "full") -> list[dict]:
    for row in rows:
        row.update({"book": book, "run_label": run_label, "stream_type": stream_type})
    return rows


def descriptive_network(stream: Sequence[str], min_edge_count: int, min_prob: float, top_n: int):
    node_counts = Counter(stream)
    edges = Counter(zip(stream, stream[1:]))
    succ: dict[str, Counter] = defaultdict(Counter)
    pred: dict[str, Counter] = defaultdict(Counter)
    for (a, b), count in edges.items():
        succ[a][b] += count
        pred[b][a] += count

    total_events = len(stream)
    total_edges = sum(edges.values())
    node_rows: list[dict] = []
    successor_rows: list[dict] = []
    predecessor_rows: list[dict] = []

    for node in sorted(node_counts):
        out = succ[node]
        inc = pred[node]
        out_total = sum(out.values())
        in_total = sum(inc.values())
        top_s = out.most_common(1)[0] if out else ("", 0)
        top_p = inc.most_common(1)[0] if inc else ("", 0)
        node_rows.append({
            "taam": node,
            "event_count": node_counts[node],
            "event_share": round(node_counts[node] / total_events, 8) if total_events else 0,
            "out_total": out_total,
            "in_total": in_total,
            "out_degree": len(out),
            "in_degree": len(inc),
            "successor_entropy": round(entropy(out), 8),
            "successor_norm_entropy": round(norm_entropy(out), 8),
            "predecessor_entropy": round(entropy(inc), 8),
            "predecessor_norm_entropy": round(norm_entropy(inc), 8),
            "top_successor": top_s[0],
            "top_successor_prob": round(top_s[1] / out_total, 8) if out_total else "",
            "top_predecessor": top_p[0],
            "top_predecessor_prob": round(top_p[1] / in_total, 8) if in_total else "",
        })
        for rank, (other, count) in enumerate(out.most_common(top_n), 1):
            successor_rows.append({"taam": node, "rank": rank, "successor": other, "count": count,
                                   "prob": round(count / out_total, 8) if out_total else 0})
        for rank, (other, count) in enumerate(inc.most_common(top_n), 1):
            predecessor_rows.append({"taam": node, "rank": rank, "predecessor": other, "count": count,
                                     "prob": round(count / in_total, 8) if in_total else 0})

    edge_rows: list[dict] = []
    for (a, b), count in edges.most_common():
        out_total = sum(succ[a].values())
        in_total = sum(pred[b].values())
        prob = count / out_total if out_total else 0.0
        if count < min_edge_count and prob < min_prob:
            continue
        reverse = edges.get((b, a), 0)
        expected = out_total * in_total / total_edges if total_edges else 0.0
        edge_rows.append({
            "source": a,
            "target": b,
            "count": count,
            "prob_given_source": round(prob, 8),
            "target_predecessor_share": round(count / in_total, 8) if in_total else 0,
            "reverse_count": reverse,
            "asymmetry_count": count - reverse,
            "asymmetry_ratio": round(count / reverse, 8) if reverse else "inf",
            "expected_independent": round(expected, 6),
            "lift": round(count / expected, 6) if expected else 0,
        })

    cadence_rows: list[dict] = []
    for cadence in sorted(CADENCE_NODES & set(node_counts)):
        total = sum(pred[cadence].values())
        for rank, (source, count) in enumerate(pred[cadence].most_common(), 1):
            if count >= min_edge_count:
                cadence_rows.append({"cadence_node": cadence, "rank": rank, "predecessor": source,
                                     "count": count, "share_of_cadence_predecessors": round(count / total, 8)})
    return node_rows, edge_rows, successor_rows, predecessor_rows, cadence_rows


def adjacent_core_edges(stream: Sequence[str], core_nodes: set[str], min_edge_count: int, min_prob: float) -> list[dict]:
    edge_counts = Counter((a, b) for a, b in zip(stream, stream[1:]) if a in core_nodes and b in core_nodes)
    succ: dict[str, Counter] = defaultdict(Counter)
    pred: dict[str, Counter] = defaultdict(Counter)
    for (a, b), count in edge_counts.items():
        succ[a][b] += count
        pred[b][a] += count
    total_edges = sum(edge_counts.values())
    rows: list[dict] = []
    for (a, b), count in edge_counts.most_common():
        out_total = sum(succ[a].values())
        in_total = sum(pred[b].values())
        prob = count / out_total if out_total else 0.0
        if count < min_edge_count and prob < min_prob:
            continue
        reverse = edge_counts.get((b, a), 0)
        expected = out_total * in_total / total_edges if total_edges else 0.0
        rows.append({
            "source": a, "target": b, "count": count,
            "prob_given_source": round(prob, 8),
            "target_predecessor_share": round(count / in_total, 8) if in_total else 0,
            "reverse_count": reverse,
            "asymmetry_count": count - reverse,
            "asymmetry_ratio": round(count / reverse, 8) if reverse else "inf",
            "expected_independent": round(expected, 6),
            "lift": round(count / expected, 6) if expected else 0,
        })
    return rows


def permutation_statistics(
    stream: Sequence[str], entropy_ks: list[int], formula_ks: list[int],
    transition_perm: int, formula_perm: int, seed: int,
    min_transition_count: int, min_formula_count: int,
    formula_candidates: int, top_k: int,
):
    observed_pairs = Counter(zip(stream, stream[1:]))
    pair_targets = {pair: count for pair, count in observed_pairs.items() if count >= min_transition_count}
    pair_nulls = {pair: [] for pair in pair_targets}

    all_ks = sorted(set(entropy_ks) | set(formula_ks))
    observed_counts: dict[int, Counter] = {k: Counter(iter_ngrams(stream, k)) for k in all_ks}
    observed_entropy = {k: entropy(observed_counts[k]) for k in entropy_ks}
    entropy_nulls: dict[int, list[float]] = {k: [] for k in entropy_ks}

    formula_targets: dict[int, list[tuple[str, ...]]] = {}
    formula_nulls: dict[tuple[int, tuple[str, ...]], list[int]] = {}
    for k in formula_ks:
        candidates = [(pat, cnt) for pat, cnt in observed_counts[k].items() if cnt >= min_formula_count]
        candidates.sort(key=lambda item: (-item[1], item[0]))
        targets = [pat for pat, _ in candidates[:formula_candidates]]
        formula_targets[k] = targets
        for pattern in targets:
            formula_nulls[(k, pattern)] = []

    rng = random.Random(seed)
    max_perm = max(transition_perm, formula_perm)
    for index in range(max_perm):
        shuffled = list(stream)
        rng.shuffle(shuffled)
        if index < transition_perm:
            pair_counts = Counter(zip(shuffled, shuffled[1:]))
            for pair in pair_targets:
                pair_nulls[pair].append(pair_counts.get(pair, 0))
        if index < formula_perm:
            for k in all_ks:
                counts = Counter(iter_ngrams(shuffled, k))
                if k in entropy_nulls:
                    entropy_nulls[k].append(entropy(counts))
                if k in formula_targets:
                    for pattern in formula_targets[k]:
                        formula_nulls[(k, pattern)].append(counts.get(pattern, 0))

    transition_rows: list[dict] = []
    for (a, b), observed in pair_targets.items():
        stats = null_summary(observed, pair_nulls[(a, b)], "upper")
        transition_rows.append({"current": a, "next": b, "observed_count": observed, **stats})
    transition_rows.sort(key=lambda r: (r["empirical_p"], -r["observed_count"], r["current"], r["next"]))

    entropy_rows: list[dict] = []
    for k in entropy_ks:
        stats = null_summary(observed_entropy[k], entropy_nulls[k], "lower", discrete_count=False)
        entropy_rows.append({"k": k, "observed_entropy": round(observed_entropy[k], 8), **stats})

    formula_rows: list[dict] = []
    for k in formula_ks:
        total = sum(observed_counts[k].values())
        current: list[dict] = []
        for pattern in formula_targets[k]:
            observed = observed_counts[k][pattern]
            null = formula_nulls[(k, pattern)]
            stats = null_summary(observed, null, "upper")
            null_mean = float(stats["null_mean"])
            current.append({
                "k": k,
                "pattern": " ".join(pattern),
                "observed_count": observed,
                "observed_share": round(observed / total, 8) if total else 0,
                "enrichment_ratio": round(observed / null_mean, 6) if null_mean > 0 else "inf",
                "total_ngrams": total,
                **stats,
            })
        current.sort(key=lambda r: (
            r["empirical_p"],
            0 if r["z_reliable"] else 1,
            -(float(r["z"]) if r["z_reliable"] else 0.0),
            -r["observed_count"],
            r["pattern"],
        ))
        for rank, row in enumerate(current[:top_k], 1):
            row["rank"] = rank
            formula_rows.append(row)
    return transition_rows, entropy_rows, formula_rows


def analyze_book(job: dict) -> dict:
    tag = job["tag"]
    input_path = Path(job["path"])
    out = Path(job["out_dir"]) / tag
    out.mkdir(parents=True, exist_ok=True)

    stream, parse_meta = extract_stream(
        input_path.read_text(encoding="utf-8-sig"),
        job["include_external"],
        job["exclude_taamim"],
    )
    if len(stream) < 2:
        raise ValueError(f"{tag}: fewer than two taam events after filtering")

    nodes, edges, successors, predecessors, cadence = descriptive_network(
        stream, job["min_edge_count"], job["min_prob"], job["top_n"]
    )
    transition_rows, entropy_rows, formula_rows = permutation_statistics(
        stream, job["entropy_ks"], job["formula_ks"],
        job["transition_perm"], job["formula_perm"], job["seed"],
        job["min_transition_count"], job["min_formula_count"],
        job["formula_candidates"], job["top_k"],
    )

    core_nodes = set(job["core_nodes"])
    core_stream = [x for x in stream if x in core_nodes]
    p_nodes, p_edges, p_succ, p_pred, p_cad = descriptive_network(
        core_stream, job["core_min_edge_count"], job["core_min_prob"], job["top_n"]
    )
    a_edges = adjacent_core_edges(stream, core_nodes, job["core_min_edge_count"], job["core_min_prob"])

    datasets = {
        "transition_nodes.csv": add_context(nodes, tag, job["run_label"]),
        "transition_edges.csv": add_context(edges, tag, job["run_label"]),
        "transition_top_successors.csv": add_context(successors, tag, job["run_label"]),
        "transition_top_predecessors.csv": add_context(predecessors, tag, job["run_label"]),
        "cadence_funnels.csv": add_context(cadence, tag, job["run_label"]),
        "transition_permutation.csv": add_context(transition_rows, tag, job["run_label"]),
        "ngram_entropy_permutation.csv": add_context(entropy_rows, tag, job["run_label"]),
        "ngram_formulas_permutation.csv": add_context(formula_rows, tag, job["run_label"]),
        "core_projected_nodes.csv": add_context(p_nodes, tag, job["run_label"], "core_projected"),
        "core_projected_edges.csv": add_context(p_edges, tag, job["run_label"], "core_projected"),
        "core_projected_top_successors.csv": add_context(p_succ, tag, job["run_label"], "core_projected"),
        "core_projected_top_predecessors.csv": add_context(p_pred, tag, job["run_label"], "core_projected"),
        "core_projected_cadence_funnels.csv": add_context(p_cad, tag, job["run_label"], "core_projected"),
        "core_adjacent_edges.csv": add_context(a_edges, tag, job["run_label"], "core_adjacent"),
    }
    for filename, rows in datasets.items():
        write_csv(out / filename, rows)

    meta = {
        "analysis": "taam_grammar",
        "book": tag,
        "run_label": job["run_label"],
        "input": str(input_path),
        "input_sha256": sha256_file(input_path),
        "include_external": job["include_external"],
        "exclude_taamim": sorted(job["exclude_taamim"]),
        "n_taam_events": len(stream),
        "n_unique_taamim": len(set(stream)),
        "entropy_ks": job["entropy_ks"],
        "formula_ks": job["formula_ks"],
        "transition_perm": job["transition_perm"],
        "formula_perm": job["formula_perm"],
        "seed": job["seed"],
        "min_transition_count": job["min_transition_count"],
        "min_formula_count": job["min_formula_count"],
        "formula_candidates": job["formula_candidates"],
        "top_k": job["top_k"],
        "top_n": job["top_n"],
        "z_reliability_rule": {
            "minimum_null_sd": NULL_SD_MIN_FOR_Z,
            "minimum_unique_null_values": NULL_UNIQUE_MIN_FOR_Z,
            "fallback": "empirical one-sided permutation p-value",
        },
        "core_nodes": sorted(core_nodes),
        "n_core_events": len(core_stream),
        "core_coverage": round(len(core_stream) / len(stream), 8),
        **parse_meta,
        "top_transitions": transition_rows[:20],
        "entropy_results": entropy_rows,
        "top_formulas": {str(k): [r for r in formula_rows if r["k"] == k][:10] for k in job["formula_ks"]},
        "most_predictable_nodes": sorted(nodes, key=lambda r: (r["successor_norm_entropy"], -r["event_count"]))[:20],
        "highest_lift_edges": sorted(edges, key=lambda r: r["lift"], reverse=True)[:20],
        "top_core_projected_edges": p_edges[:20],
        "top_core_adjacent_edges": a_edges[:20],
    }
    (out / "taam_grammar_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"meta": meta, "datasets": datasets}


def format_stat(row: dict) -> str:
    if row.get("z_reliable"):
        return f"Z={row['z']} p={row['empirical_p']}"
    return f"Z=NA p={row['empirical_p']} (degenerate null)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Taam Grammar analysis")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--book", action="append", nargs=2, required=True, metavar=("TAG", "PATH"))
    parser.add_argument("--run_label", default="main")
    parser.add_argument("--entropy_k", default="2,3,4,5,6")
    parser.add_argument("--formula_k", default="3,4,5,6")
    parser.add_argument("--transition_perm", type=int, default=500)
    parser.add_argument("--formula_perm", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--min_transition_count", type=int, default=20)
    parser.add_argument("--min_formula_count", type=int, default=20)
    parser.add_argument("--formula_candidates", type=int, default=250)
    parser.add_argument("--top_k", type=int, default=50)
    parser.add_argument("--top_n", type=int, default=10)
    parser.add_argument("--min_edge_count", type=int, default=5)
    parser.add_argument("--min_prob", type=float, default=0.0)
    parser.add_argument("--core_nodes", default="default")
    parser.add_argument("--core_min_edge_count", type=int, default=100)
    parser.add_argument("--core_min_prob", type=float, default=0.15)
    parser.add_argument("--exclude_external", action="store_true")
    parser.add_argument("--exclude_taamim", default="")
    args = parser.parse_args()

    entropy_ks = parse_int_csv(args.entropy_k)
    formula_ks = parse_int_csv(args.formula_k)
    if not entropy_ks or not formula_ks:
        parser.error("entropy_k and formula_k must not be empty")
    if any(k < 2 for k in entropy_ks) or any(k < 3 for k in formula_ks):
        parser.error("entropy k must be >=2 and formula k must be >=3")
    if args.transition_perm < 2 or args.formula_perm < 2:
        parser.error("permutation counts must be >=2")
    if args.jobs < 1:
        parser.error("jobs must be >=1")
    integer_limits = {
        "min_transition_count": args.min_transition_count,
        "min_formula_count": args.min_formula_count,
        "formula_candidates": args.formula_candidates,
        "top_k": args.top_k,
        "top_n": args.top_n,
        "min_edge_count": args.min_edge_count,
        "core_min_edge_count": args.core_min_edge_count,
    }
    for name, value in integer_limits.items():
        if value < 1:
            parser.error(f"{name} must be >=1")
    for name, value in {"min_prob": args.min_prob, "core_min_prob": args.core_min_prob}.items():
        if not 0.0 <= value <= 1.0:
            parser.error(f"{name} must be between 0 and 1")

    tags = [tag for tag, _ in args.book]
    if len(tags) != len(set(tags)):
        parser.error("book tags must be unique")
    for tag, path_text in args.book:
        path = Path(path_text)
        if not tag.strip():
            parser.error("book tags must not be empty")
        if not path.is_file():
            parser.error(f"input file does not exist: {path}")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    common = {
        "out_dir": str(out),
        "run_label": args.run_label,
        "entropy_ks": entropy_ks,
        "formula_ks": formula_ks,
        "transition_perm": args.transition_perm,
        "formula_perm": args.formula_perm,
        "seed": args.seed,
        "include_external": not args.exclude_external,
        "exclude_taamim": parse_csv(args.exclude_taamim),
        "min_transition_count": args.min_transition_count,
        "min_formula_count": args.min_formula_count,
        "formula_candidates": args.formula_candidates,
        "top_k": args.top_k,
        "top_n": args.top_n,
        "min_edge_count": args.min_edge_count,
        "min_prob": args.min_prob,
        "core_nodes": sorted(parse_core_nodes(args.core_nodes)),
        "core_min_edge_count": args.core_min_edge_count,
        "core_min_prob": args.core_min_prob,
    }
    jobs = [{**common, "tag": tag, "path": path} for tag, path in args.book]

    if args.jobs > 1 and len(jobs) > 1:
        results: list[dict] = []
        with ProcessPoolExecutor(max_workers=min(args.jobs, len(jobs))) as executor:
            futures = {executor.submit(analyze_book, job): job["tag"] for job in jobs}
            for future in as_completed(futures):
                results.append(future.result())
    else:
        results = [analyze_book(job) for job in jobs]

    order = [tag for tag, _ in args.book]
    results.sort(key=lambda result: order.index(result["meta"]["book"]))
    all_datasets: dict[str, list[dict]] = defaultdict(list)
    metas: list[dict] = []
    for result in results:
        metas.append(result["meta"])
        for filename, rows in result["datasets"].items():
            all_datasets[filename].extend(rows)
    for filename, rows in all_datasets.items():
        write_csv(out / f"ALL_{filename}", rows)
    (out / "ALL_taam_grammar_meta.json").write_text(json.dumps(metas, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== TAAM GRAMMAR ===")
    print("out:", out)
    print("run_label:", args.run_label, "jobs:", args.jobs,
          "transition_perm:", args.transition_perm, "formula_perm:", args.formula_perm)
    print("include_external:", not args.exclude_external,
          "exclude_taamim:", parse_csv(args.exclude_taamim) or "none")
    for meta in metas:
        print()
        print(meta["book"], "| events:", meta["n_taam_events"], "| unique:", meta["n_unique_taamim"],
              "| core coverage:", meta["core_coverage"])
        print(" entropy:")
        for row in meta["entropy_results"]:
            print(f"  k{row['k']}: {format_stat(row)}")
        print(" top transitions:")
        for row in meta["top_transitions"][:5]:
            print(f"  {row['current']} -> {row['next']} count={row['observed_count']} {format_stat(row)}")
        print(" top formulas:")
        for k in formula_ks:
            for row in meta["top_formulas"].get(str(k), [])[:2]:
                print(f"  k{k}: {row['pattern']} count={row['observed_count']} {format_stat(row)}")
    print("DONE")


if __name__ == "__main__":
    main()
