#!/usr/bin/env python3
"""
pipeline/inspect_ocr.py — Visualize OCR output for a single page

Shows the extracted text blocks in a readable format so you can
verify quality before processing an entire issue.

Usage:
    python3 pipeline/inspect_ocr.py output_Famitsu_1986_No01/ocr/Famitsu_1986_No01_Page_001.json
    python3 pipeline/inspect_ocr.py output_Famitsu_1986_No01/ocr/Famitsu_1986_No01_Page_001.json --full
"""

import argparse
import json
import sys
from pathlib import Path


def format_confidence(conf: float) -> str:
    pct = int(conf * 100)
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    color = "\033[92m" if pct >= 80 else "\033[93m" if pct >= 60 else "\033[91m"
    reset = "\033[0m"
    return f"{color}[{bar}]{reset} {pct}%"


def inspect(json_path: Path, show_full: bool) -> None:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{'═'*65}")
    print(f"  📄 File:       {data.get('source', json_path.name)}")
    print(f"  📐 Dimensions: {data.get('image_width', '?')} × {data.get('image_height', '?')} px")
    print(f"  🔤 Blocks:     {data.get('block_count', 0)}")
    avg_conf = data.get('average_confidence', 0)
    print(f"  📊 Confidence: {format_confidence(avg_conf)}")
    if data.get('error'):
        print(f"  ❌ Error: {data['error']}")
    print(f"{'═'*65}\n")

    blocks = data.get("ocr_blocks", [])

    if show_full:
        print("── Full extracted text ─────────────────────────────────────\n")
        print(data.get("full_text", "(empty)"))
        print()
    else:
        print("── Text blocks (top 30) ─────────────────────────────────────")
        for i, block in enumerate(blocks[:30]):
            conf = block.get("confidence", 0)
            orient = block.get("orientation", "?")
            text = block.get("text", "")
            bbox = block.get("bbox", {})
            icon = "↕" if orient == "vertical" else "↔"
            conf_color = "\033[92m" if conf >= 0.8 else "\033[93m" if conf >= 0.6 else "\033[91m"
            reset = "\033[0m"
            print(
                f"  {i+1:>3}. {icon}  {conf_color}{conf:.2f}{reset}  "
                f"({bbox.get('x', 0):.2f}, {bbox.get('y', 0):.2f})  "
                f"│  {text[:60]}"
            )
        if len(blocks) > 30:
            print(f"\n  ... and {len(blocks)-30} more blocks. Use --full to see all text.\n")

    # Orientation summary
    horizontal = sum(1 for b in blocks if b.get("orientation") == "horizontal")
    vertical = sum(1 for b in blocks if b.get("orientation") == "vertical")
    print(f"  Orientation: {horizontal} horizontal, {vertical} vertical blocks")
    print()


def main():
    p = argparse.ArgumentParser(description="Inspect a single OCR JSON output file.")
    p.add_argument("json_path", type=str, help="Path to OCR JSON file")
    p.add_argument("--full", action="store_true", help="Show full concatenated text instead of block list")
    args = p.parse_args()

    path = Path(args.json_path)
    if not path.is_absolute():
        path = Path(__file__).parent.parent / path
    if not path.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)

    inspect(path, args.full)


if __name__ == "__main__":
    main()
