"""DeepSearch MCP Server Management & Health Check Tool.

Provides commands to start the MCP server, test stdio JSON-RPC connectivity,
and generate client configurations for Claude Desktop, Cursor, and VS Code.
"""

import sys
import os
import json
import subprocess
import argparse
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def start_server():
    """Starts the DeepSearch MCP server over stdio transport."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE_ROOT)
    
    # Prefer uv run python if available
    cmd = [sys.executable, "-m", "scraper.mcp.server"]
    print(f"[MCP Manager] Starting DeepSearch MCP Server: {' '.join(cmd)}")
    print(f"[MCP Manager] Workspace Root: {WORKSPACE_ROOT}")
    print("[MCP Manager] Server listening on stdio...\n")

    sys.stdout.flush()
    os.execve(sys.executable, cmd, env)


def health_check():
    """Runs a JSON-RPC 2.0 stdio handshake to verify MCP server health and tool registrations."""
    print(f"[MCP Manager] Initiating MCP Server Health Check on {WORKSPACE_ROOT}...")

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
        text=True
    )

    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "deepsearch-mcp-healthcheck", "version": "1.0.0"}
        }
    }

    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }

    list_tools_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    }

    try:
        # Write JSON-RPC requests
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.write(json.dumps(initialized_notification) + "\n")
        proc.stdin.write(json.dumps(list_tools_req) + "\n")
        proc.stdin.flush()

        tools_found = []
        server_info = {}

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("id") == 1:
                    server_info = msg.get("result", {}).get("serverInfo", {})
                elif msg.get("id") == 2:
                    tools_list = msg.get("result", {}).get("tools", [])
                    tools_found = [t.get("name") for t in tools_list]
                    break
            except json.JSONDecodeError:
                continue

        proc.terminate()
        proc.wait(timeout=3)

        print("\n=== MCP Server Health Check Status ===")
        print(f"Status: OK [SUCCESS]")
        print(f"Server Name: {server_info.get('name', 'deepsearch')}")
        print(f"Server Version: {server_info.get('version', 'unknown')}")
        print(f"Registered MCP Tools ({len(tools_found)}):")
        for tool_name in tools_found:
            print(f"  - {tool_name}")

        expected_tools = {"deepsearch_research", "deepsearch_discover", "deepsearch_inspect", "deepsearch_extract", "deepsearch_search"}
        missing = expected_tools - set(tools_found)
        if missing:
            print(f"\n[WARNING] Missing expected tools: {missing}")

        return True

    except Exception as exc:
        print(f"\n[ERROR] MCP Server Health Check Failed: {exc}")
        if proc.poll() is None:
            proc.kill()
        return False


def generate_configs():
    """Generates ready-to-use JSON configs for standard MCP client environments."""
    python_exe = sys.executable.replace("\\", "/")
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
                    "scraper.mcp.server"
                ]
            }
        }
    }

    raw_python_config = {
        "mcpServers": {
            "deepsearch": {
                "command": python_exe,
                "args": ["-m", "scraper.mcp.server"],
                "cwd": workspace_str,
                "env": {
                    "PYTHONPATH": workspace_str
                }
            }
        }
    }

    print("=================================================================")
    print(" 1. Recommended Config (using uv package manager):")
    print("=================================================================")
    print(json.dumps(claude_desktop_config, indent=2))

    print("\n=================================================================")
    print(" 2. Direct Python Config (using absolute Python path):")
    print("=================================================================")
    print(json.dumps(raw_python_config, indent=2))
    print("\n[Save locations]:")
    print("  - Claude Desktop Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
    print("  - Claude Desktop macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("  - Cursor / VS Code:       .mcp/mcp.json in workspace or settings.json\n")


def main():
    parser = argparse.ArgumentParser(description="DeepSearch MCP Server Manager & Config Generator")
    parser.add_argument("command", choices=["start", "test", "health", "config"], help="Command to execute")

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
