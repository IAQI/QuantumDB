"""Base scraper class for conference committee data."""
from abc import abstractmethod
from typing import Dict, List, Optional

from ..base import Scraper


class BaseCommitteeScraper(Scraper):
    """Abstract base class for conference committee scrapers."""

    @abstractmethod
    def parse_committee_data(self) -> List[Dict[str, str]]:
        """Parse the committee data from the HTML.

        Returns:
            List of dicts with keys: committee_type, position, full_name, affiliation, role_title
        """

    def scrape(self) -> List[Dict[str, str]]:
        """Fetch page and parse committee data."""
        self.fetch_page()
        members = self.parse_committee_data()
        return self._deduplicate_members(members)

    @staticmethod
    def _deduplicate_members(members: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Remove duplicate members based on name, committee type, and position."""
        seen = set()
        unique_members = []

        for member in members:
            key = (
                member.get('full_name', '').lower().strip(),
                member.get('committee_type', ''),
                member.get('position', ''),
            )
            if key not in seen:
                seen.add(key)
                unique_members.append(member)

        return unique_members

    @staticmethod
    def detect_role_title(text: str, heading_text: str = '') -> Optional[str]:
        """Detect specialized role titles from text.

        Returns role_title if a specific chair role is detected, otherwise None.
        Examples: 'General Chair', 'Program Chair', 'Publicity Chair', etc.
        """
        combined = f"{heading_text} {text}".lower()

        role_patterns = [
            ('general chair', 'General Chair'),
            ('conference chair', 'General Chair'),
            ('program chair', 'Program Chair'),
            ('programme chair', 'Program Chair'),
            ('steering chair', 'Steering Chair'),
            ('local chair', 'Local Chair'),
            ('publicity chair', 'Publicity Chair'),
            ('web chair', 'Web Chair'),
            ('webmaster', 'Web Chair'),
            ('technical operations chair', 'Technical Operations Chair'),
            ('local arrangements', 'Local Arrangements Chair'),
            ('registration chair', 'Registration Chair'),
            ('proceedings chair', 'Proceedings Chair'),
            ('poster chair', 'Poster Chair'),
            ('tutorial chair', 'Tutorial Chair'),
            ('workshop chair', 'Workshop Chair'),
            ('sponsorship chair', 'Sponsorship Chair'),
            ('finance chair', 'Finance Chair'),
            ('social events chair', 'Social Events Chair'),
        ]

        for pattern, title in role_patterns:
            if pattern in combined:
                return title

        return None
