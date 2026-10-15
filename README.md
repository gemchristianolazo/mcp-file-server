# mcp-file-server
 
[![M8ven Verified](https://m8ven.ai/badge/mcp/gemchristianolazo-mcp-file-server-1y8js5?variant=verified&v=e7564accb10b21778919e3553b4a6c41)](https://m8ven.ai/mcp/gemchristianolazo-mcp-file-server-1y8js5?s=readme)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-2.3.0-orange)](https://modelcontextprotocol.io/)
[![Transport](https://img.shields.io/badge/Transport-Streamable%20HTTP-green)](https://modelcontextprotocol.io/specification/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011-0078D4)](https://www.microsoft.com/windows)

A **sandboxed MCP (Model Context Protocol) file server** for multi-session agent work. Built for **CS3 Week 6 Midterm Pt 1** (Agentic AI II - Tool Use & Orchestration).

The server exposes **10 file, search, and git-lite tools** to any compliant MCP client over Streamable HTTP, gated by a bearer token, and managed as a Windows service. It is designed so that a fresh agent, starting with no memory of previous work, can pick up exactly where the last session ended.

## Table of Contents

1. What It Does
2. Demo
3. Architecture
4. The 10 Tools
5. Requirements
6. Install
7. Configure
8. Run - Local (MCP Inspector)
9. Run - HTTP + Tunnel
10. Install as a Windows Service
11. Security
12. The Handoff Protocol
13. Repo Layout
14. Known Limitations

## What It Does

An agent connects over HTTPS, discovers 10 tools, and works inside a **sandboxed workspace**. It reads PROJECT_STATE.md at the start of every session, logs plans to PLAN_LOG.md, records architectural choices in DECISIONS.md, and writes checkpoints to CHECKPOINTS/. When the session ends, all context lives in those files - a fresh agent can pick up the work with no memory of what came before.

## Demo

The two-session agent demo is documented with verbatim transcripts in docs/DEMO.md.

A fresh Groq agent with no memory of Session 1 correctly reconstructed prior work by reading PROJECT_STATE.md alone - proving the handoff protocol works.

All 19 screenshots of the working system - tool discovery, path-traversal defense, HTTP auth, tunnel exposure, service persistence, and both agent sessions - live in docs/evidence/.

## Architecture

    Groq LLM (gpt-oss-120b)
        | HTTPS
        v
    Cloudflare Quick Tunnel
        | HTTP
        v
    run_http.py  [bearer-token gate]
        | ASGI
        v
    MCPServer  [10 tools]
        |
        +--> sandbox.py  ->  SANDBOX_ROOT
        +--> git CLI subprocess
        v
    workspace/
        PROJECT_STATE.md
        PLAN_LOG.md
        DECISIONS.md
        CHECKPOINTS/

Managed by: NSSM Windows Service (auto-restart, auto-start on boot)

How it fits MCP roles:

- **Host / Client**: Groq API discovers tools and drives the tool-calling loop
- **Server**: server.py - exposes 10 tools, knows nothing about the LLM
- **Transport**: Streamable HTTP (modern replacement for SSE)
- **Auth**: Bearer token via pure-ASGI middleware, checked before the MCP session manager runs

## The 10 Tools

| Tool | Signature | Purpose |
|------|-----------|---------|
| list_files | (path=".", pattern="*") | List files in a directory |
| read_file | (path, start_line=1, end_line=0) | Read UTF-8 text with line numbers |
| write_file | (path, content, if_version="") | Write a file; optional optimistic lock |
| str_replace | (path, old_str, new_str, replace_all=False) | Exact-match edit |
| delete_file | (path, confirm=False) | Delete; requires confirm=True |
| search_code | (query, path=".", glob="*", max_results=50) | Substring search |
| repo_map | (path=".", max_entries=200) | Compact tree to depth 3 |
| git_status | () | Git status of the workspace |
| git_diff | (staged=False, path="") | Working tree or staged diff |
| git_log | (limit=10) | Recent commits |

Design choices:

- **str_replace over write_file for edits** - smaller diffs, less chance of clobbering concurrent changes. Fails if old_str is ambiguous, forcing the agent to widen its match.
- **if_version optimistic lock on writes** - prevents overwriting a file that changed since the agent last read it. Optional to keep simple calls simple.
- **confirm=True on delete** - guards destructive actions.
- **Line-numbered reads** - so the agent can reference exact positions in follow-up str_replace calls.

## Requirements

- **Windows 10/11** (verified on Windows 11 Pro, build 26200)
- **Python 3.12** (managed by uv)
- **uv** - install: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
- **cloudflared** - Cloudflare Tunnel client
- **NSSM** - winget install nssm

## Install

    git clone https://github.com/gemchristianolazo/mcp-file-server.git
    cd mcp-file-server
    uv sync

## Configure

Copy .env.example to .env and set:

    MCP_BEARER_TOKEN=<long random string>
    SANDBOX_ROOT=C:\path\to\mcp-file-server\workspace

Generate a token:

    python -c "import secrets; print(secrets.token_urlsafe(32))"

## Run - Local (MCP Inspector)

    uv run mcp dev server.py

Opens the MCP Inspector. Click connect, then exercise any of the 10 tools.

Path traversal test:

- read_file with path=PROJECT_STATE.md  ->  succeeds
- read_file with path=../../etc/passwd  ->  isError: true, "Path escapes sandbox root"

## Run - HTTP + Tunnel

    # Terminal 1
    uv run python run_http.py

    # Terminal 2
    cloudflared tunnel --url http://127.0.0.1:8000

Verify auth in a third terminal:

    curl.exe -i -X POST http://127.0.0.1:8000/mcp
    # -> HTTP/1.1 401 Unauthorized

    curl.exe -i -X POST https://xxx.trycloudflare.com/mcp
    # -> HTTP/1.1 401 Unauthorized (through the tunnel)

## Install as a Windows Service

Administrator PowerShell:

    nssm install MCPServer "<repo>\.venv\Scripts\python.exe" "<repo>\run_http.py"
    nssm set MCPServer AppDirectory "<repo>"
    nssm set MCPServer AppStdout "<repo>\logs\server.out.log"
    nssm set MCPServer AppStderr "<repo>\logs\server.err.log"
    nssm set MCPServer AppExit Default Restart
    nssm set MCPServer AppRestartDelay 3000
    nssm set MCPServer Start SERVICE_AUTO_START
    nssm start MCPServer

Auto-restarts on crash and auto-starts on boot. Verified after a full reboot.

## Security

### Path Sandboxing

Every tool resolves paths through sandbox.safe_path(), which rejects:

- Absolute paths (/etc/passwd, C:\Windows\...)
- Traversal (../../etc/passwd, foo/../../etc/passwd)
- Symlinks pointing outside the root

Verified by 11 tests (uv run python test_sandbox.py), including deep traversal, nested traversal, empty strings, and symlink escape.

### Bearer-Token Auth

Every HTTP request must carry Authorization: Bearer <token>. Missing or wrong tokens get 401 Unauthorized from a pure-ASGI middleware that runs before the MCP session manager.

### Gated Destructive Actions

- delete_file requires explicit confirm=True
- write_file supports if_version (sha1 optimistic lock)
- str_replace fails if the match is ambiguous

## The Handoff Protocol

Four files in the workspace root that carry state across agent sessions:

| File | Purpose |
|------|---------|
| PROJECT_STATE.md | Current snapshot: done / next |
| PLAN_LOG.md | Append-only log across sessions |
| DECISIONS.md | ADR-lite record of choices |
| CHECKPOINTS/<date>-sessionN.md | Dated snapshot per session |

Proof: docs/DEMO.md shows a fresh Groq agent reading PROJECT_STATE.md, PLAN_LOG.md, and repo_map and correctly reporting what Session 1 accomplished and what to do next.

## Repo Layout

    mcp-file-server/
      server.py              The MCP server (10 tools)
      run_http.py            HTTP launcher with bearer-token gate
      sandbox.py             safe_path() + SandboxViolation
      test_sandbox.py        11 path-traversal tests
      groq_demo.py           Two-session agent demo script
      servers.json           MCP client config
      .env.example           Template for required secrets
      workspace/             The sandbox root
        PROJECT_STATE.md
        PLAN_LOG.md
        DECISIONS.md
        CHECKPOINTS/
        md2txt/              Session 1's output (left intact)
      docs/
        DEMO.md              Two-session narrative
        evidence/            19 screenshots + index
      logs/                  NSSM service logs (gitignored)
      README.md

## Known Limitations

- **Quick Tunnel URLs are ephemeral.** Every cloudflared restart yields a new trycloudflare.com subdomain. For production, a Named Tunnel with a stable hostname is the right choice.
- **Single-writer assumption.** Concurrent writes to the same file are not serialized. The if_version optimistic lock detects conflicting writes but does not prevent them.
- **No per-user accounts.** A single bearer token grants full access. For multi-user deployments, replace with OAuth 2.1 (the mcp SDK supports this via token_verifier and AuthSettings).
- **Groq Remote MCP requires Streamable HTTP.** Servers that only speak SSE are not accepted by Groq's remote MCP integration.

## License

Academic use - CS3 Week 6 Midterm Pt 1.
