# Nifty 500 Automated Paper Trading Bot

A 24/7 automated paper-trading system for Nifty 500 stocks running on a Google Cloud Platform (GCP) Virtual Machine. Features interval-based technical scans (RSI, Moving Averages, 52-week position), Gemini AI news/fundamental filtering, a Flask web dashboard, and interactive Telegram control.

---

## 0. Prerequisite VM Setup (First-Time GCP Instance Configuration)

Run these commands once on a fresh Linux instance (Ubuntu/Debian) to prepare Python and development essentials:

```bash
# 1. Update package list and upgrade existing packages
sudo apt update && sudo apt upgrade -y

# 2. Install Python 3, pip, and virtual environment support
sudo apt install -y python3 python3-pip python3-venv build-essential git

# 3. Verify installations
python3 --version
pip3 --version
```

---

## 1. Project Structure

Ensure your project directory is organized as follows:

```text
/home/kvslakshmi77/Nifty_500_Bot/
├── app.py                  # Flask web dashboard & Telegram listener
├── bot_engine.py           # Market scanning & strategy evaluation logic
├── .env                    # Environment variables & API credentials (without quotes)
├── requirements.txt        # Python package dependencies
├── templates/              # HTML templates for Flask dashboard
└── venv/                   # Python virtual environment
```

---

## 2. Environment Setup & Installation

### Step 1: Create `.env` File
Create a `.env` file in the project root with your credentials. **Important:** Do not use quotation marks (`""`) around your values, as Python can include them in the strings and cause authentication errors:

```env
TELEGRAM_BOT_TOKEN=your_actual_telegram_bot_token
TELEGRAM_CHAT_ID=your_actual_telegram_chat_id
GEMINI_API_KEY=your_actual_gemini_api_key
```

### Step 2: Virtual Environment & Dependencies
```bash
# Navigate to project folder
cd /home/kvslakshmi77/Nifty_500_Bot

# 1. Create virtual environment
python3 -m venv venv

# 2. Activate virtual environment
source venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install requirements
pip install -r requirements.txt
```

---

## 3. Systemd Service Setup

### Step 1: Create the service file
Open the system service configuration file:
```bash
sudo nano /etc/systemd/system/niftybot.service
```

### Step 2: Paste configuration
Paste the following configuration into the file (save with `Ctrl + O`, `Enter`, and exit with `Ctrl + X`):

```ini
[Unit]
Description=Nifty Paper Trading Bot
After=network.target

[Service]
User=kvslakshmi77
WorkingDirectory=/home/kvslakshmi77/Nifty_500_Bot
ExecStart=/home/kvslakshmi77/Nifty_500_Bot/venv/bin/python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Step 3: Enable and start service
```bash
# Reload systemd daemon
sudo systemctl daemon-reload

# Enable service to run automatically on boot
sudo systemctl enable niftybot

# Start the service immediately
sudo systemctl start niftybot
```

---

## 4. Service Management Commands

```bash
# Start service
sudo systemctl start niftybot

# Stop service
sudo systemctl stop niftybot

# Restart service (use after editing code files or .env)
sudo systemctl restart niftybot

# Check service status
sudo systemctl status niftybot
```

---

## 5. Web Dashboard Access & Firewall Setup

The Flask dashboard runs locally on port `5000`.

### Local Test
```bash
curl http://localhost:5000
```

### Browser Access
Open `http://<YOUR_VM_EXTERNAL_IP>:5000` in your web browser.

> **Note:** If the webpage doesn't load, make sure port `5000` is open in your GCP Firewall rules (`VPC Network` -> `Firewall` -> Create Firewall Rule allowing `TCP:5000` from source `0.0.0.0/0`).

---

## 6. Testing & Troubleshooting

### API Health Check
Verify Telegram and Gemini API connectivity directly from your terminal:
```bash
python3 -c "import os, requests; from dotenv import load_dotenv; load_dotenv(); print('Telegram:', requests.get(f'https://api.telegram.org/bot{os.getenv(\"TELEGRAM_BOT_TOKEN\")}/getMe').json().get('ok')); print('Gemini Key Loaded:', bool(os.getenv('GEMINI_API_KEY')))"
```

### View Live Service Logs
```bash
# Stream live logs in real-time
sudo journalctl -u niftybot -f

# View recent 100 log lines without paging
sudo journalctl -u niftybot -n 100 --no-pager
```

---

## 7. Telegram Bot Commands

Send these interactive commands directly to your bot in Telegram (restricted securely to your approved Chat ID):
* `/summary` - Get live portfolio stats, buy/sell signal counts, realized profit, and active stock P&L.
