"""TQC conference talk scraper."""
from typing import List, Dict, Any
from .base import BaseTalkScraper


class TQCTalkScraper(BaseTalkScraper):
    """Scraper for TQC invited/tutorial talks."""

    def get_url(self) -> str:
        """Return the URL for the TQC program/schedule page."""
        # This needs to be customized per year
        # TQC websites vary significantly year to year
        raise NotImplementedError(
            f"TQC {self.year} scraper not implemented yet. "
            "Each year requires custom HTML parsing logic."
        )

    def parse_talk_data(self) -> List[Dict[str, Any]]:
        """Parse TQC talk data from HTML."""
        raise NotImplementedError(
            "TQC talk parsing not implemented yet. "
            "Requires year-specific HTML structure analysis."
        )
