import logging
from pathlib import Path


def ensure_runtime_dirs(settings) -> None:
    for directory in (settings.data_dir, settings.logs_dir, settings.reports_dir):
        Path(directory).mkdir(parents=True, exist_ok=True)


def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def nse_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS"):
        return symbol
    return f"{symbol}.NS"


def display_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "")
