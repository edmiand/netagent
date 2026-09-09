import functools
import yaml
from pathlib import Path
from dotenv import load_dotenv
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.messages import HumanMessage

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.yaml"


@functools.lru_cache(maxsize=1)
def _load_config() -> dict:
    load_dotenv()
    with open(_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def _resolve_model(model_name: str | None) -> tuple[str, dict]:
    """Return (name, config block) for the given model, or the active one if None."""
    cfg = _load_config()
    name = model_name or cfg["active"]
    try:
        return name, cfg["models"][name]
    except KeyError:
        raise KeyError(f"Model {name!r} is not defined in config/models.yaml") from None


def get_llm(
    thinking: bool = False,
    suppress_thinking: bool = False,
    model_name: str | None = None,
) -> ChatOllama:
    name, model_block = _resolve_model(model_name)
    kwargs: dict = dict(
        model=name,
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
    return _load_config()["active"]


def list_available_models() -> list[str]:
    """Model names offered in the in-chat picker (config/models.yaml order).

    A model with `enabled: false` is hidden; the `active` model is always
    included so the picker can never end up empty or without its default.
    """
    cfg = _load_config()
    active = cfg["active"]
    return [
        name for name, block in cfg["models"].items()
        if block.get("enabled", True) or name == active
    ]


def model_supports_thinking(model_name: str | None = None) -> bool:
    _, model_block = _resolve_model(model_name)
    return bool(model_block.get("thinking", False))


async def test_llm_connection() -> bool:
    model_name = get_active_model_name()
    try:
        await get_llm().ainvoke([HumanMessage(content="ping")])
        print(f"LLM connected: {model_name}")
        return True
    except Exception as exc:
        print(f"LLM connection failed: {exc}")
        print("Hint: check that Ollama is running and the model is pulled.")
        return False
