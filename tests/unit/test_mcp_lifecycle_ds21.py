"""Unit tests for MCP Server Lifecycle, Configuration, and Protocol Health Check (§DS-21)."""

import json
from scripts.mcp_manager import health_check, generate_configs, WORKSPACE_ROOT


def test_mcp_config_json_is_minimal_and_valid():
    """Verify .mcp/config.json is strictly confined to DeepSearch server with no install commands or fake endpoints."""
    config_path = WORKSPACE_ROOT / ".mcp" / "config.json"
    assert config_path.exists(), ".mcp/config.json must exist"

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "mcpServers" in data
    servers = data["mcpServers"]
    assert "deepsearch" in servers
    assert len(servers) == 1, (
        "Only deepsearch server should be present in canonical .mcp/config.json"
    )

    srv = servers["deepsearch"]
    assert srv["command"] in ("uv", "python")
    # Verify no pip/npm install commands
    assert "install" not in srv.get("args", [])

    # Verify no fake endpoints dictionary in config
    assert "endpoints" not in data


def test_mcp_health_check_handshake():
    """Verify that mcp_manager.health_check successfully handshakes over stdio JSON-RPC."""
    success = health_check(timeout_seconds=15.0)
    assert success is True, (
        "MCP health check handshake must succeed against local server"
    )


def test_mcp_generate_configs_outputs_clean_json(capsys):
    """Verify generate_configs prints valid JSON structures to stdout."""
    generate_configs()
    captured = capsys.readouterr()
    assert "mcpServers" in captured.out
    assert "deepsearch" in captured.out
    assert "KDFX Modes" not in captured.out  # No hardcoded user directories
