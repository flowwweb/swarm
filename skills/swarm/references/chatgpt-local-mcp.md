# Direct ChatGPT local MCP

SWARM uses an existing local MCP bridge for ordinary ChatGPT repository work.
The supported v1 path is:

```text
ordinary ChatGPT chat
  -> OpenAI Secure MCP Tunnel
  -> Codexify local bridge
  -> repository tools + this SWARM stdio adapter
```

Codexify owns file reads and edits, search, shell commands, Git/diff, project
binding, tunnel lifecycle, upstream MCP forwarding, and its own audit surface.
SWARM only adds `swarm_status`, `swarm_projects`, and `swarm_usage`; these are
read-only projections of the existing console state. No Codex task, ChatGPT
Work task, model call, request mailbox, or second agent is created by this
route.

## Setup

Install the verified Codexify release using its official installer, then run:

```powershell
python skills/swarm/scripts/swarm_chatgpt_setup.py --check --project-root C:\path\to\repository
python skills/swarm/scripts/swarm_chatgpt_setup.py --write --project-root C:\path\to\repository
codexify doctor
codexify quickstart
```

The setup script merges one `swarm` entry into the existing Codexify
`mcpServers` object and preserves unrelated configuration. It does not create
cloud credentials or write ChatGPT account state. After the tunnel and
connector are created, refresh the connector in ChatGPT and start a normal Chat
conversation. Do not use Work or a Codex task for this route.

The adapter can be exercised without a tunnel:

```powershell
python -m unittest skills/swarm/tests/test_swarm_mcp.py
```

That test proves the local MCP initialize/list/read/write/delete protocol in a
temporary scratch directory. It does not prove ChatGPT discovery or a live
tunnel; those require the manual connection steps printed by Codexify.

## Tool and authority boundary

Generic repository operations remain Codexify tools. Its project binding and
path protections are the authority for file, Git, and shell operations. The
SWARM adapter does not accept arbitrary paths or SQL and does not write its
SQLite state directly. Its telemetry records only local tool metadata:
timestamp, hashed session identifier when supplied, tool, category, duration,
success, result size, and a bounded error string. Prompts, responses,
credentials, authorization headers, environment contents, and terminal output
are excluded.

Local execution is observed locally. Provider-reported usage and derived cost
estimates remain separate and are never inferred from a successful MCP call.
ChatGPT's own limits and any forwarded service billing still apply; an MCP
tool call alone is not evidence of Codex usage saved.

## Candidate decision

Codexify is preferred over a SWARM-owned general bridge because it already
provides Windows support, the official Secure MCP Tunnel runtime, ordinary Chat
connector setup, project selection, repository editing, shell/Git/diff tools,
upstream MCP aggregation, per-conversation binding, and audit controls. SWARM
does not vendor or fork it. DeskMCP was not selected because no verified
first-party repository/runtime was available during the audit. A direct
ChatGPT write/read-back proof remains a manual acceptance gate.
