import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from google import genai
from dotenv import load_dotenv

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

MIN_PRICE = float(os.getenv("MIN_STOCK_PRICE", 50))
MAX_PRICE = float(os.getenv("MAX_STOCK_PRICE", 5000))
RSI_BUY_THRESHOLD = float(os.getenv("RSI_BUY_THRESHOLD", 55.0))
# Exit threshold: if RSI drops below this during interval scans, consider exiting
RSI_EXIT_THRESHOLD = float(os.getenv("RSI_EXIT_THRESHOLD", 45.0))

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SYMBOLS_FILE = os.path.join(DATA_DIR, "nifty500_symbols.csv")
ACTIVE_FILE = os.path.join(DATA_DIR, "active_stocks.csv")
SOLD_FILE = os.path.join(DATA_DIR, "sold_stocks.csv")
TRADES_FILE = os.path.join(DATA_DIR, "trades_history.csv")
COOLING_FILE = os.path.join(DATA_DIR, "cooling_period.csv")

def get_current_ist_time():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def refresh_nifty500_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            with open(SYMBOLS_FILE, "wb") as f:
                f.write(res.content)
            print("Successfully updated Nifty 500 symbols list.")
            return
    except Exception as e:
        print(f"Failed live Nifty 500 download: {e}. Using local cache.")
    
    if not os.path.exists(SYMBOLS_FILE):
        df_default = pd.DataFrame({"Symbol": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]})
        df_default.to_csv(SYMBOLS_FILE, index=False)

def is_market_open():
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5: # Saturday, Sunday
        return False
    return dtime(9, 15) <= now_ist.time() <= dtime(15, 30)

def calculate_rsi(hist, window=14):
    delta = hist['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def fetch_stock_data_with_fallback(symbol):
    ticker_symbol = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 50:
            return None
        
        current_price = float(hist['Close'].iloc[-1])
        low_52w = float(hist['Low'].min())
        high_52w = float(hist['High'].max())
        rsi = calculate_rsi(hist)
        
        return {
            "symbol": symbol,
            "price": current_price,
            "low_52w": low_52w,
            "high_52w": high_52w,
            "rsi": rsi,
            "history": hist
        }
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def fetch_news_and_fundamentals(symbol):
    news_summary = ""
    if NEWS_API_KEY:
        try:
            url = f"https://newsapi.org/v2/everything?q={symbol}+stock+india&apiKey={NEWS_API_KEY}&pageSize=3"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                articles = res.json().get("articles", [])
                news_summary = " ".join([a.get("title", "") for a in articles])
        except Exception as e:
            print(f"NewsAPI error for {symbol}: {e}")

    if not client:
        return True, "Passed (No Gemini key)"

    prompt = f"""
    Analyze NSE stock {symbol}. 
    Recent News Context: {news_summary}
    1. Are the last quarter and last 6 months in profit/positive growth?
    2. Are fundamentals sound?
    Return format: Status: [PASS/FAIL] | Reason: [Short explanation]
    """
    try:
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = response.text.upper()
        if "FAIL" in text:
            return False, text
        return True, text
    except Exception as e:
        print(f"Gemini evaluation error for {symbol}: {e}")
        return True, "Passed (Gemini timeout fallback)"

def evaluate_technicals(hist, current_price, rsi):
    ma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
    ma_200 = hist['Close'].rolling(window=200).mean().iloc[-1] if len(hist) >= 200 else ma_50
    volume_avg = hist['Volume'].rolling(window=20).mean().iloc[-1]
    current_volume = hist['Volume'].iloc[-1]

    bullish_score = 0
    bearish_score = 0

    if current_price > ma_50: bullish_score += 2
    else: bearish_score += 1

    if current_price > ma_200: bullish_score += 2
    else: bearish_score += 1

    if rsi >= RSI_BUY_THRESHOLD: bullish_score += 2
    else: bearish_score += 1

    if current_volume > volume_avg: bullish_score += 1
    else: bearish_score += 1

    return bullish_score >= (bearish_score * 3)

def run_market_scan():
    if not is_market_open():
        return

    print(f"Running interval market scan at {get_current_ist_time()} IST...")
    if not os.path.exists(SYMBOLS_FILE):
        refresh_nifty500_symbols()
    
    df_sym = pd.read_csv(SYMBOLS_FILE)
    symbols = df_sym.iloc[:, 0].dropna().tolist()

    cooling_df = pd.read_csv(COOLING_FILE) if os.path.exists(COOLING_FILE) else pd.DataFrame(columns=["symbol", "time"])
    cooling_symbols = cooling_df["symbol"].tolist() if not cooling_df.empty else []

    active_df = pd.read_csv(ACTIVE_FILE) if os.path.exists(ACTIVE_FILE) else pd.DataFrame(columns=["symbol", "buy_price", "quantity", "buy_time"])

    # 1. Interval-Based Active Stock Evaluation (Tell when to sell based on momentum breakdown)
    for _, row in active_df.iterrows():
        sym = row["symbol"]
        buy_price = float(row["buy_price"])
        qty = int(row["quantity"])
        
        data = fetch_stock_data_with_fallback(sym)
        if not data:
            continue
        
        current_price = data["price"]
        rsi = data["rsi"]
        hist = data["history"]
        ma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        
        pnl_pct = ((current_price - buy_price) / buy_price) * 100
        
        # Dynamic Interval Exit Rules (No rigid fixed percentage):
        # Sell if momentum breaks: Price drops below 50 MA OR RSI drops below exit threshold (e.g. 45)
        momentum_broken = (current_price < ma_50) or (rsi < RSI_EXIT_THRESHOLD)
        
        if momentum_broken:
            reason = f"Momentum Broken (Price < 50 MA or RSI {rsi:.1f} < {RSI_EXIT_THRESHOLD})"
            record_sell_trade(sym, buy_price, current_price, qty)
            send_telegram(f"🔴 *DYNAMIC PAPER SELL SIGNAL*\nStock: `{sym}`\nBought: ₹{buy_price}\nCurrent: ₹{current_price}\nP&L: {pnl_pct:.2f}%\nReason: {reason}")

    # 2. Scan Universe for Buy Signals
    for sym in symbols[:50]:
        clean_sym = str(sym).strip().upper()
        if clean_sym in cooling_symbols or clean_sym in active_df["symbol"].values:
            continue
            
        data = fetch_stock_data_with_fallback(clean_sym)
        if not data:
            continue
            
        price = data["price"]
        if not (MIN_PRICE <= price <= MAX_PRICE):
            continue
            
        low = data["low_52w"]
        high = data["high_52w"]
        if high == low:
            continue
            
        perf_score = ((price - low) / (high - low)) * 100
        
        if perf_score >= 70:
            is_bullish_dominant = evaluate_technicals(data["history"], price, data["rsi"])
            
            if is_bullish_dominant:
                passed_ai, _ = fetch_news_and_fundamentals(clean_sym)
                if passed_ai:
                    msg = f"🟢 *PAPER BUY SIGNAL*\nStock: `{clean_sym}`\nPrice: ₹{price:.2f}\n52W Score: {perf_score:.1f}%\nRSI: {data['rsi']:.1f}\nReason: Bullish technicals dominant & sound fundamentals."
                    send_telegram(msg)
                    record_buy_trade(clean_sym, price)

def record_buy_trade(symbol, price):
    current_time = get_current_ist_time()
    trade_entry = {"time": current_time, "symbol": symbol, "price": price, "type": "BUY"}
    df_trades = pd.read_csv(TRADES_FILE) if os.path.exists(TRADES_FILE) else pd.DataFrame(columns=["time", "symbol", "price", "type"])
    df_trades = pd.concat([df_trades, pd.DataFrame([trade_entry])], ignore_index=True)
    df_trades.to_csv(TRADES_FILE, index=False)
    
    active_df = pd.read_csv(ACTIVE_FILE) if os.path.exists(ACTIVE_FILE) else pd.DataFrame(columns=["symbol", "buy_price", "quantity", "buy_time"])
    if symbol not in active_df["symbol"].values:
        new_row = {"symbol": symbol, "buy_price": price, "quantity": 1, "buy_time": current_time}
        active_df = pd.concat([active_df, pd.DataFrame([new_row])], ignore_index=True)
        active_df.to_csv(ACTIVE_FILE, index=False)

def record_sell_trade(symbol, buy_price, sold_price, quantity):
    current_time = get_current_ist_time()
    trade_entry = {"time": current_time, "symbol": symbol, "price": sold_price, "type": "SELL"}
    df_trades = pd.read_csv(TRADES_FILE) if os.path.exists(TRADES_FILE) else pd.DataFrame(columns=["time", "symbol", "price", "type"])
    df_trades = pd.concat([df_trades, pd.DataFrame([trade_entry])], ignore_index=True)
    df_trades.to_csv(TRADES_FILE, index=False)

    active_df = pd.read_csv(ACTIVE_FILE) if os.path.exists(ACTIVE_FILE) else pd.DataFrame(columns=["symbol", "buy_price", "quantity", "buy_time"])
    active_df = active_df[active_df["symbol"] != symbol]
    active_df.to_csv(ACTIVE_FILE, index=False)

    sold_df = pd.read_csv(SOLD_FILE) if os.path.exists(SOLD_FILE) else pd.DataFrame(columns=["symbol", "buy_price", "sold_price", "quantity", "profit", "sold_time"])
    profit = (sold_price - buy_price) * quantity
    new_sold = {
        "symbol": symbol,
        "buy_price": buy_price,
        "sold_price": sold_price,
        "quantity": quantity,
        "profit": round(profit, 2),
        "sold_time": current_time
    }
    sold_df = pd.concat([sold_df, pd.DataFrame([new_sold])], ignore_index=True)
    sold_df.to_csv(SOLD_FILE, index=False)

    cooling_df = pd.read_csv(COOLING_FILE) if os.path.exists(COOLING_FILE) else pd.DataFrame(columns=["symbol", "time"])
    new_cooling = {"symbol": symbol, "time": current_time}
    cooling_df = pd.concat([cooling_df, pd.DataFrame([new_cooling])], ignore_index=True)
    cooling_df.to_csv(COOLING_FILE, index=False)