import yaml
from pathlib import Path

import chainlit as cl
from langchain_core.messages import HumanMessage

from agent.llm import get_active_model_name
from agent.mcp_bridge import get_mcp_tools
from agent.graph import create_agent

_BRANDING_PATH = Path(__file__).parent / "config" / "branding.yaml"


def _load_branding() -> dict:
    with open(_BRANDING_PATH) as fh:
        return yaml.safe_load(fh)

TOOL_ICONS = {
    "nf_lifecycle": "⚙️",
    "system_health_snapshot": "🏥",
    "subscriber_crud": "👤",
    "list_ue_sessions": "📋",
    "tail_nf_logs": "📜",
}

_SCENARIO_ACTIONS = [
    cl.Action(
        name="health_snapshot",
        label="🏥 Health Snapshot",
        payload={"prompt": "Call system_health_snapshot now."},
    ),
    cl.Action(
        name="watch_attach",
        label="👀 Watch Subscriber Attach",
        payload={"prompt": "Call list_ue_sessions now."},
    ),
    cl.Action(
        name="debug_failure",
        label="🔍 Debug Attach Failure",
        payload={"prompt": "Call system_health_snapshot now."},
    ),
]


@cl.set_starters
async def set_starters():
    """Shown on empty chat screen before any message is sent."""
    return [
        cl.Starter(
            label="🏥 Health Snapshot",
            message="Call system_health_snapshot now.",
        ),
        cl.Starter(
            label="👀 Watch Subscriber Attach",
            message="Call list_ue_sessions now.",
        ),
        cl.Starter(
            label="🔍 Debug Attach Failure",
            message="Call system_health_snapshot now.",
        ),
    ]


@cl.on_chat_start
async def on_chat_start():
    mcp_ctx = get_mcp_tools()
    tools = await mcp_ctx.__aenter__()
    cl.user_session.set("mcp_ctx", mcp_ctx)

    agent = create_agent(tools)
    cl.user_session.set("agent", agent)

    branding = _load_branding()
    model_name = get_active_model_name()
    tool_names = "  ".join(
        f"{TOOL_ICONS.get(t.name, '🔧')} `{t.name}`" for t in tools
    )
    await cl.Message(
        content=(
            f"**{branding['welcome_title']}**\n\n"
            f"Model: `{model_name}`\n\n"
            f"**Tools:** {tool_names}"
        ),
        actions=_SCENARIO_ACTIONS,
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
    tools_active = 0
    final_msg = cl.Message(content="", actions=_SCENARIO_ACTIONS)
    await final_msg.send()

    try:
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
                tools_active += 1
                # Discard any pre-tool text the model leaked (tool-call reasoning)
                if final_msg.content:
                    final_msg.content = ""
                    await final_msg.update()

            elif kind == "on_tool_end":
                step = active_steps.pop(run_id, None)
                if step:
                    output = str(event["data"].get("output", ""))
                    step.output = output[:600] + ("…" if len(output) > 600 else "")
                    await step.update()
                tools_active -= 1

            elif kind == "on_chat_model_stream" and tools_active == 0:
                chunk = event["data"]["chunk"]
                content = getattr(chunk, "content", "")
                if isinstance(content, str) and content:
                    await final_msg.stream_token(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            await final_msg.stream_token(part["text"])

    except Exception as exc:
        for step in active_steps.values():
            step.output = f"❌ Error: {exc}"
            await step.update()
        root_cause = str(exc) or type(exc).__name__
        if "ConnectError" in type(exc).__name__ or "Connect" in root_cause:
            final_msg.content = (
                f"❌ **Cannot reach the MCP server at VM1.**\n\n"
                f"The 5G core agent connected to the LLM successfully, but the "
                f"MCP tool server (`192.168.64.19:8080`) is not responding.\n\n"
                f"**Fix:** SSH into VM1 and start the MCP server, then restart this chat."
            )
        else:
            final_msg.content = f"❌ **Agent error:** {root_cause}"

    await final_msg.update()


@cl.on_chat_end
async def on_chat_end():
    mcp_ctx = cl.user_session.get("mcp_ctx")
    if mcp_ctx:
        await mcp_ctx.__aexit__(None, None, None)
