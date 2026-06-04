import yaml
from pathlib import Path
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp.yaml"


@asynccontextmanager
async def get_mcp_tools():
    with open(_CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh)
    servers = {
        name: {"url": server["url"], "transport": server["transport"]}
        for name, server in cfg["servers"].items()
    }
    client = MultiServerMCPClient(servers)
    tools = await client.get_tools()
    yield tools


def describe_tools(tools: list) -> str:
    return "\n".join(f"  • {tool.name}: {tool.description}" for tool in tools)
