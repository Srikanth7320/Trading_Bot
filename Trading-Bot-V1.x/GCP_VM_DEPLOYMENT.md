# GCP VM Deployment Guide for NSE Trading Bot

This guide covers how to deploy the NSE trading bot on a Google Cloud VM, copy files from your local machine to the VM, and host the dashboard page.

## 1) Prerequisites

- A Google Cloud account
- A GCP project with billing enabled
- `gcloud` installed locally
- `ssh` access enabled
- Python 3.11+ on the VM
- Access to the project source code on your laptop

## 2) Create a VM in GCP

### Create the VM

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud compute instances create trading-bot-vm \
  --zone=us-central1-a \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --tags=http-server,https-server
```

### Open ports for access

For the dashboard and HTTP access:

```bash
gcloud compute firewall-rules create allow-http-8000 \
  --allow tcp:8000 \
  --target-tags=http-server
```

Optional if you want Nginx on port 80:

```bash
gcloud compute firewall-rules create allow-http-80 \
  --allow tcp:80 \
  --target-tags=http-server
```

## 3) Connect to the VM

```bash
gcloud compute ssh trading-bot-vm --zone=us-central1-a
```

## 4) Install system dependencies

On the VM:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx
```

## 5) Copy project files from local machine to the VM

From your local machine, in PowerShell:

```powershell
gcloud compute scp --recurse "E:\Trading_bot_EC2\Trading-Bot-V1.x" trading-bot-vm:/home/yourusername/ --zone=us-central1-a
```

Or from a Linux/macOS shell:

```bash
gcloud compute scp --recurse /path/to/Trading-Bot-V1.x user@trading-bot-vm:/home/user/
```

If the folder is large, you may prefer `rsync`:

```bash
rsync -avz --progress /path/to/Trading-Bot-V1.x/ user@trading-bot-vm:/home/user/Trading-Bot-V1.x/
```

## 6) Set up Python environment

On the VM:

```bash
cd /home/yourusername/Trading-Bot-V1.x
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 7) Configure environment variables

Create `.env` from the project settings:

```bash
cp .env.example .env
```

Then edit `.env` and set values such as:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GEMINI_API_KEY=...
NEWS_API_KEY=...
PAPER_TRADING=true
ENABLE_AI=true
ENABLE_NEWS=true
```

Important: check the values in `config.py` and your deployment `.env` before starting the bot.

## 8) Run the bot

Start the app in the background:

```bash
cd /home/yourusername/Trading-Bot-V1.x
source .venv/bin/activate
nohup python main.py > /tmp/trading_bot.log 2>&1 &
```

Check logs:

```bash
tail -f /tmp/trading_bot.log
```

## 9) Host the dashboard page

The dashboard is served by `dashboard_server.py`.

### Option A: Run directly on a port

```bash
cd /home/yourusername/Trading-Bot-V1.x
source .venv/bin/activate
nohup python dashboard_server.py --port 8000 > /tmp/dashboard.log 2>&1 &
```

Then open:

```text
http://<VM_EXTERNAL_IP>:8000/dashboard.html
```

### Option B: Use Nginx reverse proxy on port 80

Create a server block:

```bash
sudo nano /etc/nginx/sites-available/trading-bot
```

Add:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Then open:

```text
http://<VM_EXTERNAL_IP>/dashboard.html
```

## 10) Static dashboard hosting alternative

If you only need the HTML page and not the Python server, you can serve the folder using Nginx directly. But for this bot, the project README warns that direct `python -m http.server` on the reports directory is not the correct way because it cannot access the bot data directory correctly.

The proper way is to run `dashboard_server.py` and then expose it via Nginx or a direct port.

## 11) Useful commands

### Start bot

```bash
cd /home/yourusername/Trading-Bot-V1.x
source .venv/bin/activate
python main.py
```

### Start dashboard

```bash
cd /home/yourusername/Trading-Bot-V1.x
source .venv/bin/activate
python dashboard_server.py --port 8000
```

### Check running processes

```bash
ps -ef | grep python
```

### Stop a process

```bash
pkill -f "dashboard_server.py"
pkill -f "main.py"
```

## 12) Deployment checklist

Before you deploy to production:

- Confirm `.env` values are correct
- Confirm `GEMINI_API_KEY` and `NEWS_API_KEY` are valid
- Confirm the symbol CSV exists
- Confirm the dashboard can access the data folder
- Confirm the bot is running with `PAPER_TRADING=true` until validation passes
- Confirm the strategy passes the market-readiness gate in backtests
- Confirm there is enough disk space and uptime on the VM

## 13) Important note

This project is not currently ready for real deployment as a live profit strategy. The latest real-market sanity check showed a weak outcome:

- trades: 6
- win rate: 16.67%
- average PnL: -2.53%
- total PnL: -15.21%

So deploy only as a paper or research system until the strategy passes the profitability gate.

## 14) Useful GCP command recap

```bash
gcloud compute ssh trading-bot-vm --zone=us-central1-a
gcloud compute scp --recurse "E:\Trading_bot_EC2\Trading-Bot-V1.x" trading-bot-vm:/home/yourusername/ --zone=us-central1-a
```

## 15) Next step after deployment

Once the VM is running:

1. Open the bot dashboard at the VM IP
2. Confirm data files are visible
3. Confirm the API endpoints return data
4. Check the logs for runtime issues
5. Run the strategy validation script before enabling live trading

---

If you want, use this exact flow on your local Windows machine and VM, then the dashboard should be reachable externally through the VM IP or through Nginx on port 80.
