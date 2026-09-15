import asyncio
import base64
import json
import re
import uuid
import yaml
from pathlib import Path

import httpx
import chainlit as cl
from chainlit.context import local_steps
from chainlit.data import get_data_layer
from langchain_core.messages import HumanMessage

from chainlit.input_widget import Select, Switch

from agent.llm import get_active_model_name, list_available_models, model_supports_thinking
from agent.mcp_bridge import get_mcp_tools, get_mcp_url
from agent.graph import create_agent
from langgraph.checkpoint.memory import MemorySaver
from agent.approval import wrap_with_approval
from agent.subagents import SPECIALIST_LABELS
from agent.tools.rag import search_knowledge_base
from agent.tools.release_check import check_open5gs_release_info
from agent.tools.memory import recall_similar_incidents, record_incident
from data_layer import make_data_layer

# Optional trailing horizontal whitespace between "mermaid" and the newline
_MERMAID_RE = re.compile(r"```mermaid[ \t]*\n(.*?)```", re.DOTALL)

# LaTeX cleanup — the system prompt forbids LaTeX, but the model still emits it
# occasionally (e.g. "gNB $\longrightarrow$ AMF"). Chainlit renders it literally,
# so rewrite it to the Unicode the prompt asks for. See _strip_latex().
_LATEX_SYMBOLS = {
    "longrightarrow": "→", "rightarrow": "→", "to": "→", "mapsto": "↦",
    "longleftarrow": "←", "leftarrow": "←", "gets": "←",
    "longleftrightarrow": "↔", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "times": "×", "cdot": "·", "approx": "≈", "pm": "±",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "infty": "∞", "ldots": "…", "dots": "…", "bullet": "•", "circ": "∘",
    "alpha": "α", "beta": "β", "delta": "δ", "Delta": "Δ", "lambda": "λ",
    "mu": "μ", "sigma": "σ", "tau": "τ", "phi": "φ", "theta": "θ", "omega": "ω",
}
# Inline math: only unwrap when the body contains a backslash, so shell-style
# "$PATH" / "$1" in prose survives untouched.
_LATEX_DISPLAY_RE = re.compile(r"\$\$([^$]*\\[^$]*)\$\$")
_LATEX_INLINE_RE = re.compile(r"\$([^$\n]*\\[^$\n]*)\$")
_LATEX_PAREN_RE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_LATEX_BRACKET_RE = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_LATEX_WRAPPER_RE = re.compile(r"\\(?:text|mathrm|mathit|mathbf)\{([^{}]*)\}")
_LATEX_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
_LATEX_ESCAPE_RE = re.compile(r"\\([%_&#$~^])")
_LATEX_SPACING_RE = re.compile(r"\\[,;:!]")

_BRANDING_PATH = Path(__file__).parent / "config" / "branding.yaml"

# Chainlit persists generated files (e.g. mermaid images) under .files/<session-id>/
# and uses mkdir(exist_ok=True) without parents=True, so the parent must pre-exist.
_FILES_DIR = Path(__file__).parent / ".files"
_FILES_DIR.mkdir(exist_ok=True)


async def _send(msg: cl.Message) -> cl.Message:
    """Send a message as a root-level step so it appears in thread history."""
    msg.parent_id = None
    await msg.send()
    return msg


@cl.data_layer
def _get_data_layer():
    return make_data_layer()


@cl.header_auth_callback
def _header_auth(headers) -> cl.User:
    return cl.User(identifier="demo", metadata={"role": "demo"})


def _load_branding() -> dict:
    with open(_BRANDING_PATH) as fh:
        return yaml.safe_load(fh)

TOOL_ICONS = {
    "nf_lifecycle": "⚙️",
    "system_health_snapshot": "🏥",
    "subscriber_crud": "👤",
    "list_ue_sessions": "📋",
    "tail_nf_logs": "📜",
    "trace": "🔍",
    "search_knowledge_base": "📚",
    "check_open5gs_release_info": "🌐",
    "recall_similar_incidents": "🧩",
    "record_incident": "🧠",
    "investigate_connectivity": "📶",
    "investigate_nf_health": "🩺",
}


def _unwrap_mcp_output(output_raw) -> str:
    """Extract the plain inner text from an MCP tool output.

    In langgraph 1.2.x, event["data"]["output"] arrives as a raw string:
      '[[{"type": "text", "text": "{...actual payload...}"}]]'

    Navigate: outer JSON string → list-of-lists → content blocks → inner text.
    Works whether the value is a string, a ToolMessage, or already a list.
    """
    # Unwrap ToolMessage if present
    content = getattr(output_raw, "content", output_raw)

    # Parse the outer layer if it's a JSON string
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return content  # already plain text, return as-is

    # Flatten one level: [[block, ...]] → [block, ...]
    if isinstance(content, list):
        blocks: list = []
        for item in content:
            if isinstance(item, list):
                blocks.extend(item)
            elif isinstance(item, dict):
                blocks.append(item)
        texts = [b["text"] for b in blocks
                 if isinstance(b, dict) and b.get("type") == "text" and "text" in b]
        return "\n".join(texts) if texts else str(content)

    return str(content)



def _build_tools(raw_tools: list) -> list:
    extra_tools = [search_knowledge_base, check_open5gs_release_info]
    if cl.user_session.get("memory_learning_enabled", False):
        extra_tools += [recall_similar_incidents, record_incident]
    return wrap_with_approval(raw_tools + extra_tools)


def _make_scenario_actions() -> list[cl.Action]:
    """Return fresh Action instances each call so forId is always None on first use."""
    return [
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
            payload={"prompt": "A subscriber cannot attach to the 5G core. Investigate the root cause: check NF health, tail logs for any degraded or down functions, read their config if the logs are ambiguous, then tell me exactly what is wrong and what to do to fix it."},
        ),
    ]


def _build_widgets() -> list:
    approval_enabled = cl.user_session.get("human_approval_enabled", False)
    use_reasoning = cl.user_session.get("use_model_reasoning", True)
    show_thinking = cl.user_session.get("show_thinking", True)
    memory_enabled = cl.user_session.get("memory_learning_enabled", False)
    model_name = cl.user_session.get("model_name") or get_active_model_name()

    widgets = []
    available = list_available_models()
    if len(available) > 1:
        widgets.append(Select(
            id="model_name",
            label="Model",
            description="Ollama model backing the agent. Switching rebuilds the agent for this chat only — config/models.yaml sets the default for new chats.",
            values=available,
            initial_value=model_name if model_name in available else available[0],
        ))
    if model_supports_thinking(model_name):
        widgets.append(Switch(
            id="use_model_reasoning",
            label="Use Model Reasoning",
            description="Pass reasoning=True/False to the model — disabling skips internal reasoning entirely for faster (but shallower) responses",
            initial=use_reasoning,
        ))
        widgets.append(Switch(
            id="show_thinking",
            label="Show Model Thinking",
            description=(
                "Enable Use Model Reasoning to configure this."
                if not use_reasoning else
                "Stream the model's internal reasoning before each response"
            ),
            initial=show_thinking if use_reasoning else False,
            disabled=not use_reasoning,
        ))
    widgets.append(Switch(
        id="human_approval_enabled",
        label="Human Approval Mode",
        description="Require your approval before each tool executes",
        initial=approval_enabled,
    ))
    widgets.append(Switch(
        id="memory_learning_enabled",
        label="Memory & Learning",
        description="Let the agent recall similar past incidents and record new ones it resolves",
        initial=memory_enabled,
    ))
    return widgets


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
            message="A subscriber cannot attach to the 5G core. Investigate the root cause: check NF health, tail logs for any degraded or down functions, read their config if the logs are ambiguous, then tell me exactly what is wrong and what to do to fix it.",
        ),
    ]


@cl.on_chat_resume
async def on_chat_resume(thread):
    cl.user_session.set("read_only", True)
    await _send(cl.Message(
        content="📚 **This conversation is archived.** Start a new chat to continue working with the network agent."
    ))


@cl.on_chat_start
async def on_chat_start():
    mcp_ctx = get_mcp_tools()
    raw_tools = await mcp_ctx.__aenter__()
    cl.user_session.set("mcp_ctx", mcp_ctx)
    cl.user_session.set("raw_tools", raw_tools)

    model_name = get_active_model_name()
    thinking_capable = model_supports_thinking(model_name)
    cl.user_session.set("human_approval_enabled", False)
    cl.user_session.set("model_name", model_name)
    cl.user_session.set("use_model_reasoning", thinking_capable)
    cl.user_session.set("show_thinking", thinking_capable)
    cl.user_session.set("memory_learning_enabled", False)
    # One checkpointer for the whole session — reused on every _rebuild_agent so a
    # mid-chat model/reasoning switch keeps the conversation history.
    checkpointer = MemorySaver()
    cl.user_session.set("checkpointer", checkpointer)
    tools = _build_tools(raw_tools)

    agent = create_agent(
        tools, thinking=thinking_capable, suppress_thinking=False,
        model_name=model_name, checkpointer=checkpointer,
    )
    cl.user_session.set("agent", agent)
    cl.user_session.set("thread_id", str(uuid.uuid4()))

    branding = _load_branding()
    model_hint = "  ·  _switch in ⚙️ Settings_" if len(list_available_models()) > 1 else ""
    tool_names = "  ".join(
        f"{TOOL_ICONS.get(t.name, '🔧')} `{t.name}`" for t in tools
    )
    await _send(cl.Message(
        content=(
            f"**{branding['welcome_title']}**\n\n"
            f"Model: `{model_name}`{model_hint}\n\n"
            f"**Tools:** {tool_names}"
        ),
        actions=_make_scenario_actions(),
    ))

    await cl.ChatSettings(_build_widgets()).send()


@cl.action_callback("health_snapshot")
async def on_health_snapshot(action: cl.Action):
    if not cl.user_session.get("read_only"):
        await _run_agent(action.payload["prompt"])


@cl.action_callback("watch_attach")
async def on_watch_attach(action: cl.Action):
    if not cl.user_session.get("read_only"):
        await _run_agent(action.payload["prompt"])


@cl.action_callback("debug_failure")
async def on_debug_failure(action: cl.Action):
    if not cl.user_session.get("read_only"):
        await _run_agent(action.payload["prompt"])


def _rebuild_agent(thinking: bool, use_reasoning: bool, model_name: str | None = None) -> bool:
    """Rebuild the agent with the given model + thinking/reasoning flags. Returns False if session not ready."""
    raw_tools = cl.user_session.get("raw_tools")
    if not raw_tools:
        return False
    if model_name is None:
        model_name = cl.user_session.get("model_name") or get_active_model_name()
    tools = _build_tools(raw_tools)
    cl.user_session.set("agent", create_agent(
        tools, thinking=thinking, suppress_thinking=not use_reasoning, model_name=model_name,
        checkpointer=cl.user_session.get("checkpointer"),
    ))
    cl.user_session.set("show_thinking", thinking)
    cl.user_session.set("use_model_reasoning", use_reasoning)
    cl.user_session.set("model_name", model_name)
    return True


def _refresh_tools() -> bool:
    """Rebuild the agent's tool list only (e.g. after a memory toggle), keeping the current thinking/reasoning config."""
    return _rebuild_agent(
        cl.user_session.get("show_thinking", True),
        cl.user_session.get("use_model_reasoning", True),
    )


@cl.on_settings_update
async def on_settings_update(settings: dict):
    enabled = settings.get("human_approval_enabled", False)
    approval_changed = enabled != cl.user_session.get("human_approval_enabled", False)
    cl.user_session.set("human_approval_enabled", enabled)
    if approval_changed:
        status = "enabled" if enabled else "disabled"
        await cl.Message(content=f"🔒 Human approval mode **{status}**.").send()

    current_model = cl.user_session.get("model_name") or get_active_model_name()
    new_model = settings.get("model_name", current_model)
    if new_model not in list_available_models():
        new_model = current_model
    model_changed = new_model != current_model

    use_reasoning = settings.get("use_model_reasoning", True)
    show_thinking = settings.get("show_thinking", True)

    # show_thinking depends on reasoning being enabled — can't show reasoning that isn't generated
    if not use_reasoning:
        show_thinking = False

    # A model without `thinking: true` can neither reason nor stream thinking,
    # regardless of the toggles (which _build_widgets hides for such a model).
    if not model_supports_thinking(new_model):
        use_reasoning = False
        show_thinking = False

    reasoning_changed = use_reasoning != cl.user_session.get("use_model_reasoning", True)
    thinking_changed = show_thinking != cl.user_session.get("show_thinking", True)

    if model_changed or reasoning_changed or thinking_changed:
        if _rebuild_agent(show_thinking, use_reasoning, model_name=new_model):
            if model_changed:
                await cl.Message(content=f"🔀 Model switched to **`{new_model}`** for this chat.").send()
            elif reasoning_changed:
                status_r = "enabled" if use_reasoning else "disabled"
                await cl.Message(content=f"🧠 Model reasoning **{status_r}**.").send()
            elif thinking_changed:
                status_t = "enabled" if show_thinking else "disabled"
                await cl.Message(content=f"💭 Model thinking **{status_t}**.").send()

    if model_changed or reasoning_changed:
        # the thinking widgets' presence depends on the model; show_thinking's
        # disabled state depends on use_model_reasoning — refresh the panel
        await cl.ChatSettings(_build_widgets()).send()

    memory_enabled = settings.get("memory_learning_enabled", False)
    memory_changed = memory_enabled != cl.user_session.get("memory_learning_enabled", False)
    cl.user_session.set("memory_learning_enabled", memory_enabled)
    if memory_changed:
        _refresh_tools()
        status_m = "enabled" if memory_enabled else "disabled"
        await cl.Message(content=f"🧠 Memory & Learning **{status_m}**.").send()


@cl.on_message
async def on_message(message: cl.Message):
    if cl.user_session.get("read_only"):
        return
    await _run_agent(message.content)


async def _fetch_mermaid_image(client: httpx.AsyncClient, i: int, match: re.Match) -> tuple[cl.Image | None, re.Match]:
    mermaid_text = match.group(1).strip()
    encoded = base64.urlsafe_b64encode(mermaid_text.encode()).decode()
    try:
        resp = await client.get(f"https://mermaid.ink/img/{encoded}")
        if resp.status_code == 200:
            return cl.Image(content=resp.content, name=f"call_flow_{i}", display="inline", size="large"), match
    except Exception:
        pass
    return None, match


def _strip_latex(content: str) -> str:
    """Rewrite stray LaTeX notation as the Unicode the system prompt mandates.

    Fenced code blocks are left untouched — a shell snippet's backslashes and
    "$VAR" references are not math and must survive verbatim.
    """
    if "\\" not in content:
        return content

    # Odd-indexed segments are inside ``` fences; only rewrite the even ones.
    parts = content.split("```")
    for i in range(0, len(parts), 2):
        text = parts[i]
        if "\\" not in text:
            continue
        text = _LATEX_DISPLAY_RE.sub(r"\1", text)
        text = _LATEX_INLINE_RE.sub(r"\1", text)
        text = _LATEX_PAREN_RE.sub(r"\1", text)
        text = _LATEX_BRACKET_RE.sub(r"\1", text)
        text = _LATEX_WRAPPER_RE.sub(r"\1", text)
        # Unknown commands are left as-is rather than silently deleted.
        text = _LATEX_COMMAND_RE.sub(
            lambda m: _LATEX_SYMBOLS.get(m.group(1), m.group(0)), text
        )
        text = _LATEX_ESCAPE_RE.sub(r"\1", text)
        text = _LATEX_SPACING_RE.sub("", text)
        parts[i] = text
    return "```".join(parts)


async def _render_mermaid_diagrams(content: str) -> tuple[list[cl.Image], str]:
    """Fetch PNG renders of ```mermaid blocks from mermaid.ink concurrently.

    Returns (images, content_with_blocks_removed).
    """
    matches = list(_MERMAID_RE.finditer(content))
    if not matches:
        return [], content

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *(_fetch_mermaid_image(client, i, m) for i, m in enumerate(matches))
        )

    images: list[cl.Image] = []
    clean = content
    for image, match in results:
        if image is not None:
            images.append(image)
            clean = clean.replace(match.group(0), "")

    return images, clean.strip()


async def _run_agent(user_input: str):
    agent = cl.user_session.get("agent")
    if agent is None:
        await _send(cl.Message(
            content="❌ **Agent not ready.** The session failed to initialise — please refresh the page.",
            actions=_make_scenario_actions(),
        ))
        return

    thread_id = cl.user_session.get("thread_id")

    active_steps: dict[str, cl.Step] = {}
    tools_active = 0
    # Created lazily on the first streamed token — never pre-sent as empty
    current_msg: cl.Message | None = None
    show_thinking: bool = cl.user_session.get("show_thinking", False)
    reasoning_step: cl.Step | None = None
    last_usage: dict | None = None

    thinking_step: cl.Step | None = None
    if not show_thinking:
        thinking_step = cl.Step(name="Thinking…", type="tool")
        await thinking_step.__aenter__()

    async def dismiss_thinking() -> None:
        nonlocal thinking_step
        if thinking_step is not None:
            await thinking_step.__aexit__(None, None, None)
            thinking_step = None

    try:
        async for event in agent.astream_events(
            {"messages": [HumanMessage(content=user_input)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            kind = event["event"]
            run_id = event.get("run_id", "")

            if kind == "on_tool_start":
                await dismiss_thinking()
                tool_name = event["name"]
                specialist_label = SPECIALIST_LABELS.get(tool_name)

                # Discard any pre-tool text fragments the model leaked
                if current_msg is not None:
                    await current_msg.remove()
                    current_msg = None

                # Specialist subagent tool calls (e.g. investigate_nf_health) can run
                # concurrently with each other, so their nested tool events interleave
                # in this stream. Chainlit's ambient "currently open step" context can't
                # tell them apart — derive the real parent explicitly from parent_ids
                # (nearest ancestor run_id that's still an open step) instead.
                parent_step = None
                for ancestor_id in reversed(event.get("parent_ids", [])):
                    if ancestor_id in active_steps:
                        parent_step = active_steps[ancestor_id]
                        break

                if specialist_label:
                    # type stays "tool", not "run" — this project's cot="tool_call"
                    # setting (.chainlit/config.toml) hides any step whose type isn't
                    # "tool" from the UI entirely, so "run" would make this invisible
                    # rather than distinct. The name/icon carry the distinction instead.
                    step = cl.Step(
                        name=f"🤖 Subagent: {specialist_label}",
                        type="tool",
                        parent_id=parent_step.id if parent_step else None,
                    )
                else:
                    icon = TOOL_ICONS.get(tool_name, "🔧")
                    step = cl.Step(
                        name=f"{icon} {tool_name}",
                        type="tool",
                        parent_id=parent_step.id if parent_step else None,
                    )

                # cl.Step.__aenter__ only honors parent_id when it's truthy — for a
                # true top-level step (parent_step is None) it silently falls back to
                # Chainlit's own "last step still open" guess, which is wrong whenever
                # two specialists overlap in time (one sibling is still open when the
                # other starts). Force Chainlit's internal step stack to the parent
                # we've already derived above so __aenter__ can't override it.
                local_steps.set([parent_step] if parent_step else [])
                step.input = str(event["data"].get("input", ""))
                await step.__aenter__()
                active_steps[run_id] = step
                tools_active += 1

            elif kind == "on_tool_end":
                step = active_steps.pop(run_id, None)
                if step:
                    output_raw = event["data"].get("output", "")
                    output_str = _unwrap_mcp_output(output_raw)
                    if event["name"] in SPECIALIST_LABELS:
                        # A specialist's output is already a synthesized prose report
                        # (Findings/Likely cause/Unverifiable) — truncating it at leaf-
                        # tool length would hide the point of delegating to it.
                        step.output = output_str
                    else:
                        step.output = output_str[:300] + ("…" if len(output_str) > 300 else "")
                    await step.__aexit__(None, None, None)
                    tools_active -= 1

            elif kind == "on_chat_model_end":
                usage = getattr(event["data"].get("output"), "usage_metadata", None)
                if usage and usage.get("input_tokens") is not None:
                    last_usage = usage

            elif kind == "on_chat_model_stream" and tools_active == 0:
                chunk = event["data"]["chunk"]
                content = getattr(chunk, "content", "")
                reasoning_tokens: list[str] = []
                text_tokens: list[str] = []

                # ChatOllama (reasoning=True) puts thinking in additional_kwargs
                rc = getattr(chunk, "additional_kwargs", {}).get("reasoning_content")
                if rc:
                    reasoning_tokens.append(rc)

                if isinstance(content, str) and content:
                    text_tokens = [content]
                elif isinstance(content, list):
                    for p in content:
                        if not isinstance(p, dict):
                            continue
                        if p.get("type") == "thinking" and p.get("thinking"):
                            reasoning_tokens.append(p["thinking"])
                        elif p.get("type") == "text" and p.get("text"):
                            text_tokens.append(p["text"])

                if show_thinking and reasoning_tokens:
                    await dismiss_thinking()
                    if reasoning_step is None:
                        reasoning_step = cl.Step(name="💭 Reasoning", type="tool")
                        await reasoning_step.__aenter__()
                    for token in reasoning_tokens:
                        await reasoning_step.stream_token(token)

                if text_tokens and reasoning_step is not None:
                    await reasoning_step.__aexit__(None, None, None)
                    reasoning_step = None

                for token in text_tokens:
                    await dismiss_thinking()
                    if current_msg is None:
                        current_msg = cl.Message(content="")
                        await _send(current_msg)
                    await current_msg.stream_token(token)

    except Exception as exc:
        # Unwrap Python 3.11+ ExceptionGroup (raised by asyncio.TaskGroup internals)
        inner = exc
        if isinstance(exc, BaseExceptionGroup) and exc.exceptions:
            inner = exc.exceptions[0]
        await dismiss_thinking()
        if reasoning_step is not None:
            await reasoning_step.__aexit__(None, None, None)
            reasoning_step = None
        for step in active_steps.values():
            step.is_error = True
            step.output = f"❌ Error: {inner}"
            await step.__aexit__(None, None, None)
        root_cause = str(inner) or type(inner).__name__

        # A failed tool call leaves a dangling AIMessage with tool_calls but no
        # ToolMessage in the MemorySaver checkpointer. Reset the thread so the
        # next user message starts clean rather than hitting INVALID_CHAT_HISTORY.
        cl.user_session.set("thread_id", str(uuid.uuid4()))

        if current_msg is None:
            current_msg = cl.Message(content="")
            await _send(current_msg)

        if isinstance(inner, (httpx.ConnectError, httpx.ConnectTimeout)):
            mcp_url = get_mcp_url()
            current_msg.content = (
                f"❌ **Cannot reach the MCP server at VM1.**\n\n"
                f"The 5G core agent connected to the LLM successfully, but the "
                f"MCP tool server (`{mcp_url}`) is not responding.\n\n"
                f"**Fix:** SSH into VM1 and start the MCP server, then restart this chat."
            )
        else:
            current_msg.content = f"❌ **Agent error:** {root_cause}"

    await dismiss_thinking()
    if reasoning_step is not None:
        await reasoning_step.__aexit__(None, None, None)
        reasoning_step = None

    # Ensure there is always a message to carry the final action buttons
    if current_msg is None:
        current_msg = cl.Message(content="")
        await _send(current_msg)

    # Attach fresh action buttons (new instances so forId is None and update() sends them)
    current_msg.actions = _make_scenario_actions()

    current_msg.content = _strip_latex(current_msg.content)
    images, clean_content = await _render_mermaid_diagrams(current_msg.content)
    if images:
        current_msg.content = clean_content
        await current_msg.update()
        # Defensive re-create: Chainlit's own shutdown path (or a racing
        # process restart) can rmtree this directory out from under a still
        # -running server — a one-time mkdir at import isn't enough (see
        # CLAUDE.md's mermaid gotcha).
        _FILES_DIR.mkdir(exist_ok=True)
        await _send(cl.Message(content="", elements=images))
    else:
        await current_msg.update()

    if last_usage is not None:
        input_tokens = last_usage["input_tokens"]
        output_tokens = last_usage.get("output_tokens", 0)
        async with cl.Step(name="📊 Context", type="tool", default_open=False) as context_step:
            context_step.output = (
                f"{input_tokens:,} sent · {output_tokens:,} received "
                f"({input_tokens + output_tokens:,} total)"
            )

    if not cl.user_session.get("thread_named") and current_msg.content and not current_msg.content.startswith("❌"):
        name = user_input[:60].rstrip()
        data_layer = get_data_layer()
        if data_layer:
            await data_layer.update_thread(
                thread_id=cl.context.session.thread_id,
                name=name,
            )
        cl.user_session.set("thread_named", True)


@cl.on_chat_end
async def on_chat_end():
    mcp_ctx = cl.user_session.get("mcp_ctx")
    if mcp_ctx:
        await mcp_ctx.__aexit__(None, None, None)
