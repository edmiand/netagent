#!/usr/bin/env python3
"""
Wrapper start script — syncs config/branding.yaml into .chainlit/config.toml
then launches Chainlit. Use this instead of running chainlit directly.

Usage:
    .venv/bin/python start.py [--host 0.0.0.0] [--port 8000]
"""
import re
import sys
import subprocess
import yaml
from pathlib import Path

ROOT = Path(__file__).parent


def sync_branding():
    branding = yaml.safe_load((ROOT / "config" / "branding.yaml").read_text())
    agent_name = branding.get("agent_name", "5G Core Agent")
    logo_file = branding.get("logo_file", "rogers-logo.svg")

    config_path = ROOT / ".chainlit" / "config.toml"
    content = config_path.read_text()

    content = re.sub(
        r'^(name\s*=\s*)".+"',
        f'\\1"{agent_name}"',
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r'^(default_avatar_file_url\s*=\s*)".+"',
        f'\\1"/public/logos/{logo_file}"',
        content,
        flags=re.MULTILINE,
    )

    config_path.write_text(content)
    print(f"Branding synced → name: {agent_name!r}, logo: {logo_file}")


if __name__ == "__main__":
    sync_branding()
    extra_args = sys.argv[1:] or ["--host", "0.0.0.0", "--port", "8000"]
    sys.exit(
        subprocess.call(
            [sys.executable, "-m", "chainlit", "run", "app.py"] + extra_args
        )
    )
