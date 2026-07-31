import logging

from config import settings, validate_required_settings
from core.telegram_bot import run_bot
from core.utils import ensure_runtime_dirs, setup_logging


def main() -> None:
    ensure_runtime_dirs(settings)
    setup_logging(settings.logs_dir / "bot_system.log")
    validate_required_settings(settings)
    logging.info("Starting NSE Trading Telegram Bot")
    run_bot(settings)


if __name__ == "__main__":
    main()
