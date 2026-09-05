#!/usr/bin/env bash
# Instala o wallshift: dependências de sistema, o pacote via pipx,
# o config.toml e o autostart do KDE Plasma.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/wallshift"
CONFIG_FILE="$CONFIG_DIR/config.toml"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/wallshift.desktop"

echo "==> Verificando dependências de sistema..."

apt_packages=()

if ! command -v pipx >/dev/null 2>&1; then
    apt_packages+=("pipx")
fi

if ! command -v qdbus6 >/dev/null 2>&1 && ! command -v qdbus >/dev/null 2>&1; then
    apt_packages+=("qdbus-qt6")
fi

# Necessários pro ícone da bandeja (wallshift-tray): bindings Python do GTK
# e o AppIndicator3 usado pra registrar o ícone via StatusNotifierItem.
if ! python3 -c "import gi" >/dev/null 2>&1; then
    apt_packages+=("python3-gi")
fi
if ! python3 -c "import gi; gi.require_version('AyatanaAppIndicator3', '0.1'); from gi.repository import AyatanaAppIndicator3" >/dev/null 2>&1; then
    apt_packages+=("gir1.2-ayatanaappindicator3-0.1")
fi

if [ "${#apt_packages[@]}" -gt 0 ]; then
    echo "==> Instalando via apt: ${apt_packages[*]} (vai pedir sua senha do sudo)"
    sudo apt-get update
    sudo apt-get install -y "${apt_packages[@]}"
else
    echo "    todas as dependências de sistema já estão presentes."
fi

echo "==> Instalando o pacote wallshift com pipx..."
# --system-site-packages: o wallshift-tray precisa do 'gi' (PyGObject) do
# sistema, que não é instalável via pip sem headers de desenvolvimento do
# GTK. Sem essa flag, o venv isolado do pipx não enxergaria o pacote
# python3-gi instalado acima.
pipx install --force --system-site-packages "$SCRIPT_DIR"
pipx ensurepath || true

echo "==> Instalando o ícone da bandeja..."
# set_icon_theme_path (dentro do tray.py) sozinho não é confiável -- na
# prática o Plasma só resolve o ícone pelo nome se ele estiver de fato no
# local padrão do XDG (~/.local/share/icons/hicolor/...), então copiamos
# pra lá também. gtk-update-icon-cache é best-effort (nem todo tema exige).
ICON_DEST_DIR="$HOME/.local/share/icons/hicolor/scalable/status"
mkdir -p "$ICON_DEST_DIR"
cp "$SCRIPT_DIR/wallshift/icons/hicolor/scalable/status/wallshift.svg" "$ICON_DEST_DIR/wallshift.svg"
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi
echo "    ícone instalado em $ICON_DEST_DIR/wallshift.svg"

echo "==> Preparando configuração em $CONFIG_FILE"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
    cp "$SCRIPT_DIR/config.default.toml" "$CONFIG_FILE"
    echo "    config.toml criado a partir de config.default.toml"
else
    echo "    config.toml já existe em $CONFIG_FILE, mantendo o que já está lá"
fi

echo "==> Configurando autostart do KDE Plasma..."
mkdir -p "$AUTOSTART_DIR"
if grep -Eq '^\s*autostart\s*=\s*false' "$CONFIG_FILE"; then
    echo "    autostart = false em $CONFIG_FILE, removendo entrada de autostart (se existir)"
    rm -f "$AUTOSTART_FILE"
else
    cp "$SCRIPT_DIR/wallshift.desktop" "$AUTOSTART_FILE"
    echo "    autostart instalado em $AUTOSTART_FILE"
fi

echo
echo "==> Instalação concluída."
echo "    Teste agora com:      wallshift --once"
echo "    Ícone na bandeja:     wallshift-tray"
echo "    Configuração em:      $CONFIG_FILE"
echo "    Se os comandos não forem encontrados, abra um terminal novo (pipx"
echo "    ensurepath adiciona ~/.local/bin ao PATH apenas em sessões futuras)."
