from datetime import datetime

from core.models import SellDecision
from core.sell_engine import SellEngine
from core.storage import Storage


class PositionMonitor:
    def __init__(self, storage: Storage, sell_engine: SellEngine):
        self.storage = storage
        self.sell_engine = sell_engine

    def run_once(self) -> list[SellDecision]:
        positions = self.storage.load_positions()
        remaining = []
        decisions: list[SellDecision] = []

        for position in positions:
            decision = self.sell_engine.evaluate(position)
            decisions.append(decision)
            self.storage.append_tracking(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "symbol": position.symbol,
                    "entry_price": position.entry_price,
                    "current_price": decision.current_price,
                    "pnl_pct": decision.pnl_pct,
                    "action": decision.action,
                    "reason": decision.reason,
                }
            )
            if decision.action == "SELL":
                self.storage.append_signal(decision)
            else:
                remaining.append(position)

        self.storage.save_positions(remaining)
        return decisions
