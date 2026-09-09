from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from agent.llm import get_llm

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "subagents"

# Each specialist is its own bounded create_react_agent over a narrow, read-only
# tool subset. The supervisor sees it as a single tool call and gets back a
# synthesized report — remediation (subscriber writes, NF lifecycle) stays a
# supervisor/user-level decision, never something a specialist can act on itself.
_SPECIALISTS = [
    {
        "name": "investigate_connectivity",
        "label": "Connectivity Investigator",
        "description": (
            "Investigate a subscriber/UE connectivity problem: can't attach, no PDU "
            "session, registered but no data. Runs its own multi-step investigation "
            "across active sessions, call trace, RAN state, and the subscriber "
            "profile, then returns findings for you to synthesize. Give it the "
            "reported symptom and any known IMSI/UE id."
        ),
        "prompt_file": "connectivity.txt",
        "tool_names": {"list_ue_sessions", "get_ue_trace", "amf_ran_query", "subscriber", "tail_nf_logs"},
    },
    {
        "name": "investigate_nf_health",
        "label": "NF Health Investigator",
        "description": (
            "Investigate a network function reported down, degraded, or "
            "misbehaving. Runs its own multi-step investigation across health "
            "status, logs, resource usage, and config, then returns findings for "
            "you to synthesize. Give it the NF name if known, otherwise ask it to "
            "check all NFs."
        ),
        "prompt_file": "nf_health.txt",
        "tool_names": {"system_health_snapshot", "tail_nf_logs", "nf_resource_usage", "read_nf_config"},
    },
]

# Exposed so app.py can recognize a specialist dispatch step (vs. a leaf MCP tool
# step) and render it distinctly — see SPECIALIST_LABELS usage in _run_agent.
SPECIALIST_LABELS = {spec["name"]: spec["label"] for spec in _SPECIALISTS}


def build_specialist_tools(tools: list, model_name: str | None = None) -> list[StructuredTool]:
    """Wrap each specialist as a single dispatch tool for the supervisor agent.

    The supervisor invokes a specialist like any other tool; internally it runs
    its own create_react_agent loop, and its nested tool calls still stream as
    Chainlit steps since astream_events propagates events from runnables invoked
    via ainvoke inside the parent's callback context.
    """
    by_name = {t.name: t for t in tools}
    dispatch_tools = []

    for spec in _SPECIALISTS:
        subset = [by_name[name] for name in spec["tool_names"] if name in by_name]
        if not subset:
            continue
        prompt_text = (_PROMPTS_DIR / spec["prompt_file"]).read_text()
        sub_agent = create_react_agent(get_llm(model_name=model_name), subset, prompt=prompt_text)

        async def _run(task: str, _agent=sub_agent) -> str:
            result = await _agent.ainvoke(
                {"messages": [HumanMessage(content=task)]},
                config={"recursion_limit": 12},
            )
            return result["messages"][-1].content

        dispatch_tools.append(StructuredTool.from_function(
            coroutine=_run,
            name=spec["name"],
            description=spec["description"],
        ))

    return dispatch_tools
