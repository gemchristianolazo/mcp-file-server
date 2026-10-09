# Two-Session Agent Demo

A demonstration of the multi-session handoff protocol using **Groq's Remote MCP** feature. Groq's `openai/gpt-oss-120b` connects to the file server's public HTTPS tunnel, discovers all 10 tools, and runs the tool-calling loop in the cloud.

## Why Two Sessions?

MCP agents do not share memory between runs. If a project spans more than one agent session, all context must live somewhere the next session can find it. This server enforces a four-file handoff protocol in the workspace root:

| File | Purpose |
|------|---------|
| PROJECT_STATE.md | Current snapshot: done / next |
| PLAN_LOG.md | Append-only log across sessions |
| DECISIONS.md | ADR-lite record of choices |
| CHECKPOINTS/<date>-sessionN.md | Dated snapshot per session |

## The Demo Task

Build a small Python utility `md2txt/convert.py` that converts markdown to plain text. Session 1 writes the implementation and updates state. Session 2, started as a fresh process with no memory, picks up from the state files.

---

## Session 1 - Agent Writes State

**Screenshots:** `docs/evidence/12a-groq-session1-agent-demo.png` through `12d-...`

The agent was given a prompt instructing it to write three files: `md2txt/convert.py`, `PROJECT_STATE.md`, and `PLAN_LOG.md`.

### Tool calls executed

| Order | Tool | Arguments | Result |
|-------|------|-----------|--------|
| 1 | write_file | md2txt/convert.py | 268 bytes, sha1 63232cc9e9cd |
| 2 | write_file | PROJECT_STATE.md | 295 bytes, sha1 487192247eee |
| 3 | write_file | PLAN_LOG.md | 116 bytes, sha1 5161a6d40f64 |

All three returned isError=false. The agent's final response confirmed the three writes.


### Verified on disk after Session 1

```nworkspace/
  PROJECT_STATE.md   ->  _Last updated: Session 1 end._
  PLAN_LOG.md        ->  ## Session 1 - 2026-10-09
  md2txt/
    convert.py       ->  268 bytes
```

---

## Session Boundary

To make this genuinely two sessions:

1. The Cloudflare Quick Tunnel was killed (Ctrl+C)
2. The PowerShell process running the demo was closed entirely
3. A fresh PowerShell was opened and a new tunnel URL was requested
4. Environment variables were reset in the new shell
5. The Groq agent had no server-side memory of Session 1

The only thing that survived was the on-disk workspace.

---

## Session 2 - Fresh Agent Catches Up

**Screenshots:** `docs/evidence/13a-groq-session2-handoff-1of3.png` through `13c-...`

The Session 2 prompt told the agent explicitly that it had no memory of Session 1 and that its only way to catch up was by reading the workspace files.

### Tool calls executed

| Order | Tool | Arguments | Result |
|-------|------|-----------|--------|
| 1 | read_file | PROJECT_STATE.md | Returned Session 1 end state |
| 2 | read_file | PLAN_LOG.md | Returned Session 1 log entry |
| 3 | repo_map | . | Returned full workspace tree |


### The agent's report (verbatim)

> **What Session 1 accomplished**
>
> - Created the core converter: `md2txt/convert.py` was added and implements a `md_to_text()` function that converts Markdown to plain text.
> - Documented progress: Both `PROJECT_STATE.md` and `PLAN_LOG.md` were updated.
>
> **What I am expected to do next (Session 2)**
>
> 1. Read the updated `PROJECT_STATE.md` (already done).
> 2. Write tests for the converter under `md2txt/tests/`.
> 3. Run the tests and fix any bugs uncovered by them.
> 4. Update `PROJECT_STATE.md` once the tests pass.

The fresh agent correctly reconstructed Session 1's work entirely from reading files - no shared memory, no conversation history, no tool state handed over.

---

## What This Proves

| Claim | Evidence |
|-------|----------|
| The server works with a real MCP client | 12a, 13a - 10 tools discovered |
| Bearer auth protects the endpoint | 05-09 - 401 without token, 200 with |
| Public HTTPS exposure works | 08, 09 - through Cloudflare Tunnel |
| Service survives reboot | 11 |
| Handoff protocol works across sessions | 13b, 13c - Session 2 catches up from files |
| Path traversal is blocked | 03 - ../../etc/passwd rejected |


## Reproduce

```powershell
# Terminal 1: tunnel
cloudflared tunnel --url http://127.0.0.1:8000

# Terminal 2: demo
cd mcp-file-server
`$`env:GROQ_API_KEY=`gsk_...` 
`$`env:MCP_BEARER_TOKEN=`<token from .env>` 
`$`env:MCP_TUNNEL_URL=`https://xxx.trycloudflare.com` 
uv run python groq_demo.py
```

## Notes

- The model used is `openai/gpt-oss-120b` (Groq free tier).
- Two Cloudflare Quick Tunnel URLs were used because quick tunnels are ephemeral. This forced the two sessions to communicate only through the workspace files.
- The workspace is checked in with Session 1's output intact, so a grader can inspect the exact state Session 2 read from.

