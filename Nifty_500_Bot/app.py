import os
import threading
import time
from datetime import datetime
import pytz
import requests
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash
import schedule
from dotenv import load_dotenv
from bot_engine import (
    run_market_scan,
    refresh_nifty500_symbols,
    send_telegram,
    ACTIVE_FILE,
    SOLD_FILE,
    COOLING_FILE,
    TRADES_FILE,
    fetch_stock_data_with_fallback
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "niftybot_secure_flash_key")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
APPROVED_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))

# Official NSE Equities Trading Holidays for 2026 (Format: YYYY-MM-DD)
NSE_HOLIDAYS_2026 = {
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Holi
    "2026-03-26",  # Shri Ram Navami
    "2026-03-31",  # Shri Mahavir Jayanti
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-28",  # Bakri Id
    "2026-06-26",  # Muharram
    "2026-09-14",  # Ganesh Chaturthi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-10",  # Diwali-Balipratipada
    "2026-11-24",  # Prakash Gurpurb Sri Guru Nanak Dev
    "2026-12-25",  # Christmas
}

def is_market_open():
    """
    Checks if the Indian stock market (NSE) is currently open.
    Hours: Monday-Friday, 09:15 AM to 03:30 PM IST (excluding official NSE holidays).
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # 1. Weekend check (Saturday = 5, Sunday = 6)
    if now.weekday() >= 5:
        return False
        
    # 2. Holiday check
    today_str = now.strftime("%Y-%m-%d")
    if today_str in NSE_HOLIDAYS_2026:
        return False

    # 3. Time check (09:15 AM - 03:30 PM IST)
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_start <= now <= market_end

def telegram_command_listener():
    """Polls Telegram for commands like /summary and /scan securely"""
    if not TELEGRAM_TOKEN or not APPROVED_CHAT_ID:
        return
    
    last_update_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=30"
            res = requests.get(url, timeout=35)
            if res.status_code == 200:
                data = res.json()
                for update in data.get("result", []):
                    last_update_id = update["update_id"]
                    message = update.get("message", {})
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    text = message.get("text", "").strip().lower()

                    if chat_id == APPROVED_CHAT_ID:
                        if text == "/summary":
                            send_portfolio_summary(chat_id)
                        elif text == "/scan":
                            if not is_market_open():
                                send_telegram("⚠️ *Manual scan rejected:* Market is currently closed or on a holiday.")
                            else:
                                send_telegram("🔍 *Manual scan initiated via Telegram...* Please wait a moment.")
                                run_market_scan()
                                send_telegram("✅ *Manual scan complete!* Checked 50 stocks for entry/exit signals.")
        except Exception as e:
            print(f"Telegram Polling Error: {e}")
        time.sleep(2)

def send_portfolio_summary(chat_id):
    """Computes exact metrics and replies to Telegram /summary request"""
    buy_count, sell_count = 0, 0
    if os.path.exists(TRADES_FILE):
        df_trades = pd.read_csv(TRADES_FILE)
        buy_count = len(df_trades[df_trades["type"] == "BUY"])
        sell_count = len(df_trades[df_trades["type"] == "SELL"])

    active_count = 0
    active_pnl = 0.0
    if os.path.exists(ACTIVE_FILE):
        df_active = pd.read_csv(ACTIVE_FILE)
        active_count = len(df_active)
        for _, row in df_active.iterrows():
            live = fetch_stock_data_with_fallback(row["symbol"])
            cur_price = live["price"] if live else float(row["buy_price"])
            active_pnl += (cur_price - float(row["buy_price"])) * int(row["quantity"])

    realized_pnl = 0.0
    if os.path.exists(SOLD_FILE):
        df_sold = pd.read_csv(SOLD_FILE)
        realized_pnl = df_sold["profit"].sum() if not df_sold.empty else 0.0

    msg = (
        f"📊 *Portfolio & Bot Summary*\n\n"
        f"• Total Buy Signals: *{buy_count}*\n"
        f"• Total Sell Signals: *{sell_count}*\n"
        f"• Current Active Stocks: *{active_count}*\n"
        f"• Realized Profit (Bagged): *₹{realized_pnl:.2f}*\n"
        f"• Active Stocks P&L: *₹{active_pnl:.2f}*"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})

def background_scheduler():
    refresh_nifty500_symbols()
    schedule.every().day.at("08:00").do(refresh_nifty500_symbols)
    # Only execute scheduled market scan if market is open
    schedule.every(15).minutes.do(lambda: run_market_scan() if is_market_open() else None)
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route("/")
def dashboard():
    active_count, total_invested, total_current = 0, 0.0, 0.0
    if os.path.exists(ACTIVE_FILE):
        df_active = pd.read_csv(ACTIVE_FILE)
        active_count = len(df_active)
        for _, row in df_active.iterrows():
            live = fetch_stock_data_with_fallback(row["symbol"])
            cur_price = live["price"] if live else float(row["buy_price"])
            total_invested += float(row["buy_price"]) * int(row["quantity"])
            total_current += cur_price * int(row["quantity"])

    sold_count, realized_pnl = 0, 0.0
    if os.path.exists(SOLD_FILE):
        df_sold = pd.read_csv(SOLD_FILE)
        sold_count = len(df_sold)
        realized_pnl = df_sold["profit"].sum() if not df_sold.empty else 0.0

    cooling_count = len(pd.read_csv(COOLING_FILE)) if os.path.exists(COOLING_FILE) else 0
    unrealized_pnl = total_current - total_invested

    summary = {
        "active_count": active_count,
        "sold_count": sold_count,
        "cooling_count": cooling_count,
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2)
    }
    
    market_open = is_market_open()
    return render_template("dashboard.html", summary=summary, market_open=market_open)

@app.route("/active")
def active_page():
    active_stocks = []
    if os.path.exists(ACTIVE_FILE):
        df_active = pd.read_csv(ACTIVE_FILE)
        for _, row in df_active.iterrows():
            sym = row["symbol"]
            buy_price = float(row["buy_price"])
            qty = int(row["quantity"])
            live = fetch_stock_data_with_fallback(sym)
            current_price = live["price"] if live else buy_price
            invested = buy_price * qty
            current_val = current_price * qty
            pnl = current_val - invested
            pnl_pct = (pnl / invested) * 100 if invested > 0 else 0
            active_stocks.append({
                "symbol": sym, "buy_time": row["buy_time"], "buy_price": buy_price,
                "current_price": current_price, "quantity": qty,
                "invested": round(invested, 2), "current_val": round(current_val, 2),
                "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)
            })
    return render_template("active.html", active_stocks=active_stocks)

@app.route("/sold")
def sold_page():
    sold_stocks = pd.read_csv(SOLD_FILE).to_dict(orient="records") if os.path.exists(SOLD_FILE) else []
    return render_template("sold.html", sold_stocks=sold_stocks)

@app.route("/cooling")
def cooling_page():
    cooling_stocks = pd.read_csv(COOLING_FILE).to_dict(orient="records") if os.path.exists(COOLING_FILE) else []
    return render_template("cooling.html", cooling_stocks=cooling_stocks)

@app.route("/update_quantity", methods=["POST"])
def update_quantity():
    symbol = request.form.get("symbol")
    quantity = int(request.form.get("quantity", 1))
    if os.path.exists(ACTIVE_FILE):
        df_active = pd.read_csv(ACTIVE_FILE)
        df_active.loc[df_active["symbol"] == symbol, "quantity"] = quantity
        df_active.to_csv(ACTIVE_FILE, index=False)
    return redirect(url_for("active_page"))

@app.route("/trigger_scan", methods=["POST"])
def trigger_scan():
    if not is_market_open():
        flash("⚠️ Market is closed or on holiday. Manual scan cannot be executed.", "warning")
    else:
        run_market_scan()
        flash("✅ Manual market scan triggered successfully!", "success")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    send_telegram("🟢 *NiftyBot is online and running successfully!* 🚀")

    t_scan = threading.Thread(target=background_scheduler, daemon=True)
    t_scan.start()
    
    t_telegram = threading.Thread(target=telegram_command_listener, daemon=True)
    t_telegram.start()

    app.run(host="0.0.0.0", port=5000, debug=False)