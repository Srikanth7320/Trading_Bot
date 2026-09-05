"""
Parameter sweep using the relaxed simple backtest logic.
"""
import itertools
import logging
from dataclasses import replace
from config import Settings
from core.market_data import MarketDataClient
from core.risk import RiskEngine
from core.indicators import add_indicators

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STOP_LOSSES = [1.0, 1.5, 2.0, 2.5, 3.0]
TRAILS = [0.5, 1.0, 1.5]
RISKS = [0.5, 1.0, 1.5]


def run_sweep(symbols=None):
    base = Settings()
    market = MarketDataClient()

    if symbols is None:
        symbols = [s for s in base.symbols][:20]

    results = []
    total = len(STOP_LOSSES) * len(TRAILS) * len(RISKS)
    i = 0
    for stop, trail, risk in itertools.product(STOP_LOSSES, TRAILS, RISKS):
        i += 1
        s = replace(base, stop_loss_pct=stop, trailing_stop_pct=trail, risk_per_trade_pct=risk)
        trades = []
        for symbol in symbols:
            try:
                history = market.get_history(symbol, period="1y", interval="1d")
                if history.empty or len(history) < 90:
                    continue
                enriched = add_indicators(history).dropna()
                if enriched.empty:
                    continue
                for idx in range(60, len(enriched)):
                    latest = enriched.iloc[idx]
                    price = float(latest.get("Close", 0))
                    if price <= float(latest.get("SMA20", price)):
                        continue
                    rsi = float(latest.get("RSI", 0))
                    rsi_max = getattr(s, "rsi_entry_max", 70.0)
                    if not 40 <= rsi <= rsi_max:
                        continue
                    # build recommendation
                    risk_engine = RiskEngine(s)
                    rec = risk_engine.build_recommendation(symbol, latest, 60.0, "relaxed entry", 0.0, "sweep")
                    entry = rec.price
                    stop_price = rec.stop_loss
                    target = rec.target
                    exit_price = None
                    for future_idx in range(idx + 1, min(len(enriched), idx + s.max_holding_days + 1)):
                        future = enriched.iloc[future_idx]
                        curr = float(future["Close"])
                        if curr <= stop_price:
                            exit_price = curr
                            reason = 'stop'
                            break
                        if curr >= target:
                            exit_price = curr
                            reason = 'target'
                            break
                    if exit_price is None:
                        last_idx = min(len(enriched)-1, idx + s.max_holding_days)
                        exit_price = float(enriched.iloc[last_idx]["Close"])
                        reason = 'max_hold'
                    pnl = ((exit_price - entry) / entry) * 100
                    trades.append(pnl)
                    break
            except Exception:
                continue
        total_pnl = sum(trades)
        avg_pnl = sum(trades)/len(trades) if trades else 0.0
        wins = sum(1 for p in trades if p>0)
        win_rate = wins/len(trades)*100 if trades else 0.0
        results.append((stop, trail, risk, total_pnl, avg_pnl, win_rate, len(trades)))
        print(f"{i}/{total} stop={stop} trail={trail} risk={risk} -> total_pnl={total_pnl:.2f} avg_pnl={avg_pnl:.2f} win_rate={win_rate:.2f}% trades={len(trades)}")

    results.sort(key=lambda r: r[3], reverse=True)
    print('\nTop results:')
    for row in results[:10]:
        print(f"stop={row[0]} trail={row[1]} risk={row[2]} -> total_pnl={row[3]:.2f} avg_pnl={row[4]:.2f} win_rate={row[5]:.2f}% trades={row[6]}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='*', default=None)
    args = parser.parse_args()
    run_sweep(args.symbols)
