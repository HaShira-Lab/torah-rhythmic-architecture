#!/usr/bin/env python3
"""Shared rhyme protocol for Torah rhythmic analyses.

Protocol v4 separates strict segmental identity from optional phonetic
correspondence profiles.

Baseline (STRICT):
  * no cross-segment equivalences;
  * only identical normalized transliteration segments match;
  * FULL and optional non-transitive BRIDGE relations remain separate from
    phonetic equivalence.

The corpus-derived multigraph inventory is limited to kh, sh, and ts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

COMBINING_ACUTE = "\u0301"
STRESS_MARK = "ˈ"

# Verified against the five supplied annotated Torah files.
# 'tsh' is deliberately excluded: corpus occurrences are t + sh, not one unit.
DEFAULT_MULTIGRAPHS = ("kh", "sh", "ts")
# Deterministic default for the ambiguous sequence "tsh".
# Corpus-specific ambiguity: every observed "tsh" is t + sh, never ts + h.
# Rare lexical forms may permit the alternative segmentation ts + h.
FORCED_SEGMENT_PREFIXES: Mapping[str, tuple[str, ...]] = {"tsh": ("t", "sh")}
DEFAULT_VOWELS = frozenset({"a", "e", "i", "o", "u"})

# Every profile is optional. STRICT is the scientific baseline.
# Labels describe computational correspondence conditions, not claims of
# historical identity or identical pronunciation.
EQUIVALENCE_GROUPS: Mapping[str, tuple[tuple[str, ...], ...]] = {
    "STRICT": (),
    "VF": (("v", "f"),),
    "DT": (("d", "t"),),
    "PB": (("p", "b"),),
    "QK": (("q", "k"),),
    "H_KH": (("h", "kh"),),
    "TS_S": (("ts", "s"),),
    "VOICING": (("v", "f"), ("d", "t"), ("p", "b")),
    "TRADITION": (("q", "k"), ("h", "kh")),
    "VOICING_TRADITION": (
        ("v", "f"), ("d", "t"), ("p", "b"),
        ("q", "k"), ("h", "kh"),
    ),
    "EXPANDED_ALL": (
        ("v", "f"), ("d", "t"), ("p", "b"),
        ("q", "k"), ("h", "kh"), ("ts", "s"),
    ),
}
DEFAULT_EQUIVALENCE_PROFILE = "STRICT"
DEFAULT_EQUIVALENCES: Mapping[str, str] = {}

ANNOTATION_RE = re.compile(r"\[[^\]]*\]")
BRACE_MARKER_RE = re.compile(r"\{[^}]*\}")


class RhymeProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    text: str
    stressed: bool = False


@dataclass(frozen=True)
class RhymeSignature:
    source_token: str
    word: str
    segments: tuple[str, ...]
    stressed_index: int
    primary_raw: str
    primary_key: str
    bridge_raw: str | None
    bridge_key: str | None
    extended_left: bool
    equivalence_profile: str

    @property
    def key(self) -> str:
        """Backward-compatible alias: always the primary key."""
        return self.primary_key

    @property
    def raw_signature(self) -> str:
        """Backward-compatible alias: always the primary raw signature."""
        return self.primary_raw


@dataclass(frozen=True)
class RhymeMatch:
    rhymes: bool
    match_type: str | None
    matched_key: str | None
    left_role: str | None
    right_role: str | None


@dataclass(frozen=True)
class ProtocolConfig:
    vowels: frozenset[str] = DEFAULT_VOWELS
    multigraphs: tuple[str, ...] = DEFAULT_MULTIGRAPHS
    equivalences: Mapping[str, str] = field(default_factory=dict)
    equivalence_profile: str = DEFAULT_EQUIVALENCE_PROFILE
    require_stress: bool = True
    lowercase: bool = True

    @classmethod
    def from_profile(
        cls,
        profile: str = DEFAULT_EQUIVALENCE_PROFILE,
        *,
        require_stress: bool = True,
        lowercase: bool = True,
        vowels: frozenset[str] = DEFAULT_VOWELS,
        multigraphs: tuple[str, ...] = DEFAULT_MULTIGRAPHS,
    ) -> "ProtocolConfig":
        normalized = normalize_profile_name(profile)
        return cls(
            vowels=vowels,
            multigraphs=multigraphs,
            equivalences=equivalence_map_for_profile(normalized),
            equivalence_profile=normalized,
            require_stress=require_stress,
            lowercase=lowercase,
        )


def available_equivalence_profiles() -> tuple[str, ...]:
    return tuple(EQUIVALENCE_GROUPS.keys())


def normalize_profile_name(profile: str) -> str:
    name = profile.strip().upper().replace("-", "_")
    aliases = {
        "NONE": "STRICT",
        "EXACT": "STRICT",
        "LEGACY_ALL": "EXPANDED_ALL",
        "ALL": "EXPANDED_ALL",
        "HKH": "H_KH",
        "TSS": "TS_S",
    }
    name = aliases.get(name, name)
    if name not in EQUIVALENCE_GROUPS:
        allowed = ", ".join(available_equivalence_profiles())
        raise RhymeProtocolError(
            f"Unknown equivalence profile {profile!r}. Allowed: {allowed}"
        )
    return name


def equivalence_map_for_profile(profile: str) -> dict[str, str]:
    """Return segment-normalization mapping for one named profile."""
    name = normalize_profile_name(profile)
    mapping: dict[str, str] = {}
    for group_index, group in enumerate(EQUIVALENCE_GROUPS[name], start=1):
        representative = f"<{name}:{group_index}>"
        for segment in group:
            if segment in mapping:
                raise RhymeProtocolError(
                    f"Segment {segment!r} appears in multiple groups of {name}"
                )
            mapping[segment] = representative
    return mapping


def strip_annotations(token: str) -> str:
    return BRACE_MARKER_RE.sub("", ANNOTATION_RE.sub("", token)).strip()


def _is_letter_or_mark(char: str) -> bool:
    category = unicodedata.category(char)
    return category.startswith("L") or category.startswith("M")


def clean_word(token: str, *, lowercase: bool = True) -> str:
    text = unicodedata.normalize("NFD", strip_annotations(token))
    text = "".join(ch for ch in text if _is_letter_or_mark(ch))
    return text.lower() if lowercase else text


def _base_units(word: str) -> list[tuple[str, tuple[str, ...]]]:
    units: list[tuple[str, tuple[str, ...]]] = []
    for char in unicodedata.normalize("NFD", word):
        if unicodedata.combining(char):
            if not units:
                raise RhymeProtocolError("Combining mark occurs before a base letter")
            base, marks = units[-1]
            units[-1] = (base, marks + (char,))
        else:
            units.append((char, ()))
    return units


def segment_word(
    word: str,
    config: ProtocolConfig = ProtocolConfig(),
) -> tuple[Segment, ...]:
    units = _base_units(clean_word(word, lowercase=config.lowercase))
    plain = "".join(base for base, _ in units)
    result: list[Segment] = []
    i = 0
    multigraphs = tuple(sorted(config.multigraphs, key=len, reverse=True))
    while i < len(units):
        forced = next(
            (parts for prefix, parts in FORCED_SEGMENT_PREFIXES.items()
             if plain.startswith(prefix, i)),
            None,
        )
        if forced is not None:
            for part in forced:
                width = len(part)
                selected = units[i:i + width]
                text = "".join(base + "".join(marks) for base, marks in selected)
                stressed = any(COMBINING_ACUTE in marks for _, marks in selected)
                result.append(Segment(text=text, stressed=stressed))
                i += width
            continue
        match = next((m for m in multigraphs if plain.startswith(m, i)), None)
        width = len(match) if match else 1
        selected = units[i:i + width]
        text = "".join(base + "".join(marks) for base, marks in selected)
        stressed = any(COMBINING_ACUTE in marks for _, marks in selected)
        result.append(Segment(text=text, stressed=stressed))
        i += width
    return tuple(result)


def _segment_base(segment_text: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", segment_text)
        if not unicodedata.combining(ch)
    ).lower()


def is_vowel_segment(
    segment: Segment,
    config: ProtocolConfig = ProtocolConfig(),
) -> bool:
    return _segment_base(segment.text) in config.vowels


def normalize_segment(
    segment_text: str,
    config: ProtocolConfig = ProtocolConfig(),
) -> str:
    base = _segment_base(segment_text)
    return config.equivalences.get(base, base)


def _display_signature(
    segments: Sequence[Segment],
    indices: Sequence[int],
) -> str:
    pieces: list[str] = []
    for idx in indices:
        seg = segments[idx]
        base = unicodedata.normalize("NFC", seg.text.replace(COMBINING_ACUTE, ""))
        pieces.append((STRESS_MARK if seg.stressed else "") + base)
    return "".join(pieces)


def _normalized_signature(
    segments: Sequence[Segment],
    indices: Sequence[int],
    config: ProtocolConfig,
) -> str:
    parts: list[str] = []
    for idx in indices:
        seg = segments[idx]
        value = normalize_segment(seg.text, config)
        parts.append((STRESS_MARK if seg.stressed else "") + value)
    return "".join(parts)


def extract_rhyme_signature(
    token: str,
    config: ProtocolConfig = ProtocolConfig(),
) -> RhymeSignature | None:
    """Extract primary and optional bridge keys from one annotated token.

    Primary:
      from the final stressed vowel through word end; when that vowel is the
      final segment, extend exactly one corpus-defined segment left.

    Bridge:
      only for ...C V́ C words where V́ is the final vowel, exactly one final
      consonant follows it, and a consonant immediately precedes it. The bridge
      is C V́. It is used only in primary↔bridge comparison.
    """
    word = clean_word(token, lowercase=config.lowercase)
    if not word:
        return None
    segments = segment_word(word, config)
    stressed_vowels = [
        i
        for i, segment in enumerate(segments)
        if segment.stressed and is_vowel_segment(segment, config)
    ]
    if not stressed_vowels:
        if config.require_stress:
            raise RhymeProtocolError(f"No stressed vowel found in token: {token!r}")
        return None

    stressed_index = stressed_vowels[-1]
    start = stressed_index
    extended_left = False
    if stressed_index == len(segments) - 1 and stressed_index > 0:
        start = stressed_index - 1
        extended_left = True
    primary_indices = tuple(range(start, len(segments)))

    bridge_indices: tuple[int, int] | None = None
    vowel_indices = [
        i for i, segment in enumerate(segments)
        if is_vowel_segment(segment, config)
    ]
    is_final_vowel = bool(vowel_indices) and stressed_index == vowel_indices[-1]
    exactly_one_after = len(segments) - stressed_index - 1 == 1
    has_prev_consonant = (
        stressed_index > 0
        and not is_vowel_segment(segments[stressed_index - 1], config)
    )
    final_is_consonant = (
        exactly_one_after
        and not is_vowel_segment(segments[-1], config)
    )
    if is_final_vowel and exactly_one_after and has_prev_consonant and final_is_consonant:
        bridge_indices = (stressed_index - 1, stressed_index)

    return RhymeSignature(
        source_token=token,
        word=unicodedata.normalize("NFC", word),
        segments=tuple(unicodedata.normalize("NFC", s.text) for s in segments),
        stressed_index=stressed_index,
        primary_raw=_display_signature(segments, primary_indices),
        primary_key=_normalized_signature(segments, primary_indices, config),
        bridge_raw=(
            None
            if bridge_indices is None
            else _display_signature(segments, bridge_indices)
        ),
        bridge_key=(
            None
            if bridge_indices is None
            else _normalized_signature(segments, bridge_indices, config)
        ),
        extended_left=extended_left,
        equivalence_profile=config.equivalence_profile,
    )


def rhyme_key(
    token: str,
    config: ProtocolConfig = ProtocolConfig(),
) -> str | None:
    """Return the primary key only. Do not use this alone for pair decisions."""
    signature = extract_rhyme_signature(token, config)
    return None if signature is None else signature.primary_key


def compare_rhyme_signatures(
    left: RhymeSignature,
    right: RhymeSignature,
) -> RhymeMatch:
    """Compare two signatures without transitive bridge closure.

    Both signatures must have been generated under the same equivalence profile.
    Priority is FULL (primary↔primary), then BRIDGE (primary↔bridge in either
    direction). bridge↔bridge alone is deliberately excluded.
    """
    if left.equivalence_profile != right.equivalence_profile:
        raise RhymeProtocolError(
            "Cannot compare signatures generated under different profiles: "
            f"{left.equivalence_profile} vs {right.equivalence_profile}"
        )
    if left.primary_key == right.primary_key:
        return RhymeMatch(True, "FULL", left.primary_key, "primary", "primary")
    if right.bridge_key is not None and left.primary_key == right.bridge_key:
        return RhymeMatch(True, "BRIDGE", left.primary_key, "primary", "bridge")
    if left.bridge_key is not None and left.bridge_key == right.primary_key:
        return RhymeMatch(True, "BRIDGE", right.primary_key, "bridge", "primary")
    return RhymeMatch(False, None, None, None, None)


def compare_words(
    left: str,
    right: str,
    config: ProtocolConfig = ProtocolConfig(),
) -> RhymeMatch:
    left_signature = extract_rhyme_signature(left, config)
    right_signature = extract_rhyme_signature(right, config)
    if left_signature is None or right_signature is None:
        return RhymeMatch(False, None, None, None, None)
    return compare_rhyme_signatures(left_signature, right_signature)


def words_rhyme(
    left: str,
    right: str,
    config: ProtocolConfig = ProtocolConfig(),
) -> bool:
    return compare_words(left, right, config).rhymes


def iter_annotated_tokens(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        for token in line.split():
            if not BRACE_MARKER_RE.fullmatch(token):
                yield token


def audit_file(
    path: str | Path,
    config: ProtocolConfig = ProtocolConfig(),
    *,
    limit: int | None = None,
) -> dict[str, object]:
    total = extracted = bridge_eligible = 0
    missing_stress: list[str] = []
    primary_counts: dict[str, int] = {}
    bridge_counts: dict[str, int] = {}
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for token in iter_annotated_tokens(handle):
            total += 1
            try:
                signature = extract_rhyme_signature(token, config)
            except RhymeProtocolError:
                missing_stress.append(token)
                continue
            if signature is None:
                missing_stress.append(token)
                continue
            extracted += 1
            primary_counts[signature.primary_key] = (
                primary_counts.get(signature.primary_key, 0) + 1
            )
            if signature.bridge_key is not None:
                bridge_eligible += 1
                bridge_counts[signature.bridge_key] = (
                    bridge_counts.get(signature.bridge_key, 0) + 1
                )
            if limit is not None and total >= limit:
                break
    return {
        "file": str(path),
        "equivalence_profile": config.equivalence_profile,
        "equivalences": dict(config.equivalences),
        "multigraphs": list(config.multigraphs),
        "tokens": total,
        "signatures_extracted": extracted,
        "missing_stress_count": len(missing_stress),
        "missing_stress_examples": missing_stress[:20],
        "unique_primary_keys": len(primary_counts),
        "repeated_primary_keys": sum(c >= 2 for c in primary_counts.values()),
        "bridge_eligible_words": bridge_eligible,
        "unique_bridge_keys": len(bridge_counts),
    }


def _config_from_args(args: argparse.Namespace) -> ProtocolConfig:
    return ProtocolConfig.from_profile(
        args.equivalence_profile,
        require_stress=not getattr(args, "allow_missing_stress", False),
    )


def _cmd_profiles(_: argparse.Namespace) -> int:
    payload = {
        name: [list(group) for group in EQUIVALENCE_GROUPS[name]]
        for name in available_equivalence_profiles()
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_signature(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    failed = False
    for token in args.tokens:
        try:
            signature = extract_rhyme_signature(token, config)
        except RhymeProtocolError as exc:
            print(f"ERROR\t{token}\t{exc}", file=sys.stderr)
            failed = True
            continue
        print(json.dumps(asdict(signature) if signature else None, ensure_ascii=False))
    return 1 if failed else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    match = compare_words(args.left, args.right, config)
    print("RHYME" if match.rhymes else "NO_RHYME")
    print(json.dumps(asdict(match), ensure_ascii=False))
    print(
        "left="
        + json.dumps(
            asdict(extract_rhyme_signature(args.left, config)),
            ensure_ascii=False,
        )
    )
    print(
        "right="
        + json.dumps(
            asdict(extract_rhyme_signature(args.right, config)),
            ensure_ascii=False,
        )
    )
    return 0 if match.rhymes else 1


def _cmd_audit(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    print(
        json.dumps(
            audit_file(args.path, config, limit=args.limit),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--equivalence-profile",
        default=DEFAULT_EQUIVALENCE_PROFILE,
        type=normalize_profile_name,
        choices=available_equivalence_profiles(),
        help="Named correspondence condition; STRICT is the baseline.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("profiles", help="List available equivalence profiles")
    p.set_defaults(func=_cmd_profiles)

    p = sub.add_parser("signature")
    p.add_argument("tokens", nargs="+")
    p.add_argument("--allow-missing-stress", action="store_true")
    _add_profile_argument(p)
    p.set_defaults(func=_cmd_signature)

    p = sub.add_parser("compare")
    p.add_argument("left")
    p.add_argument("right")
    _add_profile_argument(p)
    p.set_defaults(func=_cmd_compare)

    p = sub.add_parser("audit")
    p.add_argument("path", type=Path)
    p.add_argument("--limit", type=int)
    p.add_argument("--allow-missing-stress", action="store_true")
    _add_profile_argument(p)
    p.set_defaults(func=_cmd_audit)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
