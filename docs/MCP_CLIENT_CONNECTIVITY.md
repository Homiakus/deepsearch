# DeepSearch MCP Client Connectivity Guide

Comprehensive reference for connecting external applications (**Python**, **Go**, **Claude Desktop**, **Cursor**, **VS Code**) to the DeepSearch Model Context Protocol (MCP) server.

---

## 1. Overview & Protocol Mechanics

The DeepSearch MCP Server runs on the Model Context Protocol over **`stdio` (Standard Input / Output)** transport using JSON-RPC 2.0.

- **Executable**: `python -m scraper.mcp.server` or `uv run python -m scraper.mcp.server`
- **Working Directory**: Directory containing the `deepsearch` workspace (`d:\Programms\202-Programming-Projects\deepsearch`)
- **Protocol Version**: `2024-11-05`
- **Transport**: `stdio`

---

## 2. Standard MCP Configs for LLM Assistants

### 2.1 Claude Desktop Configuration

Save to:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "uv",
      "args": [
        "--directory",
        "D:/Programms/202-Programming-Projects/deepsearch",
        "run",
        "python",
        "-m",
        "scraper.mcp.server"
      ]
    }
  }
}
```

### 2.2 Cursor / Antigravity / VS Code Configuration

Save to workspace file `.mcp/mcp.json` or global settings `mcpServers`:

```json
{
  "mcpServers": {
    "deepsearch": {
      "command": "C:/Users/KDFX Modes/AppData/Local/Programs/Python/Python313/python.exe",
      "args": [
        "-m",
        "scraper.mcp.server"
      ],
      "cwd": "D:/Programms/202-Programming-Projects/deepsearch",
      "env": {
        "PYTHONPATH": "D:/Programms/202-Programming-Projects/deepsearch"
      }
    }
  }
}
```

---

## 3. Python Integration Guide

Use the official `mcp` SDK to connect your Python application or microservice to DeepSearch.

### 3.1 Installation

```bash
pip install mcp httpx pydantic
```

### 3.2 Python Client Code Example

```python
import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Path to deepsearch workspace root
WORKSPACE_ROOT = Path("D:/Programms/202-Programming-Projects/deepsearch").resolve()

async def run_deepsearch_mcp_client():
    # Configure stdio server process parameters
    server_params = StdioServerParameters(
        command="uv",
        args=[
            "--directory",
            str(WORKSPACE_ROOT),
            "run",
            "python",
            "-m",
            "scraper.mcp.server"
        ],
        env={**os.environ, "PYTHONPATH": str(WORKSPACE_ROOT)}
    )

    print("[Python Client] Launching DeepSearch MCP Server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. Initialize MCP handshake
            await session.initialize()
            print("[Python Client] MCP Session initialized successfully.")

            # 2. List available MCP tools
            tools_response = await session.list_tools()
            print(f"[Python Client] Discovered {len(tools_response.tools)} MCP tools:")
            for tool in tools_response.tools:
                print(f"  - {tool.name}: {tool.description.splitlines()[0]}")

            # 3. Call `deepsearch_discover` to get seed URLs
            print("\n[Python Client] Calling 'deepsearch_discover'...")
            discover_res = await session.call_tool(
                "deepsearch_discover",
                arguments={
                    "query": "quantum computing algorithms",
                    "category": "science"
                }
            )
            seeds_data = json.loads(discover_res.content[0].text)
            print("Found Seed URLs:", seeds_data.get("seeds", [])[:3])

            # 4. Call `deepsearch_research` with media selection (5 to 25 images)
            print("\n[Python Client] Executing 'deepsearch_research' pipeline...")
            research_res = await session.call_tool(
                "deepsearch_research",
                arguments={
                    "query": "quantum computing algorithms",
                    "max_pages": 3,
                    "mode": "balanced",
                    "output_archive": "deepsearch_quantum_results.zip"
                }
            )
            result_data = json.loads(research_res.content[0].text)
            print("Research Status:", result_data.get("status"))
            print("Total Pages Processed:", result_data.get("total_pages_processed"))
            print("Archive Location:", result_data.get("archive_path"))
            print("Manifest Summary:", result_data.get("manifest", {}).get("summary"))

if __name__ == "__main__":
    asyncio.run(run_deepsearch_mcp_client())
```

---

## 4. Go Integration Guide

Connect a **Go application** to the DeepSearch MCP server via `stdio` JSON-RPC 2.0 subprocess transport.

### 4.1 Go Client Code Example (Native `os/exec` + JSON-RPC)

Save to `main.go`:

```go
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
)

// JSON-RPC 2.0 Data Structures
type JSONRPCRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      int         `json:"id,omitempty"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params,omitempty"`
}

type JSONRPCResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int             `json:"id"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   interface{}     `json:"error,omitempty"`
}

type CallToolParams struct {
	Name      string                 `json:"name"`
	Arguments map[string]interface{} `json:"arguments"`
}

func main() {
	workspaceRoot := "D:/Programms/202-Programming-Projects/deepsearch"

	// Launch DeepSearch MCP Server as subprocess
	cmd := exec.Command("uv", "--directory", workspaceRoot, "run", "python", "-m", "scraper.mcp.server")
	cmd.Env = append(os.environ(), "PYTHONPATH="+workspaceRoot)

	stdin, err := cmd.StdinPipe()
	if err != nil {
		log.Fatalf("Failed to create stdin pipe: %v", err)
	}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		log.Fatalf("Failed to create stdout pipe: %v", err)
	}

	if err := cmd.Start(); err != nil {
		log.Fatalf("Failed to start DeepSearch MCP server: %v", err)
	}
	defer cmd.Process.Kill()

	reader := bufio.NewReader(stdout)

	// Helper function to send request and read response line
	sendRequest := func(req JSONRPCRequest) (*JSONRPCResponse, error) {
		data, err := json.Marshal(req)
		if err != nil {
			return nil, err
		}
		_, err = stdin.Write(append(data, '\n'))
		if err != nil {
			return nil, err
		}

		line, err := reader.ReadBytes('\n')
		if err != nil && err != io.EOF {
			return nil, err
		}

		var resp JSONRPCResponse
		if err := json.Unmarshal(line, &resp); err != nil {
			return nil, err
		}
		return &resp, nil
	}

	// 1. Initialize MCP Handshake
	initReq := JSONRPCRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  "initialize",
		Params: map[string]interface{}{
			"protocolVersion": "2024-11-05",
			"capabilities":    map[string]interface{}{},
			"clientInfo": map[string]string{
				"name":    "go-deepsearch-client",
				"version": "1.0.0",
			},
		},
	}

	initResp, err := sendRequest(initReq)
	if err != nil {
		log.Fatalf("Initialize failed: %v", err)
	}
	fmt.Printf("[Go Client] Handshake Success. Server Info: %s\n", string(initResp.Result))

	// Send initialized notification
	initializedNotif := JSONRPCRequest{
		JSONRPC: "2.0",
		Method:  "notifications/initialized",
	}
	notifData, _ := json.Marshal(initializedNotif)
	stdin.Write(append(notifData, '\n'))

	// 2. Call `deepsearch_inspect` Tool
	inspectReq := JSONRPCRequest{
		JSONRPC: "2.0",
		ID:      2,
		Method:  "tools/call",
		Params: CallToolParams{
			Name: "deepsearch_inspect",
			Arguments: map[string]interface{}{
				"url": "https://en.wikipedia.org/wiki/Quantum_computing",
			},
		},
	}

	inspectResp, err := sendRequest(inspectReq)
	if err != nil {
		log.Fatalf("Tool call failed: %v", err)
	}
	fmt.Printf("\n[Go Client] 'deepsearch_inspect' Result:\n%s\n", string(inspectResp.Result))
}
```

---

## 5. Summary of Registered MCP Tools & Parameters

| MCP Tool Name | Description | Arguments Schema |
|---|---|---|
| **`deepsearch_research`** | Full research pipeline (discovery, crawl, media archive 5-25 images, zip output) | `query` (str, req), `domain` (str), `max_pages` (int), `mode` (str), `min_media` (int), `max_media` (int), `output_archive` (str) |
| **`deepsearch_discover`** | Multi-source seed discovery (ArXiv, Wikipedia, Anna's Archive) | `query` (str, req), `domain` (str), `category` (str) |
| **`deepsearch_inspect`** | Diagnostic URL inspection (static score, JS dependency, strategy) | `url` (str, req) |
| **`deepsearch_extract`** | HTML extraction to Clean Markdown, tables, and structured data | `url` (str, req) |
| **`deepsearch_search`** | Hybrid text and visual multivector search over indexed database | `query` (str, req), `limit` (int) |
