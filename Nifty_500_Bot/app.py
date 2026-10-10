import os
import threading
import time
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for
import schedule
from bot_engine import run_market_scan, refresh_nifty500_symbols, ACTIVE_FILE, SOLD_FILE, COOLING_FILE, fetch_stock_data_with_fallback

app = Flask(__name__)

def background_scheduler():
    refresh_nifty500_symbols()
    schedule.every().day.at("08:00").do(refresh_nifty500_symbols)
    schedule.every(15).minutes.do(run_market_scan)
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route("/")
def dashboard():
    # Counts & Summaries
    active_count = 0
    total_invested = 0.0
    total_current = 0.0
    
    if os.path.exists(ACTIVE_FILE):
        df_active = pd.read_csv(ACTIVE_FILE)
        active_count = len(df_active)
        for _, row in df_active.iterrows():
            live = fetch_stock_data_with_fallback(row["symbol"])
            cur_price = live["price"] if live else row["buy_price"]
            total_invested += float(row["buy_price"]) * int(row["quantity"])
            total_current += cur_price * int(row["quantity"])

    sold_count = 0
    realized_pnl = 0.0
    if os.path.exists(SOLD_FILE):
        df_sold = pd.read_csv(SOLD_FILE)
        sold_count = len(df_sold)
        realized_pnl = df_sold["profit"].sum() if not df_sold.empty else 0.0

    cooling_count = 0
    if os.path.exists(COOLING_FILE):
        df_cooling = pd.read_csv(COOLING_FILE)
        cooling_count = len(df_cooling)

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
                "symbol": sym,
                "buy_time": row["buy_time"],
                "buy_price": buy_price,
                "current_price": current_price,
                "quantity": qty,
                "invested": round(invested, 2),
                "current_val": round(current_val, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2)
            })
    return render_template("active.html", active_stocks=active_stocks)

@app.route("/sold")
def sold_page():
    sold_stocks = []
    if os.path.exists(SOLD_FILE):
        df_sold = pd.read_csv(SOLD_FILE)
        sold_stocks = df_sold.to_dict(orient="records")
    return render_template("sold.html", sold_stocks=sold_stocks)

@app.route("/cooling")
def cooling_page():
    cooling_stocks = []
    if os.path.exists(COOLING_FILE):
        df_cooling = pd.read_csv(COOLING_FILE)
        cooling_stocks = df_cooling.to_dict(orient="records")
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
    t = threading.Thread(target=background_scheduler, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)