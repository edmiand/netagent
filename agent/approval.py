import json
import logging

import chainlit as cl
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT = 120  # seconds before dialog auto-denies

_DENIAL_MSG = (
    "[Tool call '{name}' was denied by the user. Do not retry this tool. "
    "Inform the user the action was not approved and ask how to proceed.]"
)


def wrap_with_approval(tools: list) -> list:
    return [_make_approval_wrapper(tool) for tool in tools]


def _make_approval_wrapper(tool: StructuredTool) -> StructuredTool:
    original_coroutine = tool.coroutine

    async def _approval_arun(*args, **kwargs):
        if cl.user_session.get("human_approval_enabled"):
            params_display = json.dumps(kwargs, indent=2, default=str) if kwargs else str(args)
            logger.info("approval_prompt tool=%s", tool.name)
            response = await cl.AskActionMessage(
                content=(
                    f"**Tool call requires approval**\n\n"
                    f"**Tool:** `{tool.name}`\n\n"
                    f"**Parameters:**\n```json\n{params_display}\n```"
                ),
                actions=[
                    cl.Action(name="approve", label="✓ Approve", payload={"decision": "approve"}),
                    cl.Action(name="deny",    label="✗ Deny",    payload={"decision": "deny"}),
                ],
                timeout=APPROVAL_TIMEOUT,
            ).send()

            if response is None:
                logger.warning("approval_timeout tool=%s", tool.name)
                return _DENIAL_MSG.format(name=tool.name)

            if response.get("payload", {}).get("decision") != "approve":
                logger.warning("approval_denied tool=%s", tool.name)
                return _DENIAL_MSG.format(name=tool.name)

            logger.info("approval_granted tool=%s", tool.name)

        return await original_coroutine(*args, **kwargs)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=_approval_arun,
        return_direct=tool.return_direct,
    )
