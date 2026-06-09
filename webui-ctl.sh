#!/usr/bin/env bash
set -uo pipefail

PID_FILE=".chainlit.pid"
LOG_FILE="chainlit.log"
CMD=".venv/bin/python start.py"

_pid() { [[ -f "$PID_FILE" ]] && cat "$PID_FILE"; }
_running() { local p; p=$(_pid); [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; }

start() {
    if _running; then
        echo "Already running (PID $(_pid))"
        return
    fi
    nohup $CMD >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Started (PID $!  —  logs: $LOG_FILE)"
}

stop() {
    if ! _running; then
        echo "Not running"
        rm -f "$PID_FILE"
        return
    fi
    local pid; pid=$(_pid)
    # Kill chainlit child process(es) first, then the start.py wrapper
    pkill -P "$pid" 2>/dev/null
    kill "$pid" 2>/dev/null
    # Wait up to 5 s for the process to exit
    local i
    for i in {1..10}; do
        sleep 0.5
        kill -0 "$pid" 2>/dev/null || break
    done
    # Force kill if still alive
    if kill -0 "$pid" 2>/dev/null; then
        pkill -9 -P "$pid" 2>/dev/null
        kill -9 "$pid" 2>/dev/null
    fi
    # Release port in case uvicorn workers outlived the wrapper
    fuser -k 8000/tcp 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "Stopped (PID $pid)"
}

status() {
    if _running; then
        echo "Running (PID $(_pid))"
    else
        echo "Stopped"
    fi
}

case "${1:-help}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)  status ;;
    logs)    tail -f "$LOG_FILE" ;;
    *)       echo "Usage: $0 {start|stop|restart|status|logs}" ;;
esac
