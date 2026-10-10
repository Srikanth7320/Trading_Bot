import os
import threading
import time
import requests
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for
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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
APPROVED_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))

def telegram_command_listener():
    """Polls Telegram for commands like /summary and responds securely to approved Chat ID"""
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

                    # Security check: Restrict access to your approved Chat ID only
                    if chat_id == APPROVED_CHAT_ID and text == "/summary":
                        send_portfolio_summary(chat_id)
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
    schedule.every(15).minutes.do(run_market_scan)
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
    return render_template("dashboard.html", summary=summary)

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
    run_market_scan()
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    # Send startup notification to Telegram
    send_telegram("🟢 *NiftyBot is online and running successfully!* 🚀")

    # Start background market scanner
    t_scan = threading.Thread(target=background_scheduler, daemon=True)
    t_scan.start()
    
    # Start Telegram command listener thread
    t_telegram = threading.Thread(target=telegram_command_listener, daemon=True)
    t_telegram.start()

    app.run(host="0.0.0.0", port=5000, debug=False)