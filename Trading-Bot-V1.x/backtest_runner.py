import argparse
import logging
import os
from pathlib import Path

from config import Settings
from core.ai_score import AIScorer
from core.backtest import SimpleBacktester
from core.market_data import MarketDataClient
from core.news import NewsClient
from core.risk import RiskEngine


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple backtest for the NSE trading bot")
    parser.add_argument("--symbols", nargs="*", default=None, help="Optional list of symbols to backtest")
    args = parser.parse_args()

    settings = Settings()
    market = MarketDataClient()
    news = NewsClient(settings.news_api_key, settings.enable_news)
    ai = AIScorer(settings.gemini_api_key, settings.gemini_model, settings.enable_ai)
    risk = RiskEngine(settings)
    backtester = SimpleBacktester(settings, market, news, ai, risk)
    result = backtester.run(args.symbols)

    print("Backtest Summary")
    print("=" * 30)
    print(f"Trades: {result['trades']}")
    print(f"Win Rate: {result['win_rate']}%")
    print(f"Average PnL: {result['avg_pnl']}%")
    print(f"Total PnL: {result['total_pnl']}%")
    if result.get("trades_detail"):
        print("\nSample Trades:")
        for trade in result["trades_detail"][:10]:
            print(f"{trade['symbol']} | {trade['entry_date']} -> {trade['exit_date']} | {trade['pnl_pct']:.2f}% | {trade['reason']}")


if __name__ == "__main__":
    main()
