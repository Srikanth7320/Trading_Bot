import logging
from html import escape

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
    await update.message.reply_text("Scanning NSE stocks. This can take a little time...")
    recommendations = services["scanner"].scan()
    if not recommendations:
        await update.message.reply_text("No BUY recommendations matched the rules right now.")
        return

    positions = services["storage"].load_positions()
    open_slots = max(0, context.application.bot_data["settings"].max_active_positions - len(positions))
    for recommendation in recommendations[:open_slots]:
        positions.append(services["risk"].open_position(recommendation))
    services["storage"].save_positions(positions)

    await update.message.reply_html(format_recommendations(recommendations))


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
    lines = ["<b>Trading Bot Summary</b>", escape(market_status_message())]

    lines.append(f"\nActive positions: {len(positions)}")
    for item in positions[:5]:
        lines.append(
            f"{escape(item.symbol)} | Entry: {item.entry_price:.2f} | "
            f"SL: {item.stop_loss:.2f} | Target: {item.target:.2f}"
        )

    recent = history[-5:]
    if recent:
        lines.append("\n<b>Recent Signals</b>")
        for item in reversed(recent):
            symbol = escape(str(item.get("symbol", "-")))
            action = escape(str(item.get("action", "-")))
            created_at = escape(str(item.get("created_at", "-")))
            price = escape(str(item.get("price", item.get("current_price", "-"))))
            lines.append(f"{created_at} | {symbol} | {action} | {price}")
    else:
        lines.append("\nNo stored signals yet.")

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


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not settings.telegram_chat_id:
        return
    if not is_market_open():
        logger.info("Skipping scheduled scan because NSE market is closed")
        return
    recommendations = context.application.bot_data["services"]["scanner"].scan()
    if recommendations:
        await context.bot.send_message(settings.telegram_chat_id, format_recommendations(recommendations), parse_mode="HTML")


async def scheduled_monitor(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not settings.telegram_chat_id:
        return
    if not is_market_open():
        logger.info("Skipping scheduled monitor because NSE market is closed")
        return
    decisions = context.application.bot_data["services"]["monitor"].run_once()
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
        application.job_queue.run_repeating(scheduled_scan, interval=settings.scan_interval_minutes * 60, first=60)
        application.job_queue.run_repeating(scheduled_monitor, interval=settings.monitor_interval_minutes * 60, first=120)

    logger.info("Telegram polling started")
    application.run_polling()
