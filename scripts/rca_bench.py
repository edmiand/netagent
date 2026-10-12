"""Run the "Debug Attach Failure" RCA headlessly against one model and report.

Use it to vet a new config/models.yaml entry (e.g. a local model on the host
Mac) before demoing it: prints each tool call with timing, the final answer,
the tool sequence, and whether the reply has the mandated "**Root cause:**"
heading that the 🔏 fingerprint button keys on.

Tool list mirrors app.py's _build_tools() (MCP + local RAG/release tools) but
omits the Hedera tools so a test run never writes to the public HCS topic,
and skips the Human Approval wrapper (no UI to approve in).

  .venv/bin/python scripts/rca_bench.py local-ollama
  .venv/bin/python scripts/rca_bench.py local-ollama --no-reasoning
"""

import argparse
import asyncio
import time
import uuid

from langchain_core.messages import HumanMessage

from agent.graph import create_agent
from agent.llm import model_label, model_supports_thinking
from agent.mcp_bridge import get_mcp_tools
from agent.tools.rag import search_knowledge_base
from agent.tools.release_check import check_open5gs_release_info

# Keep in sync with the debug_failure action payload in app.py.
_PROMPT = (
    "A subscriber cannot attach to the 5G core. Investigate the root cause: check NF "
    "health, tail logs for any degraded or down functions, read their config if the "
    "logs are ambiguous, then tell me exactly what is wrong and what to do to fix it."
)


async def run(model: str, reasoning: bool) -> None:
    # Same default as app.py: reasoning on whenever the model's entry has thinking: true.
    thinking = reasoning and model_supports_thinking(model)
    async with get_mcp_tools() as raw_tools:
        tools = raw_tools + [search_knowledge_base, check_open5gs_release_info]
        agent = create_agent(tools, thinking=thinking, model_name=model)
        t0 = time.monotonic()
        calls, final, usage = [], "", None
        async for ev in agent.astream_events(
            {"messages": [HumanMessage(content=_PROMPT)]},
            config={"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 40},
            version="v2",
        ):
            kind = ev["event"]
            if kind == "on_tool_start":
                args = str(ev["data"].get("input"))[:120]
                print(f"[{time.monotonic() - t0:6.1f}s] → {ev['name']} {args}", flush=True)
                calls.append(ev["name"])
            elif kind == "on_tool_end":
                out = str(ev["data"].get("output"))
                print(f"[{time.monotonic() - t0:6.1f}s]   ← {len(out)} chars", flush=True)
            elif kind == "on_chat_model_end":
                msg = ev["data"]["output"]
                usage = getattr(msg, "usage_metadata", None) or usage
                if isinstance(msg.content, str) and msg.content.strip():
                    final = msg.content
        elapsed = time.monotonic() - t0

    print("\n=== FINAL ANSWER ===\n" + final)
    print(f"\n=== {model_label(model)} (reasoning {'on' if thinking else 'off'}): "
          f"{len(calls)} tool calls in {elapsed:.1f}s ===")
    print("sequence:", " → ".join(calls))
    print("last call usage:", usage)
    print("has **Root cause:** heading:", "**Root cause:**" in final)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("model", help="model name as keyed in config/models.yaml")
    parser.add_argument("--no-reasoning", action="store_true",
                        help="run with model reasoning off (default: on if the model supports it)")
    args = parser.parse_args()
    asyncio.run(run(args.model, reasoning=not args.no_reasoning))


if __name__ == "__main__":
    main()
