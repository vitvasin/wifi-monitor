#!/usr/bin/env bash
# Setup: create venv, install deps, register and start the wifi-monitor systemd service.
# Works on any machine regardless of username or install path.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="wifi-monitor"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON="$VENV_DIR/bin/python3"
CURRENT_USER="$(whoami)"

echo "==> Setting up wifi-monitor"
echo "    path : $SCRIPT_DIR"
echo "    user : $CURRENT_USER"
echo ""

# Prompt for robot name if not already set
CURRENT_NAME="$(python3 -c "
import configparser, sys
c = configparser.ConfigParser()
c.read('$SCRIPT_DIR/config.ini')
print(c.get('monitor', 'robot_name', fallback=''))
")"

if [ -z "$CURRENT_NAME" ] || [ "$CURRENT_NAME" = "Robot1" ]; then
    read -rp "Enter robot name for this machine [$(hostname)]: " ROBOT_NAME
    ROBOT_NAME="${ROBOT_NAME:-$(hostname)}"
    sed -i "s/^robot_name = .*/robot_name = $ROBOT_NAME/" "$SCRIPT_DIR/config.ini"
    echo "    robot: $ROBOT_NAME"
fi

echo ""
echo "==> Creating virtual environment..."
python3 -m venv "$VENV_DIR"

echo "==> Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo "==> Generating systemd service..."
cat > /tmp/$SERVICE_NAME.service <<EOF
[Unit]
Description=WiFi Connection Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON $SCRIPT_DIR/wifi_monitor.py
Restart=on-failure
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "==> Installing systemd service..."
sudo cp /tmp/$SERVICE_NAME.service /etc/systemd/system/$SERVICE_NAME.service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "==> Done! Service status:"
sudo systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "  tail -f $SCRIPT_DIR/logs/wifi_log.csv"
