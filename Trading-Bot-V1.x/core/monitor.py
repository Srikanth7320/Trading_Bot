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

            try:
                decision = self.sell_engine.evaluate(position)

                if decision is None:
                    remaining.append(position)
                    continue

                decisions.append(decision)

                # Save monitoring history
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

                # Persist updated values (highest_price etc.)
                if hasattr(self.storage, "update_position"):
                    self.storage.update_position(position)

                if decision.action == "SELL":

                    # Save completed trade
                    if hasattr(self.storage, "add_history"):
                        self.storage.add_history(position)

                    # Add cooldown
                    if hasattr(self.storage, "add_cooldown"):
                        self.storage.add_cooldown(
                            position.symbol,
                            self.storage.settings.cooldown_days
                            if hasattr(self.storage, "settings")
                            else 5,
                        )

                    # Save SELL signal
                    self.storage.append_signal(decision)

                    print(
                        f"[SELL] {position.symbol} | "
                        f"{decision.current_price:.2f} | "
                        f"{decision.pnl_pct:.2f}% | "
                        f"{decision.reason}"
                    )

                    # Do not add back to remaining positions

                else:

                    remaining.append(position)

                    print(
                        f"[HOLD] {position.symbol} | "
                        f"{decision.current_price:.2f} | "
                        f"{decision.pnl_pct:.2f}% | "
                        f"{decision.reason}"
                    )

            except Exception as ex:

                print(f"Monitor error for {position.symbol}: {ex}")

                # Never lose a position because of an error
                remaining.append(position)

        self.storage.save_positions(remaining)

        print(
            f"Monitoring completed. "
            f"Active Positions: {len(remaining)}"
        )

        return decisions