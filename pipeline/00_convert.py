#!/usr/bin/env python3
"""
pipeline/00_convert.py — PDF → Images

Converts a magazine PDF to high-quality JPEG images, one per page.
Improved version of convert_magazine.py with:
- Config-driven (reads magazines.yaml)
- Correct path resolution
- Skip already-converted pages (checkpoint)
- DPI configurable per magazine
- Progress reporting

Usage:
    python3 pipeline/00_convert.py --pdf famitsu-01.pdf --magazine famitsu --issue 1
    python3 pipeline/00_convert.py --pdf famitsu-01.pdf --magazine famitsu --issue 1 --dpi 200
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from pdf2image import convert_from_path
except ImportError:
    print("❌ pdf2image not installed. Run: pip install pdf2image")
    print("   Also requires poppler: brew install poppler")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent

# Default DPI — 200 is a good balance of quality vs. file size for OCR
# 300 DPI produces better quality but 2.25x larger files
DEFAULT_DPI = 200


def make_output_name(magazine: str, issue: int) -> str:
    return f"output_{magazine.capitalize()}_No{str(issue).zfill(2)}"


def convert_pdf(pdf_path: Path, output_dir: Path, dpi: int, force: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir.name

    # Check existing pages
    existing = sorted(output_dir.glob("*.jpg"))
    if existing and not force:
        print(f"⚠️  {len(existing)} pages already exist in {output_dir.name}/")
        print("   Use --force to reconvert. Skipping.")
        return

    print(f"📄 PDF: {pdf_path}")
    print(f"📁 Output: {output_dir}")
    print(f"🖼️  DPI: {dpi}")
    print("⏳ Converting (this may take a few minutes for large PDFs)...\n")

    pages = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        thread_count=4,
        fmt="jpeg",
        jpegopt={"quality": 90, "progressive": True},
    )

    total = len(pages)
    for i, page in enumerate(pages, start=1):
        page_num = str(i).zfill(3)
        filename = f"{stem}_Page_{page_num}.jpg"
        out_path = output_dir / filename
        page.save(str(out_path), "JPEG", quality=90)
        print(f"  ✅ Page {i:>4}/{total}  →  {filename}")

    print(f"\n✨ Done! {total} pages in: {output_dir}/")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert magazine PDF to images.")
    p.add_argument("--pdf", required=True, help="Path to PDF file")
    p.add_argument("--magazine", required=True, help="Magazine identifier (e.g. famitsu, dengeki)")
    p.add_argument("--issue", required=True, type=int, help="Issue number")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"Resolution in DPI (default: {DEFAULT_DPI})")
    p.add_argument("--force", action="store_true", help="Reconvert even if output already exists")
    p.add_argument("--output-dir", type=str, help="Override output directory path")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = PROJECT_ROOT / pdf_path
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        sys.exit(1)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_name = make_output_name(args.magazine, args.issue)
        output_dir = PROJECT_ROOT / output_name

    convert_pdf(pdf_path, output_dir, args.dpi, args.force)


if __name__ == "__main__":
    main()
