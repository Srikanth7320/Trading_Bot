# GCP VM Deployment Pack

This folder contains a minimal systemd-based deployment setup for the trading bot and dashboard on a Linux VM.

## Files

- `setup_vm.sh` - installs Python dependencies and registers systemd services
- `trading-bot.service` - service for the main bot
- `dashboard.service` - service for the dashboard server

## Copy to VM

From your local machine:

```powershell
gcloud compute scp --recurse "E:\Trading_bot_EC2\Trading-Bot-V1.x" your-user@trading-bot-vm:/home/your-user/ --zone=us-central1-a
```

## Install on the VM

```bash
cd /home/your-user/Trading-Bot-V1.x/deploy
chmod +x setup_vm.sh
REPO_DIR=/home/your-user/Trading-Bot-V1.x APP_USER=your-user ./setup_vm.sh
```

## Check service status

```bash
systemctl status trading-bot.service
systemctl status dashboard.service
```

## Dashboard URL

```text
http://<VM_EXTERNAL_IP>:8000/dashboard.html
```

## Important

This project is still best treated as a paper-trading or research deployment. Real-market validation is still negative in the current evidence base, so do not run live money trading until the strategy clears the profitability gate.
