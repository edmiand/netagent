import logging
import yaml
from pathlib import Path
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp.yaml"

logger = logging.getLogger(__name__)


def get_mcp_url() -> str:
    with open(_CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh)
    first_server = next(iter(cfg["servers"].values()))
    return first_server["url"]


@asynccontextmanager
async def get_mcp_tools():
    with open(_CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh)
    servers = {
        name: {"url": server["url"], "transport": server["transport"]}
        for name, server in cfg["servers"].items()
    }
    try:
        url = get_mcp_url()
        logger.info("mcp_connect url=%s", url)
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
    except Exception as exc:
        logger.error("mcp_connect_error error=%s", str(exc)[:200])
        raise
    if len(tools) == 0:
        logger.warning("mcp_tools_loaded count=%d", len(tools))
    else:
        logger.info("mcp_tools_loaded count=%d", len(tools))
    yield tools
