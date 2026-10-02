"""UE-side receiver for the send_ue_notification MCP tool.

VM1's send_ue_notification POSTs {"message", "incident_id"} to
http://<ue_ip>:<port>/notify over the UE's 5G data session. This listener runs
next to UERANSIM, waits for the UE's tunnel interface to come up, and binds to
that interface's IPv4 address only — never 0.0.0.0 — so it is reachable solely
through the PDU session, not the VM's management network.

Standard library only. Run one instance per UE interface:

    .venv/bin/python scripts/ue_notify_listener.py                     # uesimtun0:9000
    .venv/bin/python scripts/ue_notify_listener.py -i uesimtun1 -p 9000
"""

import argparse
import fcntl
import json
import os
import socket
import struct
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

_SIOCGIFADDR = 0x8915  # Linux ioctl: get interface IPv4 address
_MAX_BODY = 4096       # tool caps message at 500 chars; leave headroom for JSON + incident_id
_POLL_INTERVAL = 1.0


def _interface_ipv4(ifname: str) -> str | None:
    """Return the interface's IPv4 address, or None if it doesn't exist / has none yet."""
    if not os.path.exists(f"/sys/class/net/{ifname}"):
        return None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            packed = fcntl.ioctl(s.fileno(), _SIOCGIFADDR, struct.pack("256s", ifname[:15].encode()))
        except OSError:
            return None
    return socket.inet_ntoa(packed[20:24])


def _wait_for_ipv4(ifname: str) -> str:
    announced = False
    while True:
        ip = _interface_ipv4(ifname)
        if ip:
            return ip
        if not announced:
            print(f"Waiting for {ifname} to exist and get an IPv4 address…", flush=True)
            announced = True
        time.sleep(_POLL_INTERVAL)


def _make_handler(ifname: str):
    class NotifyHandler(BaseHTTPRequestHandler):
        server_version = "ue-notify-listener"
        sys_version = ""

        def _reply(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _reject(self, status: int, error: str) -> None:
            self._reply(status, {"ok": False, "error": error})

        def do_POST(self):
            if self.path != "/notify":
                return self._reject(404, "not found")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._reject(411, "Content-Length required")
            if length > _MAX_BODY:
                return self._reject(413, f"body exceeds {_MAX_BODY} bytes")
            try:
                data = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._reject(400, "body is not valid JSON")
            if not isinstance(data, dict):
                return self._reject(400, "body must be a JSON object")

            message = data.get("message")
            incident_id = data.get("incident_id")
            if not isinstance(message, str) or not message.strip():
                return self._reject(400, "'message' must be a non-empty string")
            if incident_id is not None and not isinstance(incident_id, str):
                return self._reject(400, "'incident_id' must be a string or null")

            ts = datetime.now().astimezone().isoformat(timespec="seconds")
            print(f"[{ts}] {ifname} incident={incident_id or '-'} from={self.client_address[0]}: {message}",
                  flush=True)
            self._reply(200, {"ok": True, "received_at": ts, "incident_id": incident_id})

        def _method_not_allowed(self):
            if self.path != "/notify":
                return self._reject(404, "not found")
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_PUT = do_DELETE = do_PATCH = _method_not_allowed

        def do_HEAD(self):
            self.send_response(404 if self.path != "/notify" else 405)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, fmt, *args):
            # Silence the default stderr access log so the terminal shows only
            # the timestamped notification lines.
            pass

    return NotifyHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive send_ue_notification POSTs on a UE tunnel interface.")
    parser.add_argument("-i", "--interface", default="uesimtun0", help="UE tunnel interface (default: uesimtun0)")
    parser.add_argument("-p", "--port", type=int, default=9000, help="TCP port (default: 9000)")
    args = parser.parse_args()

    try:
        ip = _wait_for_ipv4(args.interface)
        server = HTTPServer((ip, args.port), _make_handler(args.interface))
    except KeyboardInterrupt:
        print("\nStopped before the interface came up.")
        return
    except OSError as e:
        sys.exit(f"Cannot bind {args.interface} ({ip}:{args.port}): {e}")

    print(f"Listening on http://{ip}:{args.port}/notify ({args.interface}) — Ctrl-C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
