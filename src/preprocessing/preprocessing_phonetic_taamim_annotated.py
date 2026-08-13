import argparse
import re
import hashlib
import os
import json
import datetime
import unicodedata

# =========================
# CONSTANTS
# =========================

HEBREW_LETTERS = set("אבגדהוזחטיכלמנסעפצקרשתךםןףץ")
FINAL_TO_BASE = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}

DAGESH = "\u05BC"
SHEVA = "\u05B0"
SHIN_DOT = "\u05C1"
SIN_DOT = "\u05C2"
RAFE = "\u05BF"
UPPER_DOT = "\u05C4"

# Cantillation / prosodic marks
SOF_PASUQ = "\u05C3"
PASEQ = "\u05C0"
MAQAF = "\u05BE"
METEG = "\u05BD"
QAMATS_QATAN = "\u05C7"
MASORA_CIRCLE = "\u05AF"

TAAM_NAMES = {
    "\u0591": "atnah",
    "\u0592": "segol",
    "\u0593": "shalshelet",
    "\u0594": "zaqef_qatan",
    "\u0595": "zaqef_gadol",
    "\u0596": "tipeha",
    "\u0597": "revia",
    "\u0598": "zarqa",
    "\u0599": "pashta",
    "\u059A": "yetiv",
    "\u059B": "tevir",
    "\u059C": "geresh",
    "\u059D": "geresh_muqdam",
    "\u059E": "gershayim",
    "\u059F": "qarney_para",
    "\u05A0": "telisha_gedola",
    "\u05A1": "pazer",
    "\u05A2": "atnah_hafukh",
    "\u05A3": "munah",
    "\u05A4": "mahapakh",
    "\u05A5": "merkha",
    "\u05A6": "merkha_kefula",
    "\u05A7": "darga",
    "\u05A8": "qadma",
    "\u05A9": "telisha_qetana",
    "\u05AA": "yerah_ben_yomo",
    "\u05AB": "ole",
    "\u05AC": "iluy",
    "\u05AD": "dehi",
    "\u05AE": "zinor",
    "\u05BD": "meteg",
    "\u05C0": "paseq",
    "\u05C3": "sof_pasuq",
}

COMBINING_ACUTE = "\u0301"

# All named in-word taamim are accent-events. U+05AF MASORA CIRCLE is a
# masoretic annotation, not a taam, and is deliberately ignored.
HEBREW_ACCENTS = {
    mark for mark in TAAM_NAMES
    if mark not in {PASEQ, SOF_PASUQ, METEG}
}
# METEG (U+05BD) is included because in the input it often marks the visible
# accent/secondary stress position (e.g. וַֽיְהִי, אֽוֹר).
ACCENT_MARKS = (HEBREW_ACCENTS | {METEG}) - {PASEQ, SOF_PASUQ}
# Marks that are better represented as standalone post-/inter-word events.
# They do not belong inside word[...] because they behave as boundary separators.
EXTERNAL_TAAM_MARKS = {SOF_PASUQ, PASEQ}

GUTTURALS = {"א", "ה", "ח", "ע"}
VOCALIC_FALLBACK_LETTERS = {"ו", "י", "א", "ע"}

# =========================
# VOWELS
# =========================

VOWELS = {
        "\u05B1": "e",
        "\u05B2": "a",
        "\u05B3": "a",
        "\u05B4": "i",
        "\u05B5": "e",
        "\u05B6": "e",
        "\u05B7": "a",
        "\u05B8": "a",
        "\u05B9": "o",
        "\u05BA": "o",
        "\u05BB": "u",
        QAMATS_QATAN: "o",
}

KEEP_MARKS = set(VOWELS) | {
    DAGESH, SHEVA, SHIN_DOT, SIN_DOT,
} | ACCENT_MARKS | {PASEQ, SOF_PASUQ}
VOCALIZATION_MARKS = set(VOWELS) | {DAGESH, SHEVA, SHIN_DOT, SIN_DOT}

# =========================
# UTIL
# =========================

def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def letters_only(s: str) -> str:
    return "".join(FINAL_TO_BASE.get(ch, ch) for ch in s if ch in HEBREW_LETTERS)

def add_acute_to_first_vowel(seg: str) -> str:
    if COMBINING_ACUTE in seg:
        return seg
    for i, ch in enumerate(seg):
        if ch in "aeiou":
            return seg[:i + 1] + COMBINING_ACUTE + seg[i + 1:]
    return seg

def add_acute_to_last_vowel(seg: str) -> str:
    if COMBINING_ACUTE in seg:
        return seg
    for i in range(len(seg) - 1, -1, -1):
        if seg[i] in "aeiou":
            return seg[:i + 1] + COMBINING_ACUTE + seg[i + 1:]
    return seg

# =========================
# PARSING
# =========================

def parse_units(token: str):
    units = []
    i = 0
    while i < len(token):
        ch = token[i]
        if ch in HEBREW_LETTERS:
            base = FINAL_TO_BASE.get(ch, ch)
            marks = []
            j = i + 1
            while j < len(token) and token[j] not in HEBREW_LETTERS and token[j] != MAQAF:
                if token[j] in KEEP_MARKS:
                    marks.append(token[j])
                j += 1
            units.append((base, marks))
            i = j
        else:
            i += 1
    return units

def token_has_vocalization(token: str) -> bool:
    return any(ch in VOCALIZATION_MARKS for ch in token)

def unit_info(unit):
    letter, marks = unit
    return {
        "letter": letter,
        "marks": marks,
        "dagesh": DAGESH in marks,
        "sheva": SHEVA in marks,
        "shin_dot": SHIN_DOT in marks,
        "sin_dot": SIN_DOT in marks,
        "vowel_marks": [m for m in marks if m in VOWELS],
        "accent_marks": [m for m in marks if m in ACCENT_MARKS],
    }

def own_vowel(letter: str, info: dict) -> str:
    if letter == "ו" and info["dagesh"] and not info["vowel_marks"]:
        return "u"
    for m in info["marks"]:
        if m in VOWELS:
            return VOWELS[m]
    return ""

def has_own_vowel(letter: str, info: dict) -> bool:
    return bool(own_vowel(letter, info))

# =========================
# PROSODIC / ACCENT LOGIC v1
# =========================

def target_unit_for_accent(units, infos, accent_unit_idx: int, accent_pos: int) -> int:
    letter, marks = units[accent_unit_idx]
    relevant_marks = marks[:accent_pos]

    # 1) If the taam follows a vowel on the same Hebrew letter, stress that vowel.
    #    Example: הַחֹֽשֶך -> hahóshekh.
    if any(m in VOWELS for m in relevant_marks):
        return accent_unit_idx
    if letter == "ו" and DAGESH in relevant_marks and not any(m in VOWELS for m in marks):
        return accent_unit_idx

    # 2) If there is NO vowel before the taam on this letter, and the next
    #    vocalic carrier is א/ע/י/ו with its own vowel, stress that next nucleus
    #    before falling back to a previous vowel.
    #    Examples: מָק֣וֹם -> maqóm; הָא֖וֹר -> haór.
    for j in range(accent_unit_idx + 1, len(units)):
        next_letter = infos[j]["letter"]
        if next_letter in VOCALIC_FALLBACK_LETTERS and has_own_vowel(next_letter, infos[j]):
            return j
        # Stop once a normal consonant with its own vowel is found; this prevents
        # long-distance jumps over an ordinary syllable.
        if has_own_vowel(next_letter, infos[j]):
            break

    # 3) If the taam/meteg sits on a silent vocalic carrier, map forward to the
    #    next available vocalic unit.
    if letter in VOCALIC_FALLBACK_LETTERS and not has_own_vowel(letter, infos[accent_unit_idx]):
        for j in range(accent_unit_idx + 1, len(units)):
            if has_own_vowel(infos[j]["letter"], infos[j]) or infos[j]["letter"] in VOCALIC_FALLBACK_LETTERS:
                return j

    # 4) Previous niqqud-vowel in the word.
    for j in range(accent_unit_idx - 1, -1, -1):
        if has_own_vowel(infos[j]["letter"], infos[j]):
            return j

    # 5) If none exists, use the next vocalic unit: ו י א ע.
    for j in range(accent_unit_idx + 1, len(units)):
        if has_own_vowel(infos[j]["letter"], infos[j]) or infos[j]["letter"] in VOCALIC_FALLBACK_LETTERS:
            return j

    return accent_unit_idx

def accent_events(units, infos):
    events = []
    for i, (_letter, marks) in enumerate(units):
        for pos, mark in enumerate(marks):
            if mark in ACCENT_MARKS:
                events.append({
                    "mark": mark,
                    "source_unit": i,
                    "target_unit": target_unit_for_accent(units, infos, i, pos),
                })
    return events

def taam_name_events(units):
    """
    Return in-word taam/prosodic names in exact internal order.
    External/boundary marks such as sof_pasuq and paseq are emitted separately
    as {sof_pasuq}/{paseq}, not inside word[...].
    """
    names = []
    for _letter, marks in units:
        for mark in marks:
            if mark in EXTERNAL_TAAM_MARKS:
                continue
            name = TAAM_NAMES.get(mark)
            if name:
                names.append(name)
    return names

def external_taam_events_from_token(token: str):
    """Standalone boundary/separator events attached to or between words."""
    return [TAAM_NAMES[ch] for ch in token if ch in EXTERNAL_TAAM_MARKS and ch in TAAM_NAMES]

def external_taam_token(token: str) -> str:
    names = external_taam_events_from_token(token)
    return "{" + ",".join(names) + "}" if names else ""

# =========================
# CONSONANTS
# =========================

def map_consonant(letter: str, info: dict, idx: int, n: int, ownv: str) -> str:
    if letter in ("א", "ע"):
        return ""

    if letter == "ה":
        if idx == n - 1:
            return ""
        return "h"

    if letter == "ב":
        return "b" if info["dagesh"] else "v"
    if letter == "כ":
        return "k" if info["dagesh"] else "kh"
    if letter == "פ":
        return "p" if info["dagesh"] else "f"
    if letter == "ש":
        return "s" if info["sin_dot"] else "sh"
    if letter == "צ":
        return "ts"
    if letter == "ק":
        return "q"
    if letter == "ח":
        return "h"
    if letter == "ט":
        return "t"
    if letter == "ת":
        return "t"

    if letter == "ו":
        # וֹ / וּ can be mater-vowel (no consonantal v), but וָ etc.
        # is consonantal v + vowel. This fixes וָבֹהוּ -> vovóhu,
        # while preserving אוֹר -> ór and וּ... -> u...
        if ownv == "o" and "\u05B9" in info["marks"]:
            return ""
        if ownv == "u" and (DAGESH in info["marks"] or "\u05BB" in info["marks"]):
            return ""
        return "v"

    if letter == "י":
        return "y"

    table = {
        "ג": "g", "ד": "d", "ז": "z", "ל": "l",
        "מ": "m", "נ": "n", "ס": "s", "ר": "r",
    }
    return table.get(letter, letter)

# =========================
# MAIN TRANSLITERATION
# =========================

def _accent_special_name(word: str) -> str:
    return add_acute_to_last_vowel(word)

def transliterate_word_plain(token: str) -> str:
    base_letters = letters_only(token)
    has_accent = any(ch in ACCENT_MARKS for ch in token)

    if base_letters == "יהוה":
        return _accent_special_name("adonai") if has_accent else "adonai"
    if base_letters in {"אלהים", "אלוהים"}:
        return _accent_special_name("elohim") if has_accent else "elohim"

    if base_letters and not token_has_vocalization(token):
        return ""

    units = parse_units(token)
    if not units:
        return ""

    infos = [unit_info(u) for u in units]

    out = []
    unit_to_seg = [None] * len(units)
    prev_vowel = None
    n = len(units)

    def append_seg(unit_idx: int, seg: str):
        if seg:
            unit_to_seg[unit_idx] = len(out)
            out.append(seg)

    for idx, (letter, marks) in enumerate(units):
        info = infos[idx]
        ownv = own_vowel(letter, info)

        next_has_sheva = idx + 1 < n and infos[idx + 1]["sheva"]
        next_letter = infos[idx + 1]["letter"] if idx + 1 < n else None
        next_ownv = own_vowel(next_letter, infos[idx + 1]) if idx + 1 < n else ""

        if letter == "י" and not ownv and not info["sheva"]:
            if idx == 0 or prev_vowel != "i":
                append_seg(idx, "y")
            continue

        if letter == "י" and ownv:
            seg = "i" if (ownv == "i" and prev_vowel == "i") else "y" + ownv
            append_seg(idx, seg)
            prev_vowel = ownv
            continue

        vowel = ""
        if ownv:
            vowel = ownv
        elif info["sheva"]:
            if idx == n - 1:
                vowel = ""
            elif idx == 0:
                vowel = "e"
            elif infos[idx - 1]["sheva"]:
                vowel = "e"
            elif next_letter in GUTTURALS and next_ownv:
                vowel = "e"
            elif next_has_sheva:
                vowel = ""
            elif prev_vowel in ("o", "u"):
                vowel = "e"

        if letter == "ח" and idx == n - 1 and ownv == "a":
            append_seg(idx, "ah")
            prev_vowel = "a"
            continue

        cons = map_consonant(letter, info, idx, n, ownv)
        seg = ownv if (letter == "ו" and ownv in ("o", "u") and cons == "") else cons + vowel

        if seg:
            append_seg(idx, seg)
            prev_vowel = ownv or vowel

    if not out:
        return ""

    accented_segments = set()
    for ev in accent_events(units, infos):
        target_unit = ev["target_unit"]
        seg_idx = unit_to_seg[target_unit]

        # If the target unit produced no Latin vowel/consonant segment, fall back
        # to the nearest transliterated segment with a vowel.
        if seg_idx is None or not any(ch in "aeiou" for ch in out[seg_idx]):
            candidates = []
            for j, sidx in enumerate(unit_to_seg):
                if sidx is not None and any(ch in "aeiou" for ch in out[sidx]):
                    candidates.append((abs(j - target_unit), j, sidx))
            if not candidates:
                continue
            seg_idx = sorted(candidates)[0][2]

        if seg_idx not in accented_segments:
            out[seg_idx] = add_acute_to_first_vowel(out[seg_idx])
            accented_segments.add(seg_idx)

    return "".join(out)

def transliterate_word(token: str, annotate_taamim: bool = False) -> str:
    phon = transliterate_word_plain(token)
    if not phon or not annotate_taamim:
        return phon
    units = parse_units(token)
    names = taam_name_events(units)
    if names:
        phon += "[" + ",".join(names) + "]"
    return phon

# =========================
# BUILDERS
# =========================

def normalize_torah_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lstrip("\ufeff"))
    text = text.replace(MAQAF, " ")
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\d+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def build_torah(text: str) -> str:
    """
    Torah builder for taam-annotated transliteration.

    In-word marks:    word[taam1,taam2]
    External marks:   {sof_pasuq} {paseq}

    No visible punctuation . or , is emitted.
    """
    text = normalize_torah_text(text)
    raw_tokens = re.split(r"\s+", text.strip())
    out = []

    for raw in raw_tokens:
        phon = transliterate_word(raw, annotate_taamim=True)
        ext = external_taam_token(raw)

        if phon:
            out.append(phon)
            if ext:
                out.append(ext)
        elif ext:
            # A standalone sign between words, e.g. paseq.
            out.append(ext)

    phon = " ".join(out)
    phon = re.sub(r"\s+", " ", phon)
    return phon.strip()

# =========================
# MAIN
# =========================

def parse_cli():
    parser = argparse.ArgumentParser(
        description="Create canonical taam-annotated Torah transliteration."
    )
    parser.add_argument("input", help="UTF-8 pointed Hebrew Torah text")
    parser.add_argument("output", help="output annotated transliteration file")
    return parser.parse_args()


def validate_source(text: str):
    unknown = {}
    masora_count = text.count(MASORA_CIRCLE)
    rafe_count = text.count(RAFE)
    upper_dot_count = text.count(UPPER_DOT)
    known = KEEP_MARKS | {MAQAF, MASORA_CIRCLE, RAFE, UPPER_DOT}
    for ch in text:
        cp = ord(ch)
        if (0x0591 <= cp <= 0x05C7) and unicodedata.category(ch).startswith("M") and ch not in known:
            unknown[ch] = unknown.get(ch, 0) + 1
    if unknown:
        details = ", ".join(
            f"U+{ord(ch):04X} {unicodedata.name(ch, 'UNKNOWN')} ({count})"
            for ch, count in sorted(unknown.items(), key=lambda item: ord(item[0]))
        )
        raise ValueError(f"Unsupported Hebrew combining mark(s): {details}")
    return {
        "masora_circle_ignored": masora_count,
        "rafe_ignored": rafe_count,
        "upper_dot_ignored": upper_dot_count,
        "unknown_marks": 0,
    }


def main():
    args = parse_cli()
    inp = os.path.abspath(args.input)
    outp = os.path.abspath(args.output)
    if not os.path.isfile(inp):
        raise SystemExit(f"ERROR: input file not found: {inp}")

    with open(inp, encoding="utf8") as f:
        raw = f.read()

    validation = validate_source(unicodedata.normalize("NFC", raw))
    phon = build_torah(raw)

    out_dir = os.path.dirname(os.path.abspath(outp))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(outp, "w", encoding="utf-8-sig") as f:
        f.write(phon)

    meta = {
        "schema_version": "1.0",
        "source_type": "torah_pointed_hebrew",
        "qamats_u05b8": "a",
        "qamats_qatan_u05c7": "o",
        "accent_encoding": "combining_acute_u0301",
        "external_taam_annotation": "{paseq} and {sof_pasuq}",
        "sof_pasuq_accent": "no; preserved as {sof_pasuq}",
        "visible_punctuation": "none",
        "taam_annotation": "word[taam1,taam2,...]",
        "input_sha256": sha256(inp),
        "output_sha256": sha256(outp),
        "validation": validation,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    with open(outp + ".meta.json", "w", encoding="utf8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    words = [w for w in phon.split() if not (w.startswith("{") and w.endswith("}"))]

    print("OUTPUT:", outp)
    print("WORDS:", len(words))
    print("UNIQUE_WORDS:", len(set(words)))
    print("QAMATS:", "U+05B8=a; U+05C7=o")
    print("TAAM_ANNOTATION:", "word[taam1,taam2,...]")
    print("SHA256:", meta["output_sha256"])


if __name__ == "__main__":
    main()
