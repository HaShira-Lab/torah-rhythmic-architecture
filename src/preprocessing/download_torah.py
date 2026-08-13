"""Download the five Torah books from a specified Sefaria Hebrew version."""

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


API_URL = "https://www.sefaria.org/api/texts/{book}"
DEFAULT_VERSION = "Tanach_with_Ta'amei_Hamikra"
DEFAULT_BOOKS = (
    "Genesis",
    "Exodus",
    "Leviticus",
    "Numbers",
    "Deuteronomy",
)
REQUEST_TIMEOUT_SECONDS = 60


def flatten_text(node: Any) -> list[str]:
    """Return string leaves from a nested Sefaria text array in source order."""
    if isinstance(node, list):
        flattened: list[str] = []
        for item in node:
            flattened.extend(flatten_text(item))
        return flattened
    if isinstance(node, str):
        return [node]
    return []


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_filename(book: str) -> str:
    return f"{book.lower().replace(' ', '_')}_raw.txt"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def returned_version_name(data: dict[str, Any]) -> str | None:
    """Read the Hebrew version title exposed by the Sefaria response."""
    for key in ("heVersionTitle", "versionTitle"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def version_check(requested: str, returned: str | None) -> str:
    """Compare version title/slug while ignoring separators and punctuation."""
    if returned is None:
        return "not_reported"
    canonical = lambda value: re.sub(r"[^a-z0-9]+", "", value.casefold())
    return "match" if canonical(requested) == canonical(returned) else "mismatch"


def download_book(
    session: requests.Session,
    book: str,
    version_name: str,
) -> tuple[str, list[str], str, str | None]:
    url = API_URL.format(book=requests.utils.quote(book, safe=""))
    params = {
        "lang": "he",
        "vhe": version_name,
        "context": 0,
        "pad": 0,
        "commentary": 0,
    }
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict) or "he" not in data:
        raise ValueError("Missing 'he' field in Sefaria response")

    segments = flatten_text(data["he"])
    if not segments:
        raise ValueError("No Hebrew text segments found")

    # Strip only leading/trailing whitespace around each API segment. Empty
    # segments are omitted; the remaining segments are joined by one LF.
    cleaned_segments = [segment.strip() for segment in segments if segment.strip()]
    full_text = "\n".join(cleaned_segments)
    if not full_text:
        raise ValueError("Downloaded text is empty after whitespace cleanup")

    return response.url, cleaned_segments, full_text, returned_version_name(data)


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "book",
        "status",
        "file",
        "segments",
        "chars",
        "sha256",
        "requested_version",
        "returned_version",
        "version_check",
        "source_url",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Torah books from a specified Sefaria Hebrew version."
    )
    parser.add_argument(
        "--books",
        nargs="+",
        default=list(DEFAULT_BOOKS),
        help="Books to download (default: the five Torah books)",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Directory for raw text files and download metadata",
    )
    parser.add_argument(
        "--version-name",
        default=DEFAULT_VERSION,
        help=f"Sefaria Hebrew version title or slug (default: {DEFAULT_VERSION})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "script": "download_torah.py",
        "source": "Sefaria API",
        "api_endpoint": API_URL,
        "requested_version": args.version_name,
        "started_utc": utc_now(),
        "outdir": str(outdir),
        "books_requested": args.books,
        "results": [],
    }
    summary_rows: list[dict[str, Any]] = []
    ok_count = 0

    print("=== DOWNLOAD TORAH ===")
    print(f"OUTDIR : {outdir}")
    print(f"VERSION: {args.version_name}")
    print(f"BOOKS  : {', '.join(args.books)}\n")

    with requests.Session() as session:
        session.headers.update({"User-Agent": "Torah-Rhythmic-Architecture/1.0"})

        for book in args.books:
            print(f"[DOWNLOAD] {book}")
            try:
                source_url, segments, full_text, returned_version = download_book(
                    session, book, args.version_name
                )
                check = version_check(args.version_name, returned_version)
                filename = safe_filename(book)
                (outdir / filename).write_text(full_text, encoding="utf-8")
                digest = sha256_text(full_text)

                row = {
                    "book": book,
                    "status": "ok",
                    "file": filename,
                    "segments": len(segments),
                    "chars": len(full_text),
                    "sha256": digest,
                    "requested_version": args.version_name,
                    "returned_version": returned_version or "",
                    "version_check": check,
                    "source_url": source_url,
                    "error": "",
                }
                ok_count += 1
                print(f"  OK   file={filename}")
                print(f"  segs={len(segments)}  chars={len(full_text)}")
                print(f"  sha256={digest}")
                print(f"  returned_version={returned_version or 'not reported'}")
                print(f"  version_check={check}")
            except (requests.RequestException, ValueError, json.JSONDecodeError) as error:
                row = {
                    "book": book,
                    "status": "error",
                    "file": "",
                    "segments": "",
                    "chars": "",
                    "sha256": "",
                    "requested_version": args.version_name,
                    "returned_version": "",
                    "version_check": "failed",
                    "source_url": "",
                    "error": f"{type(error).__name__}: {error}",
                }
                print(f"  ERROR: {row['error']}")

            summary_rows.append(row)
            manifest["results"].append(row)
            print()

    manifest["finished_utc"] = utc_now()
    manifest["ok_count"] = ok_count
    manifest["error_count"] = len(args.books) - ok_count

    summary_csv = outdir / "download_summary.csv"
    manifest_json = outdir / "download_manifest.json"
    write_summary_csv(summary_csv, summary_rows)
    manifest_json.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== DONE ===")
    print(f"OK      : {ok_count}/{len(args.books)}")
    print(f"CSV     : {summary_csv}")
    print(f"MANIFEST: {manifest_json}")
    return 0 if ok_count == len(args.books) else 1


if __name__ == "__main__":
    sys.exit(main())
