from pathlib import Path
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from agent.llm import get_llm
from agent.subagents import build_specialist_tools

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.txt"


def create_agent(tools: list, thinking: bool = False, suppress_thinking: bool = False):
    system_prompt = _PROMPT_PATH.read_text()
    llm = get_llm(thinking=thinking, suppress_thinking=suppress_thinking)
    specialist_tools = build_specialist_tools(tools)
    return create_react_agent(
        llm, tools + specialist_tools, prompt=system_prompt, checkpointer=MemorySaver()
    )
