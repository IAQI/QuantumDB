#!/usr/bin/env python3
"""Debug QIP 2026 parser."""
from pathlib import Path
from bs4 import BeautifulSoup

file_path = Path.home() / 'Web/qip.iaqi.org/2026/about/programme-committee/index.html'
with open(file_path, 'r') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# Find main content wrapper
main = soup.find('div', class_='pageContentWrapper')
print(f"Found main: {main is not None}")

if main:
    paragraphs = main.find_all('p')
    print(f"Found {len(paragraphs)} paragraphs")
    
    for i, p in enumerate(paragraphs[:10]):
        print(f"\n--- Paragraph {i} ---")
        print(f"Has <strong>: {p.find('strong') is not None}")
        print(f"Has <br>: {p.find('br') is not None}")
        text = p.get_text(strip=True)[:200]
        print(f"Text: {text}")
