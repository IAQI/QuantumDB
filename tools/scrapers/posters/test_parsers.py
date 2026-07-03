#!/usr/bin/env python3
"""Lightweight assert-based tests for the poster parsers (no pytest needed).

Run: ``python3 tools/scrapers/posters/test_parsers.py``
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scrapers.posters import parsers  # noqa: E402
from scrapers.posters.parsers import split_authors, _split_authors_dot_title  # noqa: E402


def test_split_authors_semicolon_with_affiliation():
    names, affs = split_authors('Alice Ng (MIT); Bob Lee (Caltech)')
    assert names == ['Alice Ng', 'Bob Lee'], names
    assert affs == ['MIT', 'Caltech'], affs


def test_split_authors_semicolon_inside_affiliation():
    # The ';' inside the parenthetical must NOT split the author (regression:
    # QCrypt 2020 poster with a two-affiliation author).
    cell = 'Fumiki Katsuoka (Org A, Univ; Center B, Univ); Yasunobu Okamura (Org A, Univ)'
    names, affs = split_authors(cell)
    assert names == ['Fumiki Katsuoka', 'Yasunobu Okamura'], names
    assert ';' not in affs[0], affs  # folded to a comma so the CSV cell stays aligned


def test_split_authors_and_comma():
    names, affs = split_authors('Alice Ng, Bob Lee and Carol Yu')
    assert names == ['Alice Ng', 'Bob Lee', 'Carol Yu'], names
    assert affs == ['', '', '']


def test_split_authors_comma_protected_by_parens():
    names, _ = split_authors('Alice Ng (Lund University, Sweden), Bob Lee (ICFO, Spain)')
    assert names == ['Alice Ng', 'Bob Lee'], names


def test_split_authors_nested_paren_affiliation():
    # TQC 2025 regression: affiliation with nested parens + internal commas must
    # be pulled off whole, not left mangled in the author name.
    cell = ('Gautam Vemuri (Department of Physics, Indiana University-Purdue '
            'University Indianapolis (IUPUI) Indianapolis, IN 46202-3273, USA)')
    names, affs = split_authors(cell)
    assert names == ['Gautam Vemuri'], names
    assert affs[0].startswith('Department of Physics'), affs
    assert affs[0].endswith('USA'), affs


def test_split_authors_unbalanced_paren_affiliation():
    # TQC 2025 regression: the source left the affiliation paren unclosed
    # ("… (Guangzhou)" with no outer close). Name is the text before the '('.
    cell = 'Xin Wang (The Hong Kong University of Science and Technology (Guangzhou)'
    names, affs = split_authors(cell)
    assert names == ['Xin Wang'], names
    assert affs[0].startswith('The Hong Kong'), affs


def test_split_authors_and_inside_affiliation_not_split():
    # " and " inside a parenthetical affiliation must not spawn bogus authors,
    # and must survive in the affiliation text (not be folded to a comma).
    cell = ('Swati Choudhary (Harish-Chandra Research Institute (India) and '
            'Center for X (CQST)), Ujjwal Sen (HRI)')
    names, affs = split_authors(cell)
    assert names == ['Swati Choudhary', 'Ujjwal Sen'], names
    assert 'and' in affs[0], affs


def test_split_authors_recases_all_caps():
    names, _ = split_authors('YANGYANG FEI; N C RANDEEP; ZHI MA')
    assert names == ['Yangyang Fei', 'N C Randeep', 'Zhi Ma'], names


def test_split_authors_recases_all_lower():
    names, _ = split_authors('yicheng shi; juan de dios')
    assert names == ['Yicheng Shi', 'Juan de Dios'], names


def test_split_authors_capitalises_leading_lowercase_first_name():
    # Mixed-case scrape typo: lowercase first name, correct surname.
    names, _ = split_authors('jonathan Oppenheim')
    assert names == ['Jonathan Oppenheim'], names


def test_split_authors_preserves_maiden_name_paren():
    # A non-trailing parenthetical (maiden name) is NOT an affiliation.
    names, affs = split_authors('Justyna (Pytel) Zwolak')
    assert names == ['Justyna (Pytel) Zwolak'], names
    assert affs == [''], affs


def test_split_authors_strips_honorific():
    names, _ = split_authors('Dr. Colin Benjamin')
    assert names == ['Colin Benjamin'], names


def test_split_authors_collapses_source_doubled_names():
    # Source-level doubling seen in the qip_2016 / tqc_2025 mirrors.
    assert split_authors('Nike Dattani Dattani')[0] == ['Nike Dattani']
    assert split_authors('Myungshik Kim Kim')[0] == ['Myungshik Kim']
    assert split_authors('Mizanur Mizanur Rahaman')[0] == ['Mizanur Rahaman']
    assert (split_authors('Subhendu Bikash Ghosh Subhendu Bikash Ghosh')[0]
            == ['Subhendu Bikash Ghosh'])


def test_split_authors_keeps_repeated_initials():
    # Double initials are real names, not doubling artifacts.
    assert split_authors('Maneesha K K')[0] == ['Maneesha K K']


def test_dot_title_protects_initials():
    authors, title = _split_authors_dot_title('Alexander R. Dixon and Zhiliang Yuan. A QKD system')
    assert authors == 'Alexander R. Dixon and Zhiliang Yuan', authors
    assert title == 'A QKD system', title


def test_bibtex_year_filter_and_authors():
    text = (
        '@Poster{P24_1,\ntitle = {Quantum Foo},\nauthor = {Jane Doe and John Roe},\n'
        'year  = {2024},\nkeywords = {Poster session Monday},\ntppubtype = {Poster}\n}\n'
        '@Poster{P23_1,\ntitle = {Bar},\nauthor = {A B},\nyear = {2023},\n'
        'tppubtype = {Poster}\n}\n'
    )
    got = parsers.parse_tqc_bibtex(text, 2024)
    assert len(got) == 1, got
    assert got[0]['title'] == 'Quantum Foo'
    assert got[0]['authors'] == ['Jane Doe', 'John Roe']
    assert got[0]['session_name'] == 'Poster session Monday'


def test_pdf_2col_wrapping():
    text = (
        ' 1 Alice Ng and Bob Lee            Short title\n'
        ' 2 Carol Yu, Dan Ho and Eve        A title that wraps across\n'
        '                                   two output lines\n'
    )
    got = parsers.parse_qip_pdf_2col(text)
    assert len(got) == 2, got
    assert got[1]['title'] == 'A title that wraps across two output lines', got[1]
    assert got[1]['authors'] == ['Carol Yu', 'Dan Ho', 'Eve'], got[1]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
