# -*- coding: utf-8 -*-
"""Taam-only reconstruction of hidden minor cadence boundaries.

The canonical feature ladder separates strictly adjacent context from features
of the current word. No rhyme, lexical, or phonetic features are computed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


WORD_RE = re.compile(r"\[([^\]]+)\]")
EXT_RE = re.compile(r"^\{([^}]+)\}$")

MAJOR = {"atnah", "atnah_hafukh", "sof_pasuq"}
MINOR = {"revia", "zaqef_qatan", "zaqef_gadol", "shalshelet", "paseq"}

FEATURE_SET_DEFINITIONS = {
    "structure": "major-unit geometry only",
    "current_only": "visible non-minor/non-major taamim on the current word only",
    "adjacent_only": "visible taamim on the immediately previous and next words only",
    "local_taam": "current plus immediately previous and next visible taamim; no geometry",
    "structure_current": "major-unit geometry plus current-word visible taamim",
    "structure_local": "major-unit geometry plus current, previous, and next visible taamim",
}
DEFAULT_FEATURE_SETS = list(FEATURE_SET_DEFINITIONS)

PAIRWISE_COMPARISONS = [
    ("current_only", "structure"),
    ("adjacent_only", "structure"),
    ("local_taam", "structure"),
    ("local_taam", "adjacent_only"),
    ("structure_current", "structure"),
    ("structure_local", "structure"),
    ("structure_local", "structure_current"),
]


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_seed(*parts):
    raw = "\x1f".join(str(x) for x in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def split_tok(tok):
    m = EXT_RE.match(tok)
    if m:
        return "", [], [x.strip() for x in m.group(1).split(",") if x.strip()]
    m = WORD_RE.search(tok)
    if not m:
        return tok, [], []
    return (
        WORD_RE.sub("", tok),
        [x.strip() for x in m.group(1).split(",") if x.strip()],
        [],
    )


def parse_records(text):
    recs = []
    for tok in text.replace("\ufeff", "").split():
        word, internal, external = split_tok(tok)
        if external:
            if recs:
                recs[-1]["external_taamim"].extend(external)
                recs[-1]["all_taamim"].extend(external)
            continue
        if not word:
            continue
        recs.append(
            {
                "idx": len(recs),
                "word": word,
                "internal_taamim": internal,
                "external_taamim": [],
                "all_taamim": list(internal),
                "major_unit": None,
                "major_start": None,
                "major_end": None,
                "pos_from_major_start": None,
                "dist_to_major_end": None,
                "major_len": None,
            }
        )
    return recs


def has_any(record, signs):
    return any(t in signs for t in record["all_taamim"])


def hidden_minor_label(record):
    return int(has_any(record, MINOR))


def assign_major_units(recs):
    unit_id = 0
    start = 0
    for i, record in enumerate(recs):
        if has_any(record, MAJOR):
            for k in range(start, i + 1):
                recs[k].update(
                    major_unit=unit_id,
                    major_start=start,
                    major_end=i,
                    pos_from_major_start=k - start,
                    dist_to_major_end=i - k,
                    major_len=i - start + 1,
                )
            unit_id += 1
            start = i + 1
    if start < len(recs):
        end = len(recs) - 1
        for k in range(start, end + 1):
            recs[k].update(
                major_unit=unit_id,
                major_start=start,
                major_end=end,
                pos_from_major_start=k - start,
                dist_to_major_end=end - k,
                major_len=end - start + 1,
            )


def candidate_indices(recs, include_edges=False):
    out = []
    for i, record in enumerate(recs):
        if record["major_unit"] is None or has_any(record, MAJOR):
            continue
        if not include_edges and (
            record["pos_from_major_start"] == 0 or record["dist_to_major_end"] == 0
        ):
            continue
        out.append(i)
    return out


def cap_num(value, cap):
    if value is None:
        return "NA"
    return f"{cap}+" if value >= cap else str(value)


def rel_bucket(record):
    p = record["pos_from_major_start"] / max(1, (record["major_len"] or 1) - 1)
    if p < 0.25:
        return "Q1"
    if p < 0.5:
        return "Q2"
    if p < 0.75:
        return "Q3"
    return "Q4"


def visible_taam_signature(record):
    if record is None:
        return "NA"
    signs = [t for t in record["all_taamim"] if t not in MINOR and t not in MAJOR]
    return "+".join(signs) if signs else "NONE"


def structure_features(record, pos_cap, len_cap):
    pos = cap_num(record["pos_from_major_start"], pos_cap)
    dist = cap_num(record["dist_to_major_end"], pos_cap)
    return [
        "bias",
        "pos_start=" + pos,
        "dist_end=" + dist,
        "major_len=" + cap_num(record["major_len"], len_cap),
        "rel=" + rel_bucket(record),
        "half="
        + (
            "first"
            if record["pos_from_major_start"] < (record["major_len"] or 1) / 2
            else "second"
        ),
        "pos_dist_combo=" + pos + "_" + dist,
    ]


def current_features(record):
    sig = visible_taam_signature(record)
    return [
        "taam_current=" + sig,
        "has_visible_taam=" + ("1" if sig != "NONE" else "0"),
    ]


def adjacent_features(recs, i):
    prev_record = recs[i - 1] if i > 0 else None
    next_record = recs[i + 1] if i + 1 < len(recs) else None
    return [
        "taam_prev="
        + (visible_taam_signature(prev_record) if prev_record else "START"),
        "taam_next="
        + (visible_taam_signature(next_record) if next_record else "END"),
        "prev_major=" + ("1" if prev_record and has_any(prev_record, MAJOR) else "0"),
        "next_major=" + ("1" if next_record and has_any(next_record, MAJOR) else "0"),
    ]


def features_for_index(recs, i, feature_set, pos_cap, len_cap):
    record = recs[i]
    feats = []
    if feature_set in {"structure", "structure_current", "structure_local"}:
        feats.extend(structure_features(record, pos_cap, len_cap))
    if feature_set in {
        "current_only",
        "local_taam",
        "structure_current",
        "structure_local",
    }:
        feats.extend(current_features(record))
    if feature_set in {"adjacent_only", "local_taam", "structure_local"}:
        feats.extend(adjacent_features(recs, i))
    return feats or ["bias"]


def make_splits(recs, candidates, seed, evaluation_mode, folds, test_frac, split_mode):
    rng = random.Random(seed)
    if split_mode == "major_unit":
        groups = sorted({recs[i]["major_unit"] for i in candidates})
        rng.shuffle(groups)
        group_for_index = {i: recs[i]["major_unit"] for i in candidates}
    else:
        groups = list(candidates)
        rng.shuffle(groups)
        group_for_index = {i: i for i in candidates}

    if evaluation_mode == "cross_validation":
        if folds < 2 or folds > len(groups):
            raise ValueError(f"folds must be between 2 and {len(groups)}")
        test_group_sets = [set(groups[f::folds]) for f in range(folds)]
    else:
        n_test = max(1, int(len(groups) * test_frac))
        test_group_sets = [set(groups[:n_test])]

    split_rows = []
    for fold, test_groups in enumerate(test_group_sets):
        test = [i for i in candidates if group_for_index[i] in test_groups]
        train = [i for i in candidates if group_for_index[i] not in test_groups]
        if not train or not test:
            raise ValueError(f"empty train or test partition in fold {fold}")
        split_rows.append(
            {
                "fold": fold,
                "train": train,
                "test": test,
                "test_groups": test_groups,
            }
        )
    return split_rows


def train_nb(recs, indices, feature_set, pos_cap, len_cap, alpha=1.0):
    pos_count = 0
    neg_count = 0
    feat_pos = Counter()
    feat_neg = Counter()
    vocab = set()
    for i in indices:
        y = hidden_minor_label(recs[i])
        feats = features_for_index(recs, i, feature_set, pos_cap, len_cap)
        vocab.update(feats)
        if y:
            pos_count += 1
            feat_pos.update(feats)
        else:
            neg_count += 1
            feat_neg.update(feats)
    total = pos_count + neg_count
    return {
        "pos_count": pos_count,
        "neg_count": neg_count,
        "prior_pos": (pos_count + alpha) / (total + 2 * alpha),
        "prior_neg": (neg_count + alpha) / (total + 2 * alpha),
        "feat_pos": feat_pos,
        "feat_neg": feat_neg,
        "npos_feats": sum(feat_pos.values()),
        "nneg_feats": sum(feat_neg.values()),
        "V": max(1, len(vocab)),
        "alpha": alpha,
    }


def score_nb(model, feats):
    alpha = model["alpha"]
    vocab_size = model["V"]
    log_pos = math.log(model["prior_pos"])
    log_neg = math.log(model["prior_neg"])
    for feature in feats:
        log_pos += math.log(
            (model["feat_pos"][feature] + alpha)
            / (model["npos_feats"] + alpha * vocab_size)
        )
        log_neg += math.log(
            (model["feat_neg"][feature] + alpha)
            / (model["nneg_feats"] + alpha * vocab_size)
        )
    return log_pos - log_neg


def rank_fold(recs, test_indices, scores):
    gold = {i for i in test_indices if hidden_minor_label(recs[i])}
    k = len(gold)
    ranked = sorted(test_indices, key=lambda i: (-scores[i], i))
    predicted = set(ranked[:k])
    tp = len(gold & predicted)
    f1 = tp / k if k else 0.0
    return {
        "test_candidates": len(test_indices),
        "gold_boundaries": k,
        "predicted_boundaries": len(predicted),
        "tp": tp,
        "fp": len(predicted - gold),
        "fn": len(gold - predicted),
        "f1": f1,
    }, predicted


def baseline_random(recs, splits, seed, permutations):
    if permutations <= 0:
        return []
    rng = random.Random(seed)
    fold_specs = []
    total_gold = 0
    for split in splits:
        test = list(split["test"])
        gold = {i for i in test if hidden_minor_label(recs[i])}
        fold_specs.append((test, gold, len(gold)))
        total_gold += len(gold)
    values = []
    for _ in range(permutations):
        total_tp = 0
        for test, gold, k in fold_specs:
            predicted = set(rng.sample(test, k)) if k else set()
            total_tp += len(gold & predicted)
        values.append(total_tp / total_gold if total_gold else 0.0)
    return values


def null_stats(observed, values):
    if not values:
        return "", "", "", ""
    mean = sum(values) / len(values)
    sd = (
        sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    ) ** 0.5 if len(values) > 1 else 0.0
    z = (observed - mean) / sd if sd else 0.0
    p = (1 + sum(value >= observed for value in values)) / (len(values) + 1)
    return round(mean, 8), round(sd, 8), round(z, 6), round(p, 8)


def sample_sd(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((x - mean) ** 2 for x in values) / (len(values) - 1)) ** 0.5


def feature_weights(model, top_n, fold):
    vocab = sorted(set(model["feat_pos"]) | set(model["feat_neg"]))
    alpha = model["alpha"]
    vocab_size = model["V"]
    rows = []
    for feature in vocab:
        p_pos = (model["feat_pos"][feature] + alpha) / (
            model["npos_feats"] + alpha * vocab_size
        )
        p_neg = (model["feat_neg"][feature] + alpha) / (
            model["nneg_feats"] + alpha * vocab_size
        )
        rows.append(
            {
                "fold": fold,
                "feature": feature,
                "pos_count": model["feat_pos"][feature],
                "neg_count": model["feat_neg"][feature],
                "log_likelihood_ratio": round(math.log(p_pos / p_neg), 8),
            }
        )

    positive = sorted(rows, key=lambda row: (-row["log_likelihood_ratio"], row["feature"]))
    negative = sorted(rows, key=lambda row: (row["log_likelihood_ratio"], row["feature"]))
    selected = []
    seen = set()
    for rank, row in enumerate(positive[:top_n], 1):
        item = dict(row, direction="positive", rank=rank)
        selected.append(item)
        seen.add(row["feature"])
    rank = 0
    for row in negative:
        if row["feature"] in seen:
            continue
        rank += 1
        selected.append(dict(row, direction="negative", rank=rank))
        if rank >= top_n:
            break
    return selected


def paired_signflip(
    recs,
    predicted_model,
    predicted_comparator,
    tested_indices,
    group_mode,
    total_gold,
    seed,
    permutations,
):
    contributions = Counter()
    for i in tested_indices:
        if not hidden_minor_label(recs[i]):
            continue
        group = recs[i]["major_unit"] if group_mode == "major_unit" else i
        contributions[group] += int(i in predicted_model) - int(i in predicted_comparator)
    nonzero = [value for value in contributions.values() if value]
    observed = sum(nonzero) / total_gold if total_gold else 0.0
    if permutations <= 0 or not nonzero:
        return observed, "", "", "", "", len(nonzero)
    rng = random.Random(seed)
    null = []
    for _ in range(permutations):
        delta = sum(value if rng.getrandbits(1) else -value for value in nonzero)
        null.append(delta / total_gold if total_gold else 0.0)
    mean, sd, z, p = null_stats(observed, null)
    return observed, mean, sd, z, p, len(nonzero)


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def analyze_book(task):
    (
        tag,
        input_path,
        out_dir,
        feature_sets,
        seed,
        evaluation_mode,
        folds,
        test_frac,
        include_edges,
        random_perm,
        paired_perm,
        split_mode,
        pos_cap,
        len_cap,
        top_weights,
        alpha,
        run_label,
        normalized_command,
        source_sha256,
    ) = task

    recs = parse_records(Path(input_path).read_text(encoding="utf-8-sig"))
    assign_major_units(recs)
    candidates = candidate_indices(recs, include_edges)
    splits = make_splits(
        recs, candidates, seed, evaluation_mode, folds, test_frac, split_mode
    )
    random_values = baseline_random(
        recs, splits, stable_seed(seed, tag, "random_top_k"), random_perm
    )

    fold_results = {feature_set: [] for feature_set in feature_sets}
    all_predictions = {feature_set: set() for feature_set in feature_sets}
    scores_by_feature = {feature_set: {} for feature_set in feature_sets}
    weights_by_feature = {feature_set: [] for feature_set in feature_sets}
    candidate_fold = {}

    for split in splits:
        fold = split["fold"]
        for i in split["test"]:
            candidate_fold[i] = fold
        for feature_set in feature_sets:
            model = train_nb(
                recs, split["train"], feature_set, pos_cap, len_cap, alpha
            )
            scores = {
                i: score_nb(
                    model,
                    features_for_index(recs, i, feature_set, pos_cap, len_cap),
                )
                for i in split["test"]
            }
            fold_result, predicted = rank_fold(recs, split["test"], scores)
            fold_result.update(
                {
                    "fold": fold,
                    "n_train": len(split["train"]),
                    "n_test_groups": len(split["test_groups"]),
                    "train_pos": model["pos_count"],
                    "train_neg": model["neg_count"],
                }
            )
            fold_results[feature_set].append(fold_result)
            all_predictions[feature_set].update(predicted)
            scores_by_feature[feature_set].update(scores)
            weights_by_feature[feature_set].extend(
                feature_weights(model, top_weights, fold)
            )

    summary_rows = []
    for feature_set in feature_sets:
        results = fold_results[feature_set]
        total_gold = sum(row["gold_boundaries"] for row in results)
        total_tp = sum(row["tp"] for row in results)
        f1 = total_tp / total_gold if total_gold else 0.0
        random_mean, random_sd, random_z, random_p = null_stats(f1, random_values)
        fold_f1 = [row["f1"] for row in results]
        summary_rows.append(
            {
                "book": tag,
                "run_label": run_label,
                "feature_set": feature_set,
                "model_role": (
                    "geometry_baseline"
                    if feature_set == "structure"
                    else "strict_adjacency_primary"
                    if feature_set == "adjacent_only"
                    else "maximal_reconstruction"
                    if feature_set == "structure_local"
                    else "ablation"
                ),
                "n_words": len(recs),
                "n_candidates": len(candidates),
                "n_minor_boundaries_candidates": sum(
                    hidden_minor_label(recs[i]) for i in candidates
                ),
                "evaluation_mode": evaluation_mode,
                "folds": len(splits),
                "split_mode": split_mode,
                "test_frac": test_frac if evaluation_mode == "holdout" else "NA",
                "include_edges": include_edges,
                "pos_cap": pos_cap,
                "len_cap": len_cap,
                "alpha": alpha,
                "test_candidates": sum(row["test_candidates"] for row in results),
                "gold_boundaries": total_gold,
                "predicted_boundaries": sum(
                    row["predicted_boundaries"] for row in results
                ),
                "tp": total_tp,
                "fp": sum(row["fp"] for row in results),
                "fn": sum(row["fn"] for row in results),
                "precision": round(f1, 8),
                "recall": round(f1, 8),
                "f1": round(f1, 8),
                "fold_f1_mean": round(sum(fold_f1) / len(fold_f1), 8),
                "fold_f1_sd": round(sample_sd(fold_f1), 8),
                "fold_f1_min": round(min(fold_f1), 8),
                "fold_f1_max": round(max(fold_f1), 8),
                "random_f1_mean": random_mean,
                "random_f1_sd": random_sd,
                "model_vs_random_f1_z": random_z,
                "model_vs_random_empirical_p": random_p,
            }
        )

    tested_indices = sorted(candidate_fold)
    total_gold = sum(hidden_minor_label(recs[i]) for i in tested_indices)
    paired_rows = []
    for model_name, comparator_name in PAIRWISE_COMPARISONS:
        if model_name not in feature_sets or comparator_name not in feature_sets:
            continue
        observed, null_mean, null_sd, z, p, nonzero_groups = paired_signflip(
            recs,
            all_predictions[model_name],
            all_predictions[comparator_name],
            tested_indices,
            split_mode,
            total_gold,
            stable_seed(seed, tag, model_name, comparator_name, "paired"),
            paired_perm,
        )
        paired_rows.append(
            {
                "book": tag,
                "run_label": run_label,
                "model": model_name,
                "comparator": comparator_name,
                "observed_f1_difference": round(observed, 8),
                "null_mean": null_mean,
                "null_sd": null_sd,
                "z": z,
                "empirical_p_one_sided": p,
                "permutations": paired_perm,
                "cluster_unit": "major_unit" if split_mode == "major_unit" else "candidate_word",
                "nonzero_clusters": nonzero_groups,
            }
        )

    prediction_rows = []
    for i in tested_indices:
        record = recs[i]
        row = {
            "book": tag,
            "fold": candidate_fold[i],
            "idx": i,
            "word": record["word"],
            "gold_minor_boundary": hidden_minor_label(record),
            "major_unit": record["major_unit"],
            "pos_from_major_start": record["pos_from_major_start"],
            "dist_to_major_end": record["dist_to_major_end"],
            "major_len": record["major_len"],
            "visible_taam": visible_taam_signature(record),
            "true_taam_hidden_from_model": ",".join(record["all_taamim"]),
        }
        for feature_set in feature_sets:
            row[f"score_{feature_set}"] = round(
                scores_by_feature[feature_set][i], 8
            )
            row[f"predicted_{feature_set}"] = int(
                i in all_predictions[feature_set]
            )
        prediction_rows.append(row)

    out = Path(out_dir) / tag
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "boundary_reconstruction_summary.csv"
    predictions_path = out / "boundary_reconstruction_predictions.csv"
    comparisons_path = out / "boundary_reconstruction_paired_comparisons.csv"
    write_csv(summary_path, summary_rows)
    write_csv(predictions_path, prediction_rows)
    write_csv(comparisons_path, paired_rows)
    weight_paths = {}
    for feature_set in feature_sets:
        path = out / f"feature_weights_{feature_set}.csv"
        write_csv(path, weights_by_feature[feature_set])
        weight_paths[feature_set] = path

    output_hashes = {
        summary_path.name: sha256_file(summary_path),
        predictions_path.name: sha256_file(predictions_path),
        comparisons_path.name: sha256_file(comparisons_path),
    }
    output_hashes.update(
        {path.name: sha256_file(path) for path in weight_paths.values()}
    )
    meta = {
        "schema_version": "2.0",
        "analysis": "taam_boundary_reconstruction",
        "book": tag,
        "run_label": run_label,
        "input": {"path": str(input_path), "sha256": sha256_file(input_path)},
        "implementation_sha256": source_sha256,
        "normalized_analysis_command": normalized_command,
        "parameters": {
            "feature_sets": feature_sets,
            "seed": seed,
            "evaluation_mode": evaluation_mode,
            "folds": folds,
            "test_frac": test_frac,
            "split_mode": split_mode,
            "include_edges": include_edges,
            "random_perm": random_perm,
            "paired_perm": paired_perm,
            "pos_cap": pos_cap,
            "len_cap": len_cap,
            "top_weights": top_weights,
            "alpha": alpha,
            "ranking_tie_break": "ascending global word index",
        },
        "definitions": {
            "major": sorted(MAJOR),
            "hidden_minor_target": sorted(MINOR),
            "feature_sets": {
                name: FEATURE_SET_DEFINITIONS[name] for name in feature_sets
            },
            "candidate_policy": (
                "major-cadence words are always excluded; first/terminal non-major "
                "positions are excluded unless include_edges is enabled"
            ),
            "evaluation": (
                "top-k within each test fold, with k equal to the number of gold "
                "hidden boundaries; precision=recall=F1 by design"
            ),
            "random_null": "matched random top-k within each test fold",
            "paired_test": (
                "one-sided sign-flip permutation of per-cluster true-positive "
                "contributions; F1 difference is model minus comparator"
            ),
        },
        "candidate_counts": {
            "words": len(recs),
            "candidates": len(candidates),
            "hidden_minor_boundaries": sum(
                hidden_minor_label(recs[i]) for i in candidates
            ),
            "tested_candidates": len(tested_indices),
            "tested_hidden_minor_boundaries": total_gold,
        },
        "folds": [
            {
                "fold": split["fold"],
                "train_candidates": len(split["train"]),
                "test_candidates": len(split["test"]),
                "test_groups": len(split["test_groups"]),
                "test_hidden_minor_boundaries": sum(
                    hidden_minor_label(recs[i]) for i in split["test"]
                ),
            }
            for split in splits
        ],
        "outputs_sha256": output_hashes,
        "summary": summary_rows,
        "paired_comparisons": paired_rows,
    }
    meta_path = out / "boundary_reconstruction_meta.json"
    write_json(meta_path, meta)
    return summary_rows, paired_rows, meta


def parse_feature_sets(value):
    if not value or value == "default":
        return list(DEFAULT_FEATURE_SETS)
    result = [x.strip() for x in value.split(",") if x.strip()]
    unknown = [x for x in result if x not in FEATURE_SET_DEFINITIONS]
    if unknown:
        raise ValueError("unknown feature set(s): " + ", ".join(unknown))
    if len(result) != len(set(result)):
        raise ValueError("feature_sets contains duplicates")
    return result


def normalized_command(args, feature_sets):
    books = " ".join(f"--book {tag} {path}" for tag, path in args.book)
    return (
        "python src/analyses/core_taam/taam_boundary_reconstruction.py "
        f"--out_dir {args.out_dir} --run_label {args.run_label} "
        f"--jobs {args.jobs} "
        f"--feature_sets {','.join(feature_sets)} --seed {args.seed} "
        f"--evaluation_mode {args.evaluation_mode} --folds {args.folds} "
        f"--test_frac {args.test_frac} --split_mode {args.split_mode} "
        f"--random_perm {args.random_perm} --paired_perm {args.paired_perm} "
        f"--pos_cap {args.pos_cap} --len_cap {args.len_cap} "
        f"--top_weights {args.top_weights} --alpha {args.alpha} "
        + ("--include_edges " if args.include_edges else "")
        + books
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--book", action="append", nargs=2, required=True)
    parser.add_argument("--feature_sets", default="default")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--evaluation_mode",
        choices=["cross_validation", "holdout"],
        default="cross_validation",
    )
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--test_frac", type=float, default=0.2)
    parser.add_argument("--include_edges", action="store_true")
    parser.add_argument("--random_perm", type=int, default=1000)
    parser.add_argument("--paired_perm", type=int, default=10000)
    parser.add_argument(
        "--split_mode", choices=["major_unit", "random_words"], default="major_unit"
    )
    parser.add_argument("--pos_cap", type=int, default=10)
    parser.add_argument("--len_cap", type=int, default=30)
    parser.add_argument("--top_weights", type=int, default=80)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--run_label", default="main")
    args = parser.parse_args()

    if not 0 < args.test_frac < 1:
        parser.error("test_frac must be between 0 and 1")
    if args.random_perm < 0 or args.paired_perm < 0:
        parser.error("permutation counts must be non-negative")
    if args.top_weights < 1:
        parser.error("top_weights must be at least 1")
    if args.alpha <= 0:
        parser.error("alpha must be positive")
    if args.jobs < 1:
        parser.error("jobs must be at least 1")
    tags = [tag for tag, _ in args.book]
    if len(tags) != len(set(tags)):
        parser.error("book tags must be unique")
    for _, path in args.book:
        if not Path(path).is_file():
            parser.error(f"input file not found: {path}")

    try:
        feature_sets = parse_feature_sets(args.feature_sets)
    except ValueError as exc:
        parser.error(str(exc))

    source_sha256 = sha256_file(__file__)
    command = normalized_command(args, feature_sets)
    tasks = [
        (
            tag,
            path,
            args.out_dir,
            feature_sets,
            args.seed,
            args.evaluation_mode,
            args.folds,
            args.test_frac,
            args.include_edges,
            args.random_perm,
            args.paired_perm,
            args.split_mode,
            args.pos_cap,
            args.len_cap,
            args.top_weights,
            args.alpha,
            args.run_label,
            command,
            source_sha256,
        )
        for tag, path in args.book
    ]

    if args.jobs > 1:
        results = []
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(analyze_book, task): task[0] for task in tasks}
            for future in as_completed(futures):
                results.append(future.result())
        order = {tag: i for i, (tag, _) in enumerate(args.book)}
        results.sort(key=lambda result: order[result[2]["book"]])
    else:
        results = [analyze_book(task) for task in tasks]

    all_summary = []
    all_comparisons = []
    all_meta = []
    for summary, comparisons, meta in results:
        all_summary.extend(summary)
        all_comparisons.extend(comparisons)
        all_meta.append(meta)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_summary_path = out / "ALL_boundary_reconstruction_summary.csv"
    all_comparisons_path = out / "ALL_boundary_reconstruction_paired_comparisons.csv"
    write_csv(all_summary_path, all_summary)
    write_csv(all_comparisons_path, all_comparisons)
    all_meta_value = {
        "schema_version": "2.0",
        "analysis": "taam_boundary_reconstruction",
        "run_label": args.run_label,
        "implementation_sha256": source_sha256,
        "normalized_analysis_command": command,
        "execution": {"jobs": args.jobs, "python": sys.version.split()[0]},
        "outputs_sha256": {
            all_summary_path.name: sha256_file(all_summary_path),
            all_comparisons_path.name: sha256_file(all_comparisons_path),
        },
        "books": all_meta,
    }
    write_json(out / "ALL_boundary_reconstruction_meta.json", all_meta_value)

    print("=== TAAM BOUNDARY RECONSTRUCTION ===")
    print("out:", out)
    print(
        "run_label:",
        args.run_label,
        "jobs:",
        args.jobs,
        "evaluation_mode:",
        args.evaluation_mode,
        "split_mode:",
        args.split_mode,
    )
    print(
        "feature_sets:",
        ",".join(feature_sets),
        "random_perm:",
        args.random_perm,
        "paired_perm:",
        args.paired_perm,
        "include_edges:",
        args.include_edges,
    )
    print("note: top-k makes precision = recall = F1 by design")
    for summary, comparisons, meta in results:
        print("\n" + meta["book"])
        for row in summary:
            print(
                f"  {row['feature_set']}: F1={row['f1']} "
                f"Z={row['model_vs_random_f1_z']} "
                f"p={row['model_vs_random_empirical_p']} "
                f"TP={row['tp']}/{row['gold_boundaries']}"
            )
        for row in comparisons:
            if row["comparator"] == "structure" and row["model"] in {
                "adjacent_only",
                "structure_local",
            }:
                print(
                    f"  paired {row['model']} - structure: "
                    f"dF1={row['observed_f1_difference']} "
                    f"p={row['empirical_p_one_sided']}"
                )
    print("DONE")


if __name__ == "__main__":
    main()
