"""
Simple parameter sweep for stop loss, trailing stop, and risk per trade.
Run from repository root:
python tools/backtest_sweep.py --symbols RELIANCE TCS
"""
import itertools
import logging
from dataclasses import replace
from config import Settings
from core.market_data import MarketDataClient
from core.news import NewsClient
from core.ai_score import AIScorer
from core.risk import RiskEngine
from core.backtest import SimpleBacktester

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STOP_LOSSES = [1.5, 2.0, 2.5, 3.0]
TRAILS = [0.5, 1.0, 1.5]
RISKS = [0.5, 1.0, 1.5]


def run_sweep(symbols=None):
    base_settings = Settings()
    market = MarketDataClient()
    news = NewsClient(base_settings.news_api_key, base_settings.enable_news)
    ai = AIScorer(base_settings.gemini_api_key, base_settings.gemini_model, base_settings.enable_ai)

    results = []
    total = len(STOP_LOSSES) * len(TRAILS) * len(RISKS)
    i = 0
    for stop, trail, risk in itertools.product(STOP_LOSSES, TRAILS, RISKS):
        i += 1
        s = replace(base_settings, stop_loss_pct=stop, trailing_stop_pct=trail, risk_per_trade_pct=risk)
        risk_engine = RiskEngine(s)
        backtester = SimpleBacktester(s, market, news, ai, risk_engine)
        res = backtester.run(symbols)
        results.append((stop, trail, risk, res))
        print(f"{i}/{total} stop={stop} trail={trail} risk={risk} -> total_pnl={res.get('total_pnl')} avg_pnl={res.get('avg_pnl')} win_rate={res.get('win_rate')}")

    # sort by total_pnl desc
    results.sort(key=lambda r: r[3].get('total_pnl', 0), reverse=True)
    print('\nTop results:')
    for stop, trail, risk, res in results[:10]:
        print(f"stop={stop} trail={trail} risk={risk} -> total_pnl={res.get('total_pnl')} avg_pnl={res.get('avg_pnl')} win_rate={res.get('win_rate')}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='*', default=None)
    args = parser.parse_args()
    run_sweep(args.symbols)
