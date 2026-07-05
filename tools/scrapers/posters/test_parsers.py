#!/usr/bin/env python3
"""Lightweight assert-based tests for the poster parsers (no pytest needed).

Run: ``python3 tools/scrapers/posters/test_parsers.py``
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scrapers.posters import parsers  # noqa: E402
from scrapers.posters.parsers import split_authors, _split_authors_dot_title  # noqa: E402
from scrapers.posters.runner import _dedupe_rows  # noqa: E402


def _row(title, authors='', affiliations='', abstract='', session_name=''):
    return {'title': title, 'authors': authors, 'affiliations': affiliations,
            'abstract': abstract, 'session_name': session_name}


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


def test_qip_2026_posters_with_presenter():
    from bs4 import BeautifulSoup
    html = (
        '<div class="genericText"><h2>Poster Session 1</h2>'
        '<p><strong>Monday, January 26 17:30-19:30</strong></p><ol>'
        # presenter underlined; also repeated at the end (source artifact -> dedup)
        '<li><strong>Fourier Structure</strong> <u>Zhijian Lai</u>, Jiang Hu, <u>Zhijian Lai</u></li>'
        # two underlined presenters
        '<li><strong>Self-testing games</strong> <u>Matthijs Vernooij</u>, <u>Yuming Zhao</u></li>'
        # empty placeholder li -> skipped
        '<li> </li>'
        '</ol></div>'
        '<div class="genericText"><h2>Poster Session 2</h2>'
        '<p><strong>Tuesday, Jannuary 27 17:30-19:30</strong></p><ol>'
        '<li><strong>Uncloneable Encryption</strong> <u>Eric Culf</u></li>'
        '</ol></div>'
    )
    got = parsers.parse_qip_2026(BeautifulSoup(html, 'html.parser'))
    assert len(got) == 3, got
    p0 = got[0]
    assert p0['title'] == 'Fourier Structure', p0
    assert p0['authors'] == ['Zhijian Lai', 'Jiang Hu'], p0  # doubled presenter collapsed
    assert p0['speakers'] == ['Zhijian Lai'], p0
    assert p0['session_name'] == 'Poster Session 1', p0
    assert p0['scheduled_date'] == '2026-01-26', p0
    assert got[1]['speakers'] == ['Matthijs Vernooij', 'Yuming Zhao'], got[1]
    assert got[2]['scheduled_date'] == '2026-01-27', got[2]  # typo'd month still maps
    assert got[2]['speakers'] == ['Eric Culf'], got[2]


def test_qip_2026_collapses_presenter_name_variant():
    # Source artifact: the presenter is repeated as an initials-only variant
    # ("Sean R. Muleady" ... "Sean Muleady"). Both must collapse to one author,
    # or the importer's fuzzy match rejects the duplicate authorship.
    from bs4 import BeautifulSoup
    html = (
        '<div class="genericText"><h2>Poster Session 1</h2><ol>'
        '<li><strong>Sensor networks</strong> Erfan A, <u>Sean Muleady</u>, '
        'Sean R. Muleady</li></ol></div>'
    )
    got = parsers.parse_qip_2026(BeautifulSoup(html, 'html.parser'))
    assert got[0]['authors'] == ['Erfan A', 'Sean Muleady'], got[0]
    assert got[0]['speakers'] == ['Sean Muleady'], got[0]


def test_dedupe_merges_sessions_across_pages():
    # QCRYPT 2022: the in-person session (poster3) re-lists posters already in
    # sessions 1/2. The duplicate collapses to one row recording both sessions.
    rows = [
        _row('Quantum cryptography for quantum metrology', authors='A;B',
             session_name='Poster Session 1'),
        _row('Some other poster', authors='C', session_name='Poster Session 2'),
        _row('Quantum Cryptography for Quantum Metrology', authors='A;B',
             session_name='Poster Session 3 (In-person)'),
    ]
    out = _dedupe_rows(rows)
    assert len(out) == 2, out
    assert out[0]['session_name'] == 'Poster Session 1; Poster Session 3 (In-person)', out[0]
    assert out[1]['title'] == 'Some other poster', out[1]  # order preserved


def test_dedupe_keeps_richest_copy():
    # TQC 2025 source doubling: same poster twice, one copy with a fuller author
    # list -> the richer copy survives.
    rows = [
        _row('A Tokenized Signature Scheme', authors='Das'),
        _row('A Tokenized Signature Scheme', authors='Venkatachalam;Ghosh;Das',
             affiliations='X;Y;Z'),
    ]
    out = _dedupe_rows(rows)
    assert len(out) == 1, out
    assert out[0]['authors'] == 'Venkatachalam;Ghosh;Das', out[0]


def test_dedupe_leaves_distinct_titles_and_empties():
    rows = [
        _row('Paper One', authors='A'),
        _row('Paper Two', authors='B'),
        _row('', authors='C'),  # empty title never merged
        _row('', authors='D'),
    ]
    out = _dedupe_rows(rows)
    assert len(out) == 4, out


def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, 'html.parser')


def test_qcrypt_2012_li_spans():
    html = (
        '<h3 id="posters">Posters</h3><ul>'
        '<li><span class="talk-title">A Decoupling Approach</span><br>'
        '<span class="talk-authors">Frédéric Dupuis, Oleg Szehr and Marco Tomamichel</span></li>'
        '<li><span class="talk-title">A high speed generator</span><br>'
        '<span class="talk-authors">Thomas Symul and Ping Koy Lam</span></li>'
        '</ul>'
        # A stray schedule <ul> using the same span class must NOT be picked up.
        '<ul><li><span class="talk-title">09:00 Coffee</span></li></ul>'
    )
    got = parsers.parse_qcrypt_2012(_soup(html))
    assert len(got) == 2, got
    assert got[0]['title'] == 'A Decoupling Approach', got[0]
    assert got[0]['authors'] == ['Frédéric Dupuis', 'Oleg Szehr', 'Marco Tomamichel'], got[0]


def test_qcrypt_2014_area_tagged_list():
    html = (
        '<ul>'
        '<li>[Area 4] <strong>Fault-tolerant QKD over a collective-noise channel</strong>, Li Chunyan</li>'
        '<li>[Area 3] <strong>Direct Counterfactual Communication</strong>, Zhu Cao and Alice Ng</li>'
        '</ul>'
        '<p>Best Poster Award (selected by popular vote)</p>'
        # award winner repeated -> must be de-duplicated by title
        '<ul><li>[Area 3] <strong>Direct Counterfactual Communication</strong>, Zhu Cao and Alice Ng</li></ul>'
    )
    got = parsers.parse_qcrypt_2014(_soup(html))
    assert len(got) == 2, got  # duplicate award entry collapsed
    assert got[0]['title'] == 'Fault-tolerant QKD over a collective-noise channel', got[0]
    assert got[0]['authors'] == ['Li Chunyan'], got[0]
    assert got[0]['session_name'] == 'Area 4', got[0]
    assert got[1]['authors'] == ['Zhu Cao', 'Alice Ng'], got[1]


def test_qcrypt_2015_emphasis_then_authors():
    html = (
        '<p>1. <em><strong>Long distance MDI-QKD</strong></em><br>'
        'Chen Dong, Shanghong Zhao and Ying Sun'
        '<img src="icon.png"/></p>'
    )
    got = parsers.parse_qcrypt_2015(_soup(html))
    assert len(got) == 1, got
    assert got[0]['title'] == 'Long distance MDI-QKD', got[0]
    assert got[0]['authors'] == ['Chen Dong', 'Shanghong Zhao', 'Ying Sun'], got[0]


def test_qcrypt_2019_table():
    html = (
        '<h1>Poster Session Monday</h1><table>'
        '<tr><td>Poster Number</td><td>Author</td><td>Title</td></tr>'
        '<tr><td>1</td><td>Xiang-Bin Wang.</td><td>Two protocols in Twin-Field QKD.</td></tr>'
        '<tr><td>3</td><td>Toyohiro Tsurumaru.</td><td>Leftover hashing.</td></tr>'
        '</table>'
    )
    got = parsers.parse_qcrypt_2019(_soup(html))
    assert len(got) == 2, got
    assert got[0]['authors'] == ['Xiang-Bin Wang'], got[0]  # trailing '.' stripped
    assert got[0]['title'] == 'Two protocols in Twin-Field QKD', got[0]
    assert got[0]['session_name'] == 'Poster Session Monday', got[0]


def test_qip_2013_strong_br_title_with_sessions():
    html = (
        '<p><strong>SESSION 1</strong></p>'
        '<p><strong>3. Jun Zhou and Jun Song</strong><br>A new squeezed coherent state</p>'
        '<p><strong>SESSION 2</strong></p>'
        '<p><strong>150. Oleg Gittsovich and John Donohue</strong><br>Entanglement verification</p>'
    )
    got = parsers.parse_qip_2013(_soup(html))
    assert len(got) == 2, got
    assert got[0]['authors'] == ['Jun Zhou', 'Jun Song'], got[0]
    assert got[0]['title'] == 'A new squeezed coherent state', got[0]
    assert got[0]['session_name'] == 'SESSION 1', got[0]
    assert got[1]['session_name'] == 'SESSION 2', got[1]


def test_qip_2014_div_paper_spans():
    html = (
        '<h2>QIP 2014 Monday Poster Session</h2>'
        '<div class="paper"><span class="authors"><span>Alice Ng and Bob Lee</span>. </span>'
        '<span class="title">Robust bidirectional communication</span></div>'
    )
    got = parsers.parse_qip_2014(_soup(html))
    assert len(got) == 1, got
    assert got[0]['authors'] == ['Alice Ng', 'Bob Lee'], got[0]
    assert got[0]['title'] == 'Robust bidirectional communication', got[0]
    assert got[0]['session_name'] == 'QIP 2014 Monday Poster Session', got[0]


def test_qip_2024_tables_skip_not_presenting():
    html = (
        '<p>Poster Presentation Session on Jan. 15 (Monday)</p>'
        '<table><tr><td>No.</td><td>Title</td><td>Authors</td></tr>'
        '<tr><td>2</td><td>Quantum Advantage</td><td>Tomoyuki Morimae and Takashi Yamakawa</td></tr>'
        '</table>'
        '<p>Not Presenting</p>'
        '<table><tr><td>No.</td><td>Title</td><td>Authors</td></tr>'
        '<tr><td>99</td><td>Withdrawn paper</td><td>Nobody</td></tr>'
        '</table>'
    )
    got = parsers.parse_qip_2024(_soup(html))
    assert len(got) == 1, got  # the "Not Presenting" table is excluded
    assert got[0]['title'] == 'Quantum Advantage', got[0]
    assert got[0]['authors'] == ['Tomoyuki Morimae', 'Takashi Yamakawa'], got[0]
    assert got[0]['scheduled_date'] == '2024-01-15', got[0]


def test_qip_2017_pdf_columns_wrapped_title():
    text = (
        '  1    Localization effects in the circuit' + ' ' * 8 + 'Adrian Chapman and Akimasa Miyake\n'
        '       efficient exact calculation\n'
        '\n'
        '  2    Conditional mutual information' + ' ' * 12 + 'Eneet Kaur and Mark Wilde\n'
    )
    got = parsers.parse_qip_2017_pdf(text)
    assert len(got) == 2, got
    assert got[0]['title'] == 'Localization effects in the circuit efficient exact calculation', got[0]
    assert got[0]['authors'] == ['Adrian Chapman', 'Akimasa Miyake'], got[0]


def test_qip_2021_pdf_authors_left_skips_footer():
    text = (
        'Monday – Poster Session A\n'
        'Room A.1\n'
        'A.1.1   Alice Ng, Bob Lee,' + ' ' * 15 + 'Excitation dynamics\n'
        '        Carol Yu' + ' ' * 25 + 'in coupled circuits\n'
        'POSTER SESSION A, MONDAY FEB 1ST 9 PM - 11 PM CET\n'
        'Room A.2\n'
        'A.2.1   Dan Fox' + ' ' * 25 + 'Quantum stuff\n'
    )
    got = parsers.parse_qip_2021_pdf(text)
    assert len(got) == 2, got
    assert got[0]['authors'] == ['Alice Ng', 'Bob Lee', 'Carol Yu'], got[0]
    assert got[0]['title'] == 'Excitation dynamics in coupled circuits', got[0]
    assert got[0]['session_name'] == 'Monday – Poster Session A', got[0]
    # The running footer must not leak into A.2.1's authors.
    assert got[1]['authors'] == ['Dan Fox'], got[1]
    assert 'CET' not in ';'.join(got[1]['authors']), got[1]


def test_qip_2023_pdf_centered_tiebreak_and_not_presenting():
    # ID 48 sits on a line BELOW its content, equidistant from the full ID 47 and
    # the empty ID 48 -> the tie must resolve to the hungry ID 48, not merge into
    # ID 47 (regression: QIP 2023 posters 847/848).
    text = (
        'Monday session\n'
        '  ID   Title' + ' ' * 40 + 'Authors\n'
        '  47   First full poster' + ' ' * 25 + 'Alice and Bob\n'
        '       Second poster title' + ' ' * 23 + 'Carol and Dan\n'
        '  48\n'
        'Not presenting\n'
        '   Title' + ' ' * 40 + 'Authors\n'
        '       ghost' + ' ' * 35 + 'Nobody\n'
    )
    got = parsers.parse_qip_2023_pdf(text)
    assert len(got) == 2, got  # "Not presenting" section dropped
    assert got[0]['title'] == 'First full poster', got[0]
    assert got[0]['authors'] == ['Alice', 'Bob'], got[0]
    assert got[1]['title'] == 'Second poster title', got[1]
    assert got[1]['authors'] == ['Carol', 'Dan'], got[1]


def test_tqc_2022_byline_institution_split():
    # Authors are the comma-parts before the first institution; affiliation may
    # itself contain commas.
    names, aff = parsers._split_tqc_2022_byline(
        'Stephen Fenner, Rabins Wosti, University of South Carolina')
    assert names == ['Stephen Fenner', 'Rabins Wosti'], names
    assert aff == 'University of South Carolina', aff
    names, aff = parsers._split_tqc_2022_byline(
        'Harshavardhan Nareddula, Southern Illinois University, Carbondale')
    assert names == ['Harshavardhan Nareddula'], names
    assert aff == 'Southern Illinois University, Carbondale', aff


def test_tqc_2022_pdf_categories_and_wrapped_title():
    text = (
        '                       POSTER SESSION PROGRAM\n'
        'Siebel Center for Design\n'
        '\n'
        'Algorithms\n'
        '1. Avah Banerjee, Missouri University of Science and Technology\n'
        '   “Discrete Quantum Walks on the Symmetric Group”\n'
        'Foundations\n'
        '2. Luke Schaeffer, University of Waterloo\n'
        '   “Sample-optimal classical shadows for pure\n'
        '   states”\n'
        '                                INVITED SPEAKER ABSTRACTS\n'
    )
    got = parsers.parse_tqc_2022_pdf(text)
    assert len(got) == 2, got
    assert got[0]['session_name'] == 'Algorithms', got[0]
    assert got[0]['authors'] == ['Avah Banerjee'], got[0]
    # Wrapped quoted title is rejoined, not read as a category header.
    assert got[1]['title'] == 'Sample-optimal classical shadows for pure states', got[1]
    assert got[1]['session_name'] == 'Foundations', got[1]


def test_display_unicode_normalisation():
    from scrapers._lib import clean_display_name
    assert clean_display_name('Reﬁk Mansuroglu') == 'Refik Mansuroglu'   # ligature
    assert clean_display_name('Vı́ctor Zapatero') == 'Víctor Zapatero'    # dotless-i + accent
    assert clean_display_name('Elie Ass´emat') == 'Elie Assémat'         # spacing acute
    assert clean_display_name('Gómez') == 'Gómez'                        # decomposed -> composed


def test_qip_2023_session_table():
    # Indico session page: an <h2>…session</h2> heading + one ID|Title|Authors
    # table. The header row (non-numeric ID) is skipped; the "not presenting"
    # page is simply never passed to the parser. Authors are a prose "A, B and C"
    # list -> split into a semicolon list.
    from bs4 import BeautifulSoup
    html = (
        '<h1>Quantum Information Processing 2023</h1>'
        '<h2>Choose timezone</h2><h2>Monday session</h2>'
        '<table>'
        '<tr><td class="QIPtd">ID</td><td class="QIPtd">Title</td><td class="QIPtd">Authors</td></tr>'
        '<tr><td class="QIPtd">7</td><td class="QIPtd">Relation between features</td>'
        '<td class="QIPtd">Sooryansh Asthana and V. Ravishankar</td></tr>'
        '<tr><td class="QIPtd">18</td><td class="QIPtd">Out-of-distribution generalization</td>'
        '<td class="QIPtd">Matthias C. Caro, Nic Ezzell and Zoe Holmes</td></tr>'
        '</table>'
    )
    got = parsers.parse_qip_2023(BeautifulSoup(html, 'html.parser'))
    assert len(got) == 2, got  # header row skipped
    assert got[0]['session_name'] == 'Monday session', got[0]
    assert got[0]['authors'] == ['Sooryansh Asthana', 'V. Ravishankar'], got[0]
    # regression: the full leading author is kept, not truncated to a lone surname
    assert got[1]['authors'] == ['Matthias C. Caro', 'Nic Ezzell', 'Zoe Holmes'], got[1]


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
