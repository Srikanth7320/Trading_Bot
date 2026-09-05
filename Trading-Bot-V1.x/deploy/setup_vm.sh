#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/${USER:-ubuntu}/Trading-Bot-V1.x}"
APP_USER="${APP_USER:-${USER:-ubuntu}}"

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repository not found at $REPO_DIR"
  echo "Usage: REPO_DIR=/path/to/Trading-Bot-V1.x APP_USER=youruser ./setup_vm.sh"
  exit 1
fi

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git nginx

python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

if [[ -f "$REPO_DIR/.env.example" && ! -f "$REPO_DIR/.env" ]]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
fi

sed "s#__APP_DIR__#$REPO_DIR#g; s#__APP_USER__#$APP_USER#g" "$REPO_DIR/deploy/trading-bot.service" | sudo tee /etc/systemd/system/trading-bot.service > /dev/null
sed "s#__APP_DIR__#$REPO_DIR#g; s#__APP_USER__#$APP_USER#g" "$REPO_DIR/deploy/dashboard.service" | sudo tee /etc/systemd/system/dashboard.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable trading-bot.service
sudo systemctl enable dashboard.service

sudo systemctl start trading-bot.service
sudo systemctl start dashboard.service

sudo systemctl status trading-bot.service --no-pager
sudo systemctl status dashboard.service --no-pager

echo "Setup complete."
echo "Bot service: systemctl status trading-bot.service"
echo "Dashboard service: systemctl status dashboard.service"
echo "Dashboard URL: http://<VM_IP>:8000/dashboard.html"
