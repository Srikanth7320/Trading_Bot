import logging
from config import Settings
from core.market_data import MarketDataClient
from core.risk import RiskEngine
from core.indicators import add_indicators

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

settings = Settings()
market = MarketDataClient()
risk = RiskEngine(settings)
symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'ITC', 'SUNPHARMA', 'BAJFINANCE', 'AXISBANK', 'KOTAKBANK']

trades = []
for symbol in symbols:
    try:
        history = market.get_history(symbol, period='1y', interval='1d')
        if history.empty or len(history) < 90:
            continue
        enriched = add_indicators(history).dropna()
        if enriched.empty:
            continue
        for idx in range(60, len(enriched)):
            latest = enriched.iloc[idx]
            price = float(latest.get('Close', 0))
            if price <= float(latest.get('SMA20', price)):
                continue
            rsi = float(latest.get('RSI', 0))
            if not 40 <= rsi <= getattr(settings, 'rsi_entry_max', 70.0):
                continue
            rec = risk.build_recommendation(symbol, latest, 60.0, 'check entry', 0.0, 'strategy validation')
            entry = rec.price
            stop = rec.stop_loss
            target = rec.target
            exit_price = None
            exit_idx = None
            reason = 'max_hold'
            for future_idx in range(idx + 1, min(len(enriched), idx + settings.max_holding_days + 1)):
                future = enriched.iloc[future_idx]
                curr = float(future['Close'])
                if curr <= stop:
                    exit_price = curr
                    exit_idx = future_idx
                    reason = 'stop'
                    break
                if curr >= target:
                    exit_price = curr
                    exit_idx = future_idx
                    reason = 'target'
                    break
            if exit_price is None:
                exit_idx = min(len(enriched)-1, idx + settings.max_holding_days)
                exit_price = float(enriched.iloc[exit_idx]['Close'])
            pnl = ((exit_price - entry) / entry) * 100
            trades.append({'symbol': symbol, 'entry_date': str(enriched.index[idx]), 'exit_date': str(enriched.index[exit_idx]), 'pnl': pnl, 'reason': reason})
            break
    except Exception as exc:
        logging.exception('Failed for %s: %s', symbol, exc)

if not trades:
    print('No trades found')
else:
    pnl_values = [t['pnl'] for t in trades]
    wins = sum(1 for p in pnl_values if p > 0)
    print(f"Trades: {len(trades)}")
    print(f"Win rate: {wins/len(trades)*100:.2f}%")
    print(f"Avg pnl: {sum(pnl_values)/len(pnl_values):.2f}%")
    print(f"Total pnl: {sum(pnl_values):.2f}%")
    for trade in trades:
        print(trade)
