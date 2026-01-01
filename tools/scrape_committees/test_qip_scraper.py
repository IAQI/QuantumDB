#!/usr/bin/env python3
"""Test QIP 2026 scraper."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.qip import QIPScraper

scraper = QIPScraper(2026)
scraper.local_mode = True
scraper.local_dir = Path.home() / 'Web'

# Load HTML
file_path = Path.home() / 'Web/qip.iaqi.org/2026/about/programme-committee/index.html'
with open(file_path, 'r') as f:
    html = f.read()

from bs4 import BeautifulSoup
scraper.soup = BeautifulSoup(html, 'html.parser')

# Parse
members = scraper.parse_committee_data()
print(f"Found {len(members)} members")
for i, m in enumerate(members[:10]):
    print(f"{i+1}. {m['full_name']} - {m['affiliation']} ({m['position']})")
