# NSE Trading Telegram Bot

Production-oriented Telegram assistant for NSE stock recommendations, monitoring, SELL alerts, and CSV/JSON logging.

## Features

- Daily 3-5 BUY recommendations for NSE stocks in the configured price range.
- Hourly monitoring of active positions.
- Dynamic SELL signals using stop loss, target, trailing stop, RSI, and MACD checks.
- CSV logging for hourly tracking and signal history.
- JSON storage for active positions, history, and cooldown state.
- Mandatory Gemini and NewsAPI scoring.
- Symbol universe loaded only from `data/nse_symbols.csv`; live scanner filters by the configured price range.
- Market-hours guard for NSE regular hours, Monday-Friday, 09:15-15:30 IST.

## Setup

```powershell
python -m venv .venv
source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, and `NEWS_API_KEY`.

## Environment Settings

Key `.env` settings:

- `TELEGRAM_BOT_TOKEN` - Telegram bot token from BotFather.
- `TELEGRAM_CHAT_ID` - Chat ID for scheduled alerts. Manual commands work without it.
- `GEMINI_API_KEY` - Required Gemini API key for AI scoring and notes.
- `GEMINI_MODEL` - Gemini model used for AI notes, for example `gemini-3.5-flash`.
- `NEWS_API_KEY` - Required NewsAPI key for news scoring.
- `MIN_STOCK_PRICE` - Minimum stock price considered by the scanner.
- `MAX_STOCK_PRICE` - Maximum stock price considered by the scanner.
- `MIN_RECOMMENDATIONS` - Minimum qualified signals required to send a daily alert; default `1`.
- `MINIMUM_VOLUME_RATIO` - Minimum current volume relative to its 20-day average; default `1.1`.
- `MAX_RECOMMENDATIONS` - Maximum recommendations returned per scan.
- `SCAN_INTERVAL_MINUTES` - How often scheduled BUY scans run during market hours.
- `MONITOR_INTERVAL_MINUTES` - How often active positions are checked during market hours.
- `DEFAULT_QUANTITY` - Quantity saved when the bot opens a tracked paper position.
- `STOP_LOSS_PCT` - Percent below entry price used for initial stop loss. Example: `3` means 3 percent below entry.
- `TARGET_PCT` - Percent above entry price used for target booking. Example: `6` means 6 percent above entry.
- `TRAILING_STOP_PCT` - Percent below the highest reached price used to protect gains after a position moves up.
- `MAX_ACTIVE_POSITIONS` - Maximum number of open tracked positions at one time.
- `ENABLE_AI` - Must be `true`; keeps Gemini scoring enabled.
- `ENABLE_NEWS` - Must be `true`; keeps NewsAPI scoring enabled.

## Stock Universe

Edit `data/nse_symbols.csv` to control which NSE stocks are scanned. This file is mandatory. Add symbols without `.NS`; the bot adds Yahoo Finance's NSE suffix internally.

Example:

```csv
symbol,name
RELIANCE,Reliance Industries
TCS,Tata Consultancy Services
```

## Run

```powershell
python main.py
```

## Dashboard

Run the dashboard through its bundled server so it can read live positions,
signals, and symbols from the bot's data directory:

```powershell
python dashboard_server.py --port 8000
```

Then open `http://<server-ip>:8000/dashboard.html`. Do not serve the
`reports` directory with `python -m http.server`; that server cannot access
the bot data directory, which causes the dashboard to show false zero counts.

Telegram commands:

- `/start` - show bot menu.
- `/scan` - generate fresh BUY recommendations.
- `/monitor` - check active positions for SELL/HOLD.
- `/summary` - show latest stored signals and positions.
- `/positions` - show active positions.
- `/help` - show commands.

`/scan`, `/monitor`, and scheduled jobs run only during NSE regular market hours. `/summary`, `/positions`, `/help`, and `/start` work anytime.

## EC2 Notes

Use environment variables or a `.env` file. For long-running deployment, run with `systemd`, `tmux`, or `screen`.
