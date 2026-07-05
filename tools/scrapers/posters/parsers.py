"""Per-format-family parsers for accepted-poster / poster-session pages.

Each parser takes a parsed ``BeautifulSoup`` document (one source page) and
returns a list of poster dicts with the contract::

    {
        'title': str,
        'authors': list[str],        # ordered
        'affiliations': list[str],   # parallel to authors, '' where unknown
        'abstract': str | None,
        'session_name': str | None,  # where the source groups posters
    }

``speakers`` is normally absent — most poster pages mark no distinct presenter, so
the importer resolves ``presenter_author_id`` to NULL. The exception is QIP 2026,
whose page underlines (``<u>``) the presenter: ``parse_qip_2026`` emits ``speakers``
(and a ``scheduled_date``) so the importer sets the presenter. ``scheduled_time`` /
``duration_minutes`` are absent too (posters legitimately lack them). The runner
stamps ``venue``/``year``/``notes`` (source path) onto each row afterwards.

One parser per FORMAT FAMILY (not per year); the year→family+paths mapping lives
in ``runner.POSTER_SOURCES``.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag

from .._lib import clean_display_name

# Leading label some abstract blocks carry, e.g. "Abstract: ...".
_ABSTRACT_PREFIX_RE = re.compile(r'^\s*abstract\s*[:.\-]?\s*', re.IGNORECASE)


def _collapse(text: str) -> str:
    """Collapse whitespace runs (incl. newlines) to single spaces and trim."""
    return re.sub(r'\s+', ' ', text).strip()


def split_authors(cell: str) -> Tuple[List[str], List[str]]:
    """Split an author cell into parallel (names, affiliations) lists.

    Splits on ``;`` when present (Hugo poster pages use it), otherwise on
    top-level `` and `` / `` & `` / ``,`` (QIP/TQC prose lists). A trailing
    ``(parenthetical)`` on a name — even one with nested parens or internal
    commas, e.g. ``"Gautam Vemuri (Dept of Physics, Univ (IUPUI), USA)"`` — is
    pulled into the parallel affiliation slot; the affiliation is ``''`` when
    absent, so ``names`` and ``affiliations`` stay index-aligned. A parenthetical
    that is *not* trailing (a maiden name like ``"Justyna (Pytel) Zwolak"``) is
    left in the name. Each name is tidied with ``clean_display_name`` (strip a
    leading honorific; re-case a shouted ALL-CAPS name).

    HTML entities are left intact for the importer's ``clean_field`` to unescape
    (it must run before any further ``;``-split, or an entity like ``&eacute;``
    would shatter a name).
    """
    cell = cell.strip()
    if not cell:
        return [], []

    if ';' in cell:
        # ';' separates authors, but an affiliation parenthetical may itself
        # contain ';' (multiple affiliations), so split at top level only.
        parts = _split_top_level(cell, ';')
    else:
        # Prose list: split on top-level ',' / ' and ' / ' & ' — separators
        # inside affiliation parentheses are protected (so an affiliation's own
        # "X and Y" / "City, Country" does not shatter into bogus authors).
        parts = _split_authors_prose(cell)

    names: List[str] = []
    affs: List[str] = []
    for part in parts:
        name = _collapse(part)
        if not name:
            continue
        name, aff = _strip_trailing_paren(name)
        name = _collapse_doubled_name(clean_display_name(_collapse(name)))
        # Internal ';' would corrupt the downstream ';'-joined affiliation cell
        # (positional, one entry per author) — fold it to a comma.
        aff = _collapse(aff).replace(';', ',')
        if not name:
            continue
        names.append(name)
        affs.append(aff)
    return names, affs


def _strip_trailing_paren(name: str) -> Tuple[str, str]:
    """Split a trailing ``(affiliation)`` off ``name``, returning ``(name, aff)``.

    Handles three shapes seen in the poster mirrors:
      * balanced trailing group, incl. nested parens/commas —
        ``"Gautam Vemuri (Dept, Univ (IUPUI), USA)"``;
      * an affiliation the source never closed (more ``(`` than ``)``) —
        ``"Xin Wang (The Hong Kong University … (Guangzhou)"`` — where the name
        is whatever precedes the first unmatched ``(``;
      * no trailing parenthetical, or a *non*-trailing one (a maiden name like
        ``"Justyna (Pytel) Zwolak"``) — returned unchanged, empty affiliation.
    """
    name = name.rstrip()
    # Unclosed affiliation paren: the name ends mid-parenthetical. Cut at the
    # first '(' — everything after it is affiliation, however malformed.
    if name.count('(') > name.count(')'):
        idx = name.find('(')
        return name[:idx].rstrip(), name[idx + 1:].strip()
    if not name.endswith(')'):
        return name, ''
    depth = 0
    for i in range(len(name) - 1, -1, -1):
        ch = name[i]
        if ch == ')':
            depth += 1
        elif ch == '(':
            depth -= 1
            if depth == 0:
                return name[:i].rstrip(), name[i + 1:-1]
    return name, ''  # unbalanced the other way — leave intact


def _collapse_doubled_name(name: str) -> str:
    """Undo a name the source doubled (a recurring poster-scrape artifact).

    Two patterns, both seen in the accepted-poster mirrors:
      * whole name repeated — "Subhendu Bikash Ghosh Subhendu Bikash Ghosh";
      * an adjacent word repeated — "Nike Dattani Dattani", "Myungshik Kim Kim".

    Repeated *single-letter* tokens are preserved, so real double initials like
    "Maneesha K K" survive.
    """
    toks = name.split()
    if len(toks) >= 4 and len(toks) % 2 == 0:
        half = len(toks) // 2
        if toks[:half] == toks[half:] and any(len(t.strip('.')) > 1 for t in toks[:half]):
            toks = toks[:half]
    out: List[str] = []
    for t in toks:
        if out and t == out[-1] and len(t.strip('.')) > 1:
            continue
        out.append(t)
    return ' '.join(out)


def _split_authors_prose(cell: str) -> List[str]:
    """Split a prose author list on top-level ``,`` / `` and `` / `` & ``,
    protecting any separator that sits inside (affiliation) parentheses."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    i, n = 0, len(cell)
    while i < n:
        ch = cell[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if depth == 0:
            if ch == ',':
                parts.append(''.join(buf))
                buf = []
                i += 1
                continue
            m = re.match(r'\s+(?:and|&)\s+', cell[i:])
            if m:
                parts.append(''.join(buf))
                buf = []
                i += m.end()
                continue
        buf.append(ch)
        i += 1
    parts.append(''.join(buf))
    return parts


def _split_top_level(text: str, sep: str) -> List[str]:
    """Split on ``sep`` only where not nested inside parentheses."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append(''.join(buf))
    return parts


def _clean_abstract(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = _ABSTRACT_PREFIX_RE.sub('', _collapse(text))
    return text or None


# ---------------------------------------------------------------------------
# Family A — QCrypt Hugo per-session pages (2020, 2021, 2022)
# ---------------------------------------------------------------------------
def parse_hugo_session(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Parse a QCrypt Hugo ``sessions/poster*.html`` page.

    Each poster is a ``div.paper-single`` with ``div.paper-title``,
    ``div.paper-authors`` (``;``-separated, affiliation in trailing parens) and
    an optional ``div.paper-abstract-full``. The page ``<h1>`` is the session
    name (e.g. "Poster Session 1").
    """
    h1 = soup.find('h1')
    session_name = _collapse(h1.get_text(' ', strip=True)) if h1 else None

    posters: List[Dict[str, Any]] = []
    for single in soup.find_all('div', class_='paper-single'):
        title_div = single.find('div', class_='paper-title')
        if not title_div:
            continue
        title = _collapse(title_div.get_text(' ', strip=True))
        if not title:
            continue

        authors_div = single.find('div', class_='paper-authors')
        authors, affiliations = ([], [])
        if authors_div:
            authors, affiliations = split_authors(authors_div.get_text(' ', strip=True))

        abstract_div = single.find('div', class_='paper-abstract-full')
        abstract = _clean_abstract(abstract_div.get_text(' ', strip=True)) if abstract_div else None

        posters.append({
            'title': title,
            'authors': authors,
            'affiliations': affiliations,
            'abstract': abstract,
            'session_name': session_name,
        })
    return posters


def _poster(title: str, authors_cell: str, abstract: Optional[str] = None,
            session_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Assemble a poster dict from a raw title + author cell. None if no title."""
    title = _collapse(title)
    if not title:
        return None
    authors, affiliations = split_authors(authors_cell)
    return {
        'title': title,
        'authors': authors,
        'affiliations': affiliations,
        'abstract': _clean_abstract(abstract),
        'session_name': session_name,
    }


def _largest_table(soup: BeautifulSoup):
    tables = soup.find_all('table')
    return max(tables, key=lambda t: len(t.find_all('tr'))) if tables else None


# ---------------------------------------------------------------------------
# Family B — QCrypt older list pages (one small parser per page structure)
# ---------------------------------------------------------------------------
def parse_qcrypt_2011(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2011: table rows of ``<td>Authors<br><em>Title</em></td>``."""
    table = _largest_table(soup)
    posters: List[Dict[str, Any]] = []
    if not table:
        return posters
    for tr in table.find_all('tr'):
        em = tr.find('em')
        if not em:
            continue
        title = em.get_text(' ', strip=True)
        # Authors are the text node(s) before the <em> in the same cell.
        cell = em.find_parent(['td', 'th']) or tr
        authors_parts = []
        for node in cell.children:
            if node is em or (getattr(node, 'find', None) and node.find('em') is em):
                break
            if isinstance(node, NavigableString):
                authors_parts.append(str(node))
            elif getattr(node, 'get_text', None):
                authors_parts.append(node.get_text(' ', strip=True))
        p = _poster(title, ' '.join(authors_parts))
        if p:
            posters.append(p)
    return posters


def parse_qcrypt_2013(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2013: ``<td><span class="title">T</span><br>Authors<br>…
    <div class="abstract">A</div></td>``."""
    table = _largest_table(soup)
    posters: List[Dict[str, Any]] = []
    if not table:
        return posters
    for tr in table.find_all('tr'):
        cell = tr.find('td')
        if not cell:
            continue
        title_span = cell.find('span', class_='title')
        if not title_span:
            continue
        title = title_span.get_text(' ', strip=True)
        abstract_div = cell.find('div', class_='abstract')
        abstract = abstract_div.get_text(' ', strip=True) if abstract_div else None
        # Authors: everything between the title span and the first anchor
        # (Abstract/Poster links). This spans text nodes and inline <span>s —
        # some rows split an author list across both — and naturally excludes
        # any prize-note spans, which precede the title span.
        authors_parts = []
        for node in title_span.next_siblings:
            if isinstance(node, Tag):
                if node.name == 'a' or (node.name == 'div' and 'abstract' in (node.get('class') or [])):
                    break
                if node.name == 'br':
                    continue
                authors_parts.append(node.get_text(' ', strip=True))
            elif isinstance(node, NavigableString):
                authors_parts.append(str(node))
        authors = _collapse(' '.join(authors_parts))
        p = _poster(title, authors, abstract=abstract)
        if p:
            posters.append(p)
    return posters


# Curly or straight quotes around a title.
_QUOTED_TITLE_RE = re.compile(r'[“"”]([^“"”]+)[“"”]\s*by\s+(.*)', re.IGNORECASE)
# Trailing poster-session weekday marker (2016 appends Tuesday/Thursday/etc.).
_TRAILING_DAY_RE = re.compile(
    r'\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*$',
    re.IGNORECASE)


def parse_qcrypt_2016(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2016: ``<p><strong>"Title" by Authors <Day></strong></p>`` where
    the trailing weekday names the poster session."""
    ec = soup.find(class_='entry-content') or soup
    posters: List[Dict[str, Any]] = []
    for p in ec.find_all(['p', 'li']):
        text = p.get_text(' ', strip=True)
        m = _QUOTED_TITLE_RE.search(text)
        if not m:
            continue
        title = m.group(1)
        rest = m.group(2)
        session = None
        day = _TRAILING_DAY_RE.search(rest)
        if day:
            session = f"Poster Session ({day.group(1).capitalize()})"
            rest = _TRAILING_DAY_RE.sub('', rest)
        poster = _poster(title, rest, session_name=session)
        if poster:
            posters.append(poster)
    return posters


def parse_qcrypt_2018(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2018: ``<li><em>Authors. Title</em></li>`` — the author list ends
    with a period, then the title. Split on the sentence period, protecting
    single-initial ``X.`` inside names."""
    ec = soup.find(class_='entry-content') or soup
    posters: List[Dict[str, Any]] = []
    for li in ec.find_all('li'):
        text = _collapse(li.get_text(' ', strip=True))
        if not text:
            continue
        authors, title = _split_authors_dot_title(text)
        if not title:
            continue
        poster = _poster(title, authors)
        if poster:
            posters.append(poster)
    return posters


def parse_qcrypt_2012(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2012: the ``<h3 id="posters">`` heading in the program page is
    followed by a ``<ul>`` whose items are
    ``<li><span class="talk-title">Title</span><br><span class="talk-authors">Authors</span></li>``.
    Scope to that one ``<ul>`` (``talk-title`` is reused by the schedule above)."""
    heading = soup.find(id='posters')
    ul = heading.find_next('ul') if heading else None
    posters: List[Dict[str, Any]] = []
    if not ul:
        return posters
    for li in ul.find_all('li', recursive=False):
        title_span = li.find('span', class_='talk-title')
        if not title_span:
            continue
        authors_span = li.find('span', class_='talk-authors')
        authors = authors_span.get_text(' ', strip=True) if authors_span else ''
        p = _poster(title_span.get_text(' ', strip=True), authors)
        if p:
            posters.append(p)
    return posters


def parse_qcrypt_2015(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2015 "Selected Posters" list (Scientific Program page): each poster
    is ``<p>N. <em><strong>Title</strong></em><br>Authors<img>…</p>``. Title is the
    emphasised text; authors are the text node(s) after it, up to the trailing
    icon images."""
    posters: List[Dict[str, Any]] = []
    for p in soup.find_all('p'):
        text = _collapse(p.get_text(' ', strip=True))
        if not re.match(r'^\d+\.', text):
            continue
        em = p.find(['em', 'strong'])
        if not em:
            continue
        title = _collapse(em.get_text(' ', strip=True))
        if not title:
            continue
        # The emphasised title may be <em><strong>…</strong></em>; walk siblings of
        # the outermost emphasis element to collect the trailing author text.
        top = em
        while top.parent and top.parent.name in ('em', 'strong') and top.parent is not p:
            top = top.parent
        author_parts: List[str] = []
        for node in top.next_siblings:
            name = getattr(node, 'name', None)
            if name in ('img', 'a'):
                break
            if name == 'br':
                continue
            if isinstance(node, NavigableString):
                author_parts.append(str(node))
            elif getattr(node, 'get_text', None):
                author_parts.append(node.get_text(' ', strip=True))
        poster = _poster(title, _collapse(' '.join(author_parts)))
        if poster:
            posters.append(poster)
    return posters


def parse_qcrypt_2019(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QCrypt 2019 per-session page: a table with columns
    ``Poster Number | Author | Title``. Author and title cells carry a trailing
    period, stripped here. Session name comes from the page title/heading."""
    session = None
    heading = soup.find(['h1', 'h2'])
    if heading:
        session = _collapse(heading.get_text(' ', strip=True)) or None
    table = _largest_table(soup)
    posters: List[Dict[str, Any]] = []
    if not table:
        return posters
    rows = table.find_all('tr')
    header = [c.get_text(' ', strip=True).lower() for c in rows[0].find_all(['td', 'th'])]
    try:
        ai = header.index('author')
        ti = header.index('title')
    except ValueError:
        ai, ti = 1, 2
    for tr in rows[1:]:
        cells = tr.find_all(['td', 'th'])
        if len(cells) <= max(ai, ti):
            continue
        authors = re.sub(r'\.\s*$', '', cells[ai].get_text(' ', strip=True))
        title = re.sub(r'\.\s*$', '', cells[ti].get_text(' ', strip=True))
        p = _poster(title, authors, session_name=session)
        if p:
            posters.append(p)
    return posters


def _split_authors_dot_title(text: str) -> Tuple[str, str]:
    """Split "Authors. Title" on the period ending the author list.

    Skips a period that follows a single-capital initial (``R.``), so names like
    "Alexander R. Dixon" are not mistaken for the boundary.
    """
    m = re.search(r'(?<![A-Z])\.\s+', text)
    if not m:
        return '', ''
    return text[:m.start()], text[m.end():]


def _clean_authors_prefix(s: str) -> str:
    """Strip a leading list number / bullet and trailing punctuation from an
    author run captured as free text (e.g. "12. Alice and Bob." -> "Alice and Bob")."""
    s = _collapse(s)
    s = re.sub(r'^\s*\d+\s*[.)]\s*', '', s)   # "12. " / "12) "
    s = re.sub(r'^[-–—•]\s*', '', s)          # bullet / dash
    s = re.sub(r'[.,;:]\s*$', '', s).strip()  # trailing separator
    return s


def _emphasis_title(container) -> Optional[Tag]:
    """First <em>/<i> descendant of ``container`` (titles are emphasised)."""
    return container.find(['em', 'i'])


def _poster_from_emphasis(container, session_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Build a poster from a container of the form "Authors <em>Title</em>".

    ``authors`` is whatever text precedes the emphasised title. Returns None if
    there is no emphasised title.
    """
    tag = _emphasis_title(container)
    if not tag:
        return None
    title = _collapse(tag.get_text(' ', strip=True))
    full = _collapse(container.get_text(' ', strip=True))
    authors = full.split(title, 1)[0] if title and title in full else ''
    return _poster(title, _clean_authors_prefix(authors), session_name=session_name)


# ---------------------------------------------------------------------------
# Family C — QIP accepted-poster pages (per-year structure)
# ---------------------------------------------------------------------------
def parse_qip_2006(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2006: plain-text pairs of "Title" then "by Authors (Affiliation)"."""
    lines = [l for l in soup.get_text('\n', strip=True).splitlines() if l.strip()]
    posters: List[Dict[str, Any]] = []
    for i in range(len(lines) - 1):
        nxt = lines[i + 1]
        if nxt.lower().startswith('by '):
            p = _poster(lines[i], nxt[3:])
            if p:
                posters.append(p)
    return posters


def parse_qip_2009(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2009: ``<li>Authors. <em>Title</em></li>`` (authors may be <a> links)."""
    posters: List[Dict[str, Any]] = []
    for li in soup.find_all('li'):
        if not _emphasis_title(li):
            continue
        p = _poster_from_emphasis(li)
        if p:
            posters.append(p)
    return posters


_SESSION_HEADER_RE = re.compile(r'session\s+\d', re.IGNORECASE)


def parse_qip_2010(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2010: poster tables whose data cells are "Authors <em>Title</em>";
    header rows ("Session 1: Monday …") name the session."""
    posters: List[Dict[str, Any]] = []
    session = None
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 20:
            continue
        for tr in rows:
            cells = tr.find_all(['td', 'th'])
            row_text = _collapse(tr.get_text(' ', strip=True))
            if _emphasis_title(tr):
                p = _poster_from_emphasis(cells[-1] if cells else tr, session_name=session)
                if p:
                    posters.append(p)
            elif _SESSION_HEADER_RE.search(row_text):
                session = row_text
    return posters


def parse_qip_span_poster(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2011/2012: ``<div class="poster"><span class="authors">Authors:</span>
    <span class="title">Title</span></div>``, with an optional
    ``<li>Authors. <i>Title</i></li>`` fallback (2012)."""
    posters: List[Dict[str, Any]] = []
    seen_span = False
    for div in soup.find_all('div', class_='poster'):
        title_span = div.find('span', class_='title')
        authors_span = div.find('span', class_='authors')
        if not title_span:
            continue
        seen_span = True
        authors = authors_span.get_text(' ', strip=True) if authors_span else ''
        authors = re.sub(r'[.:;,]\s*$', '', authors)  # trailing "…:" / "…." only
        p = _poster(title_span.get_text(' ', strip=True), authors)
        if p:
            posters.append(p)
    # 2012 also has plain "- Authors. <i>Title</i>" list items outside div.poster.
    for li in soup.find_all('li'):
        if li.find('div', class_='poster'):
            continue
        if _emphasis_title(li):
            p = _poster_from_emphasis(li)
            if p:
                posters.append(p)
    return posters


def parse_qip_2015(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2015: a ``<br>``-separated flow of "N. Authors. <em>Title</em>
    (EasyChair …)". Titles are the only <em> tags."""
    posters: List[Dict[str, Any]] = []
    for em in soup.find_all('em'):
        title = _collapse(em.get_text(' ', strip=True))
        if not title:
            continue
        prev = em.previous_sibling
        authors = str(prev) if isinstance(prev, NavigableString) else ''
        authors = _clean_authors_prefix(authors)
        if not authors:
            continue
        p = _poster(title, authors)
        if p:
            posters.append(p)
    return posters


def parse_qip_2016(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2016: the author+title is the paper-link ``<a>`` — as
    ``<li><p><a>Authors. Title</a></p><p>Abstract</p></li>`` for most entries, or
    ``<li><a>Authors. Title</a><br><p>Abstract</p></li>`` for a few. Anchoring on
    the ``<a>`` (not "the first ``<p>``", which is the abstract in the second
    shape) reads both correctly; the abstract is the ``<p>`` that does not carry
    the anchor. Entries with no anchor fall back to the first ``<p>`` / li text.
    The author list is delimited from the title by the sentence period."""
    posters: List[Dict[str, Any]] = []
    for li in soup.find_all('li'):
        anchor = li.find('a')
        paras = li.find_all('p')
        abstract = None
        if anchor:
            head = _collapse(anchor.get_text(' ', strip=True))
            for p in paras:
                if anchor not in p.descendants:
                    abstract = _clean_abstract(p.get_text(' ', strip=True))
                    break
        elif paras:
            head = _collapse(paras[0].get_text(' ', strip=True))
            if len(paras) > 1:
                abstract = _clean_abstract(paras[1].get_text(' ', strip=True))
        else:
            head = _collapse(li.get_text(' ', strip=True))
        if not head:
            continue
        authors, title = _split_authors_dot_title(head)
        if not title:
            continue
        poster = _poster(title, authors, abstract=abstract)
        if poster:
            posters.append(poster)
    return posters


# QIP 2026 poster sessions are on fixed dates; map the session number (1/2) to
# the date rather than parse the block's date line (which has a typo, "Jannuary").
_QIP_2026_SESSION_DATES = {1: '2026-01-26', 2: '2026-01-27'}


def _name_key(name: str) -> str:
    """A loose identity key for de-duping one poster's author list: the lowercased
    first and last alphanumeric tokens (middle names/initials ignored), so
    "Sean R. Muleady" and "Sean Muleady" collapse to the same person."""
    toks = re.findall(r'\w+', name.lower())
    if not toks:
        return ''
    return f"{toks[0]}|{toks[-1]}" if len(toks) > 1 else toks[0]


def parse_qip_2026(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2026: two ``<h2>Poster Session N</h2>`` blocks, each a single ``<ol>``
    of ``<li><strong>Title</strong> Author, <u>Presenter</u>, Author…</li>``.

    Unlike the other poster pages, this one marks the presenter(s) with ``<u>`` —
    so this parser (alone) emits ``speakers``. The author cell is the ``<li>`` text
    after the title; a few entries repeat the presenter's name verbatim at another
    position (a source artifact), so exact-duplicate names are collapsed. Empty
    ``<li>`` placeholders are skipped. Session number → ``scheduled_date`` via
    ``_QIP_2026_SESSION_DATES``."""
    posters: List[Dict[str, Any]] = []
    for h2 in soup.find_all('h2'):
        session_name = _collapse(h2.get_text(' ', strip=True))
        if 'Poster Session' not in session_name:
            continue
        block = h2.find_parent('div', class_='genericText')
        if block is None:
            continue
        m = re.search(r'(\d+)', session_name)
        scheduled_date = _QIP_2026_SESSION_DATES.get(int(m.group(1))) if m else None
        for li in block.find_all('li'):
            strong = li.find('strong')
            if strong is None:
                continue
            title = _collapse(strong.get_text(' ', strip=True))
            if not title:
                continue
            # Author cell = the li's text with the leading <strong> title removed.
            authors_html = re.sub(r'<strong>.*?</strong>', '',
                                  li.decode_contents(), count=1, flags=re.S)
            authors_cell = BeautifulSoup(authors_html, 'html.parser').get_text(' ', strip=True)
            poster = _poster(title, authors_cell, session_name=session_name)
            if not poster:
                continue
            # Collapse the presenter-listed-twice artifact, keeping the first
            # occurrence's affiliation. The repeat is sometimes a name *variant*
            # ("Sean R. Muleady" then "Sean Muleady"), which the importer's fuzzy
            # author-matching would otherwise fold into one author and then reject
            # as a duplicate authorship. Key on (first, last) name token so both
            # exact repeats and initial-only variants collapse; two genuinely
            # distinct co-authors sharing first+last on one poster is implausible.
            seen: set = set()
            names: List[str] = []
            affs: List[str] = []
            for name, aff in zip(poster['authors'], poster['affiliations']):
                if name in seen or _name_key(name) in seen:
                    continue
                seen.add(name)
                seen.add(_name_key(name))
                names.append(name)
                affs.append(aff)
            poster['authors'], poster['affiliations'] = names, affs
            # Presenter(s): the <u>-wrapped names, de-duplicated in order, cleaned
            # the same way as authors so import-time normalisation aligns.
            speakers: List[str] = []
            for u in li.find_all('u'):
                sp = clean_display_name(_collapse(u.get_text(' ', strip=True)))
                if sp and sp not in speakers:
                    speakers.append(sp)
            poster['speakers'] = speakers
            poster['scheduled_date'] = scheduled_date
            posters.append(poster)
    return posters


def parse_qip_2013(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2013 poster schedule: a flow of
    ``<p><strong>N. Authors</strong><br>Title</p>`` grouped under
    ``<p><strong>SESSION 1</strong></p>`` / ``SESSION 2`` headers. Authors are the
    strong text after the leading "N."; the title is the ``<p>`` text after the
    ``<br>`` (i.e. the strong's following siblings). Numbering has gaps (withdrawn
    posters); those numbers are simply absent — not dropped here."""
    posters: List[Dict[str, Any]] = []
    session: Optional[str] = None
    for p in soup.find_all('p'):
        text = _collapse(p.get_text(' ', strip=True))
        if re.match(r'^SESSION\s+\d+\s*$', text, re.IGNORECASE):
            session = text
            continue
        strong = p.find('strong')
        if not strong:
            continue
        m = re.match(r'^\s*\d+\.\s*(.+)$', _collapse(strong.get_text(' ', strip=True)))
        if not m:
            continue
        authors = m.group(1)
        title_parts: List[str] = []
        for node in strong.next_siblings:
            if isinstance(node, NavigableString):
                title_parts.append(str(node))
            elif getattr(node, 'get_text', None) and node.name != 'br':
                title_parts.append(node.get_text(' ', strip=True))
        title = _collapse(' '.join(title_parts))
        poster = _poster(title, authors, session_name=session)
        if poster:
            posters.append(poster)
    return posters


def parse_qip_2014(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2014 per-session page: each poster is
    ``<div class="paper"><span class="authors">Authors. </span><span class="title">Title</span></div>``.
    The trailing period on the author run is stripped. Session name from the
    "QIP 2014 <Day> Poster Session" heading."""
    session = None
    for h in soup.find_all(['h1', 'h2', 'h3']):
        t = _collapse(h.get_text(' ', strip=True))
        if 'Poster Session' in t:
            session = t
            break
    posters: List[Dict[str, Any]] = []
    for div in soup.find_all('div', class_='paper'):
        title_span = div.find('span', class_='title')
        if not title_span:
            continue
        authors_span = div.find('span', class_='authors')
        authors = authors_span.get_text(' ', strip=True) if authors_span else ''
        authors = re.sub(r'\.\s*$', '', authors)
        p = _poster(title_span.get_text(' ', strip=True), authors, session_name=session)
        if p:
            posters.append(p)
    return posters


# QIP 2024 poster-session headings -> the presentation date (both in Jan 2024).
_QIP_2024_DATE_RE = re.compile(r'Jan\w*\.?\s+(\d{1,2})', re.IGNORECASE)


def parse_qip_2024(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """QIP 2024 "Accepted Posters" page: three ``No. | Title | Authors`` tables,
    each preceded by a heading. Parse only the two "Poster Presentation Session"
    tables (Mon/Tue) and **skip the "Not Presenting" table** (accepted-but-absent).
    The preceding heading gives the session name and date."""
    posters: List[Dict[str, Any]] = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        header = [c.get_text(' ', strip=True).lower() for c in rows[0].find_all(['td', 'th'])]
        if 'title' not in header or 'authors' not in header:
            continue
        # Nearest preceding heading naming this table's group.
        label = ''
        for prev in table.find_all_previous(['h1', 'h2', 'h3', 'h4', 'p', 'strong', 'b']):
            tt = _collapse(prev.get_text(' ', strip=True))
            low = tt.lower()
            if 'not presenting' in low or 'poster presentation session' in low:
                label = tt
                break
        if 'poster presentation session' not in label.lower():
            continue  # skips the "Not Presenting" table (and any stray tables)
        dm = _QIP_2024_DATE_RE.search(label)
        scheduled_date = f"2024-01-{int(dm.group(1)):02d}" if dm else None
        ti = header.index('title')
        ai = header.index('authors')
        for tr in rows[1:]:
            cells = tr.find_all(['td', 'th'])
            if len(cells) <= max(ti, ai):
                continue
            p = _poster(cells[ti].get_text(' ', strip=True),
                        cells[ai].get_text(' ', strip=True), session_name=label)
            if p:
                if scheduled_date:
                    p['scheduled_date'] = scheduled_date
                posters.append(p)
    return posters


# ---------------------------------------------------------------------------
# Families D/E — TQC accepted-poster pages + the teachpress BibTeX export
# ---------------------------------------------------------------------------
def parse_tqc_2019(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """TQC 2019: a numbered text flow of "N" / "Authors:" / "Title." lines."""
    ec = soup.find(class_='entry-content') or soup
    lines = [_collapse(l) for l in ec.get_text('\n', strip=True).splitlines() if l.strip()]
    posters: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.endswith(':') and i + 1 < len(lines):
            authors = line[:-1]
            title = re.sub(r'\.\s*$', '', lines[i + 1])
            p = _poster(title, authors)
            if p:
                posters.append(p)
            i += 2
        else:
            i += 1
    return posters


def parse_tqc_2020(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """TQC 2020: one poster per ``<p>`` as "Authors. Title"."""
    ec = soup.find(class_='entry-content') or soup
    posters: List[Dict[str, Any]] = []
    for p_tag in ec.find_all('p'):
        text = _collapse(p_tag.get_text(' ', strip=True))
        authors, title = _split_authors_dot_title(text)
        if not title:
            continue
        poster = _poster(title, authors)
        if poster:
            posters.append(poster)
    return posters


def parse_tqc_2021(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """TQC 2021: a table with columns "Title | Authors | # | Table String"."""
    table = _largest_table(soup)
    posters: List[Dict[str, Any]] = []
    if not table:
        return posters
    rows = table.find_all('tr')
    header = [c.get_text(' ', strip=True).lower() for c in rows[0].find_all(['td', 'th'])]
    try:
        ti = header.index('title')
        ai = header.index('authors')
    except ValueError:
        ti, ai = 0, 1
    for tr in rows[1:]:
        cells = tr.find_all(['td', 'th'])
        if len(cells) <= max(ti, ai):
            continue
        p = _poster(cells[ti].get_text(' ', strip=True),
                    cells[ai].get_text(' ', strip=True))
        if p:
            posters.append(p)
    return posters


def parse_tqc_2025(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """TQC 2025: ``<li><strong>Title</strong><ul><li><em>Authors …</em></li></ul></li>``
    where authors are comma-separated with parenthetical affiliations."""
    posters: List[Dict[str, Any]] = []
    for li in soup.find_all('li'):
        strong = li.find('strong')
        if not strong:
            continue
        title = strong.get_text(' ', strip=True)
        em = li.find('em')
        authors_cell = em.get_text(' ', strip=True) if em else ''
        p = _poster(title, authors_cell)
        if p:
            posters.append(p)
    return posters


# BibTeX @Poster{...} block and its title/author/year fields (teachpress export).
_BIB_ENTRY_RE = re.compile(r'@Poster\s*\{(.*?)\n\}', re.IGNORECASE | re.DOTALL)
_BIB_FIELD_RE = lambda f: re.compile(
    r'\b' + f + r'\s*=\s*\{(.*?)\}\s*,?\s*$', re.IGNORECASE | re.MULTILINE)
_BIB_TITLE_RE = _BIB_FIELD_RE('title')
_BIB_AUTHOR_RE = _BIB_FIELD_RE('author')
_BIB_YEAR_RE = _BIB_FIELD_RE('year')
_BIB_KEYWORDS_RE = _BIB_FIELD_RE('keywords')


def _bib_authors(raw: str) -> List[str]:
    """BibTeX ``author`` field -> ordered display names. Handles both
    "First Last and A B" and "Last, First and ..." forms."""
    names = []
    for part in re.split(r'\s+and\s+', raw):
        part = _collapse(part.replace('{', '').replace('}', ''))
        if not part:
            continue
        if ',' in part:
            last, first = [x.strip() for x in part.split(',', 1)]
            part = f"{first} {last}".strip()
        names.append(part)
    return names


_PDF_ROW_RE = re.compile(r'^\s*(\d+)?\s{1,}(.*?)\s{2,}(.*\S)\s*$')


def parse_qip_pdf_2col(text: str, year: int = 0) -> List[Dict[str, Any]]:
    """Parse a ``pdftotext -layout`` dump of a two-column poster list where each
    poster is "N  Authors    Title" (QIP 2019). A leading number starts a new
    poster; unnumbered lines continue the previous poster's wrapped author/title
    columns. ``year`` is unused (kept for the text-family call signature)."""
    posters: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, str]] = None
    for line in text.splitlines():
        if not line.strip() or 'list of presented posters' in line.lower():
            continue
        m = _PDF_ROW_RE.match(line)
        if m and (m.group(1) or m.group(2) or m.group(3)):
            num, authors, title = m.group(1), m.group(2).strip(), m.group(3).strip()
            if num:
                if cur:
                    posters.append(_poster(cur['title'], cur['authors']))
                cur = {'authors': authors, 'title': title}
            elif cur:
                if authors:
                    cur['authors'] += ' ' + authors
                if title:
                    cur['title'] += ' ' + title
        elif cur:
            cur['title'] += ' ' + line.strip()
    if cur:
        posters.append(_poster(cur['title'], cur['authors']))
    return [p for p in posters if p]


def _detect_split_col(lines: List[str]) -> int:
    """Find the char column where the right-hand data column starts in a
    ``pdftotext -layout`` two-column table. Looks at every ">=4-space gap
    followed by text at column >= 40" and takes the median start — robust to
    rows whose left cell is short (small leading gap) or whose right cell is
    empty (no gap at all)."""
    cols: List[int] = []
    for line in lines:
        for m in re.finditer(r'\S\s{4,}(\S)', line):
            c = m.end(1) - 1
            if c >= 40:
                cols.append(c)
    if not cols:
        return 60
    cols.sort()
    return cols[len(cols) // 2]


def _segments(line: str) -> List[Tuple[int, str]]:
    """Split a ``pdftotext -layout`` line into ``(start_col, text)`` cells at runs
    of >=2 spaces (the inter-column gap). Single spaces inside a cell are kept."""
    out: List[Tuple[int, str]] = []
    for m in re.finditer(r'\S.*?(?=\s{2,}|$)', line):
        t = m.group().strip()
        if t:
            out.append((m.start(), t))
    return out


def _bin_segments(segs: List[Tuple[int, str]], boundary: int) -> Tuple[str, str]:
    """Assign each cell to the left or right column. With exactly two cells the
    order decides (robust to column jitter); with one cell its start column vs
    ``boundary`` decides (wrapped continuation lines)."""
    if len(segs) >= 2:
        left = ' '.join(t for _, t in segs[:-1])
        right = segs[-1][1]
        return left, right
    if len(segs) == 1:
        col, t = segs[0]
        return ('', t) if col >= boundary else (t, '')
    return '', ''


def _parse_pdf_table(text: str, *, id_re, left_field: str, mode: str,
                     session_re=None, skip_re=None) -> List[Dict[str, Any]]:
    """Parse a two-data-column poster table from ``pdftotext -layout`` output.

    Each row has a poster ID (``id_re``, matched at line start) plus two wrapped
    text columns. Lines are split into cells at >=2-space gaps and binned into a
    left/right column (``_bin_segments``); ``left_field`` says which column is the
    title. ``mode`` is:

      * ``'top'`` — the ID sits on the first line of its block; wrapped
        continuation lines below belong to the current poster (QIP 2017/2021).
      * ``'centered'`` — the ID is vertically centred, so title/author fragments
        appear on lines above and below it; each non-ID line is assigned to the
        nearest ID line by line distance (QIP 2023).

    ``session_re`` matches a session-header line; ``skip_re`` drops boilerplate."""
    lines = text.splitlines()
    boundary = max(20, _detect_split_col(lines) - 10)
    records: List[Dict[str, Any]] = []

    def cells(line: str, m) -> Tuple[str, str]:
        # Blank out the ID token (preserving column positions) so a data cell
        # separated from the ID by a single space isn't merged into it.
        if m:
            line = ' ' * m.end() + line[m.end():]
        return _bin_segments(_segments(line), boundary)

    if mode == 'top':
        session = None
        cur: Optional[Dict[str, str]] = None
        for line in lines:
            if session_re is not None:
                ms = session_re.search(line)
                if ms and not id_re.match(line):
                    session = _collapse(ms.group(0))
                    continue
            if skip_re is not None and skip_re.search(line):
                continue
            m = id_re.match(line)
            left, right = cells(line, m)
            if m:
                cur = {'left': left, 'right': right, 'session': session}
                records.append(cur)
            elif cur is not None:
                cur['left'] += ' ' + left
                cur['right'] += ' ' + right
    else:  # centered
        # Start only once the first session header is seen, so the intro
        # paragraph (before it) is not swept into the first poster.
        start = 0
        if session_re is not None:
            for i, l in enumerate(lines):
                if session_re.search(l):
                    start = i
                    break
        id_idx = [i for i in range(start, len(lines)) if id_re.match(lines[i])]
        if not id_idx:
            return []
        session_at: List[Optional[str]] = [None] * len(lines)
        cur_s = None
        for i in range(start, len(lines)):
            if session_re is not None and session_re.search(lines[i]):
                cur_s = _collapse(session_re.search(lines[i]).group(0))
            session_at[i] = cur_s
        buckets = {i: {'left': '', 'right': '', 'session': session_at[i]} for i in id_idx}
        # Each ID line's own cells — used to break distance ties toward the ID
        # whose own line is empty (e.g. an ID printed on a line by itself, below
        # its title/author row) rather than always toward the earlier ID.
        own = {i: cells(lines[i], id_re.match(lines[i])) for i in id_idx}
        id_set = set(id_idx)

        def _full(i: int) -> bool:
            return bool(own[i][0].strip()) and bool(own[i][1].strip())

        def _target(i: int) -> int:
            best = min(id_idx, key=lambda k: abs(k - i))
            d = abs(best - i)
            tied = [k for k in id_idx if abs(k - i) == d]
            if len(tied) > 1:
                # Prefer a tied ID that still needs content over a complete one.
                hungry = [k for k in tied if not _full(k)]
                if hungry:
                    return min(hungry, key=lambda k: abs(k - i))
            return best

        for i in range(start, len(lines)):
            line = lines[i]
            if skip_re is not None and skip_re.search(line):
                continue
            if session_re is not None and session_re.search(line) and not id_re.match(line):
                continue
            m = id_re.match(line)
            left, right = cells(line, m)
            target = i if i in id_set else _target(i)
            buckets[target]['left'] += ' ' + left
            buckets[target]['right'] += ' ' + right
        records = [buckets[i] for i in id_idx]

    posters: List[Dict[str, Any]] = []
    for rec in records:
        title, authors = ((rec['left'], rec['right']) if left_field == 'title'
                          else (rec['right'], rec['left']))
        p = _poster(_collapse(title), _collapse(authors), session_name=rec['session'])
        if p:
            posters.append(p)
    return posters


_QIP_2017_DAY_RE = re.compile(r'\((Monday|Tuesday|Wednesday|Thursday|Friday)\)')
_QIP_2017_ID_RE = re.compile(r'^\s*(\d+)\s{2,}(?=\S)')


def parse_qip_2017_pdf(text: str, year: int = 0) -> List[Dict[str, Any]]:
    """QIP 2017 per-day poster PDF: ``Poster Number | Title | Authors`` with the
    number top-anchored and the title wrapping over several lines."""
    return _parse_pdf_table(
        text, id_re=_QIP_2017_ID_RE, left_field='title', mode='top',
        session_re=_QIP_2017_DAY_RE)


_QIP_2021_SESSION_RE = re.compile(
    r'(Monday|Tuesday|Wednesday|Thursday|Friday)\s*[–-]\s*Poster Session\s+\w')
_QIP_2021_ID_RE = re.compile(r'^([A-Z]\.\d+\.\d+)\s')
# Running page furniture that interleaves the poster rows: the "Room A.2" header
# at each page top, and the "POSTER SESSION A, MONDAY FEB 1ST … CET" footer.
_QIP_2021_SKIP_RE = re.compile(
    r'^\s*Room\s+[A-Z]\.\d|POSTER SESSION\s+[A-Z].*CET|^\s*\d+\s*$', re.IGNORECASE)


def parse_qip_2021_pdf(text: str, year: int = 0) -> List[Dict[str, Any]]:
    """QIP 2021 poster PDF: ``ID | Authors | Title`` (ID like "A.1.1"), grouped by
    "<Day> – Poster Session X". Top-anchored; authors and title both wrap. Room
    headers and the running session footer are skipped so they don't bleed into
    the preceding poster."""
    return _parse_pdf_table(
        text, id_re=_QIP_2021_ID_RE, left_field='authors', mode='top',
        session_re=_QIP_2021_SESSION_RE, skip_re=_QIP_2021_SKIP_RE)


_QIP_2023_SESSION_RE = re.compile(
    r'^(Monday|Tuesday|Wednesday|Thursday|Friday)\s+session', re.IGNORECASE)
_QIP_2023_ID_RE = re.compile(r'^\s{0,6}(\d+)(?:\s|$)')
# The per-session column-header row ("ID  Title  ...  Authors").
_QIP_2023_HEADER_RE = re.compile(r'\bID\b.{0,40}\bTitle\b.{0,120}\bAuthors?\b')


def parse_qip_2023_pdf(text: str, year: int = 0) -> List[Dict[str, Any]]:
    """QIP 2023 poster PDF: ``ID | Title | Authors`` with the ID vertically
    centred in each row (title fragments above and below the ID line), grouped by
    "<Day> session". A trailing "Not presenting" section (accepted-but-absent) is
    dropped, consistent with the QIP 2024 convention."""
    text = re.split(r'(?im)^\s*Not presenting\s*$', text)[0]
    return _parse_pdf_table(
        text, id_re=_QIP_2023_ID_RE, left_field='title', mode='centered',
        session_re=_QIP_2023_SESSION_RE, skip_re=_QIP_2023_HEADER_RE)


# Institution keywords used to find where the affiliation starts in a TQC 2022
# byline ("Name1, Name2, Affiliation" — affiliations may themselves hold commas).
# Stems (no trailing \b — they are prefixes, e.g. "Universit" in "University").
_INSTITUTION_RE = re.compile(
    r'\b(Universit|Institut|College|Center|Centre|Laborator|CNRS|Technolog|'
    r'Corporation|QuSoft|Atos|LIFO|Google|IBM|Microsoft|School|Department|Academ|'
    r'National|Max Planck|Inria|ETH|EPFL|Perimeter|Riken|Chalmers|'
    r'Bilkent|Brunel|Purdue|KAIST|UvA|Lab)', re.IGNORECASE)
_TQC_2022_NUM_RE = re.compile(r'^(\d+)\.\s+(.*)')
_TQC_2022_SKIP_RE = re.compile(
    r'POSTER SESSION PROGRAM|Siebel Center|Fourth St|Champaign|^\s*\d+\s*$|'
    r'Conference on the Theory', re.IGNORECASE)


def _split_tqc_2022_byline(byline: str) -> Tuple[List[str], str]:
    """Split "Presenter(s), Affiliation" — authors are the comma-parts before the
    first part that names an institution; the rest (which may hold commas) is the
    affiliation. Falls back to first-part-is-author when no institution matches."""
    parts = [p.strip() for p in byline.split(',') if p.strip()]
    if not parts:
        return [], ''
    idx = next((i for i, p in enumerate(parts) if _INSTITUTION_RE.search(p)), None)
    if idx is None or idx == 0:
        idx = 1  # no institution found (or first part is one) -> first part = author
    names, _aff = split_authors('; '.join(parts[:idx]))
    return names, _collapse(', '.join(parts[idx:]))


def _dequote(s: str) -> str:
    return s.strip().strip('“”"\'').strip()


def parse_tqc_2022_pdf(text: str, year: int = 0) -> List[Dict[str, Any]]:
    """TQC 2022 "POSTER SESSION PROGRAM": entries ``N. Presenter(s), Affiliation``
    each followed by a quoted title line, grouped under category headers
    (Algorithms, Cryptography, …) that name the poster session. Spans several
    pages with "…CONTINUED" banners; ends at "INVITED SPEAKER ABSTRACTS"."""
    lines = text.splitlines()
    # Anchor on the section banner (a standalone centred line), not the dotted
    # table-of-contents entry ("Poster Session Program……18").
    banner = re.compile(r'^\s*POSTER SESSION PROGRAM\s*$')
    start = next((i for i, l in enumerate(lines) if banner.match(l)), None)
    if start is None:
        return []
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r'^\s*INVITED SPEAKER ABSTRACTS\s*$', lines[i])), len(lines))

    posters: List[Dict[str, Any]] = []
    session: Optional[str] = None
    cur: Optional[Dict[str, Any]] = None
    expecting_title = False
    for line in lines[start + 1:end]:
        s = _collapse(line)
        if not s or _TQC_2022_SKIP_RE.search(s):
            continue
        m = _TQC_2022_NUM_RE.match(s)
        if m:
            names, aff = _split_tqc_2022_byline(m.group(2))
            cur = {
                'title': '', 'authors': names,
                'affiliations': [aff] * len(names) if aff else ['' for _ in names],
                'abstract': None, 'session_name': session,
            }
            posters.append(cur)
            expecting_title = True
        elif expecting_title and cur is not None:
            # Titles are quoted and may wrap over two lines; accumulate until the
            # closing curly/straight quote so a wrapped tail isn't read as a header.
            cur['title'] = _collapse((cur['title'] + ' ' + s).strip())
            if '”' in s or s.rstrip().endswith('"'):
                cur['title'] = _dequote(cur['title'])
                expecting_title = False
        else:
            session = s  # a category header naming the session
    for p in posters:
        p['title'] = _dequote(p['title'])
    return [p for p in posters if p['title']]


def parse_tqc_bibtex(text: str, year: int) -> List[Dict[str, Any]]:
    """Parse the teachpress ``@Poster{...}`` export, keeping entries for ``year``.

    Titles/authors are clean and structured; ``keywords`` names the poster
    session. This is the complete source for TQC 2023/2024 (the mirrored web
    pages are JS-paginated and truncated)."""
    posters: List[Dict[str, Any]] = []
    for m in _BIB_ENTRY_RE.finditer(text):
        body = m.group(1)
        ym = _BIB_YEAR_RE.search(body)
        if not ym or ym.group(1).strip() != str(year):
            continue
        tm = _BIB_TITLE_RE.search(body)
        am = _BIB_AUTHOR_RE.search(body)
        if not tm:
            continue
        title = _collapse(tm.group(1).replace('{', '').replace('}', ''))
        authors = _bib_authors(am.group(1)) if am else []
        km = _BIB_KEYWORDS_RE.search(body)
        session = _collapse(km.group(1)) if km else None
        posters.append({
            'title': title,
            'authors': authors,
            'affiliations': ['' for _ in authors],
            'abstract': None,
            'session_name': session,
        })
    return posters
