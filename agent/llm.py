import functools
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.yaml"

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _load_config() -> dict:
    load_dotenv()
    with open(_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def get_llm(thinking: bool = False) -> ChatOllama:
    cfg = _load_config()
    active_name = cfg["active"]
    model_block = cfg["models"][active_name]
    kwargs: dict = dict(
        model=active_name,
        base_url=model_block["base_url"],
        temperature=model_block["temperature"],
        num_predict=model_block["max_tokens"],
    )
    if thinking and model_block.get("thinking"):
        kwargs["reasoning"] = True
    return ChatOllama(**kwargs)


def get_active_model_name() -> str:
    return _load_config()["active"]


def model_supports_thinking() -> bool:
    cfg = _load_config()
    return bool(cfg["models"][cfg["active"]].get("thinking", False))


async def test_llm_connection() -> bool:
    model_name = get_active_model_name()
    try:
        await get_llm().ainvoke([HumanMessage(content="ping")])
        logger.info("llm_connected model=%s", model_name)
        return True
    except Exception as exc:
        logger.error("llm_connect_error error=%s", str(exc)[:200])
        logger.warning("llm_hint hint=%s", "check that Ollama is running and the model is pulled")
        return False
