#!/usr/bin/env python3
"""One-off: blank redundant ``role_title`` cells in every ``committees.csv``.

A ``role_title`` that merely restates the committee/position ("Chair", "PC Member",
"LO Co-Chair", "Program Chair", …) carries no information beyond what the
``committee_type`` + ``position`` columns already encode, and renders as visible noise
in the web UI. This rewrites the source CSVs in place, clearing those cells while
preserving genuinely-informative titles ("Rump Session Organizer", "Local Service",
"Honorary Chair") and any title that *disagrees* with the position.

The redundancy rule is imported from the committees importer so the one-time CSV
cleanup and the ongoing import-time guardrail can never drift apart.

Usage:
    python3 tools/one_off/blank_redundant_role_titles.py            # apply
    python3 tools/one_off/blank_redundant_role_titles.py --dry-run  # preview only
"""
import argparse
import csv
import sys
from pathlib import Path

# tools/ on the path so `from scrapers...` resolves (mirrors import_from_csv.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.committees.importer import _is_redundant_role_title  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFERENCES_DIR = REPO_ROOT / 'data' / 'conferences'
FIELDNAMES = ['venue', 'year', 'committee_type', 'position',
              'full_name', 'affiliation', 'role_title']


def _detect_line_terminator(csv_path: Path) -> str:
    """Return the file's line ending so we preserve it (files are a mix of LF and CRLF)."""
    with open(csv_path, 'rb') as f:
        sample = f.read(4096)
    return '\r\n' if b'\r\n' in sample else '\n'


def clean_file(csv_path: Path, dry_run: bool) -> list[tuple[str, str]]:
    """Blank redundant role_title cells in one CSV. Returns [(full_name, dropped_title)]."""
    line_terminator = _detect_line_terminator(csv_path)
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    dropped = []
    for row in rows:
        title = row.get('role_title')
        if _is_redundant_role_title(title):
            dropped.append((row.get('full_name', '?'), title))
            row['role_title'] = ''

    if dropped and not dry_run:
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            # Preserve the source file's line ending (csv defaults to CRLF).
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES,
                                    lineterminator=line_terminator)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in FIELDNAMES})

    return dropped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change without rewriting files')
    args = parser.parse_args()

    csv_files = sorted(CONFERENCES_DIR.glob('*/committees.csv'))
    if not csv_files:
        print(f"No committees.csv files found under {CONFERENCES_DIR}", file=sys.stderr)
        return 1

    total = 0
    files_touched = 0
    for csv_path in csv_files:
        dropped = clean_file(csv_path, args.dry_run)
        if dropped:
            files_touched += 1
            total += len(dropped)
            rel = csv_path.relative_to(REPO_ROOT)
            print(f"{rel}: cleared {len(dropped)} role_title cell(s)")
            for name, title in dropped:
                print(f"    - {name}: '{title}'")

    verb = 'would clear' if args.dry_run else 'cleared'
    print(f"\n{verb} {total} redundant role_title cell(s) across {files_touched} file(s).")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
