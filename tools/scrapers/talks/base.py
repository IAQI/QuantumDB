"""Base scraper class for conference invited/tutorial talks."""
import re
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from ..base import Scraper


class BaseTalkScraper(Scraper):
    """Abstract base class for conference talk scrapers."""

    @abstractmethod
    def parse_talk_data(self) -> List[Dict[str, Any]]:
        """Parse talk data from HTML.

        Returns:
            List of dicts with keys:
            - paper_type: 'invited' | 'tutorial' | 'keynote' | 'regular' | 'poster'
            - title: str
            - speakers: List[str]  # Names of presenters
            - authors: Optional[List[str]]  # If different from speakers
            - affiliations: Optional[List[str]]  # Parallel to speakers/authors
            - abstract: Optional[str]
            - arxiv_ids: Optional[List[str]]
            - presentation_url: Optional[str]
            - video_url: Optional[str]
            - youtube_id: Optional[str]
            - session_name: Optional[str]
            - award: Optional[str]
            - notes: Optional[str]
            - scheduled_date: Optional[str]  # ISO date 'YYYY-MM-DD'
            - scheduled_time: Optional[str]  # 'HH:MM' 24h
            - duration_minutes: Optional[int]
        """

    def scrape(self) -> List[Dict[str, Any]]:
        """Fetch page and parse talk data."""
        self.fetch_page()
        talks = self.parse_talk_data()
        return self._deduplicate_talks(talks)

    @staticmethod
    def _deduplicate_talks(talks: List[Dict]) -> List[Dict]:
        """Remove duplicate talks based on (title, paper_type, scheduled_date, scheduled_time).

        Keying on title alone collapses legitimately distinct entries that
        share a generic title (e.g., multiple poster session rows or papers
        with identical short titles in different sessions).
        """
        seen = set()
        unique = []
        for talk in talks:
            title = (talk.get('title') or '').lower().strip()
            if not title:
                continue
            key = (
                title,
                talk.get('paper_type') or '',
                talk.get('scheduled_date') or '',
                talk.get('scheduled_time') or '',
            )
            if key not in seen:
                seen.add(key)
                unique.append(talk)
        return unique

    @staticmethod
    def normalize_title(title: str) -> str:
        """Normalize talk title (remove extra whitespace, newlines)."""
        return ' '.join(title.strip().split())

    @staticmethod
    def extract_arxiv_ids(text: str) -> List[str]:
        """Extract arXiv IDs from text using regex.

        Patterns: arXiv:2401.12345, arxiv.org/abs/2401.12345, 2401.12345
        """
        patterns = [
            r'arXiv:(\d{4}\.\d{4,5})',
            r'arxiv\.org/abs/(\d{4}\.\d{4,5})',
            r'(?<!\d)(\d{4}\.\d{4,5})(?!\d)',
        ]
        ids = []
        for pattern in patterns:
            ids.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(ids))

    @staticmethod
    def extract_youtube_id(url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats."""
        if not url:
            return None
        patterns = [
            r'youtube\.com/watch\?v=([A-Za-z0-9_-]{11})',
            r'youtu\.be/([A-Za-z0-9_-]{11})',
            r'youtube\.com/embed/([A-Za-z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def detect_paper_type(session_name: str, title: str = '') -> str:
        """Detect paper_type from session name or title.

        Returns one of: 'keynote', 'tutorial', 'invited', 'poster', 'regular'.
        Defaults to 'regular' for contributed talks; callers that know they're
        looking at an invited-only context can override.
        """
        combined = f"{session_name} {title}".lower()
        if 'keynote' in combined:
            return 'keynote'
        if 'tutorial' in combined:
            return 'tutorial'
        if 'invited' in combined or 'plenary' in combined:
            return 'invited'
        if 'poster' in combined:
            return 'poster'
        if 'contributed' in combined:
            return 'regular'
        return 'regular'
