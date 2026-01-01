"""Base scraper class for conference invited/tutorial talks."""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
import re
import requests
from bs4 import BeautifulSoup


class BaseTalkScraper(ABC):
    """Abstract base class for conference talk scrapers."""

    def __init__(self, year: int, local_file: Optional[str] = None):
        self.year = year
        self.local_file = local_file
        self.soup = None

    @abstractmethod
    def get_url(self) -> str:
        """Return the URL for the conference program/schedule page."""
        pass

    @abstractmethod
    def parse_talk_data(self) -> List[Dict[str, Any]]:
        """Parse invited/tutorial talk data from HTML.

        Returns:
            List of dicts with keys:
            - paper_type: 'invited' | 'tutorial' | 'keynote'
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
        """
        pass

    def fetch_page(self) -> BeautifulSoup:
        """Fetch and parse the HTML page."""
        if self.local_file:
            with open(self.local_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            url = self.get_url()
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            html_content = response.text

        self.soup = BeautifulSoup(html_content, 'html.parser')
        return self.soup

    def scrape(self) -> List[Dict[str, Any]]:
        """Fetch page and parse talk data."""
        self.fetch_page()
        talks = self.parse_talk_data()
        return self._deduplicate_talks(talks)

    @staticmethod
    def _deduplicate_talks(talks: List[Dict]) -> List[Dict]:
        """Remove duplicate talks based on title."""
        seen = set()
        unique = []
        for talk in talks:
            key = talk.get('title', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(talk)
        return unique

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize person name (remove extra whitespace, etc.)."""
        return ' '.join(name.strip().split())

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
            r'(?<!\d)(\d{4}\.\d{4,5})(?!\d)',  # Standalone
        ]
        ids = []
        for pattern in patterns:
            ids.extend(re.findall(pattern, text, re.IGNORECASE))
        return list(set(ids))  # Deduplicate

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

        Returns: 'invited', 'tutorial', or 'keynote'
        """
        combined = f"{session_name} {title}".lower()
        if 'keynote' in combined:
            return 'keynote'
        elif 'tutorial' in combined:
            return 'tutorial'
        else:
            return 'invited'

    @staticmethod
    def normalize_affiliation(affiliation: str) -> Optional[str]:
        """Normalize affiliation (remove extra whitespace, handle empty strings)."""
        if not affiliation:
            return None
        normalized = ' '.join(affiliation.strip().split())
        return normalized if normalized else None
