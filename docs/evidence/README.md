# Evidence Index

All screenshots captured while building, testing, and demoing the
mcp-file-server. Each proves a specific claim from the project brief.

## Testing (MCP Inspector)

| File | Proves |
|------|--------|
| `01a-tools-list-part1.png` | Tools 1–6 of 10 registered |
| `01b-tools-list-part2.png` | Tools 7–10 of 10 registered |
| `02-read-success.png` | `read_file PROJECT_STATE.md` returns content |
| `03-traversal-blocked.png` | `read_file ../../etc/passwd` → `isError: true` |
| `04-write-success.png` | `write_file hello.md` returns sha1 |

## HTTP Auth (localhost)

| File | Proves |
|------|--------|
| `05-http-no-token-401.png` | Missing token → 401 |
| `06-http-wrong-token-401.png` | Wrong token → 401 |
| `07-http-valid-token-200.png` | Valid token → 200, MCP session starts |

## HTTPS Tunnel (Cloudflare)

| File | Proves |
|------|--------|
| `08-tunnel-no-token-401.png` | Public HTTPS + no token → 401 |
| `09-tunnel-valid-token-200.png` | Public HTTPS + valid token → 200 |

## Process Manager (NSSM)

| File | Proves |
|------|--------|
| `10-nssm-service-running.png` | `SERVICE_RUNNING` status |
| `11-service-survives-reboot.png` | Server responds after reboot without manual start |

## Agent Demo — Session 1.5 (Groq Remote MCP)

| File | Proves |
|------|--------|
| `12a-groq-session1-agent-demo.png` | LLM discovers all 10 tools |
| `12b-groq-session1-agent-demo.png` | LLM writes `md2txt/convert.py` |
| `12c-groq-session1-agent-demo.png` | LLM writes `PROJECT_STATE.md` |
| `12d-groq-session1-agent-demo.png` | LLM writes `PLAN_LOG.md` |

## Agent Demo — Session 2 (Fresh agent catches up)

| File | Proves |
|------|--------|
| `13a-groq-session2-handoff-1of3.png` | Fresh tunnel URL + fresh agent start |
| `13b-groq-session2-handoff-2of3.png` | Agent reads `PROJECT_STATE.md` first |
| `13c-groq-session2-handoff-3of3.png` | Agent reports what Session 1 did |

## Reproduce

See the main [README.md](../../README.md) and [DEMO.md](../DEMO.md).