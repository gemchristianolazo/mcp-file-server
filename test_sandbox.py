"""
test_sandbox.py — Path traversal tests.

Run with:  uv run python test_sandbox.py

If every line prints PASS, your sandbox is enforced.
"""
import os
import tempfile
from pathlib import Path

# Point sandbox at a temp dir before importing sandbox module
_TMP = Path(tempfile.mkdtemp(prefix="mcp-sandbox-test-"))
os.environ["SANDBOX_ROOT"] = str(_TMP)

from sandbox import SandboxViolation, get_sandbox_root, safe_path  # noqa: E402


def expect_blocked(label: str, path: str) -> None:
    try:
        safe_path(path)
    except SandboxViolation:
        print(f"PASS  blocked: {label}")
        return
    except FileNotFoundError:
        print(f"PASS  blocked (not found): {label}")
        return
    print(f"FAIL  ALLOWED (should be blocked): {label}")


def expect_allowed(label: str, path: str) -> None:
    try:
        result = safe_path(path)
        print(f"PASS  allowed: {label}  ->  {result.name}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  blocked (should be allowed): {label}  ({e})")


def main() -> None:
    root = get_sandbox_root()
    print(f"Sandbox root: {root}\n")

    # --- should be blocked ---
    expect_blocked("unix absolute", "/etc/passwd")
    expect_blocked("windows absolute", r"C:\Windows\System32\config\SAM")
    expect_blocked("single traversal", "../secret.txt")
    expect_blocked("deep traversal", "../../../../etc/passwd")
    expect_blocked("sneaky traversal", "foo/../../etc/passwd")
    expect_blocked("empty string", "")

    # --- should be allowed ---
    expect_allowed("simple file", "notes.txt")
    expect_allowed("nested file", "projects/demo/README.md")
    expect_allowed("dot in name", "file.with.dots.txt")

    # --- symlink escape test ---
    print()
    outside = Path(tempfile.mkdtemp(prefix="mcp-outside-"))
    secret = outside / "secret.txt"
    secret.write_text("TOP SECRET")

    link = root / "escape_link"
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as e:
        print(f"SKIP  symlink test (OS refused symlink creation: {e})")
    else:
        expect_blocked("symlink to outside root", "escape_link/secret.txt")

    print("\nDone.")


if __name__ == "__main__":
    main()