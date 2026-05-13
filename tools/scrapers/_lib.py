"""Shared helpers for the scrape and import CLIs."""
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

import asyncpg
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# Special characters that don't decompose via Unicode NFD — mapped explicitly.
# Mirror of src/utils/normalize.rs::replace_special_chars so Python and Rust
# normalizers agree.
_SPECIAL_CHAR_MAP = str.maketrans({
    'Ł': 'L', 'ł': 'l',          # Polish
    'Ø': 'O', 'ø': 'o',          # Nordic
    'Æ': 'A', 'æ': 'a',
    'Å': 'A', 'å': 'a',
    'ß': 's',                    # German eszett
    'Ð': 'D', 'ð': 'd',          # Icelandic
    'Þ': 'T', 'þ': 't',
    'Đ': 'D', 'đ': 'd',          # Croatian/Serbian
    'İ': 'I', 'ı': 'i',          # Turkish
    'Ğ': 'G', 'ğ': 'g',
    'Ş': 'S', 'ş': 's',
})


def normalize_name(name: str) -> str:
    """Normalize an author name for deduplication-grade matching.

    Transformations (applied in order):
      1. Strip honorifics / suffixes: Dr., Prof., Jr., Sr., Ph.D., M.D.
      2. Replace special letters that don't decompose via NFD (ł, ø, æ, ß, …).
      3. Unicode NFKD decomposition + strip combining marks (é → e, ü → u).
      4. Lowercase.
      5. Drop single-letter middle-initial tokens, both with and without a
         trailing period (so "Umesh V. Vazirani" and "Umesh Vazirani" collapse).
      6. Collapse whitespace.
    """
    if not name:
        return ''
    s = re.sub(r'\b(Dr|Prof|Jr|Sr|Ph\.?D|M\.?D)\.?\s*', ' ', name, flags=re.IGNORECASE)
    s = s.translate(_SPECIAL_CHAR_MAP)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    tokens = [t for t in s.split() if not re.fullmatch(r"[a-z]\.?", t)]
    return ' '.join(tokens)


def split_name(full_name: str) -> tuple[str, str]:
    """Split a (normalized) full name into (family_name, given_name)."""
    normalized = normalize_name(full_name)
    parts = normalized.rsplit(' ', 1)
    if len(parts) == 1:
        return parts[0], ''
    return parts[1], parts[0]


def url_to_local_path(url: str, local_dir: Optional[Path] = None) -> Path:
    """Map an http(s) URL to its mirror under ``local_dir``.

    Default ``local_dir`` is ``~/Web``. URLs ending in '/' or with no file
    extension get an ``index.html`` appended.
    """
    if local_dir is None:
        local_dir = Path.home() / 'Web'

    url = unquote(url)
    without_protocol = url.removeprefix('http://').removeprefix('https://')
    parts = without_protocol.split('/', 1)
    domain = parts[0]
    path = parts[1] if len(parts) > 1 else ''

    base = local_dir if local_dir.name == domain else local_dir / domain
    full_path = base / path

    if not path or '.' not in Path(path).name or path.endswith('/'):
        full_path = full_path / 'index.html'

    return full_path


async def get_archive_url(venue: str, year: int, columns: List[str]) -> Optional[str]:
    """Look up the archive URL for ``venue``/``year`` from the conferences table.

    ``columns`` is the preference order — committees use
    ``['archive_pc_url', 'archive_organizers_url']``, talks use
    ``['archive_program_url']``. Returns the first non-null column, or
    ``None`` if the conference is missing or has no archive set.
    """
    load_dotenv()
    database_url = os.environ.get('DATABASE_URL')

    if not database_url:
        logger.warning("DATABASE_URL not set, will use scraper's default URL")
        return None

    select = ', '.join(columns)
    try:
        conn = await asyncpg.connect(database_url)
        try:
            row = await conn.fetchrow(
                f"SELECT {select} FROM conferences WHERE venue = $1 AND year = $2",
                venue.upper(),
                year,
            )
            if not row:
                logger.warning(f"Conference {venue} {year} not found in database")
                return None
            for col in columns:
                if row[col]:
                    logger.info(f"Found archive URL in database: {row[col]}")
                    return row[col]
            logger.warning(f"Conference found but no archive URLs set for {venue} {year}")
            return None
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Error querying database: {e}. Will use scraper's default URL.")
        return None
