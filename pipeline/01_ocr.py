#!/usr/bin/env python3
"""
pipeline/01_ocr.py — Phase 0: Apple Vision OCR Harvester

Runs the compiled Swift `ocr_tool` binary on every page image in an issue folder.
Saves one JSON file per page in the `ocr/` subfolder.

Features:
- Checkpoint-aware: skips pages already processed
- Resumable: safe to interrupt and restart at any time
- Parallel: processes N pages concurrently using ThreadPoolExecutor
- Progress bar via tqdm
- Summary report at the end

Usage:
    python3 pipeline/01_ocr.py --issue output_Famitsu_1986_No01
    python3 pipeline/01_ocr.py --issue output_Famitsu_1986_No01 --workers 4
    python3 pipeline/01_ocr.py --magazine famitsu --issue-number 1
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────

# Path to the compiled Swift binary (built once with `swift build -c release`)
OCR_BINARY = Path(__file__).parent.parent / "ocr_tool" / ".build" / "release" / "ocr_tool"

# Where processed issue folders live (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent

# Image extensions to process
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}

# ── Core Functions ─────────────────────────────────────────────────────────────

def find_binary() -> Path:
    """Locate the OCR binary, building it if necessary."""
    if OCR_BINARY.exists():
        return OCR_BINARY

    print("⚙️  Swift binary not found. Building ocr_tool...")
    ocr_dir = PROJECT_ROOT / "ocr_tool"
    result = subprocess.run(
        ["swift", "build", "-c", "release"],
        cwd=ocr_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("❌ Build failed:")
        print(result.stderr)
        sys.exit(1)
    print("✅ Binary built successfully.")
    return OCR_BINARY


def get_image_files(issue_dir: Path) -> list[Path]:
    """Return sorted list of image files in the issue directory."""
    images = sorted([
        f for f in issue_dir.iterdir()
        if f.suffix.lower() in IMAGE_EXTENSIONS and f.is_file()
    ])
    return images


def ocr_page(binary: Path, image_path: Path, output_path: Path) -> dict:
    """
    Run OCR on a single page image. Saves result to output_path.
    Returns a status dict for reporting.
    """
    start = time.monotonic()

    result = subprocess.run(
        [str(binary), str(image_path)],
        capture_output=True,
        text=True,
        timeout=120  # 2 min max per page (very generous for even the densest page)
    )

    elapsed = time.monotonic() - start

    if result.returncode != 0:
        return {
            "page": image_path.name,
            "status": "error",
            "error": result.stderr.strip(),
            "elapsed": elapsed,
        }

    try:
        ocr_data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {
            "page": image_path.name,
            "status": "parse_error",
            "error": str(e),
            "elapsed": elapsed,
        }

    # Save to output file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ocr_data, f, ensure_ascii=False, indent=2)

    block_count = ocr_data.get("block_count", 0)
    avg_conf = ocr_data.get("average_confidence", 0)

    return {
        "page": image_path.name,
        "status": "ok",
        "blocks": block_count,
        "confidence": round(avg_conf, 3),
        "elapsed": round(elapsed, 2),
    }


def process_issue(issue_dir: Path, workers: int = 4, force: bool = False) -> None:
    """Process all pages in an issue directory."""
    ocr_dir = issue_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)

    images = get_image_files(issue_dir)
    if not images:
        print(f"⚠️  No images found in {issue_dir}")
        return

    print(f"\n📚 Issue: {issue_dir.name}")
    print(f"   Pages found: {len(images)}")
    print(f"   OCR output:  {ocr_dir}")
    print(f"   Workers:     {workers}")

    # Build work queue, skipping already-processed pages (checkpoint)
    tasks = []
    skipped = 0
    for img in images:
        out_path = ocr_dir / (img.stem + ".json")
        if out_path.exists() and not force:
            skipped += 1
        else:
            tasks.append((img, out_path))

    if skipped:
        print(f"   ✓ Skipping {skipped} already-processed pages (use --force to reprocess)")

    if not tasks:
        print("   ✅ All pages already processed!")
        return

    print(f"   ⏳ Processing {len(tasks)} pages...\n")

    # Process with thread pool
    results = []
    errors = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        binary = find_binary()
        future_to_page = {
            executor.submit(ocr_page, binary, img, out): img
            for img, out in tasks
        }

        completed = 0
        for future in as_completed(future_to_page):
            completed += 1
            result = future.result()
            results.append(result)

            status_icon = "✅" if result["status"] == "ok" else "❌"
            if result["status"] == "ok":
                conf_pct = int(result["confidence"] * 100)
                conf_bar = "█" * (conf_pct // 10) + "░" * (10 - conf_pct // 10)
                print(
                    f"  {status_icon} {result['page']:<45} "
                    f"{result['blocks']:>4} blocks  "
                    f"[{conf_bar}] {conf_pct}%  "
                    f"{result['elapsed']:.1f}s"
                    f"  ({completed}/{len(tasks)})"
                )
            else:
                errors.append(result)
                print(f"  {status_icon} {result['page']} — {result.get('error', 'unknown error')}")

    # Summary
    ok = [r for r in results if r["status"] == "ok"]
    total_time = sum(r["elapsed"] for r in results)
    avg_conf = sum(r["confidence"] for r in ok) / len(ok) if ok else 0

    print(f"\n{'─'*60}")
    print(f"  ✅ Processed: {len(ok)}/{len(tasks)} pages")
    print(f"  ⏱️  Total:    {total_time:.1f}s  (avg {total_time/len(tasks):.1f}s/page)")
    print(f"  📊 Avg confidence: {avg_conf:.1%}")
    if errors:
        print(f"  ❌ Errors ({len(errors)}):")
        for e in errors:
            print(f"     - {e['page']}: {e.get('error', '')}")
    print(f"  💾 Output: {ocr_dir}/\n")

    # Write session manifest
    manifest = {
        "issue_dir": str(issue_dir),
        "total_pages": len(images),
        "processed_this_run": len(tasks),
        "skipped_checkpointed": skipped,
        "ok": len(ok),
        "errors": len(errors),
        "average_confidence": round(avg_conf, 4),
        "total_elapsed_seconds": round(total_time, 2),
        "results": results,
    }
    manifest_path = ocr_dir / "_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  📋 Manifest saved: {manifest_path}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 0: Apple Vision OCR harvester for magazine pages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a specific issue folder
  python3 pipeline/01_ocr.py --issue output_Famitsu_1986_No01

  # Use 8 parallel workers for speed
  python3 pipeline/01_ocr.py --issue output_Famitsu_1986_No01 --workers 8

  # Force reprocess even if already done
  python3 pipeline/01_ocr.py --issue output_Famitsu_1986_No01 --force

  # Process all issue folders matching a pattern
  python3 pipeline/01_ocr.py --all --pattern "output_Famitsu_*"
        """
    )
    p.add_argument("--issue", type=str, help="Path to issue folder (absolute or relative to project root)")
    p.add_argument("--all", action="store_true", help="Process all matching issue folders")
    p.add_argument("--pattern", type=str, default="output_*", help="Glob pattern for --all mode (default: output_*)")
    p.add_argument("--workers", type=int, default=4, help="Parallel workers (default: 4)")
    p.add_argument("--force", action="store_true", help="Reprocess pages even if OCR output exists")
    p.add_argument("--build-only", action="store_true", help="Just build the Swift binary and exit")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Ensure binary is built
    binary = find_binary()
    print(f"🔧 OCR binary: {binary}")

    if args.build_only:
        print("✅ Build complete.")
        return

    if args.all:
        # Process all matching folders
        folders = sorted(PROJECT_ROOT.glob(args.pattern))
        issue_dirs = [f for f in folders if f.is_dir() and not f.name.startswith(".")]
        if not issue_dirs:
            print(f"⚠️  No folders matching '{args.pattern}' found in {PROJECT_ROOT}")
            sys.exit(1)
        print(f"🗂️  Found {len(issue_dirs)} issue folders to process:")
        for d in issue_dirs:
            print(f"   - {d.name}")
        for d in issue_dirs:
            process_issue(d, workers=args.workers, force=args.force)

    elif args.issue:
        issue_path = Path(args.issue)
        if not issue_path.is_absolute():
            issue_path = PROJECT_ROOT / issue_path
        if not issue_path.exists():
            print(f"❌ Issue folder not found: {issue_path}")
            sys.exit(1)
        process_issue(issue_path, workers=args.workers, force=args.force)

    else:
        print("❌ Specify --issue <folder> or --all")
        sys.exit(1)


if __name__ == "__main__":
    main()
