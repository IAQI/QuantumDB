"""Shared scraper plumbing for committees + talks."""
from abc import ABC, abstractmethod
from typing import Optional

import requests
from bs4 import BeautifulSoup


class Scraper(ABC):
    """Common base for committee and talk scrapers.

    Subclasses provide ``get_url`` (the page to fetch) and one of the
    kind-specific ``parse_*`` methods. ``fetch_page`` is shared.
    """

    def __init__(self, year: int, local_file: Optional[str] = None):
        self.year = year
        self.local_file = local_file
        self.soup: Optional[BeautifulSoup] = None

    @abstractmethod
    def get_url(self) -> str:
        """Return the URL for the conference page being scraped."""

    def fetch_page(self) -> BeautifulSoup:
        """Fetch and parse the HTML page.

        Local files are read as bytes so BeautifulSoup can sniff the encoding
        from the document — some QCrypt mirror pages declare UTF-8 in <meta>
        but actually contain CP1252-encoded bytes.
        """
        if self.local_file:
            with open(self.local_file, 'rb') as f:
                html_content = f.read()
        else:
            url = self.get_url()
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            html_content = response.content

        self.soup = BeautifulSoup(html_content, 'html.parser')
        return self.soup

    @staticmethod
    def normalize_name(name: str) -> str:
        """Collapse whitespace in a person's name."""
        return ' '.join(name.strip().split())

    @staticmethod
    def normalize_affiliation(affiliation: str) -> Optional[str]:
        """Collapse whitespace in an affiliation; empty string → None."""
        if not affiliation:
            return None
        normalized = ' '.join(affiliation.strip().split())
        return normalized if normalized else None
