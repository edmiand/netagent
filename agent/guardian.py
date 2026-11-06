"""Guardian Platform mode: every model call signed by Viper, as an enrolled agent.

Off by default (config/guardian.yaml). When on, the supervisor and each specialist are
built with the Guardian Agent SDK's `create_agent`, a drop-in for LangChain's: it routes
the chat model through the local Viper proxy (VIPER_PROXY_URL), describes the agent
(model, tools, MCP servers, middleware, prompt) as a definition, and names the agent on
every request, so the proxy signs it with that agent's key and the Agent Gateway
attributes it. When off, the same agents are built with LangChain's own `create_agent`.

Fails closed: in Guardian mode an agent that can't be described or registered raises,
and NetAgent shows the error rather than sending the call unsigned.

What is NOT signed, even in Guardian mode: MCP tool calls to VM1, Tavily, Hedera, and
the RAG / incident-memory embeddings (Ollama). Only chat-model calls go through Viper.
"""
import functools
from pathlib import Path

import yaml
from langchain.agents import create_agent as _langchain_create_agent

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "guardian.yaml"

# Guardian mode signs OpenAI-provider models only: the SDK routes ChatOpenAI and
# ChatAnthropic, and the proxy fronts the gateway's /v1/openai_api endpoint.
SIGNED_PROVIDERS = ("openai",)


@functools.lru_cache(maxsize=1)
def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH) as fh:
        return yaml.safe_load(fh) or {}


def is_enabled() -> bool:
    return bool(_load_config().get("enabled", False))


def agent_name(role: str) -> str:
    """Enrolled Viper agent name for a role: `supervisor` or a specialist's tool name."""
    names = _load_config().get("agents") or {}
    try:
        return names[role]
    except KeyError:
        raise KeyError(f"config/guardian.yaml agents: has no entry for {role!r}") from None


def build_agent(model, tools: list, *, role: str, system_prompt: str,
                middleware: list = (), checkpointer=None):
    """A LangChain agent; in Guardian mode the SDK's, signed as the role's enrolled agent."""
    if not is_enabled():
        return _langchain_create_agent(
            model, tools=tools, system_prompt=system_prompt,
            middleware=list(middleware), checkpointer=checkpointer, name=role,
        )
    # Imported here so the SDK is only needed when Guardian mode is on.
    from guardian_agent.langchain import create_agent
    return create_agent(
        model, tools=tools, system_prompt=system_prompt,
        middleware=list(middleware), checkpointer=checkpointer,
        name=agent_name(role),
    )


async def register(agent) -> str | None:
    """Register a Guardian-mode agent's definition with the proxy now, not on the first
    model call, so a stopped proxy or an unenrolled name fails at chat start. Returns the
    definition CID, or None when Guardian mode is off."""
    if not is_enabled():
        return None
    from guardian_agent.langchain import agent_of
    return await agent_of(agent).aregister()
