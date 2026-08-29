# Token Engine — Windows installer
# Usage (PowerShell):
#   iwr -useb https://raw.githubusercontent.com/enzo-bossmann/token-engine/main/scripts/install-windows.ps1 | iex
# Or after clone:
#   .\scripts\install-windows.ps1

param(
    [string]$InstallDir = "C:\Users\enzo.bossmann\token-engine",
    [string]$RepoUrl = "https://github.com/enzo-bossmann/token-engine.git",
    [switch]$SkipClone
)

$ErrorActionPreference = "Stop"

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-Python {
    if (Test-Command py) {
        $version = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ([version]$version -lt [version]"3.11") {
            throw "Python 3.11+ required. Found $version via 'py -3'."
        }
        return @{ Cmd = "py"; Args = @("-3") }
    }
    if (Test-Command python) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ([version]$version -lt [version]"3.11") {
            throw "Python 3.11+ required. Found $version."
        }
        return @{ Cmd = "python"; Args = @() }
    }
    throw "Python 3.11+ not found. Install from https://www.python.org/downloads/ and enable 'Add to PATH'."
}

function Invoke-GitClone($url, $target) {
    Write-Host "Cloning $url -> $target"
    git clone $url $target
}

Write-Host "Token Engine — Windows install"
Write-Host "=============================="
Write-Host "Target: $InstallDir"

if (-not (Test-Command git)) {
    throw "Git not found. Install Git for Windows: https://git-scm.com/download/win"
}

$python = Ensure-Python
Write-Host "Python: $($python.Cmd) $($python.Args -join ' ')"

if (Test-Path $InstallDir) {
    if (Test-Path (Join-Path $InstallDir ".git")) {
        Write-Host "Repo exists — pulling latest..."
        Push-Location $InstallDir
        git pull --ff-only
        Pop-Location
    } else {
        throw "$InstallDir exists but is not a git repo. Remove it or pick another -InstallDir."
    }
} elseif ($SkipClone) {
    throw "-SkipClone set but $InstallDir does not exist. Clone the repo first."
} else {
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir -Parent) | Out-Null
    try {
        Invoke-GitClone $RepoUrl $InstallDir
    } catch {
        throw @"
GitHub clone failed: $($_.Exception.Message)

Origin (origin.cursor.com) requires login — git clone in PowerShell will prompt forever.

Fix (pick one):
  A) gh auth login  then clone from GitHub (see README Install on Windows)
  B) WSL: origin auth login  then  origin repo clone enzo-bossmann/tmp-b653fd97de4e8e5c /mnt/c/Users/enzo.bossmann/token-engine
  C) Cursor UI: Create repo + sync to GitHub, then Clone from GitHub
"@
    }
}

$venv = Join-Path $InstallDir ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "Creating virtualenv..."
    & $python.Cmd @($python.Args) -m venv $venv
}

$pip = Join-Path $venv "Scripts\pip.exe"
$pyvenv = Join-Path $venv "Scripts\python.exe"
$tokenEngine = Join-Path $venv "Scripts\token-engine.exe"

Write-Host "Installing token-engine[cursor,dev]..."
& $pip install -e "$InstallDir[cursor,dev]"

Write-Host "Running cursor-setup..."
& $tokenEngine cursor-setup

Write-Host ""
Write-Host "Done."
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open Cursor -> File -> Open Folder -> $InstallDir"
Write-Host "  2. Settings -> MCP -> enable token-engine and codebase-memory"
Write-Host "  3. Reload window (Ctrl+Shift+P -> Developer: Reload Window)"
Write-Host ""
Write-Host "Activate venv in terminal:"
Write-Host "  $($venv)\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Quick test:"
Write-Host "  token-engine benchmark"
