import logging
from html import escape
from datetime import date

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import Settings
from core.ai_score import AIScorer
from core.market_clock import is_market_open, market_status_message
from core.market_data import MarketDataClient
from core.monitor import PositionMonitor
from core.news import NewsClient
from core.risk import RiskEngine
from core.scanner import Scanner
from core.sell_engine import SellEngine
from core.storage import Storage


logger = logging.getLogger(__name__)


def build_services(settings: Settings) -> dict:
    storage = Storage(settings.data_dir)
    storage.settings = settings
    market = MarketDataClient()
    news = NewsClient(settings.news_api_key, settings.enable_news)
    ai = AIScorer(settings.gemini_api_key, settings.gemini_model, settings.enable_ai)
    risk = RiskEngine(settings)
    scanner = Scanner(settings, market, storage, news, ai, risk)
    monitor = PositionMonitor(storage, SellEngine(settings, market))
    return {"storage": storage, "scanner": scanner, "monitor": monitor, "risk": risk}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [["/scan", "/monitor"], ["/summary", "/positions"], ["/help"]]
    await update.message.reply_text(
        "NSE Trading Bot ready.\nUse /scan for BUY ideas and /monitor for SELL/HOLD checks.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/scan - Generate NSE BUY recommendations\n"
        "/monitor - Check active positions for SELL/HOLD\n"
        "/summary - Show latest stored signals and positions\n"
        "/positions - Show active positions\n"
        "/help - Show this menu"
    )


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_market_open():
        await update.message.reply_text(market_status_message())
        return

    services = context.application.bot_data["services"]
    storage = services["storage"]

    if scan_completed_today(storage):
        await update.message.reply_text("Daily buy signal already issued today. No new buy signal will be posted until the next trading day.")
        return

    await update.message.reply_text("Scanning NSE stocks. This can take a little time...")
    recommendations = services["scanner"].scan()
    mark_scan_completed(storage)

    if not recommendations:
        await update.message.reply_text("No BUY recommendations matched the rules right now.")
        return

    positions = storage.load_positions()
    open_slots = max(0, context.application.bot_data["settings"].max_active_positions - len(positions))
    for recommendation in recommendations[:open_slots]:
        if any(position.symbol == recommendation.symbol for position in positions):
            continue
        if storage.bought_today(recommendation.symbol):
            continue
        position = services["risk"].open_position(recommendation)
        positions.append(position)
        storage.append_signal(recommendation)
        storage.mark_buy_today(recommendation.symbol)
    storage.save_positions(positions)

    await update.message.reply_html(format_recommendations(recommendations[:open_slots]))


async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_market_open():
        await update.message.reply_text(market_status_message())
        return

    services = context.application.bot_data["services"]
    decisions = services["monitor"].run_once()
    if not decisions:
        await update.message.reply_text("No active positions to monitor.")
        return
    await update.message.reply_html(format_decisions(decisions))


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.application.bot_data["services"]["storage"]
    positions = storage.load_positions()
    if not positions:
        await update.message.reply_text("No active positions.")
        return
    lines = ["<b>Active Positions</b>"]
    for item in positions:
        lines.append(
            f"{escape(item.symbol)} | Entry: {item.entry_price:.2f} | "
            f"SL: {item.stop_loss:.2f} | Target: {item.target:.2f}"
        )
    await update.message.reply_html("\n".join(lines))


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.application.bot_data["services"]["storage"]
    positions = storage.load_positions()
    history = storage.load_history()
    today = date.today().isoformat()

    lines = ["<b>Daily Trading Summary</b>", escape(market_status_message())]

    today_buys = []
    today_sells = []
    for item in history:
        created_at = str(item.get("created_at", ""))
        if created_at.startswith(today):
            if str(item.get("action", "")).upper() == "BUY":
                today_buys.append(item)
            elif str(item.get("action", "")).upper() == "SELL":
                today_sells.append(item)

    lines.append(f"\n<b>Today’s buys</b>: {len(today_buys)}")
    if today_buys:
        for item in today_buys:
            symbol = escape(str(item.get("symbol", "-")))
            price = escape(str(item.get("price", "-")))
            lines.append(f"• {symbol} @ {price}")
    else:
        lines.append("• None")

    lines.append(f"\n<b>Active positions</b>: {len(positions)}")
    if positions:
        for item in positions:
            lines.append(
                f"• {escape(item.symbol)} | Entry: {item.entry_price:.2f} | "
                f"SL: {item.stop_loss:.2f} | Target: {item.target:.2f}"
            )
    else:
        lines.append("• None")

    lines.append(f"\n<b>Today’s sells</b>: {len(today_sells)}")
    if today_sells:
        for item in today_sells:
            symbol = escape(str(item.get("symbol", "-")))
            price = escape(str(item.get("current_price", item.get("price", "-"))))
            lines.append(f"• {symbol} @ {price}")
    else:
        lines.append("• None")

    await update.message.reply_html("\n".join(lines))


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip().lower()
    if "scan" in text or "buy" in text:
        await scan_command(update, context)
    elif "monitor" in text or "sell" in text:
        await monitor_command(update, context)
    elif "position" in text:
        await positions_command(update, context)
    elif "summary" in text:
        await summary_command(update, context)
    else:
        await help_command(update, context)

def scan_completed_today(storage) -> bool:

    history = storage.load_daily_buys()

    today = date.today().isoformat()

    return today in history


def mark_scan_completed(storage):

    history = storage.load_daily_buys()

    today = date.today().isoformat()

    if today not in history:
        history[today] = []

    storage.save_daily_buys(history)


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    settings = context.application.bot_data["settings"]
    services = context.application.bot_data["services"]
    storage = services["storage"]

    if not settings.telegram_chat_id:
        return

    if not is_market_open():
        return

    if scan_completed_today(storage):
        return

    try:
        recommendations = services["scanner"].scan()
    except Exception as exc:
        logger.exception("Scheduled scan failed: %s", exc)
        await context.bot.send_message(
            settings.telegram_chat_id,
            "⚠️ Daily scan failed. Please check the bot logs.",
        )
        return

    mark_scan_completed(storage)

    if not recommendations:
        await context.bot.send_message(
            settings.telegram_chat_id,
            "📅 Daily Scan Completed\n\n"
            "No BUY opportunity today."
        )
        return

    positions = storage.load_positions()
    open_slots = max(0, settings.max_active_positions - len(positions))

    opened_positions = []
    for recommendation in recommendations[:open_slots]:
        if any(position.symbol == recommendation.symbol for position in positions):
            continue
        if storage.bought_today(recommendation.symbol):
            continue
        position = services["risk"].open_position(recommendation)
        positions.append(position)
        opened_positions.append(recommendation)
        storage.append_signal(recommendation)
        storage.mark_buy_today(recommendation.symbol)

    storage.save_positions(positions)

    if not opened_positions:
        await context.bot.send_message(
            settings.telegram_chat_id,
            "📅 Daily Scan Completed\n\n"
            "No new buy signal was posted today.",
            parse_mode="HTML",
        )
        return

    await context.bot.send_message(
        settings.telegram_chat_id,
        format_recommendations(opened_positions),
        parse_mode="HTML",
    )

async def scheduled_monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not settings.telegram_chat_id:
        return
    if not is_market_open():
        logger.info("Skipping scheduled monitor because NSE market is closed")
        return
    try:
        decisions = context.application.bot_data["services"]["monitor"].run_once()
    except Exception as exc:
        logger.exception("Scheduled monitor failed: %s", exc)
        return
    sell_decisions = [decision for decision in decisions if decision.action == "SELL"]
    if sell_decisions:
        await context.bot.send_message(settings.telegram_chat_id, format_decisions(sell_decisions), parse_mode="HTML")


def format_recommendations(recommendations) -> str:
    lines = ["<b>BUY Recommendations</b>"]
    for item in recommendations:
        lines.append(
            f"\n<b>{escape(item.symbol)}</b> @ {item.price:.2f} | Score: {item.score:.1f}\n"
            f"SL: {item.stop_loss:.2f} | Target: {item.target:.2f}\n"
            f"RSI: {item.rsi:.1f} | Vol: {item.volume_ratio:.2f}x\n"
            f"{escape(item.reason)}\n"
            f"{escape(item.ai_note[:250])}"
        )
    return "\n".join(lines)


def format_decisions(decisions) -> str:
    lines = ["<b>Position Monitor</b>"]
    for item in decisions:
        lines.append(
            f"{escape(item.symbol)} | <b>{item.action}</b> @ {item.current_price:.2f} | "
            f"PnL: {item.pnl_pct:.2f}% | {escape(item.reason)}"
        )
    return "\n".join(lines)


def run_bot(settings: Settings) -> None:
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["services"] = build_services(settings)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("monitor", monitor_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    if application.job_queue:
        application.job_queue.run_daily(scheduled_scan, time=settings.daily_scan_time)
        application.job_queue.run_repeating(scheduled_monitor, interval=settings.monitor_interval_minutes * 60, first=120)

    logger.info("Telegram polling started")
    application.run_polling()
