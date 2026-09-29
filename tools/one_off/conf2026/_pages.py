"""Page loader for the 2026 converters: static mirror first, live site second.

Source pages are not stored in the repo. A page ``<rel>`` (e.g.
``accepted-papers/``) is read from the local static mirror at
``~/Web/<mirror>/2026/<rel>index.html`` when it exists, otherwise fetched from
the live conference site. Once the 2026 sites are mirrored, the converters run
offline and reproducibly without code changes.
"""
import urllib.request
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup

WEB = Path.home() / 'Web'
UA = 'Mozilla/5.0 (QuantumDB data import)'


class Site:
    def __init__(self, live_base, mirror, year=2026):
        self.live_base = live_base.rstrip('/')  # e.g. https://qcrypt.net/2026
        self.mirror_root = WEB / mirror / str(year)
        self.used_live = set()

    def local_path(self, rel):
        """Mirror copy of page ``rel``: ``<rel>/index.html``, or ``<rel>.html``
        for mirrors that flatten leaf pages (e.g. ``sessions/invited/Li.html``;
        the lookup is case-insensitive on macOS)."""
        rel = rel.strip('/')
        if not rel:
            return self.mirror_root / 'index.html'
        if rel.endswith('.html'):
            return self.mirror_root / rel
        nested = self.mirror_root / rel / 'index.html'
        flat = self.mirror_root / f'{rel}.html'
        return nested if nested.exists() or not flat.exists() else flat

    @lru_cache(maxsize=None)
    def html(self, rel):
        path = self.local_path(rel)
        if path.exists():
            return path.read_text(encoding='utf-8')
        self.used_live.add(rel)
        return fetch(f"{self.live_base}/{rel.strip('/')}/")

    def soup(self, rel):
        return BeautifulSoup(self.html(rel), 'html.parser')

    def report(self):
        if self.used_live:
            print(f"note: {len(self.used_live)} page(s) fetched live "
                  f"(no mirror copy under {self.mirror_root})")


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8')
