# DeepSearch MCP Server Helper Script for PowerShell
param (
    [string]$Action = "start" # start | test | config
)

$WorkspaceRoot = $PSScriptRoot
$env:PYTHONPATH = $WorkspaceRoot

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " DeepSearch MCP Server Manager ($Action) " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

if ($Action -eq "start") {
    Write-Host "Starting MCP Server over stdio..." -ForegroundColor Yellow
    uv run python -m scraper.mcp.server
}
elseif ($Action -eq "test" -or $Action -eq "health") {
    Write-Host "Running stdio JSON-RPC health check..." -ForegroundColor Yellow
    & "C:\Users\KDFX Modes\AppData\Local\Programs\Python\Python313\python.exe" "$PSScriptRoot\scripts\mcp_manager.py" test
}
elseif ($Action -eq "config") {
    & "C:\Users\KDFX Modes\AppData\Local\Programs\Python\Python313\python.exe" "$PSScriptRoot\scripts\mcp_manager.py" config
}
else {
    Write-Host "Usage: .\run_mcp.ps1 [start | test | config]" -ForegroundColor Red
}
