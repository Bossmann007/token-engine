# Token Engine — Origin setup launcher for Windows
# Instala Origin CLI no WSL, faz login e clona o repo para C:\Users\enzo.bossmann\token-engine
#
# Uso (PowerShell como Administrador NÃO é necessário):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   iex (irm ...)   # ou salve este arquivo e rode: .\setup-origin.ps1

param(
    [string]$InstallDir = "C:\Users\enzo.bossmann\token-engine",
    [string]$OriginRepo = "enzo-bossmann/tmp-b653fd97de4e8e5c"
)

$ErrorActionPreference = "Stop"

function Test-Wsl {
    return [bool](Get-Command wsl -ErrorAction SilentlyContinue)
}

Write-Host "Token Engine — Origin setup"
Write-Host "============================"
Write-Host ""

if (-not (Test-Wsl)) {
    throw @"
WSL não encontrado. O Origin CLI no Windows roda via WSL.

Instale WSL (PowerShell como Admin):
  wsl --install

Reinicie o PC, abra "Ubuntu" e rode este script de novo.
Docs: https://cursor.com/docs/origin/cli
"@
}

$wslDistro = (wsl -l -q 2>$null | Select-Object -First 1)
if (-not $wslDistro) {
    throw "Nenhuma distro WSL configurada. Rode: wsl --install"
}

Write-Host "WSL distro: $wslDistro"
Write-Host ""

function ConvertTo-WslPath([string]$Path) {
    $normalized = $Path -replace '\\', '/'
    if ($normalized -match '^([A-Za-z]):(.*)$') {
        return "/mnt/$($Matches[1].ToLower())$($Matches[2])"
    }
    return $normalized
}

# Convert Windows path -> WSL path
$wslInstallDir = ConvertTo-WslPath $InstallDir

$scriptDir = $PSScriptRoot
$wslScript = Join-Path $scriptDir "setup-origin-wsl.sh"

if (Test-Path $wslScript) {
    $wslScriptPath = ConvertTo-WslPath $wslScript
    Write-Host "Rodando setup no WSL..."
    wsl bash "$wslScriptPath" "$wslInstallDir" "$OriginRepo"
} else {
    Write-Host "Script WSL não encontrado localmente — usando bootstrap embutido..."
    $bootstrap = @'
set -euo pipefail
INSTALL_DIR="$1"
ORIGIN_REPO="$2"
if ! command -v origin >/dev/null 2>&1; then
  curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  grep -q '\.local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
export PATH="$HOME/.local/bin:$PATH"
origin auth status 2>&1 | grep -qi valid || origin auth login
origin auth setup-git --global
mkdir -p "$(dirname "$INSTALL_DIR")"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  cd "$INSTALL_DIR" && git pull --ff-only
else
  origin repo clone "$ORIGIN_REPO" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR" && git log -1 --oneline
'@
    $bootstrap | wsl bash -s -- $wslInstallDir $OriginRepo
}

Write-Host ""
Write-Host "Instalando Python + token-engine (PowerShell)..."
$installScript = Join-Path $scriptDir "install-windows.ps1"
if (Test-Path $installScript) {
    & $installScript -InstallDir $InstallDir -SkipClone
} else {
    Write-Host "Rode depois:"
    Write-Host "  cd $InstallDir"
    Write-Host "  pip install -e `".[cursor,dev]`""
    Write-Host "  token-engine cursor-setup"
}

Write-Host ""
Write-Host "Abra no Cursor: $InstallDir"
Write-Host "Settings -> MCP -> ative token-engine e codebase-memory"
