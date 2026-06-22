#!/usr/bin/env python3
"""One-off: repair author/committee anomalies in the source CSVs.

Each conference's CSV is the source of truth; this script applies the targeted
corrections catalogued during the author-list anomaly cleanup. Idempotent where
possible (re-running is a no-op once the strings are fixed). See the cleanup plan
for the full rationale. Run from the repo root: `python tools/one_off/fix_author_anomalies.py`.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "data" / "conferences"


def load(rel):
    p = CONF / rel
    with open(p, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return p, r.fieldnames, list(r)


def save(p, fields, rows):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {p.relative_to(ROOT)} ({len(rows)} rows)")


def set_cell(rows, match, col, new, *, expect=1):
    n = 0
    for row in rows:
        if match(row):
            row[col] = new
            n += 1
    assert n == expect, f"expected {expect} matches, got {n} for col={col!r} new={new!r}"
    return n


def main():
    # ---- talks: qip_2010 (title/author text concatenation) ----
    p, fields, rows = load("qip_2010/talks.csv")
    set_cell(rows, lambda r: r["authors"].startswith("David Gross;Yi-Kai Liu;Steven Fla"),
             "authors", "David Gross;Yi-Kai Liu;Steven Flammia;Stephen Becker;Jens Eisert")
    set_cell(rows, lambda r: r["authors"].startswith("Dominic W. Berry;Andrew M. Childs The query"),
             "authors", "Dominic W. Berry;Andrew M. Childs")
    set_cell(rows, lambda r: r["speaker"] == "Dominic W. Berry" and not r["title"],
             "title", "Black-box Hamiltonian simulation and unitary implementation")
    set_cell(rows, lambda r: r["authors"].startswith("Maarten Van den Nest Simulating"),
             "authors", "Maarten Van den Nest")
    set_cell(rows, lambda r: r["speaker"] == "Maarten Van den Nest" and not r["title"],
             "title", "Simulating quantum computers with probabilistic methods")
    set_cell(rows, lambda r: r["authors"].startswith("Conference dinner >> After dinner"),
             "authors", "Gilles Brassard")
    set_cell(rows, lambda r: r["speaker"].startswith("Conference dinner >> After dinner"),
             "speaker", "Gilles Brassard")
    set_cell(rows, lambda r: r["title"] == "Silver Quantum Cryptography" and not r["affiliations"],
             "affiliations", "University of Montreal")
    save(p, fields, rows)

    # ---- talks: qip_2011 (parenthetical affiliations / presenter note) ----
    p, fields, rows = load("qip_2011/talks.csv")
    set_cell(rows, lambda r: "Robert Raussendorf (UBC)" in r["authors"],
             "authors", "Tzu-Chieh Wei;Ian Affleck;Robert Raussendorf;Akimasa Miyake")
    set_cell(rows, lambda r: "Talk presented by David Reeb" in r["authors"],
             "authors", "Teiko Heinosaari;Michael Wolf")
    save(p, fields, rows)

    # ---- talks: qip_2016 (author name leaked into title; truncated 'J') ----
    p, fields, rows = load("qip_2016/talks.csv")
    set_cell(rows, lambda r: r["title"].startswith("Ignacio Cirac. Rapid adiabatic"),
             "title", "Rapid adiabatic preparation of injective PEPS and Gibbs states")
    set_cell(rows, lambda r: r["authors"] == "Yimin Ge;Andras Molnar;J",
             "authors", "Yimin Ge;Andras Molnar;J. Ignacio Cirac")
    save(p, fields, rows)

    # ---- talks: qip_2021 (company appended to authors; real speakers known) ----
    p, fields, rows = load("qip_2021/talks.csv")
    set_cell(rows, lambda r: r["title"] == "Co-designing quantum computers at IQM",
             "authors", "Bruno Taketani")
    set_cell(rows, lambda r: r["title"] == "Co-designing quantum computers at IQM",
             "affiliations", "IQM")
    set_cell(rows, lambda r: r["title"] == "Quantum Computer Science at Google",
             "authors", "Cody Jones;Ryan Babbush")
    set_cell(rows, lambda r: r["title"] == "Quantum Computer Science at Google",
             "affiliations", "Google;Google")
    set_cell(rows, lambda r: r["title"] == "Demonstrating the capabilities of state-of-the-art quantum systems",
             "authors", "Sarah Sheldon")
    set_cell(rows, lambda r: r["title"] == "Demonstrating the capabilities of state-of-the-art quantum systems",
             "affiliations", "IBM")
    save(p, fields, rows)

    # ---- talks: qip_2023 ('Fred Chong and Jonathan Baker' -> two authors) ----
    p, fields, rows = load("qip_2023/talks.csv")
    set_cell(rows, lambda r: r["authors"] == "Fred Chong and Jonathan Baker",
             "authors", "Fred Chong;Jonathan Baker", expect=2)
    save(p, fields, rows)

    # ---- talks: qip_2025 / qip_2026 (strip parenthetical nicknames) ----
    for rel, repls in {
        "qip_2025/talks.csv": {
            "Seyed (Sajjad) Nezhadi": "Seyed Nezhadi",
            "Zhiyang He (Sunny)": "Zhiyang He",
            "ChunJun (Charles) Cao": "ChunJun Cao",
            "Yifan (Frank) Zhang": "Yifan Zhang",
        },
        "qip_2026/talks.csv": {
            "Hengyun (Harry) Zhou": "Hengyun Zhou",
            "Zhiyang (Sunny) He": "Zhiyang He",
            "Chi-Fang (Anthony) Chen": "Chi-Fang Chen",
            "Kathleen (Katie) Chang": "Kathleen Chang",
        },
    }.items():
        p, fields, rows = load(rel)
        total = 0
        for old, new in repls.items():
            for row in rows:
                if old in row["authors"]:
                    row["authors"] = row["authors"].replace(old, new)
                    total += 1
                if row.get("speaker") and old in row["speaker"]:
                    row["speaker"] = row["speaker"].replace(old, new)
        print(f"  {rel}: stripped {total} nickname token(s)")
        save(p, fields, rows)

    # ---- talks: QCRYPT_2025 (tilde, truncated name, column misalignment) ----
    p, fields, rows = load("QCRYPT_2025/talks.csv")
    for row in rows:
        if "Vadim~Makarov" in row["authors"]:
            row["authors"] = row["authors"].replace("Vadim~Makarov", "Vadim Makarov")
        if ";Wei-Chen;" in ";" + row["authors"] + ";":
            row["authors"] = row["authors"].replace("Wei-Chen", "Wei Chen")
    school = "School of Electronics and Communication Engineering, Sun Yat-Sen University, Shenzhen 518107, China"
    set_cell(rows, lambda r: r["authors"] == "Ye Chen;Zhiyu;Xiaodong;Ziran;Shihai",
             "authors", "Ye Chen;Zhiyu Tian;Xiaodong Fan;Ziran Xie;Shihai Sun")
    set_cell(rows, lambda r: r["affiliations"].startswith(school) and r["affiliations"].endswith(";Sun"),
             "affiliations", ";".join([school] * 5))
    save(p, fields, rows)

    # ---- talks: tqc_2025 workshop (parenthetical affil; trailing email) ----
    p, fields, rows = load("tqc_2025/workshop.csv")
    for row in rows:
        if "Iman Marvian (Duke University" in row["authors"]:
            row["authors"] = row["authors"].replace("Iman Marvian (Duke University", "Iman Marvian")
        if "Daniel Liang danliang@pdx.edu" in row["authors"]:
            row["authors"] = row["authors"].replace("Daniel Liang danliang@pdx.edu", "Daniel Liang")
    save(p, fields, rows)

    # ---- talks: qcrypt_2013 (delete the non-talk lab-tour row) ----
    p, fields, rows = load("qcrypt_2013/talks.csv")
    before = len(rows)
    rows = [r for r in rows if not r["title"].startswith("Tour of Institute for Quantum Computing")]
    assert len(rows) == before - 1, "expected to remove 1 tour row"
    save(p, fields, rows)

    # ---- committees: deletions (non-person rows) ----
    p, fields, rows = load("qcrypt_2013/committees.csv")
    before = len(rows)
    rows = [r for r in rows if r["full_name"] != "Facebook"]
    assert len(rows) == before - 1
    save(p, fields, rows)

    p, fields, rows = load("qip_2018/committees.csv")
    before = len(rows)
    rows = [r for r in rows if not r["full_name"].startswith("Lorentzweg")]
    assert len(rows) == before - 1
    save(p, fields, rows)

    # ---- committees: name / affiliation repairs ----
    p, fields, rows = load("qip_2016/committees.csv")
    set_cell(rows, lambda r: r["full_name"] == "Posters/Exhibition: Borzu Toloui", "full_name", "Borzu Toloui")
    set_cell(rows, lambda r: r["full_name"] == "Borzu Toloui", "role_title", "Posters/Exhibition")
    save(p, fields, rows)

    p, fields, rows = load("qcrypt_2022/committees.csv")
    set_cell(rows, lambda r: r["full_name"] == "Lim Ci Wen (Charles)", "full_name", "Lim Ci Wen")
    save(p, fields, rows)

    p, fields, rows = load("qip_2015/committees.csv")
    set_cell(rows, lambda r: r["full_name"] == "Ms Li Liu (UTS)", "role_title", "Registration & Payments")
    set_cell(rows, lambda r: r["full_name"] == "Ms Li Liu (UTS)", "affiliation", "UTS")
    set_cell(rows, lambda r: r["full_name"] == "Ms Li Liu (UTS)", "full_name", "Li Liu")
    save(p, fields, rows)

    p, fields, rows = load("qip_2017/committees.csv")
    set_cell(rows, lambda r: r["full_name"] == "Fang Song (Portland State U", "affiliation", "Portland State University")
    set_cell(rows, lambda r: r["full_name"] == "Fang Song (Portland State U", "full_name", "Fang Song")
    save(p, fields, rows)

    # qip_2014: the two LOC chair rows had the affiliation column = 'Chair'
    p, fields, rows = load("qip_2014/committees.csv")
    for nm, aff in (("Antonio Acín (ICFO)", "ICFO"), ("Emilio Bagan (UAB)", "UAB")):
        plain = nm.split(" (")[0]
        set_cell(rows, lambda r, nm=nm: r["full_name"] == nm, "position", "chair")
        set_cell(rows, lambda r, nm=nm: r["full_name"] == nm, "affiliation", aff)
        set_cell(rows, lambda r, nm=nm, plain=plain: r["full_name"] == nm, "full_name", plain)
    save(p, fields, rows)

    # ---- committees: qip_2023 (sponsoring junk + concatenated LOC block) ----
    p, fields, rows = load("qip_2023/committees.csv")
    set_cell(rows, lambda r: r["full_name"].startswith("SponsoringContact"), "full_name", "Gorjan Alagic")
    loc = [
        ("Nicolas Cerf", "Université libre de Bruxelles"),
        ("Nathan Goldman", "Université libre de Bruxelles"),
        ("Serge Massar", "Université libre de Bruxelles"),
        ("Ognyan Oreshkov", "Université libre de Bruxelles"),
        ("Stefano Pironio", "Université libre de Bruxelles"),
        ("Jérémie Roland", "Université libre de Bruxelles"),
        ("Kristiaan De Greve", "IMEC"),
        ("Céline Broeckaert", "Universiteit Gent"),
        ("Chanel Leong", "Universiteit Gent"),
        ("Karel Van Acoleyen", "Universiteit Gent"),
    ]
    idx = next(i for i, r in enumerate(rows) if r["full_name"].startswith("Université libre de BruxellesNicolas"))
    template = rows[idx]
    new_rows = []
    for name, aff in loc:
        nr = dict(template)
        nr["full_name"] = name
        nr["affiliation"] = aff
        new_rows.append(nr)
    rows[idx:idx + 1] = new_rows
    print(f"  qip_2023/committees.csv: expanded LOC block into {len(loc)} members")
    save(p, fields, rows)

    print("\nDone.")


if __name__ == "__main__":
    main()
