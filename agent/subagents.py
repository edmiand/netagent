import copy
import json
from pathlib import Path

from eqty_lineage.langchain import eqty_tool
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from agent.approval import HumanApprovalMiddleware
from agent.guardian import build_agent
from agent.llm import get_llm

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "subagents"

# Each specialist is its own bounded agent over a narrow, read-only
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

# Specialists only investigate. The MCP `subscriber` tool also creates and deletes;
# for a specialist only these actions run.
_READ_ONLY_ACTIONS = {"subscriber": ["read", "list"]}

_READ_ONLY_SUBSCRIBER_DESCRIPTION = (
    "Look up subscriber profiles — read one (by IMSI) or list them (optional filter). "
    "Read-only: you cannot create, update or delete subscribers; report any needed "
    "change instead. Secrets come back redacted."
)


def _read_only_view(base: StructuredTool) -> StructuredTool:
    """The MCP `subscriber` tool as specialists see it: read/list only.

    A copy of the MCP tool itself, not a wrapper around it — same coroutine and MCP
    connection, so the Guardian SDK still records its server — with the schema cut to
    the read actions (no `data`/`confirm`) and a description that says so. What the
    model is offered changes; what a call can do is enforced by ReadOnlyToolsMiddleware.
    """
    raw = base.args_schema
    # MCP tools carry a JSON-schema dict; a local tool may carry a pydantic model.
    schema = copy.deepcopy(raw) if isinstance(raw, dict) else raw.model_json_schema()
    props = schema.get("properties", {})
    props["action"] = {**props["action"], "enum": _READ_ONLY_ACTIONS[base.name],
                       "description": "read: one subscriber's stored profile (needs imsi). "
                                      "list: enumerate subscribers."}
    for create_or_delete_only in ("data", "confirm"):
        props.pop(create_or_delete_only, None)
    if "imsi" in props:
        props["imsi"] = {**props["imsi"], "description":
                         'IMSI digits (10-15) or SUPI ("imsi-<digits>"). Required for read.'}
    return base.model_copy(update={
        "description": _READ_ONLY_SUBSCRIBER_DESCRIPTION,
        "args_schema": schema,
        # Keeps it a separate Tool asset from the full tool in the EQTY manifest.
        "metadata": {**(base.metadata or {}), "read_only_view_of": base.name},
    })


class ReadOnlyToolsMiddleware(AgentMiddleware):
    """Refuses, in code, any call to a listed tool whose `action` isn't allowed.

    The schema the specialist is offered already lists only the read actions
    (_read_only_view); this makes that true whatever the model sends. Denied calls
    never reach VM1.
    """

    def __init__(self, allowed_actions: dict[str, list[str]]):
        super().__init__()
        self.allowed_actions = allowed_actions

    async def awrap_tool_call(self, request, handler):
        call = request.tool_call
        allowed = self.allowed_actions.get(call["name"])
        action = (call.get("args") or {}).get("action")
        if allowed is not None and action not in allowed:
            return ToolMessage(
                content=json.dumps({"ok": False, "error": (
                    f"action '{action}' is not allowed here: this {call['name']} tool is "
                    f"read-only ({', '.join(allowed)}). Report the needed change to the "
                    "supervisor instead.")}),
                tool_call_id=call["id"],
                name=call["name"],
                status="error",
            )
        return await handler(request)


def build_specialist_tools(tools: list, model_name: str | None = None) -> list[StructuredTool]:
    """Wrap each specialist as a single dispatch tool for the supervisor agent.

    The supervisor invokes a specialist like any other tool; internally it runs
    its own agent loop, and its nested tool calls still stream as
    Chainlit steps since astream_events propagates events from runnables invoked
    via ainvoke inside the parent's callback context. In Guardian mode each
    specialist is an enrolled agent of its own and signs its own model calls.
    """
    by_name = {t.name: t for t in tools}
    # Specialists only investigate: they get the read-only view of `subscriber`, never
    # the full tool (create/delete) the supervisor has.
    if "subscriber" in by_name:
        by_name["subscriber"] = _read_only_view(by_name["subscriber"])
    dispatch_tools = []

    for spec in _SPECIALISTS:
        subset = [by_name[name] for name in spec["tool_names"] if name in by_name]
        if not subset:
            continue
        prompt_text = (_PROMPTS_DIR / spec["prompt_file"]).read_text()
        # Read-only first, so a create/delete is refused before anyone is asked to approve it.
        sub_agent = build_agent(
            get_llm(model_name=model_name), subset, role=spec["name"],
            system_prompt=prompt_text,
            middleware=[ReadOnlyToolsMiddleware(_READ_ONLY_ACTIONS), HumanApprovalMiddleware()],
        )

        async def _run(task: str, _agent=sub_agent, _name=spec["name"]) -> str:
            # lc_agent_name is how the EQTY handler tells a subagent from a plain
            # subgraph; set per call so it stays the specialist's tool name in Guardian
            # mode too, where the agent itself is named after its enrolled identity.
            result = await _agent.ainvoke(
                {"messages": [HumanMessage(content=task)]},
                config={"recursion_limit": 12, "metadata": {"lc_agent_name": _name}},
            )
            # .text, not .content: with OpenAI (Responses API) content is a list of blocks
            # that includes encrypted reasoning, which the supervisor can't use.
            return result["messages"][-1].text

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
