#!/usr/bin/env python3
"""Build verified canonical chapter/verse maps for processed Torah files.

The existing processed text deliberately preserves the performance boundary
marker ``{sof_pasuq}``, but it does not preserve the Sefaria API's nested
chapter/verse segmentation.  This utility reconstructs that segmentation from
frozen Sefaria JSON responses, processes every canonical verse with the same
preprocessor used for the corpus, and refuses to write a map unless the
reconstructed token stream is byte-for-token identical to the frozen file.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


BOOKS = ("genesis", "exodus", "leviticus", "numbers", "deuteronomy")
SCHEMA_VERSION = "1.0"
API_URL = "https://www.sefaria.org/api/texts/{book}"
DEFAULT_VERSION = "Tanach_with_Ta'amei_Hamikra"
REQUEST_TIMEOUT_SECONDS = 60


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_preprocessor(path: Path):
    spec = importlib.util.spec_from_file_location("canonical_map_preprocessor", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import preprocessor: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "build_torah"):
        raise RuntimeError(f"Preprocessor has no build_torah(): {path}")
    return module


def is_structural_marker(token: str) -> bool:
    return token.startswith("{") and token.endswith("}")


def canonical_json_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fetch_response(book: str, version_name: str) -> tuple[dict, str]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "Live Sefaria retrieval requires the repository dependency 'requests'. "
            "Install requirements.txt or use --api-dir with frozen responses."
        ) from exc
    url = API_URL.format(book=requests.utils.quote(book.title(), safe=""))
    params = {
        "lang": "he",
        "vhe": version_name,
        "context": 0,
        "pad": 0,
        "commentary": 0,
    }
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Sefaria returned a non-object response for {book}")
    return payload, response.url


def build_map(
    book: str,
    response: dict,
    response_source: str,
    processed_path: Path,
    preprocessor,
    requested_version: str,
) -> dict:
    nested = response.get("he")
    if not isinstance(nested, list) or not all(isinstance(chapter, list) for chapter in nested):
        raise ValueError(f"{response_source}: 'he' is not a chapter/verse array")

    reconstructed: list[str] = []
    spans: list[dict[str, int]] = []
    source_word_index = 0
    canonical_ordinal = 0
    for chapter_number, chapter in enumerate(nested, 1):
        for verse_number, verse in enumerate(chapter, 1):
            if not isinstance(verse, str):
                raise ValueError(
                    f"{response_source}: non-string verse at "
                    f"{chapter_number}:{verse_number}"
                )
            canonical_ordinal += 1
            processed_tokens = preprocessor.build_torah(verse).split()
            reconstructed.extend(processed_tokens)
            word_count = sum(not is_structural_marker(token) for token in processed_tokens)
            first = source_word_index
            source_word_index += word_count
            spans.append({
                "canonical_verse_ordinal": canonical_ordinal,
                "chapter": chapter_number,
                "verse": verse_number,
                "first_source_word_index": first,
                "last_source_word_index_exclusive": source_word_index,
                "source_word_count": word_count,
            })

    frozen = processed_path.read_text(encoding="utf-8-sig").split()
    if reconstructed != frozen:
        mismatch = next(
            (
                index
                for index, (left, right) in enumerate(zip(reconstructed, frozen))
                if left != right
            ),
            min(len(reconstructed), len(frozen)),
        )
        raise RuntimeError(
            f"{book}: reconstructed API stream differs from frozen processed text "
            f"at token {mismatch}; reconstructed={len(reconstructed)}, frozen={len(frozen)}"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "book": book,
        "canonical_reference_system": "Sefaria chapter/verse array indices",
        "hebrew_version_title": response.get("heVersionTitle"),
        "hebrew_version_source": response.get("heVersionSource"),
        "requested_version": requested_version,
        "api_reference": response.get("ref"),
        "api_response_source": response_source,
        "api_payload_canonical_json_sha256": canonical_json_sha256(response),
        "processed_file": processed_path.name,
        "processed_file_sha256": sha256_file(processed_path),
        "reconstruction_verified_token_for_token": True,
        "canonical_verse_count": len(spans),
        "source_word_count": source_word_index,
        "spans": spans,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-dir",
        type=Path,
        help=(
            "Optional directory containing frozen sefaria_{book}.json responses. "
            "If omitted, the same nested responses are downloaded from Sefaria."
        ),
    )
    parser.add_argument("--processed-dir", type=Path, required=True)
    parser.add_argument("--preprocessor", type=Path, required=True)
    parser.add_argument("--version-name", default=DEFAULT_VERSION)
    parser.add_argument("--books", nargs="+", choices=BOOKS, default=list(BOOKS))
    args = parser.parse_args()

    preprocessor = load_preprocessor(args.preprocessor)
    for book in args.books:
        processed_path = args.processed_dir / f"{book}_taamim_annotated.txt"
        if not processed_path.is_file():
            raise FileNotFoundError(processed_path)
        if args.api_dir is not None:
            api_path = args.api_dir / f"sefaria_{book}.json"
            if not api_path.is_file():
                raise FileNotFoundError(api_path)
            response = json.loads(api_path.read_text(encoding="utf-8"))
            if not isinstance(response, dict):
                raise ValueError(f"Frozen response is not an object: {api_path}")
            response_source = str(api_path)
        else:
            response, response_source = fetch_response(book, args.version_name)
        payload = build_map(
            book,
            response,
            response_source,
            processed_path,
            preprocessor,
            args.version_name,
        )
        output_path = processed_path.with_name(processed_path.name + ".verse_map.json")
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"{book}: canonical_verses={payload['canonical_verse_count']} "
            f"source_words={payload['source_word_count']} WROTE: {output_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
