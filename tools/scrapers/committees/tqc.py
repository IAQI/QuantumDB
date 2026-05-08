"""TQC conference committee scraper."""
from typing import List, Dict
from .base import BaseCommitteeScraper


class TQCScraper(BaseCommitteeScraper):
    """Scraper for TQC conference committee pages.

    TQC websites vary significantly year to year — each year needs its own
    parsing logic. Pass ``--local-file`` and implement
    ``parse_committee_data`` for the specific year before running.
    """

    def get_url(self) -> str:
        raise NotImplementedError(
            f"TQC {self.year} committee scraper not implemented. "
            "Each year requires year-specific parsing logic."
        )

    def parse_committee_data(self) -> List[Dict[str, str]]:
        raise NotImplementedError(
            f"TQC {self.year} committee parsing not implemented. "
            "Add a year-specific parser in scrapers/committees/tqc.py."
        )
