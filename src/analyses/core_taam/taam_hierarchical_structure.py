# -*- coding: utf-8 -*-
"""
Taam Hierarchical Structure

Unified descriptive analysis of cadence-defined hierarchy and segment-size grammar.

Levels:
  verse = sof_pasuq
  major = atnah, atnah_hafukh, sof_pasuq
  minor = revia, zaqef_qatan, zaqef_gadol, shalshelet, paseq,
          atnah, atnah_hafukh, sof_pasuq

The script parses each book once, constructs all three segment levels, derives
verse->major and major->minor relations, validates exact parent/child coverage,
and reports size distributions and recurrent size sequences.

No fixed meter and no probabilistic null model are assumed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

ACUTE = "\u0301"
WORD_TAAM_RE = re.compile(r"\[([^\]]+)\]")
EXT_RE = re.compile(r"^\{([^}]+)\}$")
VOWELS = set("aeiouAEIOU")
ACCENTLESS_TAAMIM = {"paseq"}

LEVEL_BOUNDARIES = {
    "verse": {"sof_pasuq"},
    "major": {"atnah", "atnah_hafukh", "sof_pasuq"},
    "minor": {
        "revia", "zaqef_qatan", "zaqef_gadol", "shalshelet", "paseq",
        "atnah", "atnah_hafukh", "sof_pasuq",
    },
}

RELATIONS = {
    "verse_contains_major": ("verse", "major"),
    "major_contains_minor": ("major", "minor"),
}

MAJOR_CADENCE = {"atnah", "atnah_hafukh", "sof_pasuq"}
MINOR_CADENCE = {"revia", "zaqef_qatan", "zaqef_gadol", "shalshelet", "paseq"}


def split_csv(text: str) -> list[str]:
    return [x.strip() for x in str(text).split(",") if x.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_int_list(text: str) -> list[int]:
    vals = sorted({int(x) for x in split_csv(text)})
    if any(x < 2 for x in vals):
        raise ValueError("size n-grams must be >= 2")
    return vals


def split_word_and_taamim(token: str) -> tuple[str, list[str], list[str]]:
    ext = EXT_RE.match(token)
    if ext:
        return "", [], split_csv(ext.group(1))
    match = WORD_TAAM_RE.search(token)
    if not match:
        return token, [], []
    return WORD_TAAM_RE.sub("", token), split_csv(match.group(1)), []


def vowel_groups(word: str) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    in_group = False
    start = 0
    for i, ch in enumerate(word):
        if ch == ACUTE:
            continue
        if ch in VOWELS:
            if not in_group:
                start = i
                in_group = True
        elif in_group:
            groups.append((start, i))
            in_group = False
    if in_group:
        groups.append((start, len(word)))
    return groups


def acute_vowel_index(word: str) -> int | None:
    groups = vowel_groups(word)
    positions = [i for i, ch in enumerate(word) if ch == ACUTE]
    if not groups or not positions:
        return None
    acute = positions[0]
    for idx, (start, end) in enumerate(groups):
        if start <= acute <= end + 1:
            return idx
        if acute < start:
            return max(0, idx - 1)
    return len(groups) - 1


def parse_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for token in text.replace("\ufeff", "").split():
        word, internal, external = split_word_and_taamim(token)
        if external:
            if records:
                records[-1]["external_taamim"].extend(external)
                records[-1]["all_taamim"].extend(external)
            continue
        if not word:
            continue
        records.append({
            "word_index": len(records),
            "word": word,
            "internal_taamim": list(internal),
            "external_taamim": [],
            "all_taamim": list(internal),
            "pulse_count": len(vowel_groups(word)),
        })

    pulse_pos = 0
    for record in records:
        accent_taamim = [t for t in record["all_taamim"] if t not in ACCENTLESS_TAAMIM]
        accent_idx = acute_vowel_index(record["word"])
        if accent_idx is None and accent_taamim and record["pulse_count"]:
            accent_idx = record["pulse_count"] - 1
        record["has_accent_event"] = int(bool(accent_taamim and record["pulse_count"]))
        record["accent_syl_index"] = accent_idx
        record["start_pulse"] = pulse_pos
        record["end_pulse"] = pulse_pos + record["pulse_count"]
        record["accent_pulse"] = pulse_pos + accent_idx if accent_idx is not None else None
        pulse_pos = record["end_pulse"]
    return records


def cadence_class(taamim: Iterable[str]) -> str:
    values = set(taamim)
    if values & MAJOR_CADENCE:
        return "major"
    if values & MINOR_CADENCE:
        return "minor"
    return "other"


def bucket_pulses(n: int) -> str:
    if n <= 4: return "P1-4"
    if n <= 6: return "P5-6"
    if n <= 9: return "P7-9"
    if n <= 12: return "P10-12"
    if n <= 15: return "P13-15"
    if n <= 18: return "P16-18"
    if n <= 24: return "P19-24"
    return "P25+"


def bucket_accents(n: int) -> str:
    if n <= 1: return "A0-1"
    if n == 2: return "A2"
    if n == 3: return "A3"
    if n == 4: return "A4"
    if n == 5: return "A5"
    if n <= 7: return "A6-7"
    return "A8+"


def build_segments(records: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    boundaries = LEVEL_BOUNDARIES[level]
    rows: list[dict[str, Any]] = []
    start = 0
    index = 0
    for end, record in enumerate(records):
        ending = [t for t in record["all_taamim"] if t in boundaries]
        if not ending:
            continue
        chunk = records[start:end + 1]
        if not chunk:
            start = end + 1
            continue
        pulses = sum(x["pulse_count"] for x in chunk)
        accents = sum(x["has_accent_event"] for x in chunk)
        rows.append({
            "level": level,
            "segment_index": index,
            "start_word_index": chunk[0]["word_index"],
            "end_word_index": chunk[-1]["word_index"],
            "start_word": chunk[0]["word"],
            "end_word": chunk[-1]["word"],
            "word_count": len(chunk),
            "pulse_count": pulses,
            "accent_count": accents,
            "density_accents_per_pulse": round(accents / pulses, 8) if pulses else "",
            "cadence_taamim": "+".join(ending),
            "cadence_class": cadence_class(ending),
            "shape_PA": f"P{pulses}_A{accents}",
            "bucket_PA": f"{bucket_pulses(pulses)}_{bucket_accents(accents)}",
            "is_incomplete": 0,
        })
        index += 1
        start = end + 1

    if start < len(records):
        chunk = records[start:]
        pulses = sum(x["pulse_count"] for x in chunk)
        accents = sum(x["has_accent_event"] for x in chunk)
        rows.append({
            "level": level,
            "segment_index": index,
            "start_word_index": chunk[0]["word_index"],
            "end_word_index": chunk[-1]["word_index"],
            "start_word": chunk[0]["word"],
            "end_word": chunk[-1]["word"],
            "word_count": len(chunk),
            "pulse_count": pulses,
            "accent_count": accents,
            "density_accents_per_pulse": round(accents / pulses, 8) if pulses else "",
            "cadence_taamim": "INCOMPLETE_TRAILING",
            "cadence_class": "incomplete",
            "shape_PA": f"P{pulses}_A{accents}",
            "bucket_PA": f"{bucket_pulses(pulses)}_{bucket_accents(accents)}",
            "is_incomplete": 1,
        })
    return rows


def build_relations(
    parent_rows: list[dict[str, Any]],
    child_rows: list[dict[str, Any]],
    relation: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parents = [r for r in parent_rows if not r["is_incomplete"]]
    children = [r for r in child_rows if not r["is_incomplete"]]
    relation_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []

    child_pos = 0
    for parent in parents:
        selected: list[dict[str, Any]] = []
        while child_pos < len(children) and children[child_pos]["end_word_index"] <= parent["end_word_index"]:
            child = children[child_pos]
            if child["start_word_index"] >= parent["start_word_index"]:
                selected.append(child)
            child_pos += 1

        pulse_sum = sum(x["pulse_count"] for x in selected)
        accent_sum = sum(x["accent_count"] for x in selected)
        word_sum = sum(x["word_count"] for x in selected)
        exact = (
            pulse_sum == parent["pulse_count"] and
            accent_sum == parent["accent_count"] and
            word_sum == parent["word_count"] and
            bool(selected)
        )
        relation_rows.append({
            "relation": relation,
            "parent_level": parent["level"],
            "child_level": selected[0]["level"] if selected else "",
            "parent_index": parent["segment_index"],
            "parent_start_word_index": parent["start_word_index"],
            "parent_end_word_index": parent["end_word_index"],
            "parent_word_count": parent["word_count"],
            "parent_pulse_count": parent["pulse_count"],
            "parent_accent_count": parent["accent_count"],
            "parent_shape_PA": parent["shape_PA"],
            "parent_bucket_PA": parent["bucket_PA"],
            "parent_cadence_taamim": parent["cadence_taamim"],
            "child_count": len(selected),
            "child_word_seq": "+".join(str(x["word_count"]) for x in selected),
            "child_pulse_seq": "+".join(str(x["pulse_count"]) for x in selected),
            "child_accent_seq": "+".join(str(x["accent_count"]) for x in selected),
            "child_exact_shape_seq": " | ".join(x["shape_PA"] for x in selected),
            "child_bucket_shape_seq": " | ".join(x["bucket_PA"] for x in selected),
            "child_cadence_seq": " | ".join(x["cadence_taamim"] for x in selected),
            "child_word_sum": word_sum,
            "child_pulse_sum": pulse_sum,
            "child_accent_sum": accent_sum,
            "partition_exact": int(exact),
        })
        validation_rows.append({
            "relation": relation,
            "parent_index": parent["segment_index"],
            "word_match": int(word_sum == parent["word_count"]),
            "pulse_match": int(pulse_sum == parent["pulse_count"]),
            "accent_match": int(accent_sum == parent["accent_count"]),
            "has_children": int(bool(selected)),
            "partition_exact": int(exact),
        })
    return relation_rows, validation_rows


def median(values: list[int]) -> float | str:
    if not values:
        return ""
    values = sorted(values)
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def normalized_entropy(counter: Counter[Any]) -> float | str:
    total = sum(counter.values())
    if total <= 0:
        return ""
    if len(counter) <= 1:
        return 0.0
    h = -sum((count / total) * math.log(count / total) for count in counter.values())
    return round(h / math.log(len(counter)), 8)


def value_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [int(r[field]) for r in rows if not r["is_incomplete"]]
    if not values:
        return {}
    counts = Counter(values)
    top = counts.most_common(10)
    return {
        f"{field}_n": len(values),
        f"{field}_unique": len(counts),
        f"{field}_mean": round(sum(values) / len(values), 8),
        f"{field}_median": median(values),
        f"{field}_min": min(values),
        f"{field}_max": max(values),
        f"{field}_entropy_norm": normalized_entropy(counts),
        f"{field}_top1": top[0][0],
        f"{field}_top1_share": round(top[0][1] / len(values), 8),
        f"{field}_top3": "+".join(str(k) for k, _ in top[:3]),
        f"{field}_top3_share": round(sum(v for _, v in top[:3]) / len(values), 8),
        f"{field}_top5": "+".join(str(k) for k, _ in top[:5]),
        f"{field}_top5_share": round(sum(v for _, v in top[:5]) / len(values), 8),
    }


def level_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [r for r in rows if not r["is_incomplete"]]
    result = {
        "level": rows[0]["level"] if rows else "",
        "n_segments": len(complete),
        "n_incomplete_trailing": sum(r["is_incomplete"] for r in rows),
    }
    for field in ("word_count", "pulse_count", "accent_count"):
        result.update(value_summary(rows, field))
    densities = [float(r["density_accents_per_pulse"]) for r in complete if r["density_accents_per_pulse"] != ""]
    result["density_mean"] = round(sum(densities) / len(densities), 8) if densities else ""
    result["shape_top5"] = "+".join(k for k, _ in Counter(r["shape_PA"] for r in complete).most_common(5))
    result["bucket_shape_top5"] = "+".join(k for k, _ in Counter(r["bucket_PA"] for r in complete).most_common(5))
    return result


def relation_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(int(r["child_count"]) for r in rows)
    n = len(rows)
    values = [int(r["child_count"]) for r in rows]
    top = counts.most_common(10)
    return {
        "relation": rows[0]["relation"] if rows else "",
        "n_parent_segments": n,
        "child_count_mean": round(sum(values) / n, 8) if n else "",
        "child_count_median": median(values),
        "child_count_entropy_norm": normalized_entropy(counts),
        "child_count_top5": "+".join(str(k) for k, _ in top[:5]),
        "child_count_top5_share": round(sum(v for _, v in top[:5]) / n, 8) if n else "",
        "child_count_1_share": round(counts.get(1, 0) / n, 8) if n else "",
        "child_count_2_share": round(counts.get(2, 0) / n, 8) if n else "",
        "child_count_3_share": round(counts.get(3, 0) / n, 8) if n else "",
        "partition_exact_share": round(sum(int(r["partition_exact"]) for r in rows) / n, 8) if n else "",
        "top_child_pulse_sequences": "+".join(k for k, _ in Counter(r["child_pulse_seq"] for r in rows).most_common(5)),
        "top_child_accent_sequences": "+".join(k for k, _ in Counter(r["child_accent_seq"] for r in rows).most_common(5)),
        "top_child_bucket_sequences": "+".join(k for k, _ in Counter(r["child_bucket_shape_seq"] for r in rows).most_common(5)),
    }


def frequency_rows(rows: list[dict[str, Any]], field: str, max_value: int) -> list[dict[str, Any]]:
    values = [int(r[field]) for r in rows if not r["is_incomplete"]]
    counts = Counter(v if v <= max_value else f">{max_value}" for v in values)
    total = len(values)
    def sort_key(value: Any) -> int:
        return 10**9 if isinstance(value, str) else int(value)
    output: list[dict[str, Any]] = []
    cumulative = 0
    for value in sorted(counts, key=sort_key):
        cumulative += counts[value]
        output.append({
            "measure": field,
            "value": value,
            "count": counts[value],
            "share": round(counts[value] / total, 8) if total else 0,
            "cum_share": round(cumulative / total, 8) if total else 0,
        })
    return output


def size_ngram_rows(rows: list[dict[str, Any]], field: str, ns: list[int], top_k: int) -> list[dict[str, Any]]:
    values = [int(r[field]) for r in rows if not r["is_incomplete"]]
    output: list[dict[str, Any]] = []
    for n in ns:
        grams = [tuple(values[i:i + n]) for i in range(len(values) - n + 1)]
        counts = Counter(grams)
        total = sum(counts.values())
        for rank, (gram, count) in enumerate(counts.most_common(top_k), 1):
            output.append({
                "measure": field,
                "ngram_n": n,
                "rank": rank,
                "pattern": "-".join(map(str, gram)),
                "count": count,
                "share": round(count / total, 8) if total else 0,
            })
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def add_book(rows: list[dict[str, Any]], book: str, run_label: str) -> list[dict[str, Any]]:
    for row in rows:
        row["book"] = book
        row["run_label"] = run_label
    return rows


def analyze_book(config: dict[str, Any]) -> dict[str, Any]:
    tag = config["tag"]
    path = Path(config["path"])
    out_dir = Path(config["out_dir"])
    run_label = config["run_label"]
    records = parse_records(path.read_text(encoding="utf-8-sig"))

    levels = {level: build_segments(records, level) for level in LEVEL_BOUNDARIES}
    relation_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    relation_summaries: list[dict[str, Any]] = []
    for name, (parent_level, child_level) in RELATIONS.items():
        rel, validation = build_relations(levels[parent_level], levels[child_level], name)
        relation_rows.extend(rel)
        validation_rows.extend(validation)
        relation_summaries.append(relation_summary(rel))

    segment_rows = [row for level in ("verse", "major", "minor") for row in levels[level]]
    level_summaries = [level_summary(levels[level]) for level in ("verse", "major", "minor")]

    frequency: list[dict[str, Any]] = []
    size_ngrams: list[dict[str, Any]] = []
    for level, rows in levels.items():
        for field, maximum in (
            ("word_count", config["max_words"]),
            ("pulse_count", config["max_pulses"]),
            ("accent_count", config["max_accents"]),
        ):
            for row in frequency_rows(rows, field, maximum):
                row["level"] = level
                frequency.append(row)
            for row in size_ngram_rows(rows, field, config["ngram_ns"], config["top_ngram"]):
                row["level"] = level
                size_ngrams.append(row)

    for collection in (segment_rows, relation_rows, validation_rows, level_summaries, relation_summaries, frequency, size_ngrams):
        add_book(collection, tag, run_label)

    out = out_dir / tag
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "hierarchy_segments.csv", segment_rows)
    write_csv(out / "hierarchy_relations.csv", relation_rows)
    write_csv(out / "hierarchy_level_summary.csv", level_summaries)
    write_csv(out / "hierarchy_relation_summary.csv", relation_summaries)
    write_csv(out / "hierarchy_size_frequency.csv", frequency)
    write_csv(out / "hierarchy_size_ngram_top.csv", size_ngrams)
    write_csv(out / "hierarchy_validation.csv", validation_rows)

    meta = {
        "analysis": "taam_hierarchical_structure",
        "book": tag,
        "run_label": run_label,
        "input": str(path),
        "input_sha256": sha256_file(path),
        "n_words": len(records),
        "n_pulses": sum(r["pulse_count"] for r in records),
        "n_accents": sum(r["has_accent_event"] for r in records),
        "levels": {k: sorted(v) for k, v in LEVEL_BOUNDARIES.items()},
        "relations": RELATIONS,
        "parameters": {
            "jobs_requested": config["jobs_requested"],
            "max_words": config["max_words"],
            "max_pulses": config["max_pulses"],
            "max_accents": config["max_accents"],
            "top_ngram": config["top_ngram"],
            "ngram_ns": config["ngram_ns"],
        },
        "level_summary": level_summaries,
        "relation_summary": relation_summaries,
        "validation_all_exact": all(r["partition_exact"] == 1 for r in validation_rows),
    }
    (out / "hierarchy_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "meta": meta,
        "segments": segment_rows,
        "relations": relation_rows,
        "level_summary": level_summaries,
        "relation_summary": relation_summaries,
        "frequency": frequency,
        "size_ngrams": size_ngrams,
        "validation": validation_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--book", action="append", nargs=2, required=True, metavar=("TAG", "PATH"))
    parser.add_argument("--run_label", default="main")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--max_words", type=int, default=40)
    parser.add_argument("--max_pulses", type=int, default=80)
    parser.add_argument("--max_accents", type=int, default=25)
    parser.add_argument("--top_ngram", type=int, default=50)
    parser.add_argument("--ngram_ns", default="2,3,4,5,6")
    args = parser.parse_args()

    try:
        ngram_ns = parse_int_list(args.ngram_ns)
    except ValueError as exc:
        parser.error(str(exc))
    if not ngram_ns:
        parser.error("ngram_ns must not be empty")
    if args.jobs < 1:
        parser.error("jobs must be >= 1")
    for name in ("max_words", "max_pulses", "max_accents", "top_ngram"):
        if getattr(args, name) < 1:
            parser.error(f"{name} must be >= 1")
    tags = [tag for tag, _ in args.book]
    if len(tags) != len(set(tags)):
        parser.error("book tags must be unique")
    for tag, path_text in args.book:
        if not tag.strip():
            parser.error("book tags must not be empty")
        if not Path(path_text).is_file():
            parser.error(f"input file does not exist: {path_text}")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    known_outputs = {
        "ALL_hierarchy_segments.csv", "ALL_hierarchy_relations.csv",
        "ALL_hierarchy_level_summary.csv", "ALL_hierarchy_relation_summary.csv",
        "ALL_hierarchy_size_frequency.csv", "ALL_hierarchy_size_ngram_top.csv",
        "ALL_hierarchy_validation.csv", "ALL_hierarchy_meta.json",
    }
    for filename in known_outputs:
        path = out / filename
        if path.is_file():
            path.unlink()
    per_book_outputs = {
        "hierarchy_segments.csv", "hierarchy_relations.csv",
        "hierarchy_level_summary.csv", "hierarchy_relation_summary.csv",
        "hierarchy_size_frequency.csv", "hierarchy_size_ngram_top.csv",
        "hierarchy_validation.csv", "hierarchy_meta.json",
    }
    for tag in tags:
        for filename in per_book_outputs:
            path = out / tag / filename
            if path.is_file():
                path.unlink()
    configs = [{
        "tag": tag,
        "path": path,
        "out_dir": str(out),
        "run_label": args.run_label,
        "jobs_requested": args.jobs,
        "max_words": args.max_words,
        "max_pulses": args.max_pulses,
        "max_accents": args.max_accents,
        "top_ngram": args.top_ngram,
        "ngram_ns": ngram_ns,
    } for tag, path in args.book]

    results: dict[str, dict[str, Any]] = {}
    jobs = max(1, min(args.jobs, len(configs)))
    if jobs == 1:
        for config in configs:
            result = analyze_book(config)
            results[config["tag"]] = result
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(analyze_book, config): config["tag"] for config in configs}
            for future in as_completed(futures):
                results[futures[future]] = future.result()

    ordered = [results[tag] for tag, _ in args.book]
    mappings = {
        "ALL_hierarchy_segments.csv": "segments",
        "ALL_hierarchy_relations.csv": "relations",
        "ALL_hierarchy_level_summary.csv": "level_summary",
        "ALL_hierarchy_relation_summary.csv": "relation_summary",
        "ALL_hierarchy_size_frequency.csv": "frequency",
        "ALL_hierarchy_size_ngram_top.csv": "size_ngrams",
        "ALL_hierarchy_validation.csv": "validation",
    }
    for filename, key in mappings.items():
        write_csv(out / filename, [row for result in ordered for row in result[key]])
    metas = [result["meta"] for result in ordered]
    (out / "ALL_hierarchy_meta.json").write_text(json.dumps(metas, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== TAAM HIERARCHICAL STRUCTURE ===")
    print("out:", out)
    print("run_label:", args.run_label, "jobs:", jobs)
    print("max_words:", args.max_words, "max_pulses:", args.max_pulses,
          "max_accents:", args.max_accents, "top_ngram:", args.top_ngram,
          "ngram_ns:", args.ngram_ns)
    for result in ordered:
        meta = result["meta"]
        print()
        print(meta["book"], "| words:", meta["n_words"], "| pulses:", meta["n_pulses"], "| accents:", meta["n_accents"])
        for row in meta["level_summary"]:
            print(
                f"  {row['level']}: n={row['n_segments']} "
                f"pulses mean={row.get('pulse_count_mean')} med={row.get('pulse_count_median')} "
                f"accents mean={row.get('accent_count_mean')} med={row.get('accent_count_median')} "
                f"top5 accents={row.get('accent_count_top5')} share={row.get('accent_count_top5_share')}"
            )
        for row in meta["relation_summary"]:
            print(
                f"  {row['relation']}: n={row['n_parent_segments']} "
                f"child mean={row['child_count_mean']} med={row['child_count_median']} "
                f"2-share={row['child_count_2_share']} exact={row['partition_exact_share']}"
            )
        print("  validation_all_exact:", meta["validation_all_exact"])
    print("DONE")


if __name__ == "__main__":
    main()
