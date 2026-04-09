#!/bin/bash
# VPS setup for the new digest pipeline.
# Run once after deploying the updated agents folder.
#
#   scp -i ~/.ssh/iim_vps -r ~/dev/iimv2/agents/ root@157.180.83.168:/root/agents/
#   ssh -i ~/.ssh/iim_vps root@157.180.83.168 'bash /root/agents/setup_vps_digest.sh'

set -e

AGENTS_DIR="/root/agents"
VENV="$AGENTS_DIR/venv/bin/python"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== IIM Digest Pipeline Setup ==="

# 1. Install/update dependencies
cd "$AGENTS_DIR"
source venv/bin/activate
pip install -q -r requirements.txt

# 2. Create digest/ directory
mkdir -p "$AGENTS_DIR/digest"

# 3. Write systemd service for the Telegram bot
cat > "$SYSTEMD_DIR/iim-bot.service" <<EOF
[Unit]
Description=IIM Digest Approval Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$AGENTS_DIR
ExecStart=$VENV $AGENTS_DIR/telegram_bot.py
Restart=always
RestartSec=10
EnvironmentFile=$AGENTS_DIR/.env
StandardOutput=append:/root/logs/bot.log
StandardError=append:/root/logs/bot.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable iim-bot
systemctl restart iim-bot
echo "✓ iim-bot.service started"

# 4. Update crontab
# Remove old monitor cron (brief pipeline) if present
crontab -l 2>/dev/null | grep -v "monitor.py" | crontab - || true

# Add digest_scanner cron at 8:00 AM daily (if not already present)
(crontab -l 2>/dev/null | grep -v "digest_scanner"; \
 echo "0 8 * * * $VENV $AGENTS_DIR/digest_scanner.py >> /root/logs/digest_scanner.log 2>&1") | crontab -

echo "✓ Cron updated:"
crontab -l

# 5. Dry-run the scanner to verify everything works
echo ""
echo "=== Running scanner dry-run ==="
$VENV "$AGENTS_DIR/digest_scanner.py" --dry-run

echo ""
echo "=== Setup complete ==="
echo "Bot status: $(systemctl is-active iim-bot)"
echo "Cron: digest_scanner runs daily at 8:00 AM"
