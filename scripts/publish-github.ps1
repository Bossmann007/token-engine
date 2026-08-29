# Publish Token Engine to GitHub (run on your Windows machine after gh auth login)
# Usage:
#   cd C:\Users\enzo.bossmann\token-engine
#   .\scripts\publish-github.ps1

param(
    [string]$Repo = "enzo-bossmann/token-engine",
    [ValidateSet("public", "private")]
    [string]$Visibility = "private"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) not found. Install: winget install GitHub.cli"
}

$auth = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Log in to GitHub first:"
    Write-Host "  gh auth login"
    throw "gh is not authenticated."
}

$root = (git rev-parse --show-toplevel 2>$null)
if (-not $root) {
    throw "Run this script inside the token-engine git repository."
}

Set-Location $root

$exists = gh repo view $Repo 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating GitHub repo $Repo ($Visibility)..."
    gh repo create $Repo --$Visibility --source=. --remote=github --push
} else {
    Write-Host "Repo $Repo exists — pushing main..."
    if (-not (git remote get-url github 2>$null)) {
        git remote add github "https://github.com/$Repo.git"
    }
    git push -u github main
}

Write-Host ""
Write-Host "Published: https://github.com/$Repo"
Write-Host "Clone on this machine:"
Write-Host "  git clone https://github.com/$Repo.git C:\Users\enzo.bossmann\token-engine"
