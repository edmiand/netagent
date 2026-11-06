import functools
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from agent import guardian

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.yaml"


@functools.lru_cache(maxsize=1)
def _load_config() -> dict:
    load_dotenv()
    with open(_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def _resolve_model(model_name: str | None) -> tuple[str, dict]:
    """Return (name, config block) for the given model, or the active one if None."""
    cfg = _load_config()
    name = model_name or get_active_model_name()
    try:
        return name, cfg["models"][name]
    except KeyError:
        raise KeyError(f"Model {name!r} is not defined in config/models.yaml") from None


def model_provider(model_name: str | None = None) -> str:
    """`provider:` of a models.yaml entry: "ollama" (default) or "openai"."""
    _, model_block = _resolve_model(model_name)
    return model_block.get("provider", "ollama")


def provider_enabled(provider: str) -> bool:
    """The `providers:` switch in models.yaml. Ollama is on unless switched off;
    any other provider is off unless `providers.<name>.enabled: true`."""
    block = (_load_config().get("providers") or {}).get(provider) or {}
    return bool(block.get("enabled", provider == "ollama"))


def _openai_api_key(model_block: dict) -> str | None:
    return os.environ.get(model_block.get("api_key_env", "OPENAI_API_KEY")) or None


def model_unavailable_reason(model_name: str | None = None) -> str | None:
    """Why this entry can't be used right now, or None when it can."""
    name, model_block = _resolve_model(model_name)
    provider = model_provider(name)
    if guardian.is_enabled() and provider not in guardian.SIGNED_PROVIDERS:
        return f"Guardian mode signs {'/'.join(guardian.SIGNED_PROVIDERS)} models only (config/guardian.yaml)"
    if not provider_enabled(provider):
        return f"provider '{provider}' is disabled (config/models.yaml providers.{provider}.enabled)"
    if provider == "openai" and not _openai_api_key(model_block):
        return f"{model_block.get('api_key_env', 'OPENAI_API_KEY')} is not set in .env"
    return None


def ollama_model_name(model_name: str | None = None) -> str:
    """Provider-side model name for a models.yaml entry (Ollama tag or OpenAI model id).

    `model:` decouples the picker label (the yaml key) from the model name;
    when it is absent or empty, the key itself is the model name.
    """
    name, model_block = _resolve_model(model_name)
    return model_block.get("model") or name


def model_label(model_name: str | None = None) -> str:
    """Display label: the yaml key, plus the provider-side model name when the key
    doesn't already contain it (keys are normally `<provider>-<model>`)."""
    name, _ = _resolve_model(model_name)
    real = ollama_model_name(name)
    return name if real in name else f"{name} ({real})"


def _get_openai_llm(model_block: dict, model_name: str | None,
                    thinking: bool, suppress_thinking: bool) -> ChatOpenAI:
    """ChatOpenAI over the Responses API (needed for tool calling on current reasoning models).

    Reasoning maps onto the same two UI switches as Ollama:
      Use Model Reasoning off → `reasoning_effort_off` (lowest the model allows)
      on                      → `reasoning_effort`
      Show Model Thinking on  → also request a reasoning summary (OpenAI never returns
                                the raw reasoning; app.py streams the summary)
    store=False: OpenAI keeps no application state for these calls; reasoning comes back
    encrypted and is replayed from our own history. Abuse-monitoring retention still applies.
    """
    reason = model_unavailable_reason(model_name)
    if reason:
        raise RuntimeError(f"OpenAI model {model_name or get_active_model_name()!r} unavailable: {reason}")
    kwargs: dict = dict(
        model=ollama_model_name(model_name),
        api_key=_openai_api_key(model_block),
        max_tokens=model_block["max_tokens"],
        use_responses_api=True,
        store=False,
        stream_usage=True,   # usage on streamed calls → the 📊 Context step
    )
    if model_block.get("base_url"):
        kwargs["base_url"] = model_block["base_url"]
    effort = None
    if model_block.get("thinking"):
        effort = (model_block.get("reasoning_effort_off", "low") if suppress_thinking
                  else model_block.get("reasoning_effort", "medium"))
        kwargs["reasoning"] = {"effort": effort}
        if thinking and not suppress_thinking:
            kwargs["reasoning"]["summary"] = "auto"
    # Reasoning models reject a custom temperature unless reasoning is off ("none").
    if "temperature" in model_block and effort in (None, "none"):
        kwargs["temperature"] = model_block["temperature"]
    return ChatOpenAI(**kwargs)


def get_llm(
    thinking: bool = False,
    suppress_thinking: bool = False,
    model_name: str | None = None,
) -> BaseChatModel:
    _, model_block = _resolve_model(model_name)
    if model_block.get("provider", "ollama") == "openai":
        return _get_openai_llm(model_block, model_name, thinking, suppress_thinking)
    reason = model_unavailable_reason(model_name)
    if reason:
        raise RuntimeError(f"Model {model_name or get_active_model_name()!r} unavailable: {reason}")
    kwargs: dict = dict(
        model=ollama_model_name(model_name),
        base_url=model_block["base_url"],
        temperature=model_block["temperature"],
        num_predict=model_block["max_tokens"],
    )
    if model_block.get("context_window"):
        kwargs["num_ctx"] = model_block["context_window"]
    if model_block.get("thinking"):
        if thinking:
            kwargs["reasoning"] = True
        elif suppress_thinking:
            kwargs["reasoning"] = False
    return ChatOllama(**kwargs)


@functools.lru_cache(maxsize=1)
def get_embeddings() -> OllamaEmbeddings:
    cfg = _load_config()
    emb_block = cfg["embeddings"]
    return OllamaEmbeddings(model=emb_block["model"], base_url=emb_block["base_url"])


def get_active_model_name() -> str:
    """Default model for new chats: `active`, or — when it can't be used right now
    (provider switched off, OpenAI key missing) — the first usable, enabled entry in
    file order, so a missing key degrades to an Ollama model instead of a failed chat."""
    cfg = _load_config()
    active = cfg["active"]
    if model_unavailable_reason(active) is None:
        return active
    for name, block in cfg["models"].items():
        if block.get("enabled", True) and model_unavailable_reason(name) is None:
            return name
    return active  # nothing usable: let get_llm raise its clear error


def list_available_models() -> list[str]:
    """Model names offered in the in-chat picker (config/models.yaml order).

    Hidden: entries with `enabled: false`, entries whose provider is switched off
    in `providers:`, and OpenAI entries without an API key in .env. The effective
    default (see get_active_model_name) is always included so the picker can never
    end up empty or without its default.
    """
    cfg = _load_config()
    active = get_active_model_name()
    return [
        name for name, block in cfg["models"].items()
        if name == active
        or (block.get("enabled", True) and model_unavailable_reason(name) is None)
    ]


def model_supports_thinking(model_name: str | None = None) -> bool:
    _, model_block = _resolve_model(model_name)
    return bool(model_block.get("thinking", False))


async def test_llm_connection() -> bool:
    label = model_label()
    try:
        await get_llm().ainvoke([HumanMessage(content="ping")])
        print(f"LLM connected: {label}")
        return True
    except Exception as exc:
        print(f"LLM connection failed ({label}): {exc}")
        if model_provider() == "openai":
            print("Hint: check OPENAI_API_KEY in .env, providers.openai.enabled, and the model id.")
        else:
            print(f"Hint: check that Ollama is running and `{ollama_model_name()}` is pulled.")
        return False
