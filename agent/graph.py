from pathlib import Path
from langgraph.prebuilt import create_react_agent
from agent.llm import get_llm

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.txt"


def create_agent(tools: list):
    system_prompt = _PROMPT_PATH.read_text()
    llm = get_llm()
    return create_react_agent(llm, tools, prompt=system_prompt)
