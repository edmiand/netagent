import json

import chainlit as cl
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.config import get_config

APPROVAL_TIMEOUT = 120  # seconds before dialog auto-denies


class HumanApprovalMiddleware(AgentMiddleware):
    """Human Approval Mode: every tool call waits for the approver the run was given.

    Middleware rather than a wrapper around each tool, so the agent is given the real
    tools: the MCP tools keep their server (which the Guardian SDK records and pins),
    and nothing hides a tool inside another. Every agent gets it — the supervisor and
    each specialist, whose runs inherit the supervisor's config — so a specialist's
    nested calls are gated too.

    The approver comes from the run's config (`configurable.approve_tool_call`), not
    from this class: app.py passes `ask_in_chainlit` on every turn. A run without one
    (rca_bench.py, test_integration.py) has no gate, as before. Kept out of the class
    and its module's globals so the Guardian SDK can search the middleware's code for
    a model that would call out unsigned (Chainlit's objects are too big to search).
    """

    async def awrap_tool_call(self, request, handler):
        approve = (get_config().get("configurable") or {}).get("approve_tool_call")
        call = request.tool_call
        if approve is None or await approve(call["name"], call.get("args") or {}):
            return await handler(request)
        return ToolMessage(
            content=(f"[Tool call '{call['name']}' was denied by the user. Do not retry "
                     "this tool. Inform the user the action was not approved and ask "
                     "how to proceed.]"),
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        )


async def ask_in_chainlit(tool_name: str, args: dict) -> bool:
    """The Web UI approver: True straight away while the toggle is off, otherwise
    an approve/deny dialog that auto-denies after APPROVAL_TIMEOUT seconds."""
    if not cl.user_session.get("human_approval_enabled"):
        return True
    params_display = json.dumps(args, indent=2, default=str) if args else "{}"
    response = await cl.AskActionMessage(
        content=(
            f"**Tool call requires approval**\n\n"
            f"**Tool:** `{tool_name}`\n\n"
            f"**Parameters:**\n```json\n{params_display}\n```"
        ),
        actions=[
            cl.Action(name="approve", label="✓ Approve", payload={"decision": "approve"}),
            cl.Action(name="deny",    label="✗ Deny",    payload={"decision": "deny"}),
        ],
        timeout=APPROVAL_TIMEOUT,
    ).send()
    return response is not None and response.get("payload", {}).get("decision") == "approve"
