from pathlib import Path
from typing import Literal

from eqty_lineage.langchain import eqty_tool
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

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


class _SubscriberReadArgs(BaseModel):
    action: Literal["read", "list"] = Field(
        description="read: one subscriber's stored profile (needs imsi). list: enumerate subscribers.")
    imsi: str | None = Field(
        default=None, description='IMSI digits (10-15) or SUPI ("imsi-<digits>"). Required for read.')
    limit: int = Field(default=100, ge=1, le=1000, description="For list only. Max subscribers per page.")
    filter: dict | None = Field(
        default=None,
        description=("For list only. Equality filter; allowed keys: subscriber_status "
                     "(0=SERVICE_GRANTED, 1=OPERATOR_DETERMINED_BARRING), network_access_mode, "
                     "access_restriction_data, operator_determined_barring. E.g. "
                     '{"subscriber_status": 1} lists barred subscribers.'),
    )


def _read_only_subscriber(base: StructuredTool) -> StructuredTool:
    """The MCP `subscriber` tool restricted to read/list, for specialists.

    The full tool also creates and deletes. Specialists are investigators: their prompts
    say they can't modify subscribers, and this makes that true in code — create/delete
    aren't in the schema and are refused here even if the model sends them anyway.
    Calls go to `base`'s coroutine (the approval-wrapped tool), so Human Approval Mode
    still gates every call, without adding a second nested tool step.
    """
    async def _run(action: str, imsi: str | None = None, limit: int = 100,
                   filter: dict | None = None):
        if action not in ("read", "list"):
            return {"ok": False, "error": f"action '{action}' is not allowed here: this "
                    "subscriber tool is read-only (read, list). Report the needed change "
                    "to the supervisor instead."}
        args = {"action": action}
        if action == "read":
            args["imsi"] = imsi
        else:
            args["limit"] = limit
            if filter is not None:
                args["filter"] = filter
        return await base.coroutine(**args)

    # Same name as the MCP tool so the specialist prompts and the UI step still read
    # "subscriber"; the metadata keeps it a separate Tool asset in the EQTY manifest.
    return eqty_tool(StructuredTool.from_function(
        coroutine=_run,
        name=base.name,
        description=("Look up subscriber profiles — read one (by IMSI) or list them (optional "
                     "filter). Read-only: you cannot create, update or delete subscribers; "
                     "report any needed change instead. Secrets come back redacted."),
        args_schema=_SubscriberReadArgs,
        metadata={"read_only_view_of": base.name},
    ))


def build_specialist_tools(tools: list, model_name: str | None = None) -> list[StructuredTool]:
    """Wrap each specialist as a single dispatch tool for the supervisor agent.

    The supervisor invokes a specialist like any other tool; internally it runs
    its own create_react_agent loop, and its nested tool calls still stream as
    Chainlit steps since astream_events propagates events from runnables invoked
    via ainvoke inside the parent's callback context.
    """
    by_name = {t.name: t for t in tools}
    # Specialists only investigate: give them a read-only subscriber tool, never the
    # full one (create/delete) the supervisor has.
    if "subscriber" in by_name:
        by_name["subscriber"] = _read_only_subscriber(by_name["subscriber"])
    dispatch_tools = []

    for spec in _SPECIALISTS:
        subset = [by_name[name] for name in spec["tool_names"] if name in by_name]
        if not subset:
            continue
        prompt_text = (_PROMPTS_DIR / spec["prompt_file"]).read_text()
        # lc_agent_name is how the EQTY handler tells a subagent from a plain subgraph;
        # create_react_agent doesn't set it.
        sub_agent = create_react_agent(
            get_llm(model_name=model_name), subset, prompt=prompt_text,
        ).with_config(metadata={"lc_agent_name": spec["name"]})

        async def _run(task: str, _agent=sub_agent) -> str:
            result = await _agent.ainvoke(
                {"messages": [HumanMessage(content=task)]},
                config={"recursion_limit": 12},
            )
            return result["messages"][-1].content

        # eqty_tool goes on the StructuredTool so the source of _run is registered under
        # the tool's name. Every specialist shares that source, so metadata is what keeps
        # them from collapsing into one Tool asset in the manifest.
        dispatch_tools.append(eqty_tool(StructuredTool.from_function(
            coroutine=_run,
            name=spec["name"],
            description=spec["description"],
            metadata={"specialist": spec["name"]},
        )))

    return dispatch_tools
