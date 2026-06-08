#!/usr/bin/env python3
"""
pipeline/04_ingest.py — OCR JSON → SQLite

Reads Phase 0 OCR output and inserts page records into the database.
Also creates the magazine and issue records if they don't exist.

Usage:
    python3 pipeline/04_ingest.py --issue output_Famitsu_1986_No01 --magazine famitsu --issue-number 1
    python3 pipeline/04_ingest.py --all --pattern "output_Famitsu_*" --magazine famitsu
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "archive.db"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"
CONFIG_PATH = PROJECT_ROOT / "config" / "magazines.yaml"


# ── Database setup ─────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # Apply schema (idempotent — CREATE IF NOT EXISTS)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


# ── Magazine config ────────────────────────────────────────────────────────────

def load_magazine_config(magazine_id: str) -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    magazines = config.get("magazines", {})
    if magazine_id not in magazines:
        print(f"❌ Magazine '{magazine_id}' not found in config/magazines.yaml")
        print(f"   Available: {', '.join(magazines.keys())}")
        sys.exit(1)
    return magazines[magazine_id]


# ── Upsert helpers ─────────────────────────────────────────────────────────────

def ensure_magazine(conn: sqlite3.Connection, magazine_id: str, cfg: dict) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO magazines
            (id, name_original, name_en, country, language, publisher, started, ended,
             review_format, score_max, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        magazine_id,
        cfg.get("name_ja") or cfg.get("name_fr") or cfg.get("name_en", magazine_id),
        cfg.get("name_en"),
        cfg.get("country"),
        cfg.get("language", "ja"),
        cfg.get("publisher"),
        cfg.get("started"),
        cfg.get("ended"),
        cfg.get("review_format"),
        cfg.get("score_max"),
        cfg.get("notes"),
    ))


def ensure_issue(conn: sqlite3.Connection, magazine_id: str, issue_number: int,
                 release_date: str | None, images_dir: str, ocr_dir: str) -> str:
    issue_id = f"{magazine_id}-{str(issue_number).zfill(4)}"
    conn.execute("""
        INSERT OR IGNORE INTO issues
            (id, magazine_id, issue_number, release_date, images_dir, ocr_dir)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (issue_id, magazine_id, issue_number, release_date, images_dir, ocr_dir))

    # Update paths if they changed
    conn.execute("""
        UPDATE issues SET images_dir=?, ocr_dir=? WHERE id=?
    """, (images_dir, ocr_dir, issue_id))
    return issue_id


# ── Page ingestion ─────────────────────────────────────────────────────────────

def ingest_page(conn: sqlite3.Connection, issue_id: str, ocr_json_path: Path,
                image_path: Path | None) -> dict:
    with open(ocr_json_path, "r", encoding="utf-8") as f:
        ocr_data = json.load(f)

    # Parse page number from filename: Famitsu_1986_No01_Page_017.json → 17
    stem = ocr_json_path.stem
    page_number = 0
    for part in stem.split("_"):
        if part.isdigit():
            page_number = int(part)

    full_text = ocr_data.get("full_text", "")
    block_count = ocr_data.get("block_count", 0)
    confidence = ocr_data.get("average_confidence", 0.0)
    error = ocr_data.get("error")

    img_str = str(image_path) if image_path and image_path.exists() else None

    conn.execute("""
        INSERT OR REPLACE INTO pages
            (issue_id, page_number, image_path, ocr_json_path, ocr_full_text,
             ocr_block_count, ocr_confidence, ocr_done)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        issue_id,
        page_number,
        img_str,
        str(ocr_json_path),
        full_text,
        block_count,
        confidence,
        0 if error else 1,
    ))

    return {
        "page": page_number,
        "blocks": block_count,
        "confidence": round(confidence, 3),
        "error": error,
    }


def ingest_issue(magazine_id: str, issue_number: int, issue_dir: Path,
                 release_date: str | None = None) -> None:
    cfg = load_magazine_config(magazine_id)
    conn = get_db()

    ocr_dir = issue_dir / "ocr"
    if not ocr_dir.exists():
        print(f"❌ OCR directory not found: {ocr_dir}")
        print("   Run pipeline/01_ocr.py first.")
        sys.exit(1)

    ocr_files = sorted(ocr_dir.glob("*.json"))
    # Skip the _manifest.json
    ocr_files = [f for f in ocr_files if not f.name.startswith("_")]

    if not ocr_files:
        print(f"⚠️  No OCR JSON files found in {ocr_dir}")
        return

    print(f"\n📥 Ingesting: {issue_dir.name}")
    print(f"   Magazine:   {magazine_id}")
    print(f"   Issue:      #{issue_number}")
    print(f"   OCR pages:  {len(ocr_files)}")
    print(f"   Database:   {DB_PATH}\n")

    with conn:
        ensure_magazine(conn, magazine_id, cfg)
        issue_id = ensure_issue(
            conn, magazine_id, issue_number,
            release_date,
            str(issue_dir),
            str(ocr_dir)
        )

        ok_count = 0
        error_count = 0

        for ocr_file in ocr_files:
            # Find corresponding image
            img_stem = ocr_file.stem  # e.g. Famitsu_1986_No01_Page_017
            image_path = None
            for ext in [".jpg", ".jpeg", ".png"]:
                candidate = issue_dir / (img_stem + ext)
                if candidate.exists():
                    image_path = candidate
                    break

            result = ingest_page(conn, issue_id, ocr_file, image_path)

            if result["error"]:
                error_count += 1
                print(f"  ⚠️  Page {result['page']:>4}: {result['error']}")
            else:
                ok_count += 1
                conf_pct = int(result["confidence"] * 100)
                print(f"  ✅ Page {result['page']:>4}  {result['blocks']:>4} blocks  {conf_pct}% confidence")

        # Mark phase0 done
        conn.execute("UPDATE issues SET phase0_done=1 WHERE id=?", (issue_id,))

        # Rebuild full-text search index
        conn.execute("INSERT INTO fts_pages(fts_pages) VALUES('rebuild')")

    print(f"\n{'─'*50}")
    print(f"  ✅ Ingested: {ok_count} pages")
    if error_count:
        print(f"  ⚠️  Errors:   {error_count} pages")
    print(f"  💾 Database: {DB_PATH}\n")
    conn.close()


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest OCR output into the archive database.")
    p.add_argument("--issue", type=str, help="Path to issue folder")
    p.add_argument("--magazine", required=True, help="Magazine ID (e.g. famitsu)")
    p.add_argument("--issue-number", type=int, required=True, help="Issue number")
    p.add_argument("--release-date", type=str, help="Release date (YYYY-MM-DD)")
    p.add_argument("--all", action="store_true", help="Process all matching folders")
    p.add_argument("--pattern", type=str, default="output_*")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.all:
        folders = sorted(PROJECT_ROOT.glob(args.pattern))
        issue_dirs = [f for f in folders if f.is_dir() and not f.name.startswith(".")]
        for i, d in enumerate(issue_dirs, start=1):
            ingest_issue(args.magazine, i, d, args.release_date)
    elif args.issue:
        issue_path = Path(args.issue)
        if not issue_path.is_absolute():
            issue_path = PROJECT_ROOT / issue_path
        ingest_issue(args.magazine, args.issue_number, issue_path, args.release_date)
    else:
        print("❌ Specify --issue <folder> or --all")
        sys.exit(1)


if __name__ == "__main__":
    main()
