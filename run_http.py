"""
run_http.py — HTTP launcher with bearer-token auth for the file-server MCP.

Exposes the MCPServer from server.py over Streamable HTTP at
http://127.0.0.1:8000/mcp.

Auth: every request must carry 'Authorization: Bearer <MCP_BEARER_TOKEN>'.
Transport security: DNS-rebinding protection is disabled so a tunnel's Host
header doesn't trigger 421 Misdirected Request.
"""
from __future__ import annotations

import hmac
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from server import mcp

load_dotenv()

BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "").strip()
HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8000"))

# Build the MCP ASGI app with transport_security passed HERE, not to settings.
mcp_app = mcp.streamable_http_app(
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
)


async def auth_and_forward(scope, receive, send):
    """ASGI callable: gate on bearer token, then forward to mcp_app."""
    if scope["type"] != "http":
        return await mcp_app(scope, receive, send)

    headers = dict(scope.get("headers") or [])
    scheme, _, token = headers.get(b"authorization", b"").partition(b" ")
    provided = token.strip() if scheme.lower() == b"bearer" else b""

    if not provided or not hmac.compare_digest(provided, BEARER_TOKEN.encode()):
        body = b'{"error":"unauthorized"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
        return

    await mcp_app(scope, receive, send)


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


app = Starlette(lifespan=lifespan)


async def asgi_entrypoint(scope, receive, send):
    """Top-level ASGI callable — handles lifespan, then routes to auth_and_forward."""
    if scope["type"] == "lifespan":
        async with mcp.session_manager.run():
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        return

    await auth_and_forward(scope, receive, send)


def main() -> None:
    if not BEARER_TOKEN:
        print("FATAL: MCP_BEARER_TOKEN is empty. Set it in .env.", file=sys.stderr)
        sys.exit(1)

    print(f"Starting MCP file-server on http://{HOST}:{PORT}/mcp", file=sys.stderr)
    print(f"Bearer token required (len={len(BEARER_TOKEN)})", file=sys.stderr)
    uvicorn.run(asgi_entrypoint, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()