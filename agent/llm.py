import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "models.yaml"


def _load_config() -> dict:
    load_dotenv()
    with open(_CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


def get_llm() -> ChatOpenAI:
    cfg = _load_config()
    active_name = cfg["active"]
    model_block = cfg["models"][active_name]
    api_key = os.environ.get(model_block["api_key_env"])
    if not api_key:
        raise ValueError(
            f"Environment variable '{model_block['api_key_env']}' is not set. "
            f"Add it to .env or export it before starting the app."
        )
    return ChatOpenAI(
        base_url=model_block["base_url"],
        api_key=api_key,
        model=active_name,
        temperature=model_block["temperature"],
        max_tokens=model_block["max_tokens"],
        streaming=True,
    )


def get_active_model_name() -> str:
    return _load_config()["active"]


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
