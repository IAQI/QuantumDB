"""TQC conference committee scraper."""
from typing import List, Dict
from .base import BaseCommitteeScraper


class TQCScraper(BaseCommitteeScraper):
    """Scraper for TQC conference committee pages.
    
    TODO: Customize for TQC-specific HTML structure.
    """
    
    def get_url(self) -> str:
        """Return the URL for TQC committee page."""
        # TQC URLs need to be customized per year
        return f"https://tqc{self.year}.org/committee.html"
    
    def parse_committee_data(self) -> List[Dict[str, str]]:
        """Parse committee data from TQC HTML.
        
        TODO: Implement TQC-specific parsing logic.
        """
        raise NotImplementedError(
            f"TQC scraper for {self.year} needs to be customized. "
            "Check the HTML structure and update the parser accordingly."
        )
