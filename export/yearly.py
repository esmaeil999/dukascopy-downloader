"""Yearly packaging: merge one calendar year of hour .bin files into a single
MT5-ready BIN named <SYMBOL>_<YEAR>.BIN, plus a zip helper.

bin_v1 hour blocks are self-delimiting (uint32 tick_count + columns), so
concatenating hour files byte-for-byte in chronological order produces a valid
combined file — the same layout MT5 imports (see storage.tick_format).
"""
from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.models.instrument import Instrument
from storage.tick_format import read_hour_tick_count
from storage.tick_storage import TickStorage

COPY_BUFFER = 16 * 1024 * 1024


def yearly_output_dir(data_dir: Path) -> Path:
    """Directory that receives merged yearly packs."""
    return data_dir / "yearly"


def yearly_bin_name(symbol: str, year: int) -> str:
    return f"{symbol}_{year}.BIN"


def _year_bounds_utc(year: int) -> tuple[datetime, datetime]:
    return (
        datetime(year, 1, 1, 0, tzinfo=timezone.utc),
        datetime(year, 12, 31, 23, tzinfo=timezone.utc),
    )


def merge_year(
    storage: TickStorage,
    instrument: Instrument,
    year: int,
    out_dir: Path,
) -> tuple[Path, int] | None:
    """Merge all stored hour files of `year` into <SYMBOL>_<YEAR>.BIN.

    Hour files are appended in chronological order without modification, so the
    result stays importable by MT5. Written atomically (temp file + rename).
    Returns (output_path, total_ticks), or None when no data exists for the year.
    """
    start, end = _year_bounds_utc(year)
    hours = storage.list_stored_hours(instrument, start, end)
    if not hours:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / yearly_bin_name(instrument.symbol, year)
    tmp_path = out_path.with_name(out_path.name + ".tmp")

    total_ticks = 0
    with open(tmp_path, "wb", buffering=COPY_BUFFER) as out:
        for hour in hours:
            src = storage.hour_path(instrument, hour)
            if not src.is_file():
                continue
            total_ticks += read_hour_tick_count(src)
            with open(src, "rb") as fin:
                while True:
                    chunk = fin.read(COPY_BUFFER)
                    if not chunk:
                        break
                    out.write(chunk)
    tmp_path.replace(out_path)
    return out_path, total_ticks


def zip_yearly_bin(bin_path: Path) -> Path:
    """Zip <SYMBOL>_<YEAR>.BIN -> <SYMBOL>_<YEAR>.BIN.zip (atomically)."""
    zip_path = bin_path.parent / (bin_path.name + ".zip")
    tmp_path = zip_path.with_name(zip_path.name + ".tmp")
    with zipfile.ZipFile(
        tmp_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as zf:
        zf.write(bin_path, arcname=bin_path.name)
    tmp_path.replace(zip_path)
    return zip_path
