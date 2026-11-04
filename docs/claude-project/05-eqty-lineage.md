# NetAgent — EQTY lineage manifests

> Project knowledge file 5 of 7 · snapshot as of 2026-11-04 (commit 9d501a7).

## What gets recorded

Every agent run emits a **signed, content-addressed lineage manifest**: a record of each LangGraph
node, model call and tool call, with their inputs and outputs, built by EQTY's
`eqty_sdk` + `eqty-lineage-langchain`. An `EqtyCallbackHandler` is attached to each turn's run;
LangGraph reports every step to it and it registers each one as a signed statement.

A manifest is JSON with top-level `version`, `contexts`, `statements` and `blobs`. Nodes are
identified by content hash (`urn:cid:…`) and signed by a key (`did:key:…`). Statement types
include `ComputationRegistration` (a step: its inputs, outputs, where it ran),
`DataRegistration` and `MetadataRegistration`. Because every payload is stored, the blobs hold the
actual chat text and tool arguments and results.

## Where manifests live

- `manifests/<chat_id>.json` on VM2, one file per chat, gitignored, directory mode 0700.
- `<chat_id>` is the **Chainlit chat id** — the one in the browser URL. The app passes it as
  `metadata.thread_id`, which the lineage handler uses to pick the chat's context, while the
  checkpointer keeps its own `configurable.thread_id` (replaced after a failed turn). So a chat's
  lineage stays in one file even across failed turns. (Fixed 2026-11-04: manifests used to be
  named after the checkpointer id, so links didn't match the chat and failed turns split files.)
- The file is rewritten after every turn and holds the whole chat so far.
- `scripts/rca_bench.py` writes manifests to the same directory.
- Signing: a local key in `.eqty_sdk/` (gitignored; `chmod 700` it after first run), or a notary
  service if `EQTY_NOTARY_URL` is set.

## Viewing a manifest in the Web UI (🧬 Lineage)

- The 🧬 **Lineage** button on each message runs plain code (no agent or model call, so it adds
  nothing to the manifest) and posts two links for the current chat:
  - **Open lineage graph** → `/lineage/<chat_id>`
  - **Download manifest JSON** → `/lineage/<chat_id>/manifest.json`, sent as an attachment so the
    browser saves it. A "Save as" dialog is a browser setting ("Ask where to save each file"); the
    app can't force one.
- The page loads EQTY's published explorer web component (`@eqtylab/explorer` 0.19.0 from
  jsdelivr, pinned by SRI hash), fetches the manifest from the app, and hands it to the component,
  which draws the graph: a **computation node** per step, **data nodes** for each input/output,
  edges input → step → output. Clicking a node shows its contents and signer.
- Implementation: `lineage_viewer.py` + `lineage_viewer.html`. The routes are inserted ahead of
  Chainlit's SPA catch-all route (appended routes would never be reached) and accept only
  canonical UUIDs (no path traversal). The page's CSP allows connections only back to the app and
  to the pinned explorer directory, and `Referrer-Policy: no-referrer` keeps the chat id from
  reaching jsdelivr. The browser needs internet access to load the component; the manifest never
  leaves VM2.
- Works in archived (read-only) chats too. Switch: `config/lineage.yaml` `viewer_enabled`.

## Sensitive data

Manifests hold, in plaintext: chat text, IMSIs, UE IPs, any K/OPc typed to create a subscriber,
and 5G-AKA data from `get_ue_trace` (RAND, truncated AUTN, what looks like a truncated KSEAF).
There is no real authentication (every visitor is the `demo` user), so **anyone who can reach the
app and has a link can open a chat's manifest**. On any deployment with real subscribers, set
`viewer_enabled: false` and don't share manifests. Never put a manifest on a public ledger —
publish only its hash, as the Hedera report fingerprint does.

## Rules that fail quietly (the run works, the manifest is wrong)

- `init()` runs once per process (app.py module level; rca_bench `main()`), not per run and not in
  `start.py` (which launches Chainlit as a subprocess).
- One `EqtyCallbackHandler` per turn, never shared. Don't attach one to the specialists: they
  inherit the parent's callbacks and would be recorded twice.
- Every new local tool needs `@eqty_tool` under `@tool`, or it records as a name-only stub.
- Specialists share the source of their run function; their `metadata={"specialist": …}` keeps
  them as separate Tool assets and `lc_agent_name` records them as agents. Keep both.

## What a manifest does not show

- MCP tools on VM1: name and MCP hints only, no source code.
- Model settings and weights: name, provider and `stop` only — not temperature, num_predict,
  num_ctx or the reasoning flag, and no hash of the weights.
- Execution environment: signed with a local key (or notary), no hardware attestation.
- The approval gate: its code isn't recorded; a denial shows only as tool output text.
- Knowledge-base and memory searches: `similarity_search` fires no retriever callbacks, so results
  appear as tool output, not separate documents.
- The 🔏 fingerprint: runs outside the graph, so it isn't recorded.

Not yet confirmed in a real run: source capture on local tools other than `hcs_list_recent`, the
export after a failed turn, and recovery after pressing Stop (a stopped turn likely skips its
export; the next turn's should include it).
