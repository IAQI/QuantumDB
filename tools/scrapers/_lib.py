"""Shared helpers for the scrape and import CLIs."""
import csv
import html
import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID
from urllib.parse import unquote

import asyncpg
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Curated cross-CSV author identity map (surname changes, full-middle-name /
# particle variants that normalize_name() cannot collapse). Same file that
# dedup_authors.py Phase A consumes; the importer now applies it at ingest so
# the DB is a pure function of the CSVs and no author row is ever
# created-then-deleted (which would silently null publications.presenter_author_id).
AUTHOR_ALIASES_PATH = Path(__file__).resolve().parents[2] / 'data' / 'author_aliases.csv'


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


# Whitespace characters that should collapse to a normal space.
_WS_TRANSLATE = str.maketrans({
    ' ': ' ',   # non-breaking space (seen as "Michał Horodecki")
    ' ': ' ',   # figure space
    ' ': ' ',   # narrow no-break space
    '​': '',    # zero-width space
})


def clean_field(value: Optional[str]) -> str:
    """Normalise a raw CSV text field before it is used or split.

    Critically this HTML-unescapes entities (``&eacute;`` → ``é``) **before**
    any ``;``-splitting downstream: author lists are semicolon-delimited and an
    entity like ``&eacute;`` contains a ``;`` that would otherwise shatter a
    name (e.g. ``Claude Cr&eacute;peau`` → ``Claude Cr`` + ``peau``). It also
    folds non-breaking/zero-width spaces, trims, and collapses runs of
    whitespace. Do **not** apply this to URL fields (it would mangle paths).
    """
    if not value:
        return ''
    value = html.unescape(value)
    value = value.translate(_WS_TRANSLATE)
    return re.sub(r'\s+', ' ', value).strip()


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


# Leading honorifics stripped from a scraped *display* name (case-insensitive).
_HONORIFIC_RE = re.compile(r'^(?:Dr|Prof|Professor|Mr|Mrs|Ms|Mx)\.?\s+', re.IGNORECASE)

# Name particles that stay lower-case when re-casing an ALL-CAPS name (unless
# they lead the name). Keeps "van der Waals", "de Broglie" etc. natural.
_NAME_PARTICLES = frozenset({
    'van', 'von', 'de', 'der', 'den', 'del', 'della', 'di', 'da', 'du',
    'la', 'le', 'los', 'las', 'bin', 'ibn', 'al', 'el', 'ter', 'ten',
})


def _titlecase_word(word: str) -> str:
    """Title-case one whitespace-free token, capitalising each hyphen/apostrophe
    sub-part so "JOCHYM-O'CONNOR" → "Jochym-O'Connor" and initials stay upper."""
    def cap(piece: str) -> str:
        return piece[:1].upper() + piece[1:].lower() if piece else piece
    return ''.join(p if p in "-'’" else cap(p) for p in re.split(r"([-'’])", word))


# Latin typographic ligatures that PDF/HTML sources emit as single codepoints
# (e.g. "Reﬁk" for "Refik"). Expanded so display names stay searchable.
_LIGATURES = str.maketrans({
    'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st', 'ﬆ': 'st',
})
# LaTeX \'{\i} exports a dotless i (U+0131) followed by a combining accent; the
# intended letter is a dotted i. Restore it before NFC composes the accent.
_DOTLESS_I_RE = re.compile('ı(?=[̀-ͯ])')


def _normalize_display_unicode(name: str) -> str:
    """Compose canonical decomposed sequences and expand ligatures / the LaTeX
    dotless-i artifact, so a display name uses precomposed accented letters
    ("Gómez", "Víctor") and plain ASCII where a ligature was used ("Refik")."""
    name = _DOTLESS_I_RE.sub('i', name).translate(_LIGATURES)
    # LaTeX \'e etc. can export a spacing acute (´) just before the vowel it
    # accents ("Ass´emat" -> "Assémat"); fold it onto the following letter.
    name = re.sub(r'´([A-Za-z])', lambda m: m.group(1) + '́', name)
    return unicodedata.normalize('NFC', name)


def clean_display_name(name: str) -> str:
    """Tidy a scraped *display* name (case preserved, unlike ``normalize_name``).

    0. Compose Unicode (NFC) and expand typographic ligatures / the LaTeX
       dotless-i artifact (``_normalize_display_unicode``).
    1. Strip a leading honorific ("Dr.", "Prof.", …).
    2. If the name is a single case throughout — a "shouted" ALL-CAPS scrape
       ("YANGYANG FEI", "N C RANDEEP") or an all-lower-case one ("yicheng shi") —
       re-case it to title case, keeping single-letter initials upper and name
       particles (van, de, …) lower.

    A mixed-case name (the common case) is returned unchanged apart from the
    honorific strip, so this is safe to run over every parsed author.
    """
    if not name:
        return name
    name = _normalize_display_unicode(name)
    name = _HONORIFIC_RE.sub('', name).strip()
    letters = [c for c in name if c.isalpha()]
    if letters and (all(c.isupper() for c in letters) or all(c.islower() for c in letters)):
        recased = []
        for i, word in enumerate(name.split()):
            if i and word.lower() in _NAME_PARTICLES:
                recased.append(word.lower())
            else:
                recased.append(_titlecase_word(word))
        name = ' '.join(recased)
    # A leading all-lower-case word in an otherwise mixed-case name is a scrape
    # typo (a first name is never legitimately lower-case), e.g. "jonathan
    # Oppenheim". Capitalise it — but leave a leading particle ("van …") alone.
    words = name.split()
    if words and words[0].islower() and words[0] not in _NAME_PARTICLES:
        words[0] = _titlecase_word(words[0])
        name = ' '.join(words)
    return name


def split_name(full_name: str) -> tuple[str, str]:
    """Split a (normalized) full name into (family_name, given_name)."""
    normalized = normalize_name(full_name)
    parts = normalized.rsplit(' ', 1)
    if len(parts) == 1:
        return parts[0], ''
    return parts[1], parts[0]


@lru_cache(maxsize=1)
def load_author_aliases() -> Dict[str, str]:
    """Load ``data/author_aliases.csv`` as ``{former_full_name: current_full_name}``.

    Keyed on ``clean_field(former)`` so it matches author names as they arrive
    from the CSVs (which pass through ``clean_field`` before reaching
    ``get_or_create_author``). Both ``variant_type`` values (``former_name`` and
    ``alternate_spelling``) behave identically here: a printed spelling maps to a
    canonical identity. Cached so the file is read once per import run.
    """
    if not AUTHOR_ALIASES_PATH.exists():
        return {}
    aliases: Dict[str, str] = {}
    with open(AUTHOR_ALIASES_PATH, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            former = clean_field(row.get('former_name') or '')
            current = clean_field(row.get('current_name') or '')
            if former and current:
                aliases[former] = current
    return aliases


async def get_or_create_author(
    conn: asyncpg.Connection,
    full_name: str,
    affiliation: Optional[str],
) -> UUID:
    """Resolve ``full_name`` to a canonical author row, creating it if needed.

    Shared by the talks and committees importers. A curated alias
    (``author_aliases.csv``) maps a former/variant spelling to its canonical name
    *before* the lookup, so a "former" spelling never creates its own row and the
    identity is order-independent (the canonical row is created even if the former
    spelling is imported first). Callers keep passing the *printed* name to
    ``published_as_name`` / presenter resolution, so papers retain their published
    spelling.
    """
    canonical_name = load_author_aliases().get(full_name, full_name)
    family_name, given_name = split_name(canonical_name)
    normalized_full = normalize_name(canonical_name).lower()

    author_id = await conn.fetchval(
        """
        SELECT a.id FROM authors a
        LEFT JOIN author_name_variants v ON a.id = v.author_id
        WHERE a.normalized_name = $1
           OR LOWER(v.variant_name) = $1
        LIMIT 1
        """,
        normalized_full,
    )

    if author_id:
        logger.debug(f"Found existing author: {full_name} -> {author_id}")
        if affiliation:
            await conn.execute(
                """
                UPDATE authors
                SET affiliation = $1
                WHERE id = $2 AND (affiliation IS NULL OR affiliation != $1)
                """,
                affiliation,
                author_id,
            )
    else:
        author_id = await conn.fetchval(
            """
            INSERT INTO authors (full_name, family_name, given_name, normalized_name, affiliation, creator, modifier)
            VALUES ($1, $2, $3, $4, $5, 'import_from_csv', 'import_from_csv')
            RETURNING id
            """,
            canonical_name,
            family_name,
            given_name,
            normalized_full,
            affiliation,
        )
        logger.info(f"Created new author: {canonical_name} ({author_id})")

    # Record an aliased printed spelling as a name variant (parity with
    # dedup_authors.py). Cheap and idempotent; keeps a repeat sighting of the
    # former spelling resolvable via the variant lookup above even without the map.
    if canonical_name != full_name:
        await conn.execute(
            """
            INSERT INTO author_name_variants
                (author_id, variant_name, normalized_variant, variant_type, notes, creator)
            VALUES ($1, $2, $3, 'alternate_spelling', 'alias applied at import', 'import_from_csv')
            ON CONFLICT DO NOTHING
            """,
            author_id,
            full_name,
            normalize_name(full_name),
        )

    return author_id


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
