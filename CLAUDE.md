# 5G Demo App — Claude Code Context

## What this project is
A Chainlit web application that acts as an agentic AI assistant for managing
a live Open5GS 5G core network. The AI agent uses LangGraph to autonomously
chain MCP tool calls, diagnose network issues, and take remediation actions.
All tool calls stream visibly as Steps in the Chainlit UI.

## Architecture
- VM1 (192.168.64.19): Open5GS 5G core + MCP SSE server at :8080/sse
- VM2 (this machine, "lazy"): Chainlit app + LangGraph + Ollama
- MCP connection: HTTP SSE — no local MCP process, just a URL
- LLM: Ollama at http://localhost:11434/v1 (active model set in config/models.yaml)

## Key paths
- config/models.yaml  — model selection (change 'active' to switch models)
- config/mcp.yaml     — MCP server URL
- agent/llm.py        — LangChain model loader (reads models.yaml)
- agent/mcp_bridge.py — SSE client (MultiServerMCPClient, reads mcp.yaml)
- agent/graph.py      — LangGraph ReAct agent
- app.py              — Chainlit entry point
- prompts/system.txt  — agent system prompt
- test_integration.py — 3-check integration test

## MCP tools available on VM1
- nf_lifecycle          start/stop/restart/status any Open5GS NF
- system_health_snapshot one-shot health check of all NFs
- subscriber_crud        CRUD on subscriber profiles in MongoDB
- list_ue_sessions       list active UE registrations and PDU sessions
- tail_nf_logs           filtered log reads from NF log files

## Open5GS paths on VM1 (read-only reference)
- Logs:    /home/dmandrey/open5gs/install/var/log/open5gs/<nf>.log
- Configs: /home/dmandrey/open5gs/install/etc/open5gs/<nf>.yaml
- MongoDB: mongodb://localhost:27017  db: open5gs
- NF names: amf smf upf nrf udm udr ausf pcf bsf nssf

## Python environment
- Python 3.13, venv at .venv/
- Always use .venv/bin/python and .venv/bin/pip
- Activate: source .venv/bin/activate

## Installed versions (reference)
- chainlit               2.11.1   ← Chainlit v2 API throughout
- langgraph              1.2.4
- langchain-mcp-adapters 0.2.2
- mcp                    1.27.2
- langgraph 1.2.x: create_react_agent uses 'prompt=' not 'state_modifier='
- langchain-mcp-adapters 0.2.x: MultiServerMCPClient does NOT support async context manager;
  use: client = MultiServerMCPClient(servers); tools = await client.get_tools()
- Chainlit 2.x: @cl.set_starters only renders on a truly empty chat (no messages yet);
  for shortcuts accessible throughout a conversation, attach cl.Action buttons to messages

## Constraints
- Chainlit 2.x is installed — use v2 API only, not v1 patterns
- Do NOT hand-write .chainlit/config.toml — delete it and let Chainlit regenerate it, then patch settings in
- Do not modify anything on VM1
- Do not hardcode IPs or URLs — always read from config/mcp.yaml
- Do not hardcode model names — always read from config/models.yaml
- UPF operations on VM1 may require sudo — handle gracefully
- Tools return structured data (dicts/JSON), never raw strings

## Running the app
source .venv/bin/activate
chainlit run app.py --host 0.0.0.0 --port 8000

## Switching models
Edit config/models.yaml — change the 'active' field, restart chainlit

## Demo scenarios (3 action buttons on every message)
- Health Snapshot: calls system_health_snapshot, reports NF status table with emojis
- Watch Subscriber Attach: calls list_ue_sessions, shows registered UEs and PDU sessions
- Debug Attach Failure: calls system_health_snapshot to triage the network

## Agent behaviour (system prompt rules)
- Calls EXACTLY ONE tool per response — no autonomous chaining
- Never restarts/stops/starts a NF unless user explicitly asks
- Never suggests shell commands — uses MCP tools directly
- No preamble before tool calls ("let's call X" etc. is forbidden)
- Tool schema knowledge comes from MCP automatically — do not list tools in prompts/system.txt
