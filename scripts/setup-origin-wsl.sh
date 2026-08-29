#!/usr/bin/env bash
# Origin setup for Windows users (run inside WSL).
# Usage:
#   bash scripts/setup-origin-wsl.sh
#   bash scripts/setup-origin-wsl.sh /mnt/c/Users/enzo.bossmann/token-engine enzo-bossmann/tmp-b653fd97de4e8e5c

set -euo pipefail

INSTALL_DIR="${1:-/mnt/c/Users/enzo.bossmann/token-engine}"
ORIGIN_REPO="${2:-enzo-bossmann/tmp-b653fd97de4e8e5c}"

echo "============================================"
echo " Token Engine — Origin setup (WSL)"
echo "============================================"
echo "Install dir : $INSTALL_DIR"
echo "Origin repo : $ORIGIN_REPO"
echo ""

ensure_origin_cli() {
  if command -v origin >/dev/null 2>&1; then
    return
  fi
  echo "Installing Origin CLI..."
  curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  if ! grep -q '\.local/bin' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  fi
}

ensure_origin_cli
export PATH="$HOME/.local/bin:$PATH"

if ! origin --version >/dev/null 2>&1; then
  echo "origin CLI not found after install. Open a new WSL terminal and retry."
  exit 1
fi

echo "Origin CLI: $(origin --version)"
echo ""

if ! origin auth status 2>&1 | grep -qi 'valid'; then
  echo ">>> Login necessário <<<"
  echo "Vai abrir o browser (ou mostrar um link). Use a conta Cursor: enzombromanus@gmail.com"
  echo ""
  origin auth login
else
  echo "Já autenticado:"
  origin auth status
fi

echo ""
echo "Configurando git credential helper para origin.cursor.com..."
origin auth setup-git --global

mkdir -p "$(dirname "$INSTALL_DIR")"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo "Repo já existe — atualizando..."
  cd "$INSTALL_DIR"
  git pull --ff-only origin main || git pull --ff-only
else
  echo "Clonando via Origin CLI..."
  origin repo clone "$ORIGIN_REPO" "$INSTALL_DIR"
fi

echo ""
echo "Verificando repositório..."
cd "$INSTALL_DIR"
git remote -v
git log -1 --oneline

echo ""
echo "============================================"
echo " Origin OK"
echo "============================================"
echo "Pasta Windows: C:\\Users\\enzo.bossmann\\token-engine"
echo ""
echo "Próximo passo (PowerShell):"
echo "  cd C:\\Users\\enzo.bossmann\\token-engine"
echo "  .\\scripts\\install-windows.ps1 -SkipClone"
