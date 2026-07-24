#!/usr/bin/env bash
# Installs the NetAgent Chainlit app as a systemd --user service so it
# starts automatically on boot (survives reboots without a manual login).
#
# Usage: ./scripts/install_service.sh
#
# webui-ctl.sh auto-detects this service (by the name below) and delegates
# start/stop/restart/status to systemctl --user once it's enabled.
set -euo pipefail

SERVICE_NAME="netagent-app.service"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_PATH="$UNIT_DIR/$SERVICE_NAME"

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
    echo "error: $REPO_ROOT/.venv/bin/python not found — run 'pip install -e .' in a venv first" >&2
    exit 1
fi

mkdir -p "$UNIT_DIR"

cat > "$UNIT_PATH" <<EOF
[Unit]
Description=NetAgent 5G Core Chainlit Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT
ExecStart=$REPO_ROOT/.venv/bin/python start.py
Restart=on-failure
RestartSec=5
StandardOutput=append:$REPO_ROOT/chainlit.log
StandardError=append:$REPO_ROOT/chainlit.log

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"

# Lingering lets the user service start at boot without an active login
# session — without this, systemd --user units only start after you log in.
loginctl enable-linger "$(whoami)" 2>/dev/null || {
    echo "warning: could not enable lingering automatically — run manually:" >&2
    echo "  sudo loginctl enable-linger $(whoami)" >&2
}

echo "Installed and enabled $SERVICE_NAME (unit: $UNIT_PATH)"
echo "Start it now with: ./webui-ctl.sh start"
