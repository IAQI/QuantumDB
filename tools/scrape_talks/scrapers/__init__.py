"""Conference talk scrapers."""
from .base import BaseTalkScraper
from .qcrypt import QCryptTalkScraper
from .qip import QIPTalkScraper
from .tqc import TQCTalkScraper

__all__ = ['BaseTalkScraper', 'QCryptTalkScraper', 'QIPTalkScraper', 'TQCTalkScraper']
