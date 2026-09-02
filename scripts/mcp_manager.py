"""DeepSearch MCP Server Management & Health Check Tool (§DS-21).

Provides commands to start the MCP server, test stdio JSON-RPC connectivity,
and generate client configurations for Claude Desktop, Cursor, and VS Code.
All operational and diagnostic logs are routed strictly to stderr.
"""

import sys
import os
import json
import time
import subprocess
import argparse
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def log_diag(msg: str):
    """Outputs diagnostic status messages strictly to stderr to preserve stdout stream isolation."""
    print(msg, file=sys.stderr, flush=True)


def start_server():
    """Starts the DeepSearch MCP server over stdio transport."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE_ROOT)

    cmd = [sys.executable, "-m", "scraper.mcp.server"]
    log_diag(f"[MCP Manager] Starting DeepSearch MCP Server: {' '.join(cmd)}")
    log_diag(f"[MCP Manager] Workspace Root: {WORKSPACE_ROOT}")
    log_diag("[MCP Manager] Server listening on stdio...\n")

    os.execve(sys.executable, cmd, env)


def health_check(timeout_seconds: float = 10.0) -> bool:
    """Runs a JSON-RPC 2.0 stdio handshake to verify MCP server health and tool registrations."""
    log_diag(f"[MCP Manager] Initiating MCP Server Health Check on {WORKSPACE_ROOT}...")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE_ROOT)
    cmd = [sys.executable, "-m", "scraper.mcp.server"]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(WORKSPACE_ROOT),
        env=env,
        text=True,
    )

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "deepsearch-mcp-healthcheck", "version": "1.0.0"},
        },
    }

    initialized_notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    list_tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

    try:
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("Failed to open subprocess pipes for MCP health check.")

        # Send initialize and tools/list requests
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.write(json.dumps(initialized_notification) + "\n")
        proc.stdin.write(json.dumps(list_tools_req) + "\n")
        proc.stdin.flush()

        tools_found = []
        server_info = {}
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue

            line_str = line.strip()
            if not line_str:
                continue

            try:
                msg = json.loads(line_str)
                if msg.get("id") == 1:
                    server_info = msg.get("result", {}).get("serverInfo", {})
                elif msg.get("id") == 2:
                    tools_list = msg.get("result", {}).get("tools", [])
                    tools_found = [t.get("name") for t in tools_list]
                    break
            except json.JSONDecodeError:
                continue

        if not tools_found and proc.poll() is not None:
            stderr_err = proc.stderr.read() if proc.stderr else ""
            log_diag(
                f"[ERROR] MCP Server process exited early with code {proc.returncode}: {stderr_err}"
            )
            return False

        if not tools_found:
            log_diag(
                f"[ERROR] MCP Server Health Check timed out after {timeout_seconds}s without receiving tools/list."
            )
            return False

        log_diag("\n=== MCP Server Health Check Status ===")
        log_diag("Status: OK [SUCCESS]")
        log_diag(f"Server Name: {server_info.get('name', 'deepsearch')}")
        log_diag(f"Server Version: {server_info.get('version', 'unknown')}")
        log_diag(f"Registered MCP Tools ({len(tools_found)}):")
        for tool_name in tools_found:
            log_diag(f"  - {tool_name}")

        expected_tools = {
            "deepsearch_research",
            "deepsearch_discover",
            "deepsearch_inspect",
            "deepsearch_extract",
            "deepsearch_search",
            "deepsearch_crawl",
            "deepsearch_capabilities",
        }
        missing = expected_tools - set(tools_found)
        if missing:
            log_diag(f"\n[WARNING] Missing expected tools: {missing}")

        return True

    except Exception as exc:
        log_diag(f"\n[ERROR] MCP Server Health Check Failed: {exc}")
        return False
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()


def generate_configs():
    """Generates ready-to-use JSON configs for standard MCP client environments."""
    workspace_str = str(WORKSPACE_ROOT).replace("\\", "/")

    claude_desktop_config = {
        "mcpServers": {
            "deepsearch": {
                "command": "uv",
                "args": [
                    "--directory",
                    workspace_str,
                    "run",
                    "python",
                    "-m",
                    "scraper.mcp.server",
                ],
            }
        }
    }

    raw_python_config = {
        "mcpServers": {
            "deepsearch": {
                "command": "uv",
                "args": ["run", "python", "-m", "scraper.mcp.server"],
                "cwd": workspace_str,
                "env": {"PYTHONPATH": workspace_str},
            }
        }
    }

    log_diag("=================================================================")
    log_diag(" 1. Recommended Config (using uv package manager):")
    log_diag("=================================================================")
    print(json.dumps(claude_desktop_config, indent=2))

    log_diag("\n=================================================================")
    log_diag(" 2. Direct Python Config (using workspace relative environment):")
    log_diag("=================================================================")
    print(json.dumps(raw_python_config, indent=2))
    log_diag("\n[Save locations]:")
    log_diag(
        "  - Claude Desktop Windows: %APPDATA%\\Claude\\claude_desktop_config.json"
    )
    log_diag(
        "  - Claude Desktop macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json"
    )
    log_diag(
        "  - Cursor / VS Code:       .mcp/mcp.json in workspace or settings.json\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="DeepSearch MCP Server Manager & Config Generator"
    )
    parser.add_argument(
        "command",
        choices=["start", "test", "health", "config"],
        help="Command to execute",
    )

    args = parser.parse_args()

    if args.command == "start":
        start_server()
    elif args.command in ("test", "health"):
        success = health_check()
        sys.exit(0 if success else 1)
    elif args.command == "config":
        generate_configs()


if __name__ == "__main__":
    main()
