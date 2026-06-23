# Video recording sources & coverage

Per-conference status of talk **video recordings** (the `video_url` column in the talk CSVs /
`publications.video_url` in the DB). Companion to `data/SOURCES.md` (which tracks committee/talk
text provenance). Coverage % = talks with a `video_url` ÷ total talk rows.

Maintained alongside `tools/video_channels.json` (the machine-readable YouTube source registry that
`tools/video_pass.py` reads). When you find or harvest a new source, update **both** files.

**Status legend**
- `recorded` — good coverage from a known source (≥70%).
- `partial` — some videos linked, but incomplete (a source exists but doesn't cover every talk, or
  matching is imperfect).
- `none — no recordings` — no public recordings are known to exist (pre-recording era, or the event
  wasn't recorded / was disrupted).
- `none — source not on YouTube` — recordings exist but only on the conference website, not a
  harvestable YouTube playlist/channel (would need a different scraper).
- `pending` — too recent; recordings may still be published.

Last updated: 2026-06-23.

## QIP

| Year | Coverage | Source | Status |
|------|----------|--------|--------|
| 1998–2009 | 0% | — | none — no recordings (pre-recording era) |
| 2010 | 95% | (prior enrichment) | recorded |
| 2011 | 100% | qip.iaqi.org archive (`movie.php` per-talk) | recorded |
| 2012 | 63% | (prior enrichment) | partial |
| 2013 | 93% | (prior enrichment) | recorded |
| 2014 | 0% | — | none — no recordings found (Barcelona) |
| 2015 | 91% | YouTube channel `UCZ1yRuDPlCsXRBELSClnfCw` | recorded |
| 2016 | 77% | YouTube channel `UCzmk-rGeX1siWh6tUx6IJ2Q` (IQST UCalgary) | recorded |
| 2017 | 88% | YouTube playlist (Microsoft Research) | recorded |
| 2018 | 0% | — | none — no recordings found (Delft/QuTech) |
| 2019 | 83% | YouTube playlist (CU Boulder) | recorded |
| 2020 | 0% | — | none — conference disrupted (Shenzhen, Jan 2020); slides only |
| 2021 | 98% | YouTube playlist (MCQST) | recorded |
| 2022 | 89% | YouTube channel `UCfN1uBQkn_FIp9EpkHZFi2w` (Caltech) | recorded |
| 2023 | 97% | `@QIP2023` | recorded |
| 2024 | 80% | `@QIP2024` | recorded |
| 2025 | 28% | `@QIP2025` | partial — recent; more may be posted |
| 2026 | 0% | — | pending (Riga, Jan 2026) |

## QCrypt

| Year | Coverage | Source | Status |
|------|----------|--------|--------|
| 2011–2014 | 74–94% | (prior enrichment) | recorded |
| 2015 | 5% | — | none — almost no recordings found |
| 2016 | 90% | (prior enrichment) | recorded |
| 2017 | 21% | videos on `2017.qcrypt.net` (Cambridge) | none — source not on YouTube |
| 2018 | 97% | (prior enrichment) | recorded |
| 2019 | 2% | — | none — almost no recordings found |
| 2020 | 72% | `@qcryptconference239` (+ `channel_filter_year`) | recorded |
| 2021 | 86% | `@qcryptconference239` (+ `/streams`, year-filtered) | recorded |
| 2022 | 17% | `@qcryptconference239` (year-filtered) | partial — channel videos are titled by *speaker*, not talk title, so few auto-match |
| 2023 | 68% | playlist `PLbY0Lk6JsgBEph5CPYTQZs6cOKBPGSnnI` (UMaryland) | recorded — added 2026-06 |
| 2024 | 0% | videos on `2024.qcrypt.net` (Vigo) | none — source not on YouTube |
| 2025 | 98% | (prior enrichment) | recorded |

**Note:** the `@qcryptconference239` channel hosts **only 2020/2021/2022** (verified by enumeration).

## TQC

| Year | Coverage | Source | Status |
|------|----------|--------|--------|
| 2006–2018 | 0% | — | none — no recordings (pre-recording era) |
| 2019 | 58% | YouTube playlist (UMD) | partial |
| 2020 | 0% | `c/TQC2020` (livestreams only) | none — only day-long livestreams, not per-talk |
| 2021 | 83% | `c/TQC2020` (+ `channel_filter_year`) | recorded |
| 2022 | 0% | — | none — no public recordings found (Illinois) |
| 2023 | 92% | `@SquidSchools` (year-filtered) | recorded |
| 2024 | 89% | `@SquidSchools` (year-filtered) | recorded |
| 2025 | 80% | `@tqc-conference` (year-filtered) | recorded |

## Worklist (open items)
- **QCrypt 2024 / 2017**: recordings exist on the conference websites (`2024.qcrypt.net`,
  `2017.qcrypt.net`) but no clean YouTube playlist was found — would need a site scraper.
- **QCrypt 2022**: channel has 86 videos but they're titled by speaker; would need a
  speaker-keyed matcher rather than title-Jaccard.
- **TQC 2020 / 2022**: 2020 is livestream-only; 2022 (Illinois) has no public recordings found.
- **QIP 2025 / 2026**: recent — re-run `video_pass` as more videos are posted.
