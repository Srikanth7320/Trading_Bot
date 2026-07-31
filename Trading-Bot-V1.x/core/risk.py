from datetime import datetime

from core.models import Position, Recommendation


class RiskEngine:
    def __init__(self, settings):
        self.settings = settings

    def price_allowed(self, price: float) -> bool:
        return self.settings.min_price <= price <= self.settings.max_price

    def build_recommendation(self, symbol: str, latest, score: float, reason: str, news_score: float, ai_note: str) -> Recommendation:
        price = float(latest["Close"])
        atr = float(latest.get("ATR14") or 0)
        stop_distance = max(price * (self.settings.stop_loss_pct / 100), atr * 1.2 if atr > 0 else 0)
        target_distance = max(price * (self.settings.target_pct / 100), stop_distance * 1.5)
        return Recommendation(
            symbol=symbol,
            price=round(price, 2),
            score=round(score, 2),
            action="BUY",
            reason=reason,
            stop_loss=round(price - stop_distance, 2),
            target=round(price + target_distance, 2),
            rsi=round(float(latest.get("RSI", 0)), 2),
            macd=round(float(latest.get("MACD", 0)), 4),
            signal=round(float(latest.get("MACD_SIGNAL", 0)), 4),
            volume_ratio=round(float(latest.get("VOLUME_RATIO", 0)), 2),
            news_score=round(news_score, 2),
            ai_note=ai_note,
        )

    def open_position(self, recommendation: Recommendation) -> Position:
        return Position(
            symbol=recommendation.symbol,
            entry_price=recommendation.price,
            quantity=self.settings.default_quantity,
            stop_loss=recommendation.stop_loss,
            target=recommendation.target,
            highest_price=recommendation.price,
            opened_at=datetime.now().isoformat(timespec="seconds"),
            reason=recommendation.reason,
        )
