"""
server.py — MCP file-server connector.

10 tools across three groups:
  File ops:    list_files, read_file, write_file, str_replace, delete_file
  Search:      search_code, repo_map
  Git-lite:    git_status, git_diff, git_log

Transport: stdio by default. Set MCP_TRANSPORT=http to run over Streamable HTTP
with bearer-token auth.

All file paths are resolved through sandbox.safe_path — escapes are rejected.
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from sandbox import SandboxViolation, get_sandbox_root, relative_to_root, safe_path

load_dotenv()

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = MCPServer(
    name="file-server",
    instructions=(
        "A sandboxed shared workspace for multi-session agent work. "
        "All paths are relative to the workspace root. "
        "Read PROJECT_STATE.md at the start of every session, "
        "append to PLAN_LOG.md as you work, and write CHECKPOINTS at the end."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_READ_BYTES = 200_000  # ~200 KB per read; keep results small for the agent


def _ok(text: str, **meta: Any) -> dict:
    """Standard success envelope."""
    return {"content": [{"type": "text", "text": text}], "isError": False, **meta}


def _err(message: str) -> dict:
    """Standard error envelope — agent can read and recover."""
    return {"content": [{"type": "text", "text": f"ERROR: {message}"}], "isError": True}


# ===========================================================================
# FILE OPS
# ===========================================================================


@mcp.tool()
def list_files(path: str = ".", pattern: str = "*") -> dict:
    """List files in a workspace directory.

    Args:
        path: Directory relative to the workspace root. Defaults to root.
        pattern: Glob pattern to filter names (e.g. '*.md', '*.py'). Default '*'.

    Returns:
        One line per entry: 'type size name'. Directories end with '/'.
    """
    try:
        target = safe_path(path)
        if not target.exists():
            return _err(f"Directory not found: {path}")
        if not target.is_dir():
            return _err(f"Not a directory: {path}")

        lines = []
        for entry in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
            if not fnmatch.fnmatch(entry.name, pattern):
                continue
            rel = entry.relative_to(target).as_posix()
            if entry.is_dir():
                lines.append(f"dir       -  {rel}/")
            else:
                lines.append(f"file  {entry.stat().st_size:>6}  {rel}")

        if not lines:
            return _ok(f"(empty) no entries match {pattern!r} in {path}")
        return _ok(f"{len(lines)} entries in {path}:\n" + "\n".join(lines))
    except SandboxViolation as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def read_file(path: str, start_line: int = 1, end_line: int = 0) -> dict:
    """Read a UTF-8 text file from the workspace.

    ALWAYS read a file before editing it. Never edit blind.

    Args:
        path: File path relative to the workspace root.
        start_line: 1-based first line to return (default 1).
        end_line: 1-based last line to return inclusive. 0 means 'to end of file'.

    Returns:
        The requested lines, prefixed by 'N: ' line numbers so you can
        reference exact positions in follow-up calls.
    """
    try:
        target = safe_path(path, must_exist=True)
        if target.is_dir():
            return _err(f"Is a directory, not a file: {path}")

        size = target.stat().st_size
        if size > MAX_READ_BYTES:
            return _err(
                f"File too large ({size} bytes > {MAX_READ_BYTES}). "
                "Use search_code to find what you need, or read a line range."
            )

        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        start = max(1, start_line) - 1
        end = len(lines) if end_line <= 0 else min(end_line, len(lines))
        chunk = lines[start:end]

        if not chunk:
            return _ok(f"(no lines) {path} has {len(lines)} lines")

        body = "\n".join(f"{i + start + 1:>4}: {ln}" for i, ln in enumerate(chunk))
        return _ok(
            f"{path} (lines {start + 1}-{start + len(chunk)} of {len(lines)}):\n{body}"
        )
    except (SandboxViolation, FileNotFoundError) as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def write_file(path: str, content: str, if_version: str = "") -> dict:
    """Create or overwrite a file with the given content.

    For small edits to existing files, prefer str_replace — it's safer and
    keeps the diff readable.

    Args:
        path: File path relative to the workspace root.
        content: Full file content to write (UTF-8).
        if_version: Optional optimistic-lock guard. If set and the file's
            current sha1 differs from this value, the write is refused.

    Returns:
        Confirmation with the new sha1 and byte count.
    """
    try:
        target = safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if if_version:
            import hashlib

            current = (
                hashlib.sha1(target.read_bytes()).hexdigest() if target.exists() else ""
            )
            if current != if_version:
                return _err(
                    f"if_version mismatch: expected {if_version}, current is {current or '(missing)'}"
                )

        data = content.encode("utf-8")
        target.write_bytes(data)

        import hashlib

        digest = hashlib.sha1(data).hexdigest()
        return _ok(
            f"wrote {relative_to_root(target)} ({len(data)} bytes, sha1 {digest[:12]})"
        )
    except SandboxViolation as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def str_replace(path: str, old_str: str, new_str: str, replace_all: bool = False) -> dict:
    """Replace an exact substring in a file.

    old_str must appear in the file. If replace_all is False, old_str must
    appear exactly once, otherwise the call fails — widen the match with
    surrounding text to disambiguate.

    Args:
        path: File path relative to the workspace root.
        old_str: Exact substring to find.
        new_str: Replacement substring.
        replace_all: If True, replace every occurrence. Default False.

    Returns:
        Number of replacements and the new sha1.
    """
    try:
        target = safe_path(path, must_exist=True)
        text = target.read_text(encoding="utf-8", errors="replace")

        count = text.count(old_str)
        if count == 0:
            return _err(f"old_str not found in {path}")
        if count > 1 and not replace_all:
            return _err(
                f"old_str appears {count} times in {path}. "
                "Widen the match with surrounding text, or pass replace_all=True."
            )

        new_text = text.replace(old_str, new_str, -1 if replace_all else 1)
        target.write_text(new_text, encoding="utf-8")

        import hashlib

        digest = hashlib.sha1(new_text.encode("utf-8")).hexdigest()
        return _ok(
            f"replaced {count if replace_all else 1} occurrence(s) in {path} "
            f"(sha1 {digest[:12]})"
        )
    except (SandboxViolation, FileNotFoundError) as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def delete_file(path: str, confirm: bool = False) -> dict:
    """Delete a file. Destructive — requires confirm=True.

    Args:
        path: File path relative to the workspace root.
        confirm: Must be True. Guards against accidental deletion.

    Returns:
        Confirmation message.
    """
    if not confirm:
        return _err("Refused: pass confirm=True to delete. This is destructive.")
    try:
        target = safe_path(path, must_exist=True)
        if target.is_dir():
            return _err(f"Refusing to delete a directory via delete_file: {path}")
        size = target.stat().st_size
        target.unlink()
        return _ok(f"deleted {path} ({size} bytes)")
    except (SandboxViolation, FileNotFoundError) as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


# ===========================================================================
# SEARCH
# ===========================================================================


@mcp.tool()
def search_code(query: str, path: str = ".", glob: str = "*", max_results: int = 50) -> dict:
    """Search file contents for a literal substring (case-insensitive).

    Args:
        query: Literal text to search for. Not a regex.
        path: Directory relative to the workspace root to search under.
        glob: Filename filter (e.g. '*.py', '*.md'). Default '*'.
        max_results: Cap on returned matches. Default 50.

    Returns:
        'path:line: text' for each match, up to max_results.
    """
    try:
        root = safe_path(path)
        if not root.exists():
            return _err(f"Search path not found: {path}")

        q = query.lower()
        hits: list[str] = []
        for file in root.rglob("*"):
            if not file.is_file():
                continue
            if not fnmatch.fnmatch(file.name, glob):
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            rel = file.relative_to(root).as_posix()
            for i, line in enumerate(text.splitlines(), 1):
                if q in line.lower():
                    hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        break
            if len(hits) >= max_results:
                break

        if not hits:
            return _ok(f"no matches for {query!r} in {path}")
        return _ok(f"{len(hits)} match(es) for {query!r}:\n" + "\n".join(hits))
    except SandboxViolation as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


@mcp.tool()
def repo_map(path: str = ".", max_entries: int = 200) -> dict:
    """Compact tree of the workspace — top-level files and dirs to depth 3.

    Useful at the start of a session to orient quickly without reading
    every file.

    Args:
        path: Root directory to map, relative to the workspace root.
        max_entries: Cap on lines returned.

    Returns:
        An indented tree of names with sizes.
    """
    try:
        root = safe_path(path)
        if not root.exists():
            return _err(f"Not found: {path}")

        lines: list[str] = [f"{relative_to_root(root) or '.'}/"]

        def walk(d: Path, prefix: str, depth: int) -> None:
            if depth > 3 or len(lines) >= max_entries:
                return
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
            for entry in entries:
                if len(lines) >= max_entries:
                    lines.append(f"{prefix}... (truncated)")
                    return
                if entry.is_dir():
                    lines.append(f"{prefix}{entry.name}/")
                    walk(entry, prefix + "  ", depth + 1)
                else:
                    lines.append(f"{prefix}{entry.name}  ({entry.stat().st_size}b)")

        walk(root, "  ", 0)
        return _ok("\n".join(lines))
    except SandboxViolation as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"{type(e).__name__}: {e}")


# ===========================================================================
# GIT-LITE  (shells out to git; degrades gracefully if not a repo)
# ===========================================================================


def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run a git command inside cwd. Returns (returncode, output)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (result.stdout or "") + (result.stderr or "")
        return result.returncode, out.strip()
    except FileNotFoundError:
        return 127, "git not installed on this machine"
    except subprocess.TimeoutExpired:
        return 124, "git command timed out"
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


@mcp.tool()
def git_status() -> dict:
    """Show working-tree status of the sandbox root (git status --short)."""
    root = get_sandbox_root()
    code, out = _git(["status", "--short", "--branch"], root)
    if code != 0:
        return _err(out or f"git exited {code}")
    return _ok(out or "(clean working tree)")


@mcp.tool()
def git_diff(staged: bool = False, path: str = "") -> dict:
    """Show the diff of the working tree (or staged area).

    Args:
        staged: If True, show `git diff --cached` instead of the working tree.
        path: Optional file path to limit the diff to.
    """
    root = get_sandbox_root()
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        try:
            target = safe_path(path)
            args.append("--")
            args.append(str(target))
        except SandboxViolation as e:
            return _err(str(e))
    code, out = _git(args, root)
    if code != 0:
        return _err(out or f"git exited {code}")
    if not out:
        return _ok("(no changes)")
    return _ok(out[:MAX_READ_BYTES])


@mcp.tool()
def git_log(limit: int = 10) -> dict:
    """Show the most recent commits (one line each).

    Args:
        limit: Number of commits to return. Default 10.
    """
    root = get_sandbox_root()
    code, out = _git(["log", f"-{max(1, min(limit, 100))}", "--oneline"], root)
    if code != 0:
        return _err(out or "not a git repository (run `git init` in the workspace)")
    return _ok(out)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "8000")),
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()