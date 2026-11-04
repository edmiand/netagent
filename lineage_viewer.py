"""Web UI viewer for this app's EQTY lineage manifests (config/lineage.yaml).

Two routes on Chainlit's FastAPI app:
    GET <root>/lineage/<thread_id>                — page showing the manifest in <eqty-explorer>
    GET <root>/lineage/<thread_id>/manifest.json  — the manifest itself

The explorer is the published @eqtylab/explorer web component, loaded from jsdelivr pinned
by version and SRI hash (same pin as the eqty-explorer skill). The manifest is fetched from
this server by the page and never sent anywhere else: the CSP only allows connections back
here and to the pinned explorer directory, and Referrer-Policy keeps the thread id in the
URL from reaching jsdelivr.
"""
import json
import secrets
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, HTMLResponse

ROOT = Path(__file__).parent
MANIFESTS_DIR = ROOT / "manifests"
_CONFIG_PATH = ROOT / "config" / "lineage.yaml"
_PAGE_PATH = ROOT / "lineage_viewer.html"

# A new version means a new hash:
#   curl -s <EXPLORER_JS> | openssl dgst -sha384 -binary | openssl base64 -A
EXPLORER_VERSION = "0.19.0"
EXPLORER_BASE = f"https://cdn.jsdelivr.net/npm/@eqtylab/explorer@{EXPLORER_VERSION}/dist/standalone/"
EXPLORER_JS = EXPLORER_BASE + "explorer.js"
EXPLORER_SRI = "sha384-wePxnL/hqJZdlNQPrjNNXr13ODwp5VDoV/nyGh+FHqD022h/oVfUXlvmZvz8mSdP"

_COMMON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


def is_enabled() -> bool:
    try:
        return bool(yaml.safe_load(_CONFIG_PATH.read_text()).get("viewer_enabled", False))
    except (OSError, AttributeError):
        return False


def _manifest_path(thread_id: str) -> Path | None:
    """The manifest for a canonical UUID thread id, or None. Only canonical UUIDs pass,
    so no path built from user input can leave manifests/."""
    try:
        if str(uuid.UUID(thread_id)) != thread_id:
            return None
    except ValueError:
        return None
    path = MANIFESTS_DIR / f"{thread_id}.json"
    return path if path.is_file() else None


def manifest_exists(thread_id: str | None) -> bool:
    return bool(thread_id) and _manifest_path(thread_id) is not None


def viewer_url(thread_id: str, root_path: str = "") -> str:
    return f"{root_path.rstrip('/')}/lineage/{thread_id}"


def _not_found() -> Response:
    return Response("No lineage manifest for this id.", status_code=404,
                    media_type="text/plain", headers=_COMMON_HEADERS)


def _build_router(root_path: str) -> APIRouter:
    router = APIRouter(prefix=f"{root_path.rstrip('/')}/lineage")

    @router.get("/{thread_id}/manifest.json")
    async def manifest_json(thread_id: str):
        path = _manifest_path(thread_id)
        if path is None:
            return _not_found()
        return FileResponse(path, media_type="application/json", headers={
            **_COMMON_HEADERS,
            "Content-Disposition": f'attachment; filename="netagent-lineage-{thread_id}.json"',
        })

    @router.get("/{thread_id}")
    async def page(thread_id: str):
        if _manifest_path(thread_id) is None:
            return _not_found()
        nonce = secrets.token_urlsafe(16)
        config = {"threadId": thread_id, "explorerSrc": EXPLORER_JS, "explorerSri": EXPLORER_SRI}
        # `</` can't close the script it sits in; the nonce lets only that inline script run.
        html = (_PAGE_PATH.read_text()
                .replace("__CONFIG__", json.dumps(config).replace("</", "<\\/"))
                .replace("__NONCE__", nonce))
        csp = (f"default-src 'none'; script-src 'nonce-{nonce}' 'wasm-unsafe-eval' {EXPLORER_BASE}; "
               f"style-src 'unsafe-inline'; img-src data: blob:; worker-src blob: {EXPLORER_BASE}; "
               f"connect-src 'self' {EXPLORER_BASE}; frame-src 'none'; "
               f"frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        return HTMLResponse(html, headers={**_COMMON_HEADERS, "Content-Security-Policy": csp})

    return router


def mount(app, root_path: str = "") -> None:
    """Add the routes ahead of Chainlit's catch-all `/{full_path:path}` (which serves the
    SPA and is registered when chainlit.server is imported, so anything appended after it
    would never be reached)."""
    routes = _build_router(root_path).routes
    app.router.routes[0:0] = routes
