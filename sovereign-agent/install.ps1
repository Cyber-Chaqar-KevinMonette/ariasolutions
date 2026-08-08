# install.ps1 — Aria sovereign-agent installer for Windows (PowerShell 5.1+)
#
# Usage (from PowerShell):
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#   .\install.ps1
#
# What this does:
#   1. Checks Python 3.11+ is available
#   2. Creates a virtual environment at %LOCALAPPDATA%\sovereign-agent\venv
#   3. Installs sovereign-agent and all deps
#   4. Writes launcher scripts to %LOCALAPPDATA%\sovereign-agent\bin\
#   5. Offers to add the bin dir to PATH
#
# After install:
#   sov --help
#   sov-mcp             <- plug Aria into Claude Desktop on Windows

$ErrorActionPreference = "Stop"

$AppName = "sovereign-agent"
$LocalData = "$env:LOCALAPPDATA\$AppName"
$VenvDir = "$LocalData\venv"
$BinDir = "$LocalData\bin"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== Aria — sovereign-agent Windows installer ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Python check ───────────────────────────────────────────────────

$PythonExe = $null
foreach ($candidate in @("python3", "python", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $PythonExe = $candidate
                Write-Host "  OK  Python $major.$minor found ($candidate)" -ForegroundColor Green
                break
            }
        }
    } catch { }
}

if (-not $PythonExe) {
    Write-Host "  ERR  Python 3.11+ not found." -ForegroundColor Red
    Write-Host "       Install from: https://www.python.org/downloads/"
    Write-Host "       Or via winget: winget install Python.Python.3.12"
    exit 1
}

# ── Step 2: Create venv ────────────────────────────────────────────────────

New-Item -ItemType Directory -Force -Path $LocalData | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

if (-not (Test-Path "$VenvDir\Scripts\python.exe")) {
    Write-Host "  Creating venv at $VenvDir ..."
    & $PythonExe -m venv $VenvDir
    Write-Host "  OK  venv created" -ForegroundColor Green
} else {
    Write-Host "  OK  venv exists at $VenvDir" -ForegroundColor Green
}

$PythonVenv = "$VenvDir\Scripts\python.exe"
$PipVenv = "$VenvDir\Scripts\pip.exe"

# ── Step 3: Upgrade pip + install ─────────────────────────────────────────

Write-Host "  Upgrading pip..."
& $PipVenv install --upgrade pip -q

Write-Host "  Installing sovereign-agent (this may take a minute)..."
& $PipVenv install -e "$ScriptDir" -q

Write-Host "  OK  sovereign-agent installed" -ForegroundColor Green

# ── Step 4: Launcher scripts ───────────────────────────────────────────────

foreach ($cmd in @("sov", "sovereign", "sov-chat", "sov-mcp")) {
    $wrapper = @"
@echo off
"$VenvDir\Scripts\$cmd.exe" %*
"@
    $wrapper | Out-File -FilePath "$BinDir\$cmd.cmd" -Encoding ASCII
}

Write-Host "  OK  Launchers written to $BinDir" -ForegroundColor Green

# ── Step 5: PATH offer ─────────────────────────────────────────────────────

$CurrentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($CurrentPath -notlike "*$BinDir*") {
    Write-Host ""
    Write-Host "  Add Aria to your PATH? (Recommended)" -ForegroundColor Yellow
    $answer = Read-Host "  [Y/n]"
    if ($answer -ne "n" -and $answer -ne "N") {
        [Environment]::SetEnvironmentVariable(
            "PATH",
            "$BinDir;$CurrentPath",
            "User"
        )
        Write-Host "  OK  PATH updated — restart PowerShell to use sov/sov-mcp" -ForegroundColor Green
    }
} else {
    Write-Host "  OK  $BinDir already in PATH" -ForegroundColor Green
}

# ── Step 6: Summary ───────────────────────────────────────────────────────

Write-Host ""
Write-Host "=== Install complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Commands:  sov, sov-chat, sov-mcp"
Write-Host "  Version:   $(& $PythonVenv -m sovereign_agent.cli --version 2>&1)"
Write-Host ""
Write-Host "  Plug into Claude Desktop (plug & play):"
Write-Host '  Add to %APPDATA%\Claude\claude_desktop_config.json:' -ForegroundColor Yellow
Write-Host ""
Write-Host '  {' -ForegroundColor White
Write-Host '    "mcpServers": {' -ForegroundColor White
Write-Host '      "aria": {' -ForegroundColor White
Write-Host "        `"command`": `"$BinDir\sov-mcp.cmd`"," -ForegroundColor White
Write-Host '        "args": []' -ForegroundColor White
Write-Host '      }' -ForegroundColor White
Write-Host '    }' -ForegroundColor White
Write-Host '  }' -ForegroundColor White
Write-Host ""
Write-Host "  Then restart Claude Desktop — Aria's tools will appear in Claude." -ForegroundColor Green
Write-Host ""
