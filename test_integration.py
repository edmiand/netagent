import asyncio
import sys
import uuid

from langchain_core.messages import HumanMessage


async def test_llm_connection() -> bool:
    print("\n[Test 1] LLM connection")
    try:
        from agent.llm import test_llm_connection
        result = await test_llm_connection()
        if result:
            print("  PASS")
        else:
            print("  FAIL — test_llm_connection returned False")
        return result
    except Exception as exc:
        print(f"  FAIL — {exc}")
        return False


async def test_mcp_tools_load() -> bool:
    print("\n[Test 2] MCP tools load")
    required = {
        "nf_lifecycle",
        "system_health_snapshot",
        "subscriber",
        "list_ue_sessions",
        "tail_nf_logs",
    }
    try:
        from agent.mcp_bridge import get_mcp_tools
        async with get_mcp_tools() as tools:
            names = {t.name for t in tools}
            for name in sorted(names):
                print(f"  • {name}")
            missing = required - names
            if not missing:
                print("  PASS")
                return True
            else:
                print(f"  FAIL — missing tools: {missing}")
                return False
    except Exception as exc:
        print(f"  FAIL — {exc}")
        return False


async def test_agent_round_trip() -> bool:
    print("\n[Test 3] Agent round trip")
    try:
        from agent.mcp_bridge import get_mcp_tools
        from agent.graph import create_agent

        async with get_mcp_tools() as tools:
            agent = create_agent(tools)
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content="What NFs are currently running? One sentence only.")]},
                config={"configurable": {"thread_id": "integration-test"}},
            )
            messages = result.get("messages", [])
            response = ""
            for msg in reversed(messages):
                content = getattr(msg, "content", "")
                if isinstance(content, str) and content:
                    response = content
                    break

            if response:
                print(f"  Response: {response[:150]}")
                print("  PASS")
                return True
            else:
                print("  FAIL — empty response from agent")
                return False
    except Exception as exc:
        print(f"  FAIL — {exc}")
        return False


async def test_hcs_round_trip() -> bool | None:
    print("\n[Test 4] Hedera HCS round trip (optional)")
    from dotenv import load_dotenv
    from agent.tools import hedera

    load_dotenv()
    if not hedera.is_enabled():
        print("  SKIP — config/hedera.yaml has enabled: false")
        return None
    try:
        text = f"netagent integration test {uuid.uuid4()}"
        sent = await hedera.hcs_submit_message.ainvoke({"message": text})
        if sent.get("status") != "SUCCESS":
            print(f"  FAIL — submit returned {sent}")
            return False
        print(f"  Submitted seq {sent['sequence_number']} to {sent['topic_id']}")
        got = await hedera.hcs_read_message.ainvoke({"sequence_number": sent["sequence_number"]})
        if got.get("message") == text:
            print("  PASS")
            return True
        print(f"  FAIL — read back {got}")
        return False
    except Exception as exc:
        print(f"  FAIL — {exc}")
        return False


async def main():
    print("=" * 50)
    print("5G Demo App — Integration Tests")
    print("=" * 50)

    results = [
        await test_llm_connection(),
        await test_mcp_tools_load(),
        await test_agent_round_trip(),
        await test_hcs_round_trip(),
    ]
    results = [r for r in results if r is not None]  # drop skipped checks

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"Summary: {passed}/{total} tests passed")
    print("=" * 50)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
