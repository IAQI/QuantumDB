#!/usr/bin/env python3
"""Resolve QCrypt 2026 initials-only author lists to full names via arXiv.

The QCrypt 2026 accepted-papers page prints authors as initials ("D. Tupkary").
The DB importer matches authors on exact normalized full name, so importing the
initials would spawn duplicate authors. For every accepted talk/poster this
script searches the arXiv API by title and accepts a hit only when

* the normalized titles agree (difflib ratio >= 0.93), and
* every printed author maps to exactly one arXiv author with the same surname
  and first initial (arXiv may list extra authors; those are ignored).

Accepted hits record the aligned full names and the arXiv id; everything else is
left for the surname-index fallback in ``convert_qcrypt_2026.py``. Results are
cached in ``data/conferences/qcrypt_2026/raw/arxiv_matches.json`` (keyed by
submission id) so reruns only query what is missing. arXiv asks for <= 1
request / 3 s.

Usage: python3 tools/one_off/conf2026/qcrypt_2026_arxiv_names.py
"""
import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # trusted source (arXiv API); no DTDs expanded
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_qcrypt_2026 import parse_accepted, RAW  # noqa: E402

CACHE = RAW / 'arxiv_matches.json'
ATOM = '{http://www.w3.org/2005/Atom}'
API = 'https://export.arxiv.org/api/query?'
# Bump to re-query cached misses after changing the query strategy.
QUERY_VERSION = 2
# arXiv's title search fails on AND-ed stopwords, so only query content words.
STOP = {'and', 'the', 'for', 'with', 'from', 'via', 'into', 'its', 'are', 'how',
        'towards', 'toward', 'using', 'based', 'under', 'over', 'beyond',
        'without', 'all', 'more', 'non', 'can', 'not', 'our', 'new'}


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def norm_title(s):
    s = re.sub(r'\$[^$]*\$', ' ', fold(s))
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def surname_initial(name):
    """'D. Tupkary' / 'Devashish Tupkary' -> ('tupkary', 'd')."""
    parts = fold(name).replace('.', ' ').split()
    return (re.sub(r'[^a-z]', '', parts[-1]), parts[0][0]) if parts else ('', '')


def same_person(printed, full):
    ps, pi = surname_initial(printed)
    fs, fi = surname_initial(full)
    # Tolerate compound surnames split differently ("Y. Li" vs "Yu-Huai Li").
    return (ps == fs or fold(full).replace('-', ' ').endswith(' ' + ps)) and pi == fi


def authors_match(printed, full):
    """-> full names aligned to ``printed`` when every printed author maps to
    exactly one arXiv author, else None."""
    out = []
    for p in printed:
        hits = [f for f in full if same_person(p, f)]
        if len(hits) != 1:
            return None
        out.append(hits[0])
    return out if len(set(out)) == len(out) else None


def query(title):
    words = [w for w in norm_title(title).split() if len(w) > 2 and w not in STOP]
    words = sorted(words, key=len, reverse=True)[:6]
    q = ' AND '.join(f'ti:{w}' for w in words)
    url = API + urllib.parse.urlencode({'search_query': q, 'max_results': 10})
    with urllib.request.urlopen(url, timeout=60) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall(f'{ATOM}entry'):
        out.append(dict(
            title=' '.join(e.find(f'{ATOM}title').text.split()),
            authors=[a.find(f'{ATOM}name').text.strip() for a in e.findall(f'{ATOM}author')],
            arxiv_id=re.sub(r'v\d+$', '', e.find(f'{ATOM}id').text.rsplit('/abs/', 1)[1])))
    return out


def main():
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    items = parse_accepted()
    todo = [p for p in items
            if str(p['pid']) not in cache
            or (cache[str(p['pid'])].get('unmatched') and cache[str(p['pid'])].get('q') != QUERY_VERSION)]
    print(f'{len(items)} accepted entries, {len(todo)} to query', flush=True)
    for n, p in enumerate(todo, 1):
        try:
            hits = query(p['title'])
        except Exception as e:  # network hiccup: leave uncached, retry next run
            print(f'  #{p["pid"]}: error {e}', flush=True)
            time.sleep(10)
            continue
        best = None
        for h in hits:
            ratio = difflib.SequenceMatcher(None, norm_title(h['title']), norm_title(p['title'])).ratio()
            names = authors_match(p['authors'], h['authors']) if ratio >= 0.93 else None
            if names:
                best = dict(h, authors=names, arxiv_authors=h['authors'], ratio=round(ratio, 3))
                break
        cache[str(p['pid'])] = best or {'unmatched': True, 'q': QUERY_VERSION,
                                        'candidates': [h['title'] for h in hits[:3]]}
        print(f'  [{n}/{len(todo)}] #{p["pid"]}: {"OK " + best["arxiv_id"] if best else "--"}  {p["title"][:60]}',
              flush=True)
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True))
        time.sleep(3.1)
    ok = sum(1 for v in cache.values() if not v.get('unmatched'))
    print(f'matched {ok}/{len(cache)}')


if __name__ == '__main__':
    main()
