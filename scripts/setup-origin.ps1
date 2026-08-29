# Token Engine — Origin setup for Windows (native, no WSL)
#
# Usage (PowerShell):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   irm https://downloads.cursor.com/origin/install.ps1 | iex   # if origin missing
#   .\scripts\setup-origin.ps1

param(
    [string]$InstallDir = "C:\Users\enzo.bossmann\token-engine",
    [string]$OriginRepo = "enzo-bossmann/tmp-b653fd97de4e8e5c",
    [switch]$UseWsl
)

$ErrorActionPreference = "Stop"

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-OriginCli {
    if (Test-Command origin) {
        Write-Host "Origin CLI: $(origin --version)"
        return
    }

    Write-Host "Instalando Origin CLI (Windows nativo)..."
    irm https://downloads.cursor.com/origin/install.ps1 | iex

    $binDir = Join-Path $env:LOCALAPPDATA "cursor\bin"
    if (Test-Path $binDir) {
        $env:Path = "$binDir;$env:Path"
    }

    if (-not (Test-Command origin)) {
        throw @"
origin ainda nao esta no PATH. Feche e abra o PowerShell, ou rode:
  `$env:Path = `"$binDir;`$env:Path`"
  origin --version
"@
    }

    Write-Host "Origin CLI: $(origin --version)"
}

function Ensure-OriginAuth {
    $status = origin auth status 2>&1 | Out-String
    if ($status -match 'valid') {
        Write-Host "Ja autenticado no Origin."
        origin auth status
        return
    }

    Write-Host ""
    Write-Host ">>> Login Origin <<<"
    Write-Host "Vai abrir o browser. Use: enzombromanus@gmail.com"
    Write-Host ""
    origin auth login
    origin auth status
}

function ConvertTo-WslPath([string]$Path) {
    $normalized = $Path -replace '\\', '/'
    if ($normalized -match '^([A-Za-z]):(.*)$') {
        return "/mnt/$($Matches[1].ToLower())$($Matches[2])"
    }
    return $normalized
}

function Invoke-WslSetup {
    if (-not (Test-Command wsl)) {
        throw "WSL nao encontrado. Use o setup nativo (sem -UseWsl) ou instale WSL."
    }
    $wslScript = Join-Path $PSScriptRoot "setup-origin-wsl.sh"
    $wslInstallDir = ConvertTo-WslPath $InstallDir
    if (Test-Path $wslScript) {
        $wslScriptPath = ConvertTo-WslPath $wslScript
        wsl bash $wslScriptPath $wslInstallDir $OriginRepo
    } else {
        throw "setup-origin-wsl.sh nao encontrado."
    }
}

Write-Host "Token Engine — Origin setup (Windows)"
Write-Host "====================================="
Write-Host "Destino: $InstallDir"
Write-Host ""

if ($UseWsl) {
    Invoke-WslSetup
} else {
    if (-not (Test-Command git)) {
        throw "Git nao encontrado. Instale: winget install Git.Git"
    }

    Ensure-OriginCli
    Ensure-OriginAuth

    Write-Host ""
    Write-Host "Configurando git credential helper..."
    origin auth setup-git --global

    if (Test-Path (Join-Path $InstallDir ".git")) {
        Write-Host "Repo ja existe — atualizando..."
        Push-Location $InstallDir
        git pull --ff-only
        Pop-Location
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir -Parent) | Out-Null
        Write-Host "Clonando $OriginRepo ..."
        origin repo clone $OriginRepo $InstallDir
    }

    Push-Location $InstallDir
    git log -1 --oneline
    Pop-Location
}

Write-Host ""
$installScript = Join-Path $PSScriptRoot "install-windows.ps1"
if (Test-Path $installScript) {
    Write-Host "Instalando Python + token-engine..."
    & $installScript -InstallDir $InstallDir -SkipClone
} else {
    Write-Host "Depois rode:"
    Write-Host "  cd $InstallDir"
    Write-Host "  pip install -e `".[cursor,dev]`""
    Write-Host "  token-engine cursor-setup"
}

Write-Host ""
Write-Host "Abra no Cursor: $InstallDir"
