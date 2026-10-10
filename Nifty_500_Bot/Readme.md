# 1. Create virtual environment (if not already done)
python3 -m venv venv

# 2. Activate it
source venv/bin/activate

# 3. Upgrade pip to prevent build issues
pip install --upgrade pip

# 4. Install requirements
pip install -r requirements.txt

# Start the bot service
sudo systemctl start niftybot

# Check its status (it should show 'active (running)')
sudo systemctl status niftybot

http://<your-server-ip>:5000

To watch your bot's live background activity and API calls in real time, check the system logs:
journalctl -u niftybot -f