from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable, List

import requests

logger = logging.getLogger(__name__)

NSE_INDEX_URLS = {
    "nifty50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "nifty100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    "nifty500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
}


def _normalize_index_name(filename: str) -> str:
    normalized = filename.lower()
    for index_name in NSE_INDEX_URLS:
        if index_name in normalized:
            return index_name
    return "nifty200"


def fetch_nse_index_symbols(index_name: str, destination: Path) -> list[str]:
    url = NSE_INDEX_URLS.get(index_name)
    if not url:
        raise ValueError(f"Unknown NSE index name: {index_name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=15)
    response.raise_for_status()

    raw_lines = response.text.splitlines()
    reader = csv.DictReader(raw_lines)
    symbols: list[str] = []
    rows: list[tuple[str, str]] = []
    for row in reader:
        symbol = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
        name = (row.get("Company Name") or row.get("Company") or row.get("Name") or "").strip()
        if not symbol:
            continue
        symbol = symbol.replace(".NS", "")
        symbols.append(symbol)
        rows.append((symbol, name))

    if not symbols:
        raise RuntimeError(f"Failed to parse symbols from NSE index CSV at {url}")

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "name"])
        for symbol, name in rows:
            writer.writerow([symbol, name])

    logger.info("Downloaded %d symbols for %s to %s", len(symbols), index_name, destination)
    return symbols


def load_symbols_from_csv(path: Path, allow_download: bool = True) -> list[str]:
    if not path.exists():
        if allow_download and path.name.lower().startswith("nifty"):
            try:
                return fetch_nse_index_symbols(_normalize_index_name(path.name), path)
            except Exception as exc:
                raise RuntimeError(f"Unable to download NSE index symbol list for {path.name}: {exc}") from exc
        raise RuntimeError(f"NSE symbols file is missing: {path}")

    symbols: list[str] = []
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise RuntimeError(f"NSE symbols file has no header row: {path}")

        symbol_column = next(
            (name for name in reader.fieldnames if name.strip().lower() in {"symbol", "tradingsymbol", "ticker"}),
            reader.fieldnames[0],
        )

        for row in reader:
            raw_symbol = (row.get(symbol_column) or "").strip().upper()
            if not raw_symbol:
                continue
            symbols.append(raw_symbol.replace(".NS", ""))

    unique_symbols = list(dict.fromkeys(symbols))
    if not unique_symbols:
        raise RuntimeError(f"NSE symbols file is empty: {path}")
    return unique_symbols
