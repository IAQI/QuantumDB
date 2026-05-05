#!/usr/bin/env python3
"""Unified import CLI: ``./import_from_csv.py {committees|talks} <csv> ...``.

Examples:
    ./import_from_csv.py committees ../../data/conferences/qip_2024/committees.csv --dry-run
    ./import_from_csv.py talks ../../data/conferences/qcrypt_2024/talks.csv
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.committees import importer as committees_importer  # noqa: E402
from scrapers.talks import importer as talks_importer  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Import committee or talk CSV(s) into the QuantumDB database.',
    )
    sub = parser.add_subparsers(dest='kind', required=True,
                                metavar='{committees,talks}')

    p_c = sub.add_parser('committees', help='Import committee CSV(s)')
    committees_importer.add_arguments(p_c)

    p_t = sub.add_parser('talks', help='Import talk CSV(s)')
    talks_importer.add_arguments(p_t)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    importer = committees_importer if args.kind == 'committees' else talks_importer
    return asyncio.run(importer.async_main(args)) or 0


if __name__ == '__main__':
    sys.exit(main())
