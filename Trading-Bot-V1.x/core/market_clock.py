from datetime import datetime, time
from zoneinfo import ZoneInfo


NSE_TZ = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)


def ist_now() -> datetime:
    return datetime.now(NSE_TZ)


def ist_today():
    """Return the NSE trading date independently of the server timezone."""
    return ist_now().date()


def is_market_open(now: datetime | None = None) -> bool:
    current = now.astimezone(NSE_TZ) if now else ist_now()
    if current.weekday() >= 5:
        return False
    return NSE_OPEN <= current.time() <= NSE_CLOSE


def market_status_message(now: datetime | None = None) -> str:
    current = now.astimezone(NSE_TZ) if now else ist_now()
    status = "OPEN" if is_market_open(current) else "CLOSED"
    return (
        f"NSE market is {status}.\n"
        f"Current IST: {current.strftime('%A, %d %b %Y %I:%M %p')}.\n"
        "Trading scans and monitoring run only Monday-Friday, 09:15-15:30 IST.\n"
        "Use /summary or /positions anytime."
    )
