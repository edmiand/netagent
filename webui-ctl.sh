#!/usr/bin/env bash
set -uo pipefail

SERVICE="5g-demo-app.service"
LOG_FILE="chainlit.log"
KB_DIR="data/chroma"

# Build the RAG knowledge base if it hasn't been built yet on this VM —
# data/chroma/ is gitignored so a fresh clone/pull never has it.
_ensure_knowledge_base() {
    if [[ ! -d "$KB_DIR" ]]; then
        echo "Knowledge base not found — building ($KB_DIR missing)..."
        .venv/bin/python scripts/build_knowledge_base.py
    fi
}

# Delegate to systemd user service when available (boot-managed path)
if systemctl --user is-enabled "$SERVICE" &>/dev/null; then
    case "${1:-help}" in
        start)   _ensure_knowledge_base; systemctl --user start   "$SERVICE" && echo "Started via systemd" ;;
        stop)    systemctl --user stop    "$SERVICE" && echo "Stopped via systemd" ;;
        restart) _ensure_knowledge_base; systemctl --user restart "$SERVICE" && echo "Restarted via systemd" ;;
        status)  systemctl --user status  "$SERVICE" ;;
        logs)    tail -f "$LOG_FILE" ;;
        *)       echo "Usage: $0 {start|stop|restart|status|logs}" ;;
    esac
    exit $?
fi

# Fallback: direct nohup management (service not enabled)
PID_FILE=".chainlit.pid"
CMD=".venv/bin/python start.py"

_pid() { [[ -f "$PID_FILE" ]] && cat "$PID_FILE"; }
_running() { local p; p=$(_pid); [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; }

start() {
    if _running; then
        echo "Already running (PID $(_pid))"
        return
    fi
    _ensure_knowledge_base
    nohup $CMD >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started (PID $!  —  logs: $LOG_FILE)"
}

stop() {
    local pid; pid=$(_pid)
    if [[ -n "$pid" ]]; then
        pkill -P "$pid" 2>/dev/null
        kill "$pid" 2>/dev/null
        local i
        for i in {1..10}; do
            sleep 0.5
            kill -0 "$pid" 2>/dev/null || break
        done
        if kill -0 "$pid" 2>/dev/null; then
            pkill -9 -P "$pid" 2>/dev/null
            kill -9 "$pid" 2>/dev/null
        fi
    fi
    # Always evict anything holding port 8000 — catches orphaned processes
    # whose PID is no longer in the PID file.
    fuser -k 8000/tcp 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "Stopped${pid:+ (PID $pid)}"
}

case "${1:-help}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)  if _running; then echo "Running (PID $(_pid))"; else echo "Stopped"; fi ;;
    logs)    tail -f "$LOG_FILE" ;;
    *)       echo "Usage: $0 {start|stop|restart|status|logs}" ;;
esac
