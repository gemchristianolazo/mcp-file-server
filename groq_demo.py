"""Session 2: fresh agent catches up from state files only."""
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

TUNNEL_URL = os.environ["MCP_TUNNEL_URL"]
BEARER = os.environ["MCP_BEARER_TOKEN"]

mcp_tool = {
    "type": "mcp",
    "server_label": "file-server",
    "server_description": "Sandboxed workspace for multi-session agent work.",
    "server_url": f"{TUNNEL_URL}/mcp",
    "headers": {"Authorization": f"Bearer {BEARER}"},
    "require_approval": "never",
}

prompt = (
    "You are Session 2 of a 2-session project. "
    "You have NO memory of Session 1 whatsoever. "
    "Your ONLY way to catch up is by reading the workspace files.\n\n"
    "Do these steps in order:\n"
    "1. Call read_file with path='PROJECT_STATE.md'.\n"
    "2. Call read_file with path='PLAN_LOG.md'.\n"
    "3. Call repo_map with path='.'.\n\n"
    "Then report:\n"
    "- What did Session 1 accomplish?\n"
    "- What are you expected to do next?\n"
    "Do NOT write any files."
)

response = client.responses.create(
    model="openai/gpt-oss-120b",
    input=prompt,
    tools=[mcp_tool],
)
print(response.output_text)
print("\n=== FULL RESPONSE ===")
print(response)