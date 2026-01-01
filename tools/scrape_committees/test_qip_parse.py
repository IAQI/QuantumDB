#!/usr/bin/env python3
"""Test parsing QIP 2026 committee page."""
from bs4 import BeautifulSoup
from pathlib import Path

file_path = Path.home() / 'Web/qip.iaqi.org/2026/about/programme-committee/index.html'
with open(file_path, 'r') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
main = soup.find('div', class_='pageContentWrapper')
if main:
    paragraphs = main.find_all('p')
    for i, p in enumerate(paragraphs):
        text = p.get_text(strip=True)
        if text:
            print(f'{i}: {text}')
