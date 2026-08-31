import csv
import os
from dataclasses import dataclass, field
from pathlib import Path
from datetime import time
from zoneinfo import ZoneInfo

from core.universe import load_symbols_from_csv

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional at import time
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent
NSE_TZ = ZoneInfo("Asia/Kolkata")
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

def _env_time(name: str, default: str) -> time:
    value = os.getenv(name, default)

    hour, minute = map(int, value.split(":"))

    # Keep the job on IST even when the EC2 host itself uses UTC.
    return time(hour=hour, minute=minute, tzinfo=NSE_TZ)

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
    max_price: float = _env_float("MAX_STOCK_PRICE", 1000.0)
    max_recommendations: int = _env_int("MAX_RECOMMENDATIONS", 5)
    min_recommendations: int = _env_int("MIN_RECOMMENDATIONS", 1)
    scan_interval_minutes: int = _env_int("SCAN_INTERVAL_MINUTES", 30)
    monitor_interval_minutes: int = _env_int("MONITOR_INTERVAL_MINUTES", 30)
    history_period: str = os.getenv("HISTORY_PERIOD", "60d")
    history_interval: str = os.getenv("HISTORY_INTERVAL", "30m")
    default_quantity: int = _env_int("DEFAULT_QUANTITY", 1)

    stop_loss_pct: float = _env_float("STOP_LOSS_PCT", 3.0)
    target_pct: float = _env_float("TARGET_PCT", 6.0)
    trailing_stop_pct: float = _env_float("TRAILING_STOP_PCT", 4.0)
    max_active_positions: int = _env_int("MAX_ACTIVE_POSITIONS", 5)
    enable_ai: bool = _env_bool("ENABLE_AI", True)
    enable_news: bool = _env_bool("ENABLE_NEWS", True)

    portfolio_size: float = _env_float("PORTFOLIO_SIZE", 100000.0)
    risk_per_trade_pct: float = _env_float("RISK_PER_TRADE_PCT", 1.0)
    max_position_value_pct: float = _env_float("MAX_POSITION_VALUE_PCT", 5.0)
    paper_trading: bool = _env_bool("PAPER_TRADING", True)

    symbols_file: Path = Path(os.getenv("SYMBOLS_FILE", str(BASE_DIR / "data" / "nifty200.csv")))
    symbols: list[str] = field(default_factory=lambda: load_symbols_from_csv(Path(os.getenv("SYMBOLS_FILE", str(BASE_DIR / "data" / "nifty200.csv")))))

    # Daily Scan
    daily_scan_time: str = _env_time("DAILY_SCAN_TIME", "09:20")

    # Trading Filters
    minimum_buy_score: float = _env_float("MINIMUM_BUY_SCORE", 65.0)
    minimum_volume_ratio: float = _env_float("MINIMUM_VOLUME_RATIO", 1.0)

    # Holding
    max_holding_days: int = _env_int("MAX_HOLDING_DAYS", 30)

    # Cooldown
    cooldown_days: int = _env_int("COOLDOWN_DAYS", 5)

    # Don't buy same stock twice in one day
    prevent_same_day_buy: bool = _env_bool("PREVENT_SAME_DAY_BUY", True)


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
        missing.append(f"{active_settings.symbols_file} must contain at least one symbol")
    if not active_settings.enable_ai:
        missing.append("ENABLE_AI must be true")
    if not active_settings.enable_news:
        missing.append("ENABLE_NEWS must be true")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Mandatory configuration missing: {joined}")

