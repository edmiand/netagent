import chainlit as cl
from langchain_core.messages import HumanMessage

from agent.llm import get_active_model_name
from agent.mcp_bridge import get_mcp_tools, describe_tools
from agent.graph import create_agent

TOOL_ICONS = {
    "nf_lifecycle": "⚙️",
    "system_health_snapshot": "🏥",
    "subscriber_crud": "👤",
    "list_ue_sessions": "📋",
    "tail_nf_logs": "📜",
}

_DEMO_ACTIONS = [
    cl.Action(
        name="health_snapshot",
        label="🏥 Health Snapshot",
        payload={
            "prompt": (
                "Run a full health snapshot of the 5G core network and report "
                "the status of every network function."
            )
        },
    ),
    cl.Action(
        name="watch_attach",
        label="👀 Watch Subscriber Attach",
        payload={
            "prompt": (
                "List all active UE sessions and show me which subscribers are "
                "currently attached to the network."
            )
        },
    ),
    cl.Action(
        name="debug_failure",
        label="🔍 Debug Attach Failure",
        payload={
            "prompt": (
                "A subscriber cannot attach to the network. Run a health snapshot, "
                "tail the relevant NF logs to find the root cause, fix the issue, "
                "and verify recovery."
            )
        },
    ),
]


@cl.on_chat_start
async def on_chat_start():
    mcp_ctx = get_mcp_tools()
    tools = await mcp_ctx.__aenter__()
    cl.user_session.set("mcp_ctx", mcp_ctx)

    agent = create_agent(tools)
    cl.user_session.set("agent", agent)

    model_name = get_active_model_name()
    await cl.Message(
        content=(
            f"**5G Core Agent ready**\n\n"
            f"Model: `{model_name}`\n\n"
            f"**Available tools:**\n{describe_tools(tools)}\n\n"
            f"Ask me anything about the network, or pick a scenario below."
        ),
        actions=_DEMO_ACTIONS,
    ).send()


@cl.action_callback("health_snapshot")
async def on_health_snapshot(action: cl.Action):
    await _run_agent(action.payload["prompt"])


@cl.action_callback("watch_attach")
async def on_watch_attach(action: cl.Action):
    await _run_agent(action.payload["prompt"])


@cl.action_callback("debug_failure")
async def on_debug_failure(action: cl.Action):
    await _run_agent(action.payload["prompt"])


@cl.on_message
async def on_message(message: cl.Message):
    await _run_agent(message.content)


async def _run_agent(user_input: str):
    agent = cl.user_session.get("agent")

    active_steps: dict[str, cl.Step] = {}
    final_msg = cl.Message(content="")
    await final_msg.send()

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=user_input)]},
        version="v2",
    ):
        kind = event["event"]
        run_id = event.get("run_id", "")

        if kind == "on_tool_start":
            tool_name = event["name"]
            icon = TOOL_ICONS.get(tool_name, "🔧")
            step = cl.Step(name=f"{icon} {tool_name}", type="tool")
            step.input = str(event["data"].get("input", ""))
            await step.send()
            active_steps[run_id] = step

        elif kind == "on_tool_end":
            step = active_steps.pop(run_id, None)
            if step:
                output = str(event["data"].get("output", ""))
                step.output = output[:600] + ("…" if len(output) > 600 else "")
                await step.update()

        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            content = getattr(chunk, "content", "")
            if isinstance(content, str) and content:
                await final_msg.stream_token(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        await final_msg.stream_token(part["text"])

    await final_msg.update()


@cl.on_chat_end
async def on_chat_end():
    mcp_ctx = cl.user_session.get("mcp_ctx")
    if mcp_ctx:
        await mcp_ctx.__aexit__(None, None, None)
