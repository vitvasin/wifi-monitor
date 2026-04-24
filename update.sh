#!/usr/bin/env bash
# Pull latest code and restart the service.
# Safe to run on any robot — config.local.ini and credentials are never touched.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="wifi-monitor"

echo "==> Pulling latest code..."
# Ensure we are on main branch (not detached HEAD)
git -C "$SCRIPT_DIR" checkout main 2>/dev/null || git -C "$SCRIPT_DIR" checkout -b main --track origin/main

# Discard local changes to runtime files that shouldn't conflict with pulls
for f in .sync_state config.ini; do
    if git -C "$SCRIPT_DIR" ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        git -C "$SCRIPT_DIR" checkout -- "$f" 2>/dev/null || true
    fi
done

git -C "$SCRIPT_DIR" pull origin main

echo "==> Updating Python dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install -q --upgrade -r "$SCRIPT_DIR/requirements.txt"

echo "==> Restarting service..."
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "==> Done! Running version:"
git -C "$SCRIPT_DIR" log -1 --oneline
sudo systemctl status "$SERVICE_NAME" --no-pager -l
