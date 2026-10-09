"""
sandbox.py — Path safety layer.

Every tool in this server resolves user-supplied paths through safe_path().
If a path escapes SANDBOX_ROOT, we raise SandboxViolation and the tool
returns isError=True so the agent can recover.
"""
from __future__ import annotations

import os
from pathlib import Path


class SandboxViolation(Exception):
    """Raised when a requested path escapes the sandbox root."""


def get_sandbox_root() -> Path:
    """Read SANDBOX_ROOT from env and return a resolved Path."""
    raw = os.environ.get("SANDBOX_ROOT")
    if not raw:
        raise RuntimeError(
            "SANDBOX_ROOT is not set. Copy .env.example to .env and set it."
        )
    root = Path(raw).resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    return root


def safe_path(user_path: str, *, must_exist: bool = False) -> Path:
    """
    Resolve `user_path` against SANDBOX_ROOT and reject any escape.

    Rejected cases (all raise SandboxViolation):
      - Absolute paths like /etc/passwd or C:\\Windows
      - Traversal like ../../etc/passwd
      - Symlinks whose real target is outside the root

    Args:
        user_path: Relative path supplied by the agent.
        must_exist: If True, raise FileNotFoundError if the target is missing.

    Returns:
        The resolved absolute Path inside SANDBOX_ROOT.
    """
    if not isinstance(user_path, str) or not user_path:
        raise SandboxViolation("Path must be a non-empty string.")

    root = get_sandbox_root()

    # Reject absolute paths outright. Cross-platform because we also
    # check is_relative_to below.
    candidate = Path(user_path)
    if candidate.is_absolute():
        raise SandboxViolation(f"Absolute paths are not allowed: {user_path}")

    # Resolve and verify containment.
    resolved = (root / candidate).resolve()

    # is_relative_to is the authoritative check: it follows symlinks
    # because we already called .resolve().
    if not resolved.is_relative_to(root):
        raise SandboxViolation(
            f"Path escapes sandbox root: {user_path} -> {resolved}"
        )

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Not found in sandbox: {user_path}")

    return resolved


def relative_to_root(path: Path) -> str:
    """Return a POSIX-style path relative to SANDBOX_ROOT for display."""
    return path.relative_to(get_sandbox_root()).as_posix()