#!/usr/bin/env python3
"""One-off: fix QIP presenters that were seeded as "first author".

The historical QIP talk scraper (tools/one_off/historical/scrape_qip_talks_historical.py)
filled `speakers` with author_list[0] whenever the source page didn't mark a presenter.
The importer marks the speakers as the talk's presenters, so for QIP 2008,
2009, 2014, 2016 and 2024 every multi-author talk showed its first author as presenter
(reported by a site visitor for QIP 2014, 2026-11-13).

Policy: a multi-author talk keeps a presenter only if a source names it; otherwise
`speakers` is cleared and the talk has no presenter after re-import.
Single-author talks are untouched (the sole author is the presenter).

Sources:
  - QIP 2009: presenter in <b> on the archived homepage (qip.iaqi.org/2009/index.html,
    "Talks (in order of presentation)"); slide filenames agree.
  - QIP 2014: presenter in <b> in cgi-bin/talks/allprint.pl.html (35 of 45 talks; the
    archive lacks the rest of the schedule). Toby Cubitt's invited talk is not in that
    page; cgi-bin/speakers.pl.html lists him as the plenary speaker.
  - QIP 2024: the YouTube title suffix "..._<Speaker>" (video_title), or the talk's
    opening in YouTube auto-captions (video_captions: self-introduction, or the speaker
    naming every co-author but themselves), or a manual check of the recording
    (manual_video_check).
  - QIP 2008 (Program.pdf) and QIP 2016 (scientific-program.html) mark no presenter,
    so their multi-author talks are cleared.

Report-only by default; pass --write to update the talks.csv files. Then re-import:
    python3 tools/scrapers/import_from_csv.py talks data/conferences/qip_{2008,2009,2014,2016,2024}/talks.csv

Usage:
    python3 tools/one_off/fix_qip_first_author_presenters.py [--write]
"""
from __future__ import annotations

import argparse
import csv
import io
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YEARS = (2008, 2009, 2014, 2016, 2024)

# title -> presenters (canonical author spelling from talks.csv)
QIP_2009 = {'A generalized Grothendieck inequality and entanglement in XOR games': ['Jop Briet'],
 'A no-go theorem for a two-dimensional self-correcting quantum memory based on stabilizer codes': ['Sergey Bravyi'],
 'Analyzing Quantum Circuits Using the Least Action Principle': ['Wim van Dam'],
 'Approximate quantum error correction for correlated noise': ['Amnon Ta-Shma'],
 'Can non-private channels transmit quantum information?': ['John Smolin'],
 'Closed Timelike Curves Make Quantum and Classical Computing Equivalent': ['Scott Aaronson'],
 'Efficient Quantum Tensor Product Expanders and k-designs': ['Richard Low'],
 'Efficient discrete-time simulations of continuous-time quantum query algorithms': ['Rolando Somma'],
 'Exact entanglement renormalization for string-net models': ['Robert Koenig'],
 'Fault-tolerant quantum computing against highly biased noise': ['Panos Aliferis'],
 'Instantaneous Quantum Computation': ['Dan Shepherd'],
 'Interacting electrons, Density Functional Theory, and Quantum Merlin Arthur': ['Norbert Schuch'],
 'Key Distribution and Oblivious Transfer à la Merkle': ['Gilles Brassard'],
 'Lieb Robinson bounds and "supersonic quantum communication"': ['David Gross'],
 'Most quantum states are useless for measurement-based quantum computation': ['Steve Flammia'],
 'On Non-Locality Distillation': ['Dejan Dukaric'],
 'Oracularization and Two-Prover One-Round Interactive Proofs against Nonlocal Strategies': ['Tsuyoshi Ito'],
 'Postselection-technique with applications to quantum cryptography and the parallel repetition problem': ['Dejan '
                                                                                                           'Dukaric'],
 "Quantum Stein's Lemma for Correlated States and Asymptotic Entanglement Transformations": ['Fernando Brandao'],
 'Quantum boolean functions': ['Ashley Montanaro'],
 'Restrictions on Transversal Encoded Quantum Gate Sets': ['Bryan Eastin'],
 'The Fidelity Alternative and Quantum Measurement Simulation': ['Andreas Winter'],
 'The Operational Meaning of Min- and Max-Entropy': ['Christian Schaffner'],
 'The computational difficulty of finding MPS ground states': ['Norbert Schuch']}

QIP_2014 = {'A new quantum generalization of the Rényi divergence with applications to the strong converse in quantum channel coding': ['Marco '
                                                                                                                             'Tomamichel'],
 'A parallel repetition theorem for entangled projection games': ['Thomas Vidick'],
 'A polynomial-time algorithm for the ground state of 1D gapped local Hamiltonians': ['Umesh Vazirani'],
 'An improved Landauer Principle with finite-size corrections and applications to statistical physics': ['David Reeb'],
 'Bound entangled states with secret key and their classical counterpart': ['Maris Ozols'],
 'Classification of the complexity of local Hamiltonian problems': ['Ashley Montanaro'],
 'Decoupling with random quantum circuits': ['Omar Fawzi'],
 'Entanglement rates and area laws': ['Michaël Mariën'],
 'Entanglement sampling and applications': ['Omar Fawzi'],
 'Infinite randomness expansion and amplification with a constant number of devices': ['Matthew Coudron'],
 'Nested quantum walk': ['Stacey Jeffery'],
 'No psi-epistemic model can explain the indistinguishability of quantum states': ['Eric Cavalcanti'],
 'Noisy Interactive quantum communication': ['Dave Touchette'],
 'Purifications of multipartite states: limitations and constructive methods': ['Gemma De Las Cuevas'],
 'Quantum 3-SAT is QMA1-complete': ['David Gosset'],
 'Quantum Fourier transforms and the complexity of link invariants for quantum doubles of finite groups': ['Hari '
                                                                                                           'Krovi'],
 'Quantum interactive proofs and the complexity of entanglement detection': ['Mark Wilde'],
 'Quantum locally testable codes': ['Lior Eldar'],
 'Quantum simulation of sparse Hamiltonians and continuous queries with optimal error dependence': ['Robin Kothari'],
 'Quantum subdivision capacities and continuous-time quantum coding': ['Alexander Müller-Hermes'],
 'Robust device-independent randomness amplification with few devices': ['Karol Horodecki'],
 'Robust protocols for securely expanding randomness and distributing keys using untrusted quantum devices': ['Carl '
                                                                                                              'Miller'],
 'Stability of local quantum dissipative systems': ['Angelo Lucia'],
 'The Bose-Hubbard model is QMA-complete': ['David Gosset'],
 'The second laws of quantum thermodynamics': ['Jonathan Oppenheim'],
 'Universal fault-tolerant quantum computation with only transversal gates and error correction': ['Adam Paetznick'],
 'Zero-error source-channel coding with entanglement': ['Teresa Piovesan']}

# title -> (presenters, evidence)
QIP_2024 = {"A Constructive Approach to Zauner's Conjecture via the Stark Conjectures": (['Steve Flammia'], 'video_title'),
 'A One-Query Lower Bound for Unitary Synthesis and Breaking Quantum Cryptography': (['Fermi Ma'], 'video_captions'),
 'A Quantum Speed-Up for Approximating the Top Eigenvector of a Matrix': (['Yanlin Chen'], 'video_title'),
 'A distribution testing oracle separating QMA and QCMA': (['Anand Natarajan'], 'video_title'),
 'A mathematical foundation for self-testing: Lifting common assumptions': (['Ranyiliu Chen'], 'video_title'),
 'A new operator extension of strong subadditivity of quantum entropy': (['Ting-Chun Lin'], 'video_title'),
 'A tight and general finite-size security proof for quantum key distribution': (['Thomas van Himbeeck'],
                                                                                 'video_captions'),
 'An Exponential Separation Between Quantum Query Complexity and the Polynomial Degree': (['Andris Ambainis'],
                                                                                          'video_title'),
 'An efficient quantum parallel repetition theorem and applications': (['John Bostanci'], 'video_title'),
 'Approaching the Quantum Singleton Bound with Approximate Error Correction': (['Louis Golowich'], 'video_title'),
 'Bounding the Quantum Value of Compiled Nonlocal Games: From CHSH to BQP Verification': (['Anand Natarajan'],
                                                                                          'video_captions'),
 'Breaking badly: unexpected Trotter error scaling for realistic quantum systems': (['Alexander Hahn'],
                                                                                    'video_captions'),
 'Bypassing Joint Typicality in Network Quantum Shannon Theory': (['Pau Colomer'], 'video_title'),
 'Catalytic and asymptotic equivalence for quantum entanglement': (['Alexander Streltsov'], 'video_title'),
 'Certified algorithms for equilibrium states of quantum lattice systems': (['Samuel Scalet'], 'video_title'),
 'Certifying highly-entangled states from few single-qubit measurements': (['Hsin-Yuan Huang'], 'video_title'),
 'Circuit-to-Hamiltonian from tensor networks and fault tolerance': (['Quynh Nguyen'], 'video_title'),
 'Classical simulation of non-Gaussian fermionic circuits': (['Beatriz Cardoso Dias'], 'video_title'),
 'Classical simulation of peaked shallow quantum circuits': (['Yinchen Liu'], 'video_title'),
 'Classification of dynamical Lie algebras for translation-invariant 2-local spin systems in one dimension': (['Bojko '
                                                                                                               'Bakalov'],
                                                                                                              'video_captions'),
 'Commuting Local Hamiltonian Problem on 2D beyond qubits': (['Sandy Irani'], 'video_title'),
 'Commuting operations factorise': (['Ramona Wolf'], 'video_title'),
 'Complexity Classification of Product State Problems for Local Hamiltonians': (['Justin Yirka'], 'video_title'),
 'Complexity and order in approximate quantum error-correcting codes': (['Zi-Wen Liu'], 'video_title'),
 'Complexity-theoretic foundations of BosonSampling with a linear number of modes': (['Ishaun Datta'],
                                                                                     'video_captions'),
 'Computational Entanglement Theory': (['Thomas Vidick'], 'video_title'),
 'Connecting entanglement distillation and entanglement testing with restricted measurements': (['Ludovico Lami'],
                                                                                                'video_captions'),
 'Constant-Overhead Fault-Tolerant Quantum Computation with Reconfigurable Atom Arrays': (['Qian Xu'],
                                                                                          'video_captions'),
 'Cryptography from Quantum One-Wayness': (['Kabir Tomer'], 'video_title'),
 'Discreteness of asymptotic tripartite entanglement measures': (['Itai Leigh'], 'video_title'),
 'Effect of non–unital noise on random circuit sampling': (['Soumik Ghosh'], 'video_title'),
 'Entanglement cost for infinite-dimensional physical systems': (['Hayata Yamasaki'], 'video_title'),
 'Entanglement monogamy via multivariate trace inequalities': (['Mario Berta'], 'video_title'),
 'Exact Steering Bound for Two-Qubit Werner States': (['Yujie Zhang'], 'video_title'),
 'Expected Utility Theory and its novel application in Quantum Information Science': (['Paul Skrzypczyk'],
                                                                                      'video_captions'),
 'Exponential Quantum Streaming Advantage for Maximum Directed Cut': (['Nadezhda Voronova'], 'video_title'),
 'Exponential quantum speedup in simulating coupled classical oscillators': (['Robin Kothari'], 'video_title'),
 'Gelfand-Tsetlin basis for partially transposed permutations, with applications to quantum information': (['Dmitry '
                                                                                                            'Grinko'],
                                                                                                           'video_captions'),
 'Generalised group designs: overcoming the 3-design-barrier and constructing novel 2-designs in arbitrary dimensions': (['Zoltán '
                                                                                                                          'Kolarovszki'],
                                                                                                                         'video_captions'),
 'Geometrically Local Quantum and Classical Codes from Subdivision': (['Ting-Chun Lin'], 'video_title'),
 'Heisenberg-limited metrology with perturbing interactions, and efficient sampling of short-time quantum evolution': (['Chao '
                                                                                                                        'Yin'],
                                                                                                                       'video_captions'),
 'High-threshold and low-overhead fault-tolerant quantum memory': (['Patrick Rall'], 'video_title'),
 'Layer Codes: Saturating the BPT Bound in 3D': (['Nouédyn Baspin'], 'video_title'),
 'Learning Quantum States With Respect to the Stabilizer Formalism': (['Sabee Grewal'], 'video_title'),
 'Learning quantum Hamiltonians at any temperature in polynomial time': (['Allen Liu'], 'video_title'),
 'Learning shallow quantum circuits': (['Hsin-Yuan Huang'], 'video_title'),
 'Limitations of local update recovery in stabilizer-GKP codes: a quantum optimal transport approach': (['Cambyse '
                                                                                                         'Rouzé'],
                                                                                                        'video_captions'),
 'Local minima in quantum systems': (['Leo Zhou'], 'video_title'),
 'Making Existing Quantum Position Verification Protocols Secure Against Arbitrary Transmission Loss': (['Philip '
                                                                                                         'Verduyn '
                                                                                                         'Lunel'],
                                                                                                        'video_captions'),
 'Matrix product algebras and their application for phase classification': (['Andras Molnar'], 'video_title'),
 'Matrix product state approximations to quantum states of low energy variance': (['Kshiti Sneh Rai'],
                                                                                  'video_captions'),
 'Measurement Quantum Cellular Automata and Anomalies in Floquet Codes': (['Zhi Li'], 'video_title'),
 'Monogamy of highly symmetric states': (['Dmitry Grinko'], 'video_title'),
 'NLTS Hamiltonians and Strongly-Explicit SoS Lower Bounds from Low-Rate Quantum LDPC Codes': (['Louis Golowich'],
                                                                                               'video_captions'),
 'Non-Linear Transformations of Quantum Amplitudes: Exponential Improvement, Generalization, and Applications': (['Arthur '
                                                                                                                  'Rattew'],
                                                                                                                 'video_captions'),
 'On the Pauli Spectrum of QAC0': (['Shivam Nadimpalli'], 'video_title'),
 'On the quantum time complexity of divide and conquer': (['Jinge Bao'], 'video_title'),
 'Provably Efficient Learning of Phases of Matter': (['James Watson'], 'video_title'),
 'Public-key pseudoentanglement and the hardness of learning ground state entanglement structure': (['Tony Metger'],
                                                                                                    'video_captions'),
 'Quadratic Lower bounds on the Approximate Stabilizer Rank: A Probabilistic Approach': (['Mehrdad Tahmasbi'],
                                                                                         'video_captions'),
 'Quantum Algorithm for Reducing Induced Representations with Applications to Port-based Teleportation': (['Sydney '
                                                                                                           'Timmerman',
                                                                                                           'Jiani Fei'],
                                                                                                          'video_captions'),
 'Quantum Lower Bounds for Finding Stationary Points of Nonconvex Functions': (['Chenyi Zhang'], 'video_title'),
 'Quantum Merlin-Arthur and proofs without relative phase': (['Kunal Marwaha'], 'video_title'),
 'Quantum Pseudorandom Scramblers': (['Mingnan Zhao'], 'video_title'),
 'Quantum Renyi and f-divergences from integral representations': (['Christoph Hirche'], 'video_captions'),
 'Quantum Thermal State Preparation': (['Chi-Fang Chen'], 'video_title'),
 'Quantum Uncertainty Principles for Measurements with Interventions': (['Yunlong Xiao'], 'video_title'),
 'Quantum chi-squared tomography and mutual information testing': (["Ryan O'Donnell"], 'video_title'),
 'Quantum complexity of the Kronecker coefficients': (['Vojtech Havlicek'], 'video_title'),
 'Quantum eigenvalue processing': (['Yuan Su'], 'video_title'),
 'Quantum metrology in the finite-sample regime': (['Johannes Jakob Meyer'], 'video_title'),
 'Quantum query complexity of functions of matrices': (['Ashley Montanaro'], 'video_title'),
 'Quantum speedups for linear programming via interior point methods': (['Simon Apers'], 'video_title'),
 'Query-optimal estimation of unitary channels in diamond distance': (['Ewin Tang'], 'video_title'),
 'Relating non-local computation to information theoretic cryptography': (['Alex May'], 'video_title'),
 'Reversibility of quantum resources through probabilistic protocols': (['Bartosz Regula'], 'video_title'),
 'Robust Quantum Public-Key Encryption with Applications to Quantum Key Distribution': (['Giulio Malavolta'],
                                                                                        'video_captions'),
 'Robust sparse IQP sampling in constant depth': (['Louis Paletta'], 'video_title'),
 'Security of position-based verification limits Hamiltonian simulation via holography': (['Harriet Apel'],
                                                                                          'video_captions'),
 'Self-duality and Jordan structure of quantum theory follow from homogeneity and pure transitivity': (['Howard '
                                                                                                        'Barnum'],
                                                                                                       'video_captions'),
 'Spectral gap implies rapid mixing for commuting Hamiltonians': (['Jan Kochanowski'], 'video_title'),
 'Tensor Network Decoding Beyond 2D': (['Christophe Piveteau'], 'video_title'),
 'Testing quantum satisfiability': (['Dominic Verdon'], 'video_title'),
 'The Power of Adaptivity in Quantum Query Algorithms': (['Kewen Wu'], 'video_title'),
 'The Power of Unentangled Quantum Proofs with Non-negative Amplitudes': (['Pei Wu'], 'video_title'),
 'The Quantum Entropy Cone near its Apex': (['Lasse H. Wolff'], 'video_title'),
 'The Schmidt rank for the commuting operator framework': (['Lauritz van Luijk'], 'video_title'),
 'The active-volume architecture and elliptic-curve cryptography': (['Daniel Litinski'], 'video_title'),
 'The advantage of quantum control in many-body Hamiltonian learning': (['Alicja Dutkiewicz'], 'video_title'),
 'The resource theory of tensor networks': (['Vincent Steffan'], 'video_title'),
 'Towards a unification of different measures of correlations and locality in Gibbs states': (['Ángela Capel'],
                                                                                              'video_captions'),
 'Trade-offs between Entanglement and Communication': (['Uma Girish'], 'video_title'),
 'Unifying speed limit and Lieb-Robinson bound: Wisdom from optimal transport': (['Tan Van Vu'], 'video_title'),
 'Unitary Complexity and the Uhlmann Transformation Problem': (['Tony Metger'], 'video_title'),
 "Viderman's algorithm for quantum LDPC codes": (['Anirudh Krishna'], 'video_title'),
 'What exactly does Bekenstein bound?': (['Jinzhao Wang'], 'video_title')}

# QIP 2024 talks the automated pass could not resolve, checked by hand in the
# recordings (2026-11-14, via the Speaker Picker artifact). title -> presenters
QIP_2024_MANUAL = {
    'Constant-Overhead Fault-Tolerant Quantum Computation with Reconfigurable Atom Arrays': ['Qian Xu'],
    'Going Beyond Gadgets: The Importance of Scalability for Analogue Quantum Simulators': ['Dylan Harley'],
    'Improved rate-distance trade-offs for quantum codes with restricted connectivity': ['Nouédyn Baspin'],
    'Linear combination of Hamiltonian simulation for non-unitary dynamics with optimal state preparation cost': ['Lin Lin'],
    'Quantum Public-Key Encryption with Tamper-Resilient Public Keys from One-Way Functions': ['Tomoyuki Morimae'],
    'Universal embezzlers': ['Lauritz van Luijk', 'Alexander Stottmeister', 'Henrik Wilming'],
}

VERIFIED = {
    2009: {t: (p, "bold_on_homepage") for t, p in QIP_2009.items()},
    2014: {
        **{t: (p, "bold_in_allprint") for t, p in QIP_2014.items()},
        "Undecidability of the spectral gap": (["Toby Cubitt"], "plenary_speakers_page"),
    },
    2024: {**QIP_2024, **{t: (p, "manual_video_check") for t, p in QIP_2024_MANUAL.items()}},
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _add_note(notes: str, note: str) -> str:
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    parts = [p for p in parts if not p.startswith("presenter=")]
    parts.append(note)
    return "; ".join(parts)


def fix_year(year: int, write: bool) -> None:
    path = ROOT / f"data/conferences/qip_{year}/talks.csv"
    raw = path.read_bytes()
    eol = "\r\n" if b"\r\n" in raw else "\n"
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    fields = list(rows[0].keys())
    verified = VERIFIED.get(year, {})
    set_n = cleared = kept = 0
    for r in rows:
        authors = [a.strip() for a in r["authors"].split(";") if a.strip()]
        if len(authors) < 2:
            continue
        hit = verified.get(r["title"])
        if hit:
            presenters, evidence = hit
            assert all(p in authors for p in presenters), (year, r["title"], presenters)
            new = ";".join(presenters)
            note = f"presenter={evidence}"
        else:
            new, note = "", "presenter=unknown (first-author default cleared)"
        if r["speakers"] != new:
            print(f"  {year} {r['title'][:60]:60} {r['speakers']!r} -> {new!r}")
            set_n += bool(new)
            cleared += not new
        else:
            kept += 1
        r["speakers"] = new
        r["notes"] = _add_note(r["notes"], note)
    print(f"QIP {year}: {set_n} presenters changed, {cleared} cleared, {kept} already correct")
    missing = set(verified) - {r["title"] for r in rows}
    assert not missing, (year, missing)
    if write:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields, lineterminator=eol)
        w.writeheader()
        w.writerows(rows)
        path.write_bytes(buf.getvalue().encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="update the talks.csv files")
    args = ap.parse_args()
    for year in YEARS:
        fix_year(year, args.write)


if __name__ == "__main__":
    main()
