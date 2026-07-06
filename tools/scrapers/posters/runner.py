"""CLI body for ``scrape_to_csv.py posters`` — scrape accepted-poster pages.

Posters are written to a dedicated ``<output_dir>/<venue>_<year>/posters.csv``
(same 18-column schema as ``talks.csv``), separate from the hand-curated talks.
The file is overwritten wholesale each run (with a ``--force`` guard), so the
scrape is idempotent — no drop-and-regenerate merge is needed. Import with
``import_from_csv.py talks <dir>/posters.csv`` (the importer is schema-driven).
"""
import argparse
import csv
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from . import parsers

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "conferences"

# Same 18 columns as talks.csv, so posters.csv imports through the talks path.
FIELDNAMES = [
    'venue', 'year', 'paper_type', 'title', 'speakers', 'authors',
    'affiliations', 'abstract', 'arxiv_ids', 'presentation_url',
    'video_url', 'youtube_id', 'session_name', 'award', 'notes',
    'scheduled_date', 'scheduled_time', 'duration_minutes',
]

# Local-mirror domain per venue (under --local-dir).
_DOMAINS = {
    'QCRYPT': 'qcrypt.iaqi.org',
    'QIP': 'qip.iaqi.org',
    'TQC': 'tqc.iaqi.org',
}

# Format families -> parser functions.
_PARSERS = {
    'hugo_session': parsers.parse_hugo_session,
    'qcrypt_2011': parsers.parse_qcrypt_2011,
    'qcrypt_2012': parsers.parse_qcrypt_2012,
    'qcrypt_2013': parsers.parse_qcrypt_2013,
    'qcrypt_2014': parsers.parse_qcrypt_2014,
    'qcrypt_2015': parsers.parse_qcrypt_2015,
    'qcrypt_2016': parsers.parse_qcrypt_2016,
    'qcrypt_2018': parsers.parse_qcrypt_2018,
    'qcrypt_2019': parsers.parse_qcrypt_2019,
    'qip_2006': parsers.parse_qip_2006,
    'qip_2009': parsers.parse_qip_2009,
    'qip_2010': parsers.parse_qip_2010,
    'qip_span_poster': parsers.parse_qip_span_poster,
    'qip_2013': parsers.parse_qip_2013,
    'qip_2014': parsers.parse_qip_2014,
    'qip_2015': parsers.parse_qip_2015,
    'qip_2016': parsers.parse_qip_2016,
    'qip_2020_js': parsers.parse_qip_2020,
    'qip_2023': parsers.parse_qip_2023,
    'qip_2024': parsers.parse_qip_2024,
    'qip_2026': parsers.parse_qip_2026,
    'tqc_2019': parsers.parse_tqc_2019,
    'tqc_2020': parsers.parse_tqc_2020,
    'tqc_2021': parsers.parse_tqc_2021,
    'tqc_2025': parsers.parse_tqc_2025,
    'tqc_bibtex': parsers.parse_tqc_bibtex,  # signature (text, year), not (soup)
    'qip_pdf_2col': parsers.parse_qip_pdf_2col,
    'qip_2017_pdf': parsers.parse_qip_2017_pdf,
    'qip_2021_pdf': parsers.parse_qip_2021_pdf,
    'qip_2023_pdf': parsers.parse_qip_2023_pdf,
    'tqc_2022_pdf': parsers.parse_tqc_2022_pdf,
}

# Families whose parser takes raw text + year (not a BeautifulSoup). PDF sources
# are extracted to text via `pdftotext -layout` first.
# qip_2020_js reads a JS bundle (the SPA hard-codes its poster list as a JS array
# literal); text family, but not a PDF, so the runner passes the raw file text.
_TEXT_FAMILIES = {'tqc_bibtex', 'qip_pdf_2col', 'qip_2017_pdf', 'qip_2021_pdf',
                  'qip_2023_pdf', 'tqc_2022_pdf', 'qip_2020_js'}
_PDF_FAMILIES = {'qip_pdf_2col', 'qip_2017_pdf', 'qip_2021_pdf', 'qip_2023_pdf', 'tqc_2022_pdf'}

# (venue, year) -> (family, [relative paths under the venue domain]).
# Paths/formats are per-year, so encode them explicitly rather than deriving.
# QCrypt 2023/2024/2025 are intentionally absent — they are JSON-sourced via
# talks/qcrypt_json_to_csv.py, which writes their posters.csv directly.
POSTER_SOURCES: Dict[tuple, tuple] = {
    ('QCRYPT', 2020): ('hugo_session', [
        '2020/sessions/poster1.html',
        '2020/sessions/poster2.html',
    ]),
    ('QCRYPT', 2021): ('hugo_session', [
        '2021/sessions/poster1/index.html',
        '2021/sessions/poster2/index.html',
    ]),
    ('QCRYPT', 2022): ('hugo_session', [
        '2022/sessions/poster1/index.html',
        '2022/sessions/poster2/index.html',
        '2022/sessions/poster3/index.html',
    ]),
    ('QCRYPT', 2011): ('qcrypt_2011', ['2011/programme/posters/index.html']),
    ('QCRYPT', 2012): ('qcrypt_2012', ['2012/program.html']),
    ('QCRYPT', 2013): ('qcrypt_2013', ['2013/posters/index.html']),
    # 2014's poster list is at the bottom of the program page (the dedicated
    # posters page is a "To be announced" stub).
    ('QCRYPT', 2014): ('qcrypt_2014', ['2014/program/index.html']),
    ('QCRYPT', 2015): ('qcrypt_2015', ['2015/index.html?p=25.html']),
    ('QCRYPT', 2016): ('qcrypt_2016', ['2016/posters/index.html']),
    ('QCRYPT', 2018): ('qcrypt_2018', ['2018/others/accepted-posters/index.html']),
    ('QCRYPT', 2019): ('qcrypt_2019', [
        '2019/scientific-program/poster-session-monday-26-august-2019/index.html',
        '2019/scientific-program/poster-session-wednesday-28-august-2019/index.html',
    ]),
    ('QIP', 2006): ('qip_2006', ['2006/accepted_posters.html']),
    ('QIP', 2009): ('qip_2009', ['2009/posters.html']),
    ('QIP', 2010): ('qip_2010', ['2010/postersession.html']),
    ('QIP', 2011): ('qip_span_poster', ['2011/scientificprogramme/postersession.php.html']),
    ('QIP', 2012): ('qip_span_poster', ['2012/posters_e.php.html']),
    ('QIP', 2013): ('qip_2013', ['2013/index.html@p=351.html']),
    ('QIP', 2014): ('qip_2014', ['2014/MondaySession.html', '2014/TuesdaySession.html']),
    ('QIP', 2015): ('qip_2015', ['2015/AcceptedPosters.php.html']),
    ('QIP', 2016): ('qip_2016', ['2016/accepted-posters.html']),
    ('QIP', 2017): ('qip_2017_pdf', [
        '2017/wp-content/uploads/2017/11/QIP-2017-Posters-Day-1-Monday-January-16.pdf',
        '2017/wp-content/uploads/2017/11/QIP-2017-Posters-Day-2-Tuesday-January-17.pdf',
    ]),
    ('QIP', 2018): ('qip_pdf_2col', ['2018/qutech.nl/wp-content/uploads/2018/01/Posters_QIP-2018.pdf']),
    ('QIP', 2019): ('qip_pdf_2col', ['2019/qip2019_accepted_posters.pdf']),
    # QIP 2020 is a JS SPA — its poster list is hard-coded as a `posterList`
    # array literal inside the bundled app.js (content-hashed filename).
    ('QIP', 2020): ('qip_2020_js', ['2020/static/js/app.1ac155286edb3bd13e8f.js']),
    # QIP 2021 accepted-poster list PDF is not on the mirror — it lived off-site
    # (mcqst.de). Fetched into the conference data dir and referenced by @-path.
    ('QIP', 2021): ('qip_2021_pdf', ['@data/conferences/qip_2021/raw/AllPostersQIP2021.pdf']),
    # Re-derived from the two Indico *session* pages (the "not presenting" page,
    # .../page/3898-not-presenting.html, is deliberately excluded). Supersedes the
    # PDF list (parse_qip_2023_pdf), whose text extraction dropped/truncated
    # leading authors and line-wrapped titles.
    ('QIP', 2023): ('qip_2023', [
        '2023/event/13076/page/3896-monday-session.html',
        '2023/event/13076/page/3897-tuesday-session.html',
    ]),
    ('QIP', 2024): ('qip_2024', ['2024/site/mypage.aspx?pid=263&lang=en&sid=1522.html']),
    # QIP 2026 uniquely underlines the presenter -> the parser emits `speakers`.
    ('QIP', 2026): ('qip_2026', ['2026/programme/poster-sessions/index.html']),
    # QIP 2002 poster page is unstructured prose (presenter/affiliation/abstract)
    # with no title markup — not reliably parseable; left for manual entry.
    # QIP 2005 (per-poster PDFs) is left for manual entry — its source files are
    # noted in data/SOURCES.md.
    ('TQC', 2022): ('tqc_2022_pdf', ['2022/files/2022/07/TQC-2022-Program-FINAL.pdf']),
    ('TQC', 2019): ('tqc_2019', ['2019/accepted-posters/index.html']),
    ('TQC', 2020): ('tqc_2020', ['2020/accepted-posters/index.html']),
    ('TQC', 2021): ('tqc_2021', ['2021/program/accepted-posters/index.html']),
    ('TQC', 2025): ('tqc_2025', ['2025/accepted-posters/index.html']),
    # TQC 2023/2024: parse the complete teachpress BibTeX export (the mirrored
    # web pages are JS-paginated and truncated to 100 of ~429). The .bib lives
    # under the conference data dir, not the web mirror.
    ('TQC', 2023): ('tqc_bibtex', ['@data/conferences/tqc_2024/raw/tqc-publications-23-24.bib']),
    ('TQC', 2024): ('tqc_bibtex', ['@data/conferences/tqc_2024/raw/tqc-publications-23-24.bib']),
}


def _build_row(venue: str, year: int, poster: Dict[str, Any],
               source: Optional[str]) -> Dict[str, str]:
    """Turn a parser poster dict into a full 18-column CSV row."""
    authors = poster.get('authors') or []
    affiliations = poster.get('affiliations') or []
    aff_cell = ';'.join(affiliations) if any(a for a in affiliations) else ''
    row = {c: '' for c in FIELDNAMES}
    row.update(
        venue=venue.upper(),
        year=str(year),
        paper_type='poster',
        title=(poster.get('title') or '').strip(),
        speakers=';'.join(poster.get('speakers') or []),
        authors=';'.join(authors),
        affiliations=aff_cell,
        abstract=(poster.get('abstract') or '').strip(),
        session_name=(poster.get('session_name') or ''),
        notes=(f"Source: {source}" if source else ''),
        scheduled_date=(poster.get('scheduled_date') or ''),
    )
    return row


def _dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Collapse rows describing the same poster listed more than once — e.g. a
    hybrid event's in-person poster session re-lists the online posters (QCRYPT
    2022 poster3), or a source page repeats each entry (QCRYPT 2021, TQC 2024/25).

    Rows are keyed on their whitespace-collapsed, lowercased title. Within a group
    the richest copy is kept (most authors, then longest affiliations, then longest
    abstract, then first seen), and the distinct ``session_name`` values are merged
    (first-seen order, ``"; "``-joined) so the surviving row records every session
    it appeared in. Rows with an empty title are never merged (kept verbatim)."""
    def author_count(r: Dict[str, str]) -> int:
        return len([a for a in (r.get('authors') or '').split(';') if a.strip()])

    order: List[Any] = []
    buckets: Dict[Any, List[Dict[str, str]]] = {}
    for i, r in enumerate(rows):
        title_key = ' '.join((r.get('title') or '').split()).lower()
        key: Any = title_key if title_key else (None, i)  # empties stay unique
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)

    out: List[Dict[str, str]] = []
    for key in order:
        grp = buckets[key]
        if len(grp) == 1:
            out.append(grp[0])
            continue
        best = max(grp, key=lambda r: (author_count(r),
                                       len(r.get('affiliations') or ''),
                                       len(r.get('abstract') or '')))
        sessions: List[str] = []
        for r in grp:
            s = (r.get('session_name') or '').strip()
            if s and s not in sessions:
                sessions.append(s)
        merged = dict(best)
        merged['session_name'] = '; '.join(sessions)
        out.append(merged)
        logger.info(f"  deduped {len(grp)}x -> 1: {best['title'][:60]}"
                    + (f" (sessions: {merged['session_name']})" if merged['session_name'] else ''))
    return out


def save_posters(venue: str, year: int, rows: List[Dict[str, str]],
                 output_dir: Path, force: bool = False) -> Optional[Path]:
    """Write poster rows to ``<output_dir>/<venue>_<year>/posters.csv``."""
    conference_dir = output_dir / f"{venue.lower()}_{year}"
    conference_dir.mkdir(parents=True, exist_ok=True)
    output_file = conference_dir / "posters.csv"

    if output_file.exists() and not force:
        logger.warning(f"Output file already exists: {output_file}")
        logger.warning("Use --force to overwrite")
        return None

    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Saved {len(rows)} posters to {output_file}")
    return output_file


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Wire CLI flags onto ``parser``. Used by the unified entry point."""
    parser.add_argument('--venue', required=True, choices=list(_DOMAINS.keys()),
                        help='Conference venue')
    parser.add_argument('--year', type=int, required=True,
                        help='Conference year')
    parser.add_argument('--local', action='store_true',
                        help='Read from the local website mirror (default source)')
    parser.add_argument('--local-file', type=str, action='append',
                        help='Explicit local HTML file(s); repeatable. Overrides the registry.')
    parser.add_argument('--local-dir', type=str, default='~/Web',
                        help='Base directory for the local mirror (default: ~/Web)')
    parser.add_argument('--output-dir', type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f'Output dir; CSV -> <output-dir>/<venue>_<year>/posters.csv (default: {DEFAULT_OUTPUT_DIR})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and print poster rows without writing the CSV')
    parser.add_argument('--force', action='store_true',
                        help='Overwrite existing posters.csv')


def _pdf_to_text(path: Path) -> Optional[str]:
    """Extract text from a PDF via ``pdftotext -layout`` (preserves columns)."""
    try:
        out = subprocess.run(
            ['pdftotext', '-layout', str(path), '-'],
            capture_output=True, check=True)
        return out.stdout.decode('utf-8', errors='replace')
    except FileNotFoundError:
        logger.error("pdftotext not found — install poppler (e.g. `brew install poppler`).")
    except subprocess.CalledProcessError as e:
        logger.error(f"pdftotext failed on {path}: {e}")
    return None


def _resolve_path(rel: str, venue: str, local_dir: Path) -> Path:
    """Map a registry path to a file. ``@foo`` is repo-relative (e.g. a raw
    data-dir source); otherwise it is under the venue's mirror domain."""
    if rel.startswith('@'):
        return REPO_ROOT / rel[1:]
    domain = _DOMAINS[venue.upper()]
    base = local_dir if local_dir.name == domain else local_dir / domain
    return base / rel


def _source_ref(rel: str, venue: str) -> str:
    """A provenance string for the ``notes`` column that never leaks a local
    filesystem path: the public site URL for a mirror page, or the repo-relative
    path for an ``@`` data-dir source (e.g. a raw ``.bib``)."""
    if rel.startswith('@'):
        return rel[1:]
    domain = _DOMAINS[venue.upper()]
    url = f"https://{domain}/{rel.lstrip('/')}"
    return re.sub(r'/index\.html$', '/', url)


def _resolve_sources(venue: str, year: int, local_dir: Path,
                     local_files: Optional[List[str]]) -> tuple:
    """Return (family, [(Path, source_ref)]) for the given venue/year."""
    key = (venue.upper(), year)
    if local_files:
        family = POSTER_SOURCES.get(key, (None, None))[0]
        if not family:
            raise ValueError(
                f"No format family registered for {venue} {year}; cannot parse "
                f"--local-file without one. Add it to POSTER_SOURCES.")
        # Manual override: reconstruct the public URL from the mirror-relative
        # tail if possible, else fall back to the given name (no local path).
        entries = []
        for f in local_files:
            p = Path(f).expanduser()
            entries.append((p, _url_from_local(p)))
        return family, entries

    if key not in POSTER_SOURCES:
        raise ValueError(
            f"No poster sources registered for {venue} {year}. "
            f"Add an entry to POSTER_SOURCES, or pass --local-file.")
    family, rel_paths = POSTER_SOURCES[key]
    return family, [(_resolve_path(rel, venue, local_dir), _source_ref(rel, venue))
                    for rel in rel_paths]


def _url_from_local(path: Path) -> str:
    """Best-effort public URL for an explicit local file: the tail from the
    ``<domain>.iaqi.org`` component onward, else just the file name (never an
    absolute local path)."""
    parts = path.parts
    for i, seg in enumerate(parts):
        if seg in _DOMAINS.values():
            url = f"https://{seg}/" + '/'.join(parts[i + 1:])
            return re.sub(r'/index\.html$', '/', url)
    return path.name


async def async_main(args: argparse.Namespace) -> int:
    """Run the poster scrape end-to-end. Returns shell exit code."""
    local_dir = Path(args.local_dir).expanduser()
    output_dir = Path(args.output_dir)

    try:
        family, entries = _resolve_sources(
            args.venue, args.year, local_dir, args.local_file)
    except ValueError as e:
        logger.error(str(e))
        return 1

    parser_func = _PARSERS[family]
    is_text = family in _TEXT_FAMILIES
    is_pdf = family in _PDF_FAMILIES

    rows: List[Dict[str, str]] = []
    for path, source_ref in entries:
        if not path.exists():
            logger.error(f"Source file not found: {path}")
            return 1
        logger.info(f"Parsing {path}")
        if is_pdf:
            text = _pdf_to_text(path)
            if text is None:
                return 1
            posters = parser_func(text, args.year)
        elif is_text:
            posters = parser_func(path.read_text(encoding='utf-8', errors='replace'), args.year)
        else:
            posters = parser_func(BeautifulSoup(path.read_bytes(), 'html.parser'))
        logger.info(f"  -> {len(posters)} posters")
        for p in posters:
            rows.append(_build_row(args.venue, args.year, p, source=source_ref))

    if not rows:
        logger.warning("No posters parsed! Check the source page structure / registry.")
        return 1

    before = len(rows)
    rows = _dedupe_rows(rows)
    if len(rows) != before:
        logger.info(f"Collapsed {before - len(rows)} duplicate poster row(s) "
                    f"across sessions/pages -> {len(rows)} unique.")

    if args.dry_run:
        logger.info(f"\n[dry-run] {len(rows)} poster rows for {args.venue} {args.year}:")
        for r in rows:
            logger.info(f"  {r['title'][:70]} | {r['authors'][:80]}")
        return 0

    output_file = save_posters(args.venue, args.year, rows, output_dir, force=args.force)
    if output_file:
        logger.info(f"\n✓ Saved {len(rows)} posters to: {output_file}")
        logger.info("\nNext steps:")
        logger.info(f"  1. Review: {output_file}")
        logger.info(f"  2. Import: ./import_from_csv.py talks {output_file}")
    return 0
