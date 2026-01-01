"""Base scraper class for conference committee data."""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup


class BaseCommitteeScraper(ABC):
    """Abstract base class for conference committee scrapers."""
    
    def __init__(self, year: int, local_file: Optional[str] = None):
        self.year = year
        self.local_file = local_file
        self.soup = None
    
    @abstractmethod
    def get_url(self) -> str:
        """Return the URL for the conference committee page."""
        pass
    
    @abstractmethod
    def parse_committee_data(self) -> List[Dict[str, str]]:
        """Parse the committee data from the HTML.
        
        Returns:
            List of dicts with keys: committee_type, position, full_name, affiliation, notes
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
            # Create a key from the identifying fields
            key = (
                member.get('full_name', '').lower().strip(),
                member.get('committee_type', ''),
                member.get('position', '')
            )
            
            if key not in seen:
                seen.add(key)
                unique_members.append(member)
        
        return unique_members
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize person name (remove extra whitespace, etc.)."""
        return ' '.join(name.strip().split())
    
    @staticmethod
    def normalize_affiliation(affiliation: str) -> Optional[str]:
        """Normalize affiliation (remove extra whitespace, handle empty strings)."""
        if not affiliation:
            return None
        normalized = ' '.join(affiliation.strip().split())
        return normalized if normalized else None
