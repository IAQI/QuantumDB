#!/usr/bin/env python3
"""Unified scrape CLI: ``./scrape_to_csv.py {committees|talks} ...``.

Examples:
    ./scrape_to_csv.py committees --venue QIP --year 2024 --local
    ./scrape_to_csv.py talks --venue QCRYPT --year 2023 --local
    ./scrape_to_csv.py posters --venue QCRYPT --year 2020 --local
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow `python tools/scrapers/scrape_to_csv.py …` from a checkout that
# isn't on PYTHONPATH — make `scrapers` importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.committees import runner as committees_runner  # noqa: E402
from scrapers.posters import runner as posters_runner  # noqa: E402
from scrapers.talks import runner as talks_runner  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Scrape conference data (committees or talks) to CSV.',
    )
    sub = parser.add_subparsers(dest='kind', required=True,
                                metavar='{committees,talks,posters}')

    p_c = sub.add_parser('committees', help='Scrape committee membership data')
    committees_runner.add_arguments(p_c)

    p_t = sub.add_parser('talks', help='Scrape talk/paper data')
    talks_runner.add_arguments(p_t)

    p_p = sub.add_parser('posters', help='Scrape accepted-poster data')
    posters_runner.add_arguments(p_p)

    return parser


_RUNNERS = {
    'committees': committees_runner,
    'talks': talks_runner,
    'posters': posters_runner,
}


def main() -> int:
    args = build_parser().parse_args()
    runner = _RUNNERS[args.kind]
    return asyncio.run(runner.async_main(args)) or 0


if __name__ == '__main__':
    sys.exit(main())
