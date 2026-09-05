#!/usr/bin/env bash
# Desinstala o wallshift: pacote (pipx), autostart, config.toml e cache de imagens.
set -euo pipefail

CONFIG_DIR="$HOME/.config/wallshift"
CONFIG_FILE="$CONFIG_DIR/config.toml"
AUTOSTART_FILE="$HOME/.config/autostart/wallshift.desktop"
DEFAULT_CACHE_DIR="$HOME/.cache/wallshift"

echo "==> Removendo o pacote wallshift do pipx..."
if command -v pipx >/dev/null 2>&1 && pipx list --short 2>/dev/null | grep -q '^wallshift '; then
    pipx uninstall wallshift
else
    echo "    wallshift não está instalado via pipx (ou pipx não encontrado), pulando."
fi

echo "==> Removendo ícone da bandeja..."
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/status/wallshift.svg"
if [ -f "$ICON_FILE" ]; then
    rm -f "$ICON_FILE"
    echo "    removido: $ICON_FILE"
else
    echo "    nenhum ícone encontrado em $ICON_FILE"
fi

echo "==> Removendo autostart..."
if [ -f "$AUTOSTART_FILE" ]; then
    rm -f "$AUTOSTART_FILE"
    echo "    removido: $AUTOSTART_FILE"
else
    echo "    nenhum autostart encontrado em $AUTOSTART_FILE"
fi

# O cache_dir pode ter sido customizado pelo usuário no config.toml,
# então lemos o valor real antes de decidir o que apagar.
CACHE_DIR="$DEFAULT_CACHE_DIR"
if [ -f "$CONFIG_FILE" ]; then
    configured=$(grep -E '^\s*cache_dir\s*=' "$CONFIG_FILE" | sed -E 's/^[^=]*=\s*"(.*)"\s*$/\1/') || true
    if [ -n "${configured:-}" ]; then
        CACHE_DIR="${configured/#\~/$HOME}"
    fi
fi

echo "==> Removendo cache de imagens em $CACHE_DIR..."
if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR"
    echo "    removido: $CACHE_DIR"
else
    echo "    nenhum cache encontrado em $CACHE_DIR"
fi

echo "==> Removendo configuração em $CONFIG_DIR..."
if [ -d "$CONFIG_DIR" ]; then
    rm -rf "$CONFIG_DIR"
    echo "    removido: $CONFIG_DIR"
else
    echo "    nenhuma configuração encontrada em $CONFIG_DIR"
fi

echo
echo "==> wallshift desinstalado."
echo "    Dependências de sistema (pipx, qdbus-qt6) NÃO foram removidas de propósito:"
echo "    elas podem ser usadas por outras aplicações ou fazem parte do próprio KDE Plasma."
echo "    Pra removê-las manualmente, se quiser: sudo apt remove pipx qdbus-qt6"
