from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NewsItem:
    title: str
    source: str
    url: str = ""
    published_at: str = ""


@dataclass
class Recommendation:
    symbol: str
    price: float
    score: float
    action: str
    reason: str
    stop_loss: float
    target: float
    rsi: float
    macd: float
    signal: float
    volume_ratio: float
    news_score: float = 0.0
    ai_note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    highest_price: float
    opened_at: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Position":
        return cls(
            symbol=payload["symbol"],
            entry_price=float(payload["entry_price"]),
            quantity=int(payload.get("quantity", 1)),
            stop_loss=float(payload["stop_loss"]),
            target=float(payload["target"]),
            highest_price=float(payload.get("highest_price", payload["entry_price"])),
            opened_at=payload.get("opened_at", datetime.now().isoformat(timespec="seconds")),
            reason=payload.get("reason", ""),
        )


@dataclass
class SellDecision:
    symbol: str
    action: str
    current_price: float
    pnl_pct: float
    reason: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
