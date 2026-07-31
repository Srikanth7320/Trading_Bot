import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional at import time
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def load_symbols_from_csv(path: Path) -> list[str]:
    if not path.exists():
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


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")

    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    reports_dir: Path = BASE_DIR / "reports"

    min_price: float = _env_float("MIN_STOCK_PRICE", 10.0)
    max_price: float = _env_float("MAX_STOCK_PRICE", 500.0)
    max_recommendations: int = _env_int("MAX_RECOMMENDATIONS", 5)
    min_recommendations: int = _env_int("MIN_RECOMMENDATIONS", 3)
    scan_interval_minutes: int = _env_int("SCAN_INTERVAL_MINUTES", 60)
    monitor_interval_minutes: int = _env_int("MONITOR_INTERVAL_MINUTES", 60)
    default_quantity: int = _env_int("DEFAULT_QUANTITY", 1)

    stop_loss_pct: float = _env_float("STOP_LOSS_PCT", 3.0)
    target_pct: float = _env_float("TARGET_PCT", 6.0)
    trailing_stop_pct: float = _env_float("TRAILING_STOP_PCT", 4.0)
    max_active_positions: int = _env_int("MAX_ACTIVE_POSITIONS", 5)
    enable_ai: bool = _env_bool("ENABLE_AI", True)
    enable_news: bool = _env_bool("ENABLE_NEWS", True)

    symbols_file: Path = BASE_DIR / "data" / "nse_symbols.csv"
    symbols: list[str] = field(default_factory=lambda: load_symbols_from_csv(BASE_DIR / "data" / "nse_symbols.csv"))


settings = Settings()


def validate_required_settings(active_settings: Settings) -> None:
    missing = []
    if not active_settings.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not active_settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if not active_settings.news_api_key:
        missing.append("NEWS_API_KEY")
    if not active_settings.symbols:
        missing.append("data/nse_symbols.csv must contain at least one symbol")
    if not active_settings.enable_ai:
        missing.append("ENABLE_AI must be true")
    if not active_settings.enable_news:
        missing.append("ENABLE_NEWS must be true")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Mandatory configuration missing: {joined}")
