# 1. Create virtual environment (if not already done)
python3 -m venv venv

# 2. Activate it
source venv/bin/activate

# 3. Upgrade pip to prevent build issues
pip install --upgrade pip

# 4. Install requirements
pip install -r requirements.txt

# Setting Up NiftyBot Systemd Service

### Step 1: Create the service file
Open the service configuration file with nano:
```bash
sudo nano /etc/systemd/system/niftybot.service

### Step 2: Paste the configuration
### Paste the configuration below into the file. Save with Ctrl + O then Enter, and exit with Ctrl + X:

Ini, TOML
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

### Step 3: Reload the systemd daemon
### Tell Linux to recognize the new service configuration:

Bash
sudo systemctl daemon-reload

### Step 4: Enable and start the bot service
### Set the service to run automatically on system boot and start it immediately:

Bash
sudo systemctl enable niftybot
sudo systemctl start niftybot
sudo systemctl status niftybot

#### Check it's running

sudo systemctl status niftybot

### Start, Stop & restart the bot
Bash
sudo systemctl start niftybot
sudo systemctl stop niftybot
sudo systemctl restart niftybot