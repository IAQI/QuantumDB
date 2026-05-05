"""QCrypt conference talk scraper.

Handles four schedule layouts that have appeared on qcrypt.iaqi.org:
- Hugo era (2020+): <article class="day"> / <div class="session"> / startt span
- TablePress era (2017-2019): <table class="tablepress"> with column-2..8
- 2013: <table class="schedule-table"> with <tr class="talk"|"food">
- WordPress "program" era (2012, 2014): <table class="program"> with row-class talk type
- ETH 2011: <table class="silvatable list"> with plain time cells

Years 2015 and 2016 use ad-hoc bgcolor tables / navigation pages and require
manual entry; the scraper logs a warning and returns an empty list for those.
"""
import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseTalkScraper

logger = logging.getLogger(__name__)


# Conference start dates (Monday of conference week) used to compute
# scheduled_date from the day-of-week label in pre-Hugo schedules.
QCRYPT_START_DATES: Dict[int, date] = {
    2011: date(2011, 9, 12),
    2012: date(2012, 9, 10),
    2013: date(2013, 8, 5),
    2014: date(2014, 9, 1),
    2015: date(2015, 9, 28),
    2016: date(2016, 9, 12),
    2017: date(2017, 9, 18),
    2018: date(2018, 8, 27),
    2019: date(2019, 8, 26),
    2020: date(2020, 8, 10),
    2021: date(2021, 8, 23),
    2022: date(2022, 8, 29),
    2023: date(2023, 8, 14),
    2024: date(2024, 9, 2),
}

DAY_NAMES = ['monday', 'tuesday', 'wednesday', 'thursday',
             'friday', 'saturday', 'sunday']

NON_TALK_KEYWORDS = (
    'coffee', 'lunch', 'break', 'registration', 'reception',
    'welcome cocktail', 'welcome ap', 'welcome reception',
    'opening', 'closing', 'rump session', 'industry session',
    'banquet', 'dinner', 'excursion', 'public lecture',
    'panel', 'updates & announcements', 'updates and announcements',
    'check-in', 'group photo', 'awards ceremony', 'best paper',
    'q&a', 'networking', 'space-quest',
)


_TRAILING_LINK_TEXT_RE = re.compile(
    r'\s*(\[\s*(?:video|slides|abstract|extended\s*abstract|pdf|paper)\s*\])+\s*$',
    re.IGNORECASE,
)


def _strip_link_suffixes(title: str) -> str:
    if not title:
        return title
    prev = None
    cur = title.strip()
    while cur != prev:
        prev = cur
        cur = _TRAILING_LINK_TEXT_RE.sub('', cur).strip()
    return cur


def _is_non_talk(text: str) -> bool:
    if not text:
        return True
    lower = text.strip().lower()
    if not lower:
        return True
    return any(kw in lower for kw in NON_TALK_KEYWORDS)


def _day_index(day_name: str) -> Optional[int]:
    if not day_name:
        return None
    lower = day_name.strip().lower()
    for idx, name in enumerate(DAY_NAMES):
        if name in lower:
            return idx
    return None


def _normalize_time(text: str) -> Optional[str]:
    """Extract HH:MM from a free-text cell (handles '9:00', '09:00–10:30')."""
    if not text:
        return None
    match = re.search(r'(\d{1,2})[:.](\d{2})', text)
    if not match:
        return None
    h, m = int(match.group(1)), int(match.group(2))
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return None


def _strip_arxiv_link_text(text: str) -> List[str]:
    """Pull arXiv IDs out of a chunk of text."""
    return BaseTalkScraper.extract_arxiv_ids(text)


class QCryptTalkScraper(BaseTalkScraper):
    """Scraper for QCrypt schedule pages, all eras."""

    def get_url(self) -> str:
        """Return the canonical archive URL for the year's schedule page."""
        if self.year < 2011:
            raise NotImplementedError(f"QCrypt {self.year} not supported")
        if self.year >= 2020:
            return f"https://qcrypt.iaqi.org/{self.year}/schedule/index.html"
        if self.year == 2016:
            # 2016 scientific-program/index.html is just a nav stub;
            # the actual schedule lives under /schedule/.
            return f"https://qcrypt.iaqi.org/{self.year}/schedule/index.html"
        if self.year >= 2015:
            return f"https://qcrypt.iaqi.org/{self.year}/scientific-program/index.html"
        if self.year >= 2013:
            return f"https://qcrypt.iaqi.org/{self.year}/program/index.html"
        if self.year == 2012:
            return f"https://qcrypt.iaqi.org/{self.year}/program.html"
        return f"https://qcrypt.iaqi.org/{self.year}/programme/index.html"

    # ------------------------------------------------------------------
    # Top-level dispatch
    # ------------------------------------------------------------------
    def parse_talk_data(self) -> List[Dict[str, Any]]:
        if self.soup.find('article', class_='day'):
            return self._parse_hugo()
        if self.soup.find('table', class_='tablepress'):
            return self._parse_tablepress()
        if self.soup.find('table', class_='schedule-table'):
            return self._parse_schedule_table_2013()
        if self.soup.find('table', class_='program'):
            return self._parse_wp_program()
        if self.soup.find('table', class_='silvatable'):
            return self._parse_eth_2011()
        # Years with no shared CSS hooks: dispatch by year.
        if self.year == 2015:
            return self._parse_2015_grid()
        if self.year == 2016:
            return self._parse_2016_matrix()
        logger.warning(
            "QCrypt %s: schedule HTML format not recognized — manual entry "
            "needed (no article.day, table.program, table.tablepress, "
            "table.schedule-table, or table.silvatable found).",
            self.year,
        )
        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _date_for_day_name(self, heading_text: str) -> Optional[str]:
        idx = _day_index(heading_text)
        if idx is None:
            return None
        start = QCRYPT_START_DATES.get(self.year)
        if not start:
            return None
        return (start + timedelta(days=idx)).isoformat()

    def _empty_talk(self) -> Dict[str, Any]:
        return {
            'paper_type': 'regular',
            'title': None,
            'speakers': None,
            'authors': None,
            'affiliations': None,
            'abstract': None,
            'arxiv_ids': None,
            'presentation_url': None,
            'video_url': None,
            'youtube_id': None,
            'session_name': None,
            'award': None,
            'notes': None,
            'scheduled_date': None,
            'scheduled_time': None,
            'duration_minutes': None,
        }

    @staticmethod
    def _split_authors_speaker(authors_html_node) -> Tuple[List[str], List[str]]:
        """Given a node containing a flat author list with optional <span class='speaker'>
        / <u> markup designating the presenter, return (authors, speakers).
        """
        if authors_html_node is None:
            return [], []
        text = authors_html_node.get_text(' ', strip=True)
        text = re.sub(r'\s+', ' ', text).strip().rstrip('.').rstrip(',')
        if not text:
            return [], []
        # Try to extract speakers from explicit markers
        speakers: List[str] = []
        for marker in authors_html_node.find_all(['span', 'u']):
            cls = marker.get('class') or []
            if marker.name == 'u' or 'speaker' in cls:
                name = marker.get_text(' ', strip=True)
                if name:
                    speakers.append(' '.join(name.split()))
        # Split full author list on " and " / commas
        cleaned = re.sub(r'\s+and\s+', ',', text)
        names = [n.strip() for n in cleaned.split(',') if n.strip()]
        # Filter trailing affiliation noise (single-word stray tokens)
        names = [n for n in names if len(n) >= 2]
        # Dedupe while keeping order
        seen = set()
        authors = []
        for n in names:
            key = n.lower()
            if key not in seen:
                seen.add(key)
                authors.append(n)
        if not speakers and authors:
            # No explicit marker — assume single-author talk
            if len(authors) == 1:
                speakers = list(authors)
        return authors, speakers

    @staticmethod
    def _extract_links(td) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (presentation_url, video_url, youtube_id) from anchors in td."""
        if td is None:
            return None, None, None
        slides_url = None
        video_url = None
        for a in td.find_all('a'):
            href = a.get('href', '') or ''
            text = (a.get_text(' ', strip=True) or '').lower()
            cls = ' '.join(a.get('class') or [])
            if not href:
                continue
            is_video = (
                'youtube.com' in href or 'youtu.be' in href
                or 'multimedia.ethz.ch' in href
                or 'video' in text or 'watch' in text or 'video' in cls
            )
            is_slides = (
                href.lower().endswith('.pdf')
                or 'slides' in text or 'slides' in cls
            )
            if is_video and not video_url:
                video_url = href
            elif is_slides and not slides_url:
                slides_url = href
        youtube_id = BaseTalkScraper.extract_youtube_id(video_url) if video_url else None
        return slides_url, video_url, youtube_id

    # ------------------------------------------------------------------
    # Hugo era (2020+)
    # ------------------------------------------------------------------
    def _parse_hugo(self) -> List[Dict[str, Any]]:
        talks: List[Dict[str, Any]] = []
        for article in self.soup.find_all('article', class_='day'):
            article_id = article.get('id', '')  # e.g. 'day_2024-09-02'
            m = re.search(r'(\d{4}-\d{2}-\d{2})', article_id)
            sched_date = m.group(1) if m else None
            for session in article.find_all('div', class_='session'):
                talk_dicts = self._parse_hugo_session(session, sched_date)
                talks.extend(talk_dicts)
        return talks

    def _parse_hugo_session(self, session, sched_date: Optional[str]) -> List[Dict[str, Any]]:
        # Skip explicit non-talk session tags
        cls = session.get('class') or []
        tag_classes = [c for c in cls if c.startswith('tag-')]
        skip_tags = {'tag-other', 'tag-break', 'tag-food', 'tag-social'}
        is_poster_session = 'tag-poster' in tag_classes

        # Time
        startt = session.find('span', class_='startt')
        sched_time = None
        if startt:
            hh = startt.find('span', class_='hh')
            mm = startt.find('span', class_='mm')
            if hh and mm:
                try:
                    h, m = int(hh.get_text(strip=True)), int(mm.get_text(strip=True))
                    sched_time = f"{h:02d}:{m:02d}"
                except ValueError:
                    pass

        # Title
        h4 = session.find('h4')
        if not h4:
            return []
        # h4 may contain a nested <span class=language></span>; strip it
        for span in h4.find_all('span'):
            span.extract()
        raw_title = h4.get_text(' ', strip=True)
        if not raw_title:
            return []
        if any(t in skip_tags for t in tag_classes):
            return []

        # Session URL — store in notes for traceability
        anchor = session.find('a')
        session_url = anchor.get('href') if anchor else None

        # Speakers (invited / tutorial format)
        speakers_ul = session.find('ul', class_='speakers')
        speakers: List[str] = []
        if speakers_ul:
            for sp in speakers_ul.find_all('strong', class_='speaker-name'):
                name = sp.get_text(' ', strip=True)
                if name:
                    speakers.append(' '.join(name.split()))

        # Paper list (contributed talks)
        paper_list = session.find('ul', class_='paper-list')
        papers: List[Dict[str, Any]] = []
        if paper_list:
            for li in paper_list.find_all('li', class_='paper-short'):
                for paper_simple in li.find_all('div', class_='paper-simple'):
                    title_div = paper_simple.find('div', class_='paper-title')
                    authors_div = paper_simple.find('div', class_='paper-authors')
                    if not title_div:
                        continue
                    p_title = self.normalize_title(title_div.get_text(' ', strip=True))
                    authors_text = ''
                    if authors_div:
                        # paper-authors uses ';' or ',' / 'and' separators
                        authors_text = authors_div.get_text(' ', strip=True)
                    authors = []
                    if authors_text:
                        cleaned = re.sub(r'\s+and\s+', ';', authors_text)
                        authors = [a.strip() for a in re.split(r'[;,]', cleaned) if a.strip()]
                    papers.append({
                        'title': p_title,
                        'authors': authors,
                    })

        # Build talks
        if papers:
            # Contributed session — emit one talk per paper
            session_name = self.normalize_title(raw_title)
            results: List[Dict[str, Any]] = []
            for paper in papers:
                talk = self._empty_talk()
                talk['paper_type'] = 'regular'
                talk['title'] = paper['title']
                talk['authors'] = paper['authors'] or None
                # Last author conventionally presents in Hugo lists; we don't
                # know for sure, so leave speakers empty.
                talk['speakers'] = None
                talk['session_name'] = session_name
                talk['scheduled_date'] = sched_date
                talk['scheduled_time'] = sched_time
                if session_url:
                    talk['notes'] = f"Session URL: {session_url}"
                arxiv_ids = _strip_arxiv_link_text(
                    ' '.join((paper['authors'] or []) + [paper['title']])
                )
                if arxiv_ids:
                    talk['arxiv_ids'] = arxiv_ids
                results.append(talk)
            return results

        # Single talk (invited, tutorial, keynote, plenary, poster session header)
        title_clean = re.sub(
            r"^(Tutorial|Invited|Keynote|Plenary)(?:\s+Talk)?:\s*[\'\"]*\s*",
            '',
            raw_title,
            flags=re.IGNORECASE,
        ).strip().strip("'").strip('"').strip()
        title_clean = self.normalize_title(title_clean) or self.normalize_title(raw_title)
        if not title_clean or _is_non_talk(title_clean):
            return []

        if is_poster_session:
            paper_type = 'poster'
        else:
            paper_type = self.detect_paper_type(raw_title, '')

        talk = self._empty_talk()
        talk['paper_type'] = paper_type
        talk['title'] = title_clean
        talk['speakers'] = speakers or None
        talk['session_name'] = paper_type.capitalize() + ' Talk' if paper_type in ('invited', 'tutorial', 'keynote', 'plenary') else None
        talk['scheduled_date'] = sched_date
        talk['scheduled_time'] = sched_time
        if session_url:
            talk['notes'] = f"Session URL: {session_url}"
        return [talk]

    # ------------------------------------------------------------------
    # WordPress class="program" era (2012, 2014)
    # ------------------------------------------------------------------
    def _parse_wp_program(self) -> List[Dict[str, Any]]:
        talks: List[Dict[str, Any]] = []
        # Day headings appear as <p><strong>Monday (...)</strong>...</p> (2014)
        # or <h3 id="Monday">Monday (10th September)</h3> (2012). Iterate all
        # tables in document order and pair each with the most recent day
        # heading found earlier.
        current_date: Optional[str] = None
        for el in self.soup.find_all(True):
            text = el.get_text(' ', strip=True) if hasattr(el, 'get_text') else ''
            # Day heading detection
            if el.name in ('p', 'h2', 'h3', 'h4'):
                idx = _day_index(text)
                if idx is not None and len(text) < 200:
                    new_date = self._date_for_day_name(text)
                    if new_date:
                        current_date = new_date
                        continue
            if el.name == 'table' and 'program' in (el.get('class') or []):
                talks.extend(self._parse_wp_program_table(el, current_date))
        return talks

    def _parse_wp_program_table(self, table, sched_date: Optional[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for tr in table.find_all('tr'):
            row_cls = tr.get('class') or []
            time_td = tr.find('td', class_='time')
            time_str = _normalize_time(time_td.get_text(' ', strip=True)) if time_td else None
            content_tds = [td for td in tr.find_all('td') if 'time' not in (td.get('class') or [])]
            if not content_tds:
                continue
            content = content_tds[-1]
            title_span = content.find('span', class_='talk-title')
            if not title_span:
                continue
            title = _strip_link_suffixes(self.normalize_title(title_span.get_text(' ', strip=True)))
            if not title or _is_non_talk(title) or 'event' in row_cls:
                continue
            # Type from row class, or fallback to title prefix
            paper_type = 'regular'
            if 'invited' in row_cls:
                paper_type = 'invited'
            elif 'tutorial' in row_cls:
                paper_type = 'tutorial'
            elif 'keynote' in row_cls:
                paper_type = 'keynote'
            else:
                paper_type = self.detect_paper_type(title, '')
            # Strip type prefixes off the title
            title = re.sub(
                r"^(Invited Talk|Invited|Tutorial|Focus tutorial|Keynote|Plenary)\s*[:\-]\s*",
                '',
                title,
                flags=re.IGNORECASE,
            ).strip()
            authors_node = content.find('span', class_='talk-authors')
            authors, speakers = self._split_authors_speaker(authors_node)
            slides_url, video_url, youtube_id = self._extract_links(content)
            arxiv_ids = _strip_arxiv_link_text(content.get_text(' ', strip=True))
            talk = self._empty_talk()
            talk.update({
                'paper_type': paper_type,
                'title': title,
                'speakers': speakers or None,
                'authors': authors or None,
                'presentation_url': slides_url,
                'video_url': video_url,
                'youtube_id': youtube_id,
                'arxiv_ids': arxiv_ids or None,
                'scheduled_date': sched_date,
                'scheduled_time': time_str,
            })
            results.append(talk)
        return results

    # ------------------------------------------------------------------
    # TablePress era (2017, 2018, 2019)
    # ------------------------------------------------------------------
    def _parse_tablepress(self) -> List[Dict[str, Any]]:
        talks: List[Dict[str, Any]] = []
        current_date: Optional[str] = None
        for el in self.soup.find_all(True):
            if el.name in ('h2', 'h3', 'h4'):
                heading_text = el.get_text(' ', strip=True)
                if heading_text and len(heading_text) < 200:
                    idx = _day_index(heading_text)
                    if idx is not None:
                        d = self._date_for_day_name(heading_text)
                        if d:
                            current_date = d
                continue
            if el.name == 'table' and 'tablepress' in (el.get('class') or []):
                talks.extend(self._parse_tablepress_table(el, current_date))
        return talks

    def _parse_tablepress_table(self, table, sched_date: Optional[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        # Determine column meanings from header row
        header_tr = table.find('thead')
        column_map: Dict[str, int] = {}
        if header_tr:
            for idx, th in enumerate(header_tr.find_all('th')):
                key = th.get_text(' ', strip=True).lower()
                column_map[key] = idx
        # Schedule tables have Time + Type columns; poster tables don't.
        col_time = column_map.get('time')
        col_type = column_map.get('type')
        col_authors = column_map.get('authors')
        col_title = column_map.get('title')
        col_abstract = column_map.get('abstract')
        col_video = column_map.get('video')
        col_slides = column_map.get('slides')
        is_poster_table = col_time is None and col_type is None
        if col_authors is None or col_title is None:
            return []
        body = table.find('tbody') or table
        for tr in body.find_all('tr'):
            tds = tr.find_all('td')
            required = [c for c in (col_time, col_type, col_authors, col_title) if c is not None]
            if not tds or (required and len(tds) < max(required) + 1):
                continue
            time_str = _normalize_time(tds[col_time].get_text(' ', strip=True)) if col_time is not None else None
            type_text = tds[col_type].get_text(' ', strip=True).lower() if col_type is not None else ''
            title = self.normalize_title(tds[col_title].get_text(' ', strip=True))
            authors_text = tds[col_authors].get_text(' ', strip=True)
            if not title or _is_non_talk(title):
                continue
            if is_poster_table:
                paper_type = 'poster'
            elif 'tutorial' in type_text:
                paper_type = 'tutorial'
            elif 'invited' in type_text:
                paper_type = 'invited'
            elif 'keynote' in type_text:
                paper_type = 'keynote'
            elif 'contributed' in type_text:
                paper_type = 'regular'
            elif 'poster' in type_text:
                paper_type = 'poster'
            else:
                paper_type = self.detect_paper_type(type_text, title)
            authors, affils = _split_tablepress_authors(authors_text)
            speakers = []
            if len(authors) == 1:
                speakers = [authors[0]]
            slides_url = None
            video_url = None
            if col_slides is not None and col_slides < len(tds):
                a = tds[col_slides].find('a')
                if a and a.get('href'):
                    slides_url = a['href']
            if col_video is not None and col_video < len(tds):
                a = tds[col_video].find('a')
                if a and a.get('href'):
                    video_url = a['href']
            youtube_id = BaseTalkScraper.extract_youtube_id(video_url) if video_url else None
            abstract_url = None
            if col_abstract is not None and col_abstract < len(tds):
                a = tds[col_abstract].find('a')
                if a and a.get('href'):
                    abstract_url = a['href']
            arxiv_ids = _strip_arxiv_link_text(authors_text + ' ' + title)
            talk = self._empty_talk()
            talk.update({
                'paper_type': paper_type,
                'title': title,
                'speakers': speakers or None,
                'authors': authors or None,
                'affiliations': affils or None,
                'presentation_url': slides_url,
                'video_url': video_url,
                'youtube_id': youtube_id,
                'arxiv_ids': arxiv_ids or None,
                'scheduled_date': sched_date,
                'scheduled_time': time_str,
                'notes': f"Abstract URL: {abstract_url}" if abstract_url else None,
            })
            results.append(talk)
        return results

    # ------------------------------------------------------------------
    # 2013 schedule-table era
    # ------------------------------------------------------------------
    def _parse_schedule_table_2013(self) -> List[Dict[str, Any]]:
        talks: List[Dict[str, Any]] = []
        current_date: Optional[str] = None
        for el in self.soup.find_all(True):
            if el.name in ('h2', 'h3'):
                text = el.get_text(' ', strip=True)
                idx = _day_index(text)
                if idx is not None:
                    d = self._date_for_day_name(text)
                    if d:
                        current_date = d
                continue
            if el.name == 'table' and 'schedule-table' in (el.get('class') or []):
                talks.extend(self._parse_schedule_table_2013_table(el, current_date))
        return talks

    def _parse_schedule_table_2013_table(self, table, sched_date: Optional[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for tr in table.find_all('tr'):
            row_cls = tr.get('class') or []
            if 'food' in row_cls:
                continue  # break / lunch
            time_td = tr.find('td', class_='time-td')
            content_tds = [td for td in tr.find_all('td') if 'time-td' not in (td.get('class') or [])]
            if not time_td or not content_tds:
                continue
            content = content_tds[-1]
            title_span = content.find('span', class_='title')
            if not title_span:
                continue
            title_raw = _strip_link_suffixes(self.normalize_title(title_span.get_text(' ', strip=True)))
            if not title_raw or _is_non_talk(title_raw):
                continue
            paper_type = 'regular'
            title = title_raw
            m = re.match(r'^(Invited talk|Invited|Tutorial|Keynote|Plenary)\s*[:\-]\s*(.+)$', title_raw, flags=re.IGNORECASE)
            if m:
                kind = m.group(1).lower()
                if 'tutorial' in kind:
                    paper_type = 'tutorial'
                elif 'keynote' in kind:
                    paper_type = 'keynote'
                elif 'plenary' in kind:
                    paper_type = 'invited'
                else:
                    paper_type = 'invited'
                title = m.group(2).strip()
            # Authors live in a text node after title <span>; capture by removing tags we don't want
            content_clone = _content_after_title(content)
            authors_text = re.sub(r'\s+', ' ', content_clone).strip().rstrip('.').rstrip(',')
            authors, speakers = _parse_2013_authors(content, authors_text)
            slides_url, video_url, youtube_id = self._extract_links(content)
            arxiv_ids = _strip_arxiv_link_text(content.get_text(' ', strip=True))
            time_str = _normalize_time(time_td.get_text(' ', strip=True))
            talk = self._empty_talk()
            talk.update({
                'paper_type': paper_type,
                'title': title,
                'speakers': speakers or None,
                'authors': authors or None,
                'presentation_url': slides_url,
                'video_url': video_url,
                'youtube_id': youtube_id,
                'arxiv_ids': arxiv_ids or None,
                'scheduled_date': sched_date,
                'scheduled_time': time_str,
            })
            results.append(talk)
        return results

    # ------------------------------------------------------------------
    # ETH 2011 silvatable era
    # ------------------------------------------------------------------
    def _parse_eth_2011(self) -> List[Dict[str, Any]]:
        talks: List[Dict[str, Any]] = []
        current_date: Optional[str] = None
        for el in self.soup.find_all(True):
            if el.name in ('h2', 'h3'):
                text = el.get_text(' ', strip=True)
                idx = _day_index(text)
                if idx is not None:
                    d = self._date_for_day_name(text)
                    if d:
                        current_date = d
                continue
            if el.name == 'table' and 'silvatable' in (el.get('class') or []):
                talks.extend(self._parse_eth_table(el, current_date))
        return talks

    def _parse_eth_table(self, table, sched_date: Optional[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        body = table.find('tbody') or table
        for tr in body.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) < 2:
                continue
            time_str = _normalize_time(tds[0].get_text(' ', strip=True))
            content = tds[1]
            text = content.get_text(' ', strip=True)
            if not text or _is_non_talk(text):
                continue
            title_node = content.find('em')
            if not title_node:
                # No title in italics — treat as informational row, skip
                continue
            title = self.normalize_title(title_node.get_text(' ', strip=True))
            if not title:
                continue
            # Authors: everything before the <em> in the cell, stripped of links
            authors_html = ''
            for child in content.children:
                if getattr(child, 'name', None) == 'em':
                    break
                if hasattr(child, 'get_text'):
                    authors_html += ' ' + child.get_text(' ', strip=True)
                else:
                    authors_html += ' ' + str(child)
            authors_text = re.sub(r'\s+', ' ', authors_html).strip().rstrip('.').rstrip(',')
            authors, speakers = _parse_eth_authors(content, authors_text)
            slides_url, video_url, youtube_id = self._extract_links(content)
            paper_type = 'regular'
            # ETH 2011 had a single track of mostly invited / contributed talks.
            # Use length of author list as a weak heuristic: solo authors with
            # no co-authors at QCrypt 2011 were typically invited / plenary.
            if len(authors) <= 1 and len(speakers) == 1:
                paper_type = 'invited'
            talk = self._empty_talk()
            talk.update({
                'paper_type': paper_type,
                'title': title,
                'speakers': speakers or None,
                'authors': authors or None,
                'presentation_url': slides_url,
                'video_url': video_url,
                'youtube_id': youtube_id,
                'scheduled_date': sched_date,
                'scheduled_time': time_str,
            })
            results.append(talk)
        return results


    # ------------------------------------------------------------------
    # 2015 single-table grid (bgcolor-tagged talk types)
    # ------------------------------------------------------------------
    def _parse_2015_grid(self) -> List[Dict[str, Any]]:
        # The "Full Program" table is the only border="1" table containing
        # day-of-week headings; pick whichever tracks day rows.
        target = None
        for table in self.soup.find_all('table'):
            if table.find('th', string=re.compile(r'(?:Sun|Mon|Tues|Wednes|Thurs|Fri|Satur)day', re.I)):
                target = table
                break
        if target is None:
            logger.warning("QCrypt 2015: no full-program table found")
            return []
        results: List[Dict[str, Any]] = []
        current_date: Optional[str] = None
        for tr in target.find_all('tr'):
            # Day heading row: a single <th colspan> with "Sunday 27th September"
            ths = tr.find_all('th')
            if ths and len(ths) == 1 and ths[0].get('colspan'):
                heading = ths[0].get_text(' ', strip=True)
                d = _parse_2015_day_heading(heading, self.year)
                if d:
                    current_date = d
                continue
            tds = tr.find_all('td', recursive=False)
            if not tds:
                continue
            # Skip session-chair-only rows ("Chair: Gilles Brassard")
            if len(tds) == 1 and tds[0].get('colspan') == '3':
                continue
            # Skip break / lunch rows: <td colspan="2"> in second cell
            if len(tds) >= 2 and tds[1].get('colspan') == '2':
                continue
            if len(tds) < 3:
                continue
            time_str = _normalize_time(tds[0].get_text(' ', strip=True))
            type_label = tds[1].get_text(' ', strip=True).lower()
            content = tds[2]
            paper_type = _classify_2015_type(type_label)
            if paper_type is None:
                # Public lecture / non-talk row
                continue
            title_node = content.find(['em', 'strong'])
            if not title_node:
                continue
            # Title text is the contents of the first <em> (or <strong>) chain
            title = self.normalize_title(title_node.get_text(' ', strip=True))
            title = _strip_link_suffixes(title)
            if not title or _is_non_talk(title):
                continue
            # Authors: first non-empty text node after the title chain, before
            # the embedded <img>/abstract <a>.
            authors_text = _2015_authors_text(content)
            authors, speakers = _parse_eth_authors(content, authors_text)
            slides_url, video_url, youtube_id = self._extract_links(content)
            arxiv_ids = _strip_arxiv_link_text(content.get_text(' ', strip=True))
            talk = self._empty_talk()
            talk.update({
                'paper_type': paper_type,
                'title': title,
                'speakers': speakers or None,
                'authors': authors or None,
                'presentation_url': slides_url,
                'video_url': video_url,
                'youtube_id': youtube_id,
                'arxiv_ids': arxiv_ids or None,
                'scheduled_date': current_date,
                'scheduled_time': time_str,
            })
            results.append(talk)
        return results

    # ------------------------------------------------------------------
    # 2016 matrix layout (days as columns)
    # ------------------------------------------------------------------
    def _parse_2016_matrix(self) -> List[Dict[str, Any]]:
        target = None
        for table in self.soup.find_all('table'):
            ths = table.find_all('th')
            day_ths = [th for th in ths if _day_index(th.get_text(' ', strip=True)) is not None]
            if len(day_ths) >= 4:
                target = table
                break
        if target is None:
            logger.warning("QCrypt 2016: no matrix-layout table found")
            return []
        results: List[Dict[str, Any]] = []
        rows = target.find_all('tr')
        if not rows:
            return []
        # Header row maps column index -> day-of-week index (0=Mon)
        header_cells = rows[0].find_all(['td', 'th'])
        col_to_day: Dict[int, int] = {}
        for col_idx, cell in enumerate(header_cells):
            d_idx = _day_index(cell.get_text(' ', strip=True))
            if d_idx is not None:
                col_to_day[col_idx] = d_idx
        if not col_to_day:
            return []
        start = QCRYPT_START_DATES.get(self.year)
        for tr in rows[1:]:
            cells = tr.find_all(['td', 'th'], recursive=False)
            if not cells:
                continue
            time_str = _normalize_time(cells[0].get_text(' ', strip=True))
            if not time_str:
                continue
            for col_idx, cell in enumerate(cells):
                if col_idx not in col_to_day:
                    continue
                results.extend(self._parse_2016_cell(
                    cell, time_str, col_to_day[col_idx], start
                ))
        return results

    def _parse_2016_cell(self, cell, time_str: str, day_offset: int,
                         start_date: Optional[date]) -> List[Dict[str, Any]]:
        # Skip empty / continuation / break cells
        text = cell.get_text(' ', strip=True)
        if not text:
            return []
        text_lower = text.lower()
        if _is_non_talk(text_lower):
            return []
        if re.fullmatch(r'\(?(?:until|at)\s+\d{1,2}[:.]?\d{0,2}\s*(?:pm|am)?\)?', text_lower):
            return []
        if 'free afternoon' in text_lower or 'free morning' in text_lower:
            return []
        # Talks are wrapped in <a><strong>...</strong></a> (invited/tutorial)
        # or <a>plain title</a> (contributed). Sometimes multiple talks share
        # a cell (lined separated by <br /> or <p>).
        anchors = cell.find_all('a')
        if not anchors:
            return []
        sched_date = (start_date + timedelta(days=day_offset)).isoformat() if start_date else None
        # Build one talk per top-level anchor
        results = []
        for a in anchors:
            href = a.get('href', '') or ''
            inner_text = a.get_text(' ', strip=True)
            if not inner_text:
                continue
            if _is_non_talk(inner_text):
                continue
            strong = a.find('strong')
            if strong:
                strong_text = strong.get_text(' ', strip=True)
                paper_type, title = _classify_2016_strong(strong_text)
                if paper_type is None:
                    continue
            else:
                paper_type = 'regular'
                title = inner_text
            title = _strip_link_suffixes(self.normalize_title(title))
            if not title:
                continue
            talk = self._empty_talk()
            talk.update({
                'paper_type': paper_type,
                'title': title,
                'speakers': None,
                'authors': None,
                'scheduled_date': sched_date,
                'scheduled_time': time_str,
                'notes': f"Source link: {href}" if href else None,
            })
            results.append(talk)
        # If a cell holds back-to-back talks (Friday afternoon dual-anchor
        # cells), emit all of them with the cell's stamped time so they
        # survive into the CSV for review.
        return results


# ----------------------------------------------------------------------
# 2015 helpers
# ----------------------------------------------------------------------
_MONTH_NAMES = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12,
}


def _parse_2015_day_heading(text: str, year: int) -> Optional[str]:
    """Parse '<DayName> <Day>(st|nd|rd|th) <Month>' into 'YYYY-MM-DD'."""
    if not text:
        return None
    m = re.search(
        r'(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+)',
        text,
    )
    if not m:
        return None
    day_num = int(m.group(1))
    month_name = m.group(2).lower()
    month = _MONTH_NAMES.get(month_name)
    if not month:
        return None
    try:
        return date(year, month, day_num).isoformat()
    except ValueError:
        return None


def _classify_2015_type(label: str) -> Optional[str]:
    if not label:
        return None
    lower = label.lower()
    if 'keynote' in lower:
        return 'keynote'
    if 'tutorial' in lower:
        return 'tutorial'
    if 'invited' in lower:
        return 'invited'
    if 'contributed' in lower:
        return 'regular'
    if 'summary' in lower:
        return 'invited'
    if 'after-dinner' in lower or 'after dinner' in lower:
        return 'invited'
    return None


def _2015_authors_text(content_node) -> str:
    """For 2015 cells, authors live as a text node after the first <em>/<strong>
    grouping and before the abstract <a> / <img> noise. Concatenate plain-text
    children (and <span>) up to the first <a> or <img>.
    """
    parts: List[str] = []
    seen_title = False
    for child in content_node.children:
        name = getattr(child, 'name', None)
        if not seen_title:
            if name in ('em', 'strong'):
                seen_title = True
            continue
        if name in ('a', 'img'):
            break
        if name == 'br':
            parts.append(' ')
            continue
        if name is None:
            text = str(child)
            if text:
                parts.append(text)
        elif hasattr(child, 'get_text'):
            parts.append(child.get_text(' ', strip=True))
    text = ' '.join(parts)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.rstrip('.').rstrip(',')
    return text


# ----------------------------------------------------------------------
# 2016 helpers
# ----------------------------------------------------------------------
def _classify_2016_strong(strong_text: str) -> Tuple[Optional[str], str]:
    """Map a <strong>-wrapped 2016 cell label to (paper_type, clean_title).
    Returns (None, '') for cells that are not talks (e.g. 'Industry session',
    'Special Session', 'Hot Topics Session', 'Poster session').
    """
    if not strong_text:
        return None, ''
    lower = strong_text.lower()
    if 'industry' in lower or 'special session' in lower or 'hot topics' in lower:
        return None, ''
    if 'poster' in lower and 'session' in lower:
        return None, ''
    if 'free' in lower:
        return None, ''
    m = re.match(
        r'^(Tutorial|Invited Talk|Invited|Keynote|Plenary)\s*[:\-]\s*(.+)$',
        strong_text,
        flags=re.IGNORECASE,
    )
    if m:
        kind = m.group(1).lower()
        title = m.group(2).strip()
        if 'tutorial' in kind:
            return 'tutorial', title
        if 'keynote' in kind:
            return 'keynote', title
        if 'plenary' in kind:
            return 'invited', title
        return 'invited', title
    # Bold but no prefix — treat as contributed (rare in 2016)
    return 'regular', strong_text


# ----------------------------------------------------------------------
# Module-level helpers (kept outside class for testability)
# ----------------------------------------------------------------------

def _split_tablepress_authors(text: str) -> Tuple[List[str], List[str]]:
    """Parse 'Name (Affiliation), Name (Affiliation) and Name (Affiliation)'
    into parallel author / affiliation lists.
    """
    if not text:
        return [], []
    # Replace 'and ' separator with ',' for splitting
    cleaned = re.sub(r'\s+and\s+', ',', text)
    chunks = [c.strip() for c in cleaned.split(',') if c.strip()]
    authors: List[str] = []
    affils: List[str] = []
    for chunk in chunks:
        m = re.match(r'^(.+?)\s*\(([^()]+)\)\s*$', chunk)
        if m:
            authors.append(m.group(1).strip())
            affils.append(m.group(2).strip())
        else:
            authors.append(chunk)
            affils.append('')
    if not any(affils):
        affils = []
    return authors, affils


def _content_after_title(content_node) -> str:
    """Return text content of `content_node` minus the leading title span."""
    parts: List[str] = []
    seen_title = False
    for child in content_node.children:
        if not seen_title:
            if getattr(child, 'name', None) == 'span' and 'title' in (child.get('class') or []):
                seen_title = True
                continue
            continue
        if getattr(child, 'name', None) in (None, 'br'):
            text = child if isinstance(child, str) else ''
            if text:
                parts.append(text)
        elif getattr(child, 'name', None) in ('a', 'div'):
            # skip abstracts, links
            continue
        elif hasattr(child, 'get_text'):
            parts.append(child.get_text(' ', strip=True))
    return ' '.join(parts)


def _parse_2013_authors(content_node, fallback_text: str) -> Tuple[List[str], List[str]]:
    """Extract authors from 2013 schedule cells.

    Authors appear as a flat text node after <span class='title'>. The
    presenter is wrapped in <span style='text-decoration: underline;'>.
    """
    speakers: List[str] = []
    for span in content_node.find_all('span'):
        style = span.get('style') or ''
        if 'underline' in style:
            n = span.get_text(' ', strip=True)
            if n:
                speakers.append(' '.join(n.split()))
    text = fallback_text
    if not text:
        return [], speakers
    cleaned = re.sub(r'\s+and\s+', ',', text)
    names = [n.strip() for n in cleaned.split(',') if n.strip()]
    names = [re.sub(r'\.+$', '', n) for n in names if len(n) >= 2]
    if not speakers and len(names) == 1:
        speakers = [names[0]]
    return names, speakers


def _parse_eth_authors(content_node, fallback_text: str) -> Tuple[List[str], List[str]]:
    """Extract authors from ETH 2011 cells.

    Presenter is in <u>...</u>; co-authors are plain text separated by ', '
    or ' and '.
    """
    speakers: List[str] = []
    for u in content_node.find_all('u'):
        n = u.get_text(' ', strip=True)
        if n:
            speakers.append(' '.join(n.split()))
    text = fallback_text
    if not text:
        return [], speakers
    cleaned = re.sub(r'\s+and\s+', ',', text)
    names = [n.strip() for n in cleaned.split(',') if n.strip()]
    names = [re.sub(r'\.+$', '', n) for n in names if len(n) >= 2]
    if not speakers and len(names) == 1:
        speakers = [names[0]]
    return names, speakers
