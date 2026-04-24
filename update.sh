#!/usr/bin/env bash
# Pull latest code and restart the service.
# Safe to run on any robot — config.local.ini and credentials are never touched.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="wifi-monitor"

echo "==> Pulling latest code..."
git -C "$SCRIPT_DIR" pull

echo "==> Updating Python dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install -q --upgrade -r "$SCRIPT_DIR/requirements.txt"

echo "==> Restarting service..."
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "==> Done! Running version:"
git -C "$SCRIPT_DIR" log -1 --oneline
sudo systemctl status "$SERVICE_NAME" --no-pager -l
