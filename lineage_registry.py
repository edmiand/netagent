"""Register each chat's EQTY lineage with Integrity Service (config/lineage.yaml `register`).

When on, every chat becomes a lineage graph under one Guardian project, listed on that
project's Lineage Graphs page and updated after every turn. The EQTY SDK does the upload
(`Context.register`) from inside EqtyCallbackHandler; this module only decides whether it
happens and where. The local manifests/ file and the 🧬 viewer are unaffected.

What is uploaded is everything the local manifest holds — chat text and tool data,
including IMSIs, UE IPs and any K/OPc typed in. Only turn this on for a project whose
members may see that.

The SDK reads the API key from EQTY_API_KEY (.env). It needs Create Declarations and
View Project Data on the project.
"""
import logging
import os
import uuid
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config" / "lineage.yaml"


@lru_cache(maxsize=1)
def _settings() -> tuple[str, uuid.UUID] | None:
    """(Integrity Service URL, project UUID) when registration is on and configured, else None."""
    try:
        cfg = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    reg = cfg.get("register") or {}
    if not reg.get("enabled", False):
        return None
    url = str(reg.get("integrity_service_url") or "").rstrip("/")
    project = str(reg.get("project_uuid") or "").removeprefix("urn:uuid:")
    try:
        project_uuid = uuid.UUID(project)
    except ValueError:
        logger.warning("lineage registration off: project_uuid %r is not a UUID", project)
        return None
    if not url:
        logger.warning("lineage registration off: integrity_service_url is not set")
        return None
    if not os.environ.get("EQTY_API_KEY"):
        logger.warning("lineage registration off: EQTY_API_KEY is not set in .env")
        return None
    return url, project_uuid


def is_enabled() -> bool:
    return _settings() is not None


def project_uuid() -> uuid.UUID | None:
    """The Guardian project to root lineage at, or None to keep it local."""
    s = _settings()
    return s[1] if s else None


def integrity_service_url() -> str | None:
    """Passed to EqtyCallbackHandler; None keeps it from registering anything."""
    s = _settings()
    return s[0] if s else None
