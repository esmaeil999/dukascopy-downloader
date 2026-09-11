# Dukascopy Tick Downloader

Downloads historical tick data from the Dukascopy JETTA API into local
**MT5-ready binary files** and imports ticks into **MetaTrader 5**
custom symbols via a bundled MQL5 script.

## Install

```powershell
pip install -r requirements.txt
```

Requires Python 3.10+.

If you are upgrading from an older Parquet-based install, run the one-time
migration after installing:

```powershell
python main.py migrate
```

(`pyarrow` is only needed for that migration step.)

## Web UI

```powershell
python main.py web
# open http://127.0.0.1:8080
```

Minimal white-themed interface for search, **bulk download** (multiple symbols in one
job), MT5 import, gap scan/repair, stored-data library, and live job progress.

## Usage (CLI)

```powershell
# Find an instrument (1600+ in the bundled catalog)
python main.py search gold
python main.py search eurusd

# Download ticks into binary hour files (resumable, concurrent, auto-retrying)
python main.py download EURUSD 2025-01-01 2025-06-30

# Merge the downloaded range into one MT5-ready pack and upload it to a
# GitHub release — works for any range, e.g. daily or monthly:
#   2025-01-15 .. 2025-01-15  ->  EURUSD_2025-01-15.BIN -> EURUSD_2025-01-15.zip
#   2025-01-01 .. 2025-01-31  ->  EURUSD_2025-01.BIN    -> EURUSD_2025-01.zip
# Needs GITHUB_TOKEN and --repo owner/name (or GITHUB_REPOSITORY,
# both set automatically in the bundled GitHub Actions workflow).
python main.py download EURUSD 2025-01-15 2025-01-15 --upload-release
python main.py download EURUSD 2025-01-01 2025-01-31 --upload-release

# Yearly mode: a multi-year range is processed one calendar year at a time;
# each finished year is merged into its own pack:
#   data/yearly/EURUSD_2015.BIN, data/yearly/EURUSD_2016.BIN, ...
python main.py download EURUSD 2015-01-01 2026-12-31 --yearly --upload-release

# One-time: convert legacy .parquet data to .bin
python main.py migrate

# Check for and repair holes in the dataset
python main.py gaps EURUSD 2025-01-01 2025-06-30 --repair

# Scan the entire recorded range (no dates needed)
python main.py gaps EURUSD --all
python main.py gaps EURUSD --all --repair
python main.py gaps EURUSD --all --repair --refetch-empty   # also re-request empty hours

# What is stored locally?
python main.py status EURUSD
```

`download` options: `--workers N` (default 15, max 64), `--force`, `--profile`,
`--yearly`, `--upload-release`, `--repo owner/name`

## Period packs & GitHub releases

`--upload-release` merges the downloaded range into one pack, zips it, and
uploads it to a GitHub release. `--yearly` additionally splits a multi-year
range into one pack per calendar year. Pack names follow the period covered:

| requested range                 | pack file                  | zip asset            | release tag           |
| ------------------------------- | -------------------------- | -------------------- | --------------------- |
| full year 2025                  | `EURUSD_2025.BIN`          | `EURUSD_2025.zip`    | `EURUSD-2025`         |
| full month Jan 2025             | `EURUSD_2025-01.BIN`       | `EURUSD_2025-01.zip` | `EURUSD-2025-01`      |
| single day 2025-01-15           | `EURUSD_2025-01-15.BIN`    | `EURUSD_2025-01-15.zip` | `EURUSD-2025-01-15` |
| any other range                 | `EURUSD_<start>_<end>.BIN` | `EURUSD_<start>_<end>.zip` | `EURUSD-<start>_<end>` |

Packs are written to `data/yearly/`; the zip (`.BIN` suffix dropped, e.g.
`EURUSD_2025.zip`) is what gets uploaded. Re-running the same period replaces
the release asset. Notes:

- Auth: `GITHUB_TOKEN` with contents write access; the repository comes from
  `--repo owner/name` or `GITHUB_REPOSITORY` (both automatic in the workflow).
- GitHub limits release assets to **2 GB** per file; very liquid symbols can
  exceed that for a full year — split such jobs into shorter ranges.
- Long multi-year jobs can outgrow GitHub-hosted runner limits (~6 h per job,
  limited disk). For 10+ years of a liquid symbol, run locally or launch the
  workflow once per few years — every run is independent and resumable.

## How it works

```
plan hours -> fetch JETTA JSON (parallel) -> decode -> verify -> .bin (atomic)
                                                                  |
                 SQLite ledger: completed / empty / failed  <-----+
                                                                  |
                              MT5 import  <-- link hour .bin files --+
```

- **One `.bin` file per instrument-hour** (`data/EURUSD/2025/01/02/14.bin`),
  stored in the same bin_v1 layout MT5 imports. Written atomically via temp file
  + rename and never overwritten.
- **SQLite ledger** (`data/metadata.db`) records every hour's state. Completed
  and empty hours are never re-downloaded, so interrupted runs resume for free
  and progress is never lost.
- **Retry manager**: exponential backoff with jitter for network errors and
  5xx responses; corrupt payloads (JSON/structure/verification failures)
  trigger a fresh fetch. Hours that still fail get extra retry rounds, then
  remain flagged for `gaps --repair`. Temporary failures never abort a run.
- **Planner** clamps ranges to each instrument's earliest available data and
  skips the not-yet-published most recent hours. Hours with no tick data are
  recorded as empty after an empty JETTA response.
- **Verification** checks record structure, timestamp monotonicity and bounds,
  positive prices, and plausible spreads before anything is persisted.
- **Instrument catalog** (`config/instruments.json`) carries display names used
  to resolve JETTA instrument codes, plus data start dates.

## MT5 import

Downloads are already MT5-ready. Import hard-links each hour `.bin` into the
MT5 job folder (no concat copy) and launches MetaTrader 5 with
`DukascopyTickImport.mq5`, which reads `hours.txt` and imports each file
via `CustomTicksReplace`.

## Layout

```
core/
  models/        instrument, tick, tick_batch, hour-task
  services/      instrument_search, planner, download_engine,
                 retry_manager, decoder, verification, gap_scanner
storage/         tick_storage, tick_format, metadata_db, parquet_migration
export/          yearly, github_release, mt5_tick_publisher, mt5_importer
mt5/             DukascopyTickImport.mq5
config/          settings, instruments.json
cli/             commands
scripts/         migrate_parquet_to_bin.py
data/            binary tick store + SQLite ledger   (created at runtime)
data/yearly/     merged period packs <SYMBOL>_<PERIOD>.BIN (+ <SYMBOL>_<PERIOD>.zip)
```
