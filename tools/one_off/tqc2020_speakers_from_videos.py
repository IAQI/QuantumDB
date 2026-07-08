#!/usr/bin/env python3
"""One-off: set TQC 2020 talk presenters (and video links) from the day recordings.

TQC 2020 was virtual; talks were streamed as four full-day recordings
("TQC 2020: Day 1..4" on the @TQC2020 channel). Each day description carries a
timestamped schedule, so every talk maps to a day-video + offset. Seeking there
shows the talk's title card, which marks the presenter (name shown prominently /
underlined / highlighted, and YouTube's webcam name label). workshop.csv had the
`speakers` column seeded with the full author list (no single presenter known) and
no video links at all.

This script embeds the video-derived presenter mapping (title -> presenter +
confidence) and the per-talk day-video offset, then:
  - writes the HIGH-confidence presenters into `speakers`, canonicalized to each
    row's author spelling (so the importer resolves presenter_author_id),
  - sets `video_url` to the timestamped day-video link and `youtube_id` to the day
    video for every mapped talk.
MEDIUM/LOW rows keep their existing `speakers` (listed for manual review).

Report-only by default; pass --write to update workshop.csv.

Usage:
    python3 tools/one_off/tqc2020_speakers_from_videos.py [--write]
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[2] / "data/conferences/tqc_2020/workshop.csv"

# title -> (presenter, confidence). Read off each talk's TQC 2020 day-video title card.
PRESENTERS = {
    'A Framework of Quantum Strong Exponential-Time Hypotheses': ('Subhasree Patro', 'HIGH'),
    'A Scalable Decoder Micro-architecture for Fault-Tolerant Quantum Computing': ('Christopher A. Pattison', 'HIGH'),
    'A device-independent protocol for XOR oblivious transfer': ('Srijita Kundu', 'HIGH'),
    'Approximate tensor decompositions: disappearance of all separations': ('Andreas Klingler', 'HIGH'),
    'Beyond the swap test: efficient estimation of distances between quantum states': ('Marco Fanizza', 'HIGH'),
    'Building trust for continuous variable quantum states': ('Ulysse Chabaud', 'HIGH'),
    'Computing partition functions in the one clean qubit model': ('Anirban Chowdhury', 'HIGH'),
    'Convergence rates for the quantum central limit theorem': ('Ludovico Lami', 'HIGH'),
    'Efficient unitary designs with a system size independent number of non-Clifford gates': ('Jonas Haferkamp', 'HIGH'),
    'Encoding classical information into quantum resources': ('Kamil Korzekwa', 'HIGH'),
    'Exponential quantum communication reductions from generalizations of the Boolean Hidden Matching problem': ('João Fernando Doriguello', 'HIGH'),
    'Extendibility of bosonic Gaussian states': ('Gerardo Adesso', 'HIGH'),
    'Fast and effective techniques for T-count reduction via spider nest identities': ('Niel de Beaudrap', 'HIGH'),
    'Faster quantum and classical SDP approximations for quadratic binary optimization': ('Daniel Stilck França', 'HIGH'),
    'Fault-tolerant quantum gates with defects in topological stabiliser codes': ('Paul Webster', 'HIGH'),
    'Improved Approximate Degree Bounds For k-distinctness': ('Shuchen Zhu', 'HIGH'),
    'Models of quantum complexity growth': ('Nick Hunter-Jones', 'HIGH'),
    'Non-Pauli Stabilizers from Twisted Quantum Doubles': ('Julio Carlos Magdalena de la Fuente', 'HIGH'),
    'Non-additivity in classical-quantum wiretap channels': ('Arkin Tikku', 'HIGH'),
    'On Quantum Complexity for Closest Pair and Orthogonal Vectors': ('Ruizhe Zhang', 'HIGH'),
    'On the complexity of zero gap MIP*': ('Seyed Sajjad Nezhadi', 'HIGH'),
    'On the modified logarithmic Sobolev inequality for the heat-bath dynamics for 1D systems': ('Ángela Capel', 'HIGH'),
    'Optimal Protocols in Quantum Annealing and QAOA Problems': ('Lucas T. Brady', 'HIGH'),
    'Playing Games with Multiple Access Channels': ('Felix Leditzky', 'HIGH'),
    'Quantifying quantum speedups: improved classical simulation from tighter magic monotones': ('James Seddon', 'HIGH'),
    'Quantum Coupon Collector': ('Ronald de Wolf', 'HIGH'),
    'Quantum Distributed Algorithm for Triangle Finding in the CONGEST Model': ('Frédéric Magniez', 'HIGH'),
    'Quantum algorithms for computational geometry problems': ('Nikita Larka', 'HIGH'),
    'Quantum circuit approximations and entanglement renormalization for the Dirac field in 1+1 dimensions': ('Freek Witteveen', 'HIGH'),
    'Quantum flags, and new bounds on the quantum capacity of the depolarizing channel': ('Farzad Kianvash', 'HIGH'),
    'Quasirandom quantum channels': ('Farrokh Labib', 'HIGH'),
    'Second-order asymptotics of quantum data compression and state merging': ('Dina Abdelhadi', 'HIGH'),
    'Self-testing of a single quantum device under computational assumptions': ('Tony Metger', 'HIGH'),
    'Semi-device-independent certification of indefinite causal order': ('Jessica Bavaresco', 'HIGH'),
    'Simpler Proofs of Quantumness': ('Venkata Koppula', 'HIGH'),
    'Slightly beyond product state approximations for a quantum analogue of Max Cut': ('Karen Morenz', 'HIGH'),
    'Spectral Quantum Tomography': ('Jonas Helsen', 'HIGH'),
    'Strictly linear light cones in long-range interacting systems of arbitrary dimensions': ('Tomotaka Kuwahara', 'HIGH'),
    'Tight Quantum Lower Bound for Approximate Counting with Quantum States': ('Aleksandrs Belovs', 'HIGH'),
    'Towards Quantum One-Time Memories from Stateless Hardware': ('Sevag Gharibian', 'HIGH'),
    'Uncloneable Quantum Encryption via Oracles': ('Sébastien Lord', 'HIGH'),
}

# title -> (day_video_id, offset_seconds). From the day descriptions' timestamped schedule.
VIDEO = {
    'A Framework of Quantum Strong Exponential-Time Hypotheses': ('Y0gdvvzuADY', 10060),
    'A Scalable Decoder Micro-architecture for Fault-Tolerant Quantum Computing': ('sc_rWyCVZRY', 20412),
    'A device-independent protocol for XOR oblivious transfer': ('EOV19AtJR8o', 3023),
    'Approximate tensor decompositions: disappearance of all separations': ('EOV19AtJR8o', 13755),
    'Beyond the swap test: efficient estimation of distances between quantum states': ('Hkq8MwISUD4', 20902),
    'Building trust for continuous variable quantum states': ('sc_rWyCVZRY', 10925),
    'Computing partition functions in the one clean qubit model': ('sc_rWyCVZRY', 17158),
    'Convergence rates for the quantum central limit theorem': ('EOV19AtJR8o', 7356),
    'Efficient unitary designs with a system size independent number of non-Clifford gates': ('EOV19AtJR8o', 18412),
    'Elena Kirshanova: Quantum speed-ups for sieving algorithms for the shortest vector problem': ('Y0gdvvzuADY', 149),
    'Encoding classical information into quantum resources': ('Y0gdvvzuADY', 6650),
    'Exponential quantum communication reductions from generalizations of the Boolean Hidden Matching problem': ('EOV19AtJR8o', 15161),
    'Extendibility of bosonic Gaussian states': ('EOV19AtJR8o', 8928),
    'Fast and effective techniques for T-count reduction via spider nest identities': ('sc_rWyCVZRY', 21960),
    'Faster quantum and classical SDP approximations for quadratic binary optimization': ('EOV19AtJR8o', 10629),
    'Fault-tolerant quantum gates with defects in topological stabiliser codes': ('Hkq8MwISUD4', 5145),
    'Improved Approximate Degree Bounds For k-distinctness': ('Y0gdvvzuADY', 12958),
    'Improved local spectral gap thresholds for lattices of finite dimension': ('sc_rWyCVZRY', 14137),
    'Models of quantum complexity growth': ('EOV19AtJR8o', 21507),
    'Non-Pauli Stabilizers from Twisted Quantum Doubles': ('Hkq8MwISUD4', 6714),
    'Non-additivity in classical-quantum wiretap channels': ('sc_rWyCVZRY', 2874),
    'On Quantum Complexity for Closest Pair and Orthogonal Vectors': ('Y0gdvvzuADY', 11739),
    'On the complexity of zero gap MIP*': ('EOV19AtJR8o', 16567),
    'On the modified logarithmic Sobolev inequality for the heat-bath dynamics for 1D systems': ('Hkq8MwISUD4', 3080),
    'Optimal Protocols in Quantum Annealing and QAOA Problems': ('sc_rWyCVZRY', 18721),
    'Optimizing the fundamental limits for quantum and private communication': ('Y0gdvvzuADY', 5025),
    'Playing Games with Multiple Access Channels': ('Hkq8MwISUD4', 17717),
    'Quantifying quantum speedups: improved classical simulation from tighter magic monotones': ('Hkq8MwISUD4', 8400),
    'Quantum Coupon Collector': ('sc_rWyCVZRY', 8904),
    'Quantum Distributed Algorithm for Triangle Finding in the CONGEST Model': ('EOV19AtJR8o', 12288),
    'Quantum algorithms for computational geometry problems': ('Nikita Larka', 'HIGH'),
    'Quantum circuit approximations and entanglement renormalization for the Dirac field in 1+1 dimensions': ('Hkq8MwISUD4', 1626),
    'Quantum flags, and new bounds on the quantum capacity of the depolarizing channel': ('Y0gdvvzuADY', 5025),
    'Quasirandom quantum channels': ('EOV19AtJR8o', 5017),
    'Second-order asymptotics of quantum data compression and state merging': ('Y0gdvvzuADY', 8288),
    'Self-testing of a single quantum device under computational assumptions': ('Y0gdvvzuADY', 3401),
    'Semi-device-independent certification of indefinite causal order': ('Hkq8MwISUD4', 19360),
    'Simpler Proofs of Quantumness': ('Hkq8MwISUD4', 22352),
    'Slightly beyond product state approximations for a quantum analogue of Max Cut': ('sc_rWyCVZRY', 15554),
    'Spectral Quantum Tomography': ('sc_rWyCVZRY', 12358),
    'Strictly linear light cones in long-range interacting systems of arbitrary dimensions': ('Hkq8MwISUD4', 204),
    'Thomas Monz: Experimental quantum error correction: from qubit loss to lattice surgery': ('sc_rWyCVZRY', 193),
    'Tight Quantum Lower Bound for Approximate Counting with Quantum States': ('sc_rWyCVZRY', 6000),
    'Towards Quantum One-Time Memories from Stateless Hardware': ('Hkq8MwISUD4', 10569),
    'Uncloneable Quantum Encryption via Oracles': ('Hkq8MwISUD4', 12293),
    'Unitary designs from statistical mechanics in random quantum circuits': ('EOV19AtJR8o', 20021),
}


def name_tokens(s):
    s = re.sub(r"\([^)]*\)", " ", s).replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ł", "l").replace("Ł", "l")
    return [t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if t]


def canonical_author(name, authors):
    nt = name_tokens(name)
    if not nt:
        return None
    best, best_score = None, 0
    for a in authors:
        at = name_tokens(a)
        if at and nt[-1] == at[-1] and len(set(nt) & set(at)) > best_score:
            best, best_score = a, len(set(nt) & set(at))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="update workshop.csv (default: report only)")
    args = ap.parse_args()

    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    applied, links, skipped, mism = [], 0, [], []
    for r in rows:
        title = r["title"]
        if title in VIDEO:
            vid, t = VIDEO[title]
            r["video_url"] = f"https://www.youtube.com/watch?v={vid}&t={t}s"
            r["youtube_id"] = vid
            links += 1
        entry = PRESENTERS.get(title)
        if not entry:
            continue
        presenter, conf = entry
        if conf != "HIGH" or not presenter:
            skipped.append((conf, presenter, title))
            continue
        authors = [a.strip() for a in r["authors"].split(";") if a.strip()]
        canon = canonical_author(presenter, authors)
        if canon is None:
            mism.append((presenter, authors, title))
            continue
        r["speakers"] = canon
        applied.append((canon, title))

    print(f"=== APPLIED presenters ({len(applied)} HIGH) ; video links set ({links}) ===")
    for canon, title in applied:
        print(f"  {canon:<28} | {title[:52]}")
    print(f"\n=== SKIPPED for manual review ({len(skipped)}: MEDIUM/LOW) ===")
    for conf, sp, title in skipped:
        print(f"  [{conf}] {sp or '(unresolved)':<24} | {title[:50]}")
    if mism:
        print(f"\n=== presenter NOT matched to any author ({len(mism)}) ===")
        for sp, authors, title in mism:
            print(f"  {sp!r} not in {authors}  ({title[:40]})")

    if args.write:
        with CSV_PATH.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\r\n")
            w.writeheader()
            w.writerows(rows)
        print(f"\nWROTE {CSV_PATH}")
    else:
        print("\n(report only; pass --write to update workshop.csv)")


if __name__ == "__main__":
    main()
