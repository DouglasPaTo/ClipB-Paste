#!/usr/bin/env bash
# setup-ydotool.sh — habilita a digitação sintética no Wayland.
#
# Este é o único passo que precisa de root, e só uma vez. Ele:
#   1. instala o pacote ydotool (cliente) se faltar;
#   2. libera /dev/uinput para o grupo "input" (regra udev);
#   3. coloca seu usuário no grupo "input";
#   4. instala um serviço de usuário que sobe o ydotoold;
#   5. (opcional) compila o helper uinput-type, usado como fallback.
#
# Uso:  ./scripts/setup-ydotool.sh
#       ./scripts/setup-ydotool.sh --uninstall

set -euo pipefail

RULE_FILE="/etc/udev/rules.d/60-uinput-clipbpaste.rules"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/ydotoold.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
    log "removendo regra udev, serviço e helper"
    sudo rm -f "$RULE_FILE"
    systemctl --user disable --now ydotoold.service 2>/dev/null || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload || true
    sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput || true
    log "removido. Seu usuário continua no grupo 'input' (remova manualmente se quiser)."
    exit 0
fi

[[ "$(id -u)" -ne 0 ]] || die "rode sem sudo: o script pede sudo quando precisa"

# ---------------------------------------------------------------- 1. pacote
if ! command -v ydotool >/dev/null && ! command -v ydotoold >/dev/null; then
    log "ydotool não encontrado; instalando com apt"
    sudo apt-get update -qq
    sudo apt-get install -y ydotool
else
    log "ydotool já instalado ($(command -v ydotool 2>/dev/null || command -v ydotoold))"
fi

if ! command -v ydotool >/dev/null; then
    warn "o cliente 'ydotool' não existe neste sistema."
    warn "Na 24.04 o pacote às vezes traz só o ydotoold; nesse caso veja"
    warn "'scripts/install-ydotool-client.sh' para compilar o cliente."
fi

# ---------------------------------------------------------------- 2. udev
log "liberando /dev/uinput para o grupo 'input'"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee "$RULE_FILE" >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput || true
if [[ ! -e /dev/uinput ]]; then
    warn "/dev/uinput não existe — carregando o módulo"
    sudo modprobe uinput || warn "não foi possível carregar o módulo uinput"
fi
sudo chgrp input /dev/uinput 2>/dev/null || true
sudo chmod 0660 /dev/uinput 2>/dev/null || true

# ---------------------------------------------------------------- 3. grupo
if id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
    log "usuário já está no grupo 'input'"
else
    log "adicionando $USER ao grupo 'input'"
    sudo usermod -aG input "$USER"
    RELOGIN=1
fi

# ---------------------------------------------------------------- 4. serviço
log "instalando serviço de usuário do ydotoold"
mkdir -p "$UNIT_DIR"
YDOTOOLD_BIN="$(command -v ydotoold || true)"
[[ -n "$YDOTOOLD_BIN" ]] || die "ydotoold não encontrado após instalar"

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=ydotoold — daemon de entrada sintética (usado pelo ClipB-Paste)
After=graphical-session.target

[Service]
Type=simple
# --socket-path precisa bater com o que o ClipB-Paste procura:
#   \$XDG_RUNTIME_DIR/.ydotool_socket
ExecStart=$YDOTOOLD_BIN --socket-path=%t/.ydotool_socket --socket-perm=0600
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ydotoold.service || warn "não consegui iniciar o serviço agora"

# ---------------------------------------------------------------- 5. helper C
if command -v cc >/dev/null && [[ -f "$ROOT_DIR/scripts/uinput-type.c" ]]; then
    log "compilando helper uinput-type (fallback sem ydotool)"
    mkdir -p "$HOME/.local/share/clipb-paste/bin"
    cc -O2 -o "$HOME/.local/share/clipb-paste/bin/uinput-type" "$ROOT_DIR/scripts/uinput-type.c" \
        && log "helper instalado em ~/.local/share/clipb-paste/bin/uinput-type" \
        || warn "falha ao compilar o helper (não é obrigatório)"
fi

echo
log "pronto."
if [[ "${RELOGIN:-0}" == "1" ]]; then
    warn "FAÇA LOGOUT e LOGIN de novo — o grupo 'input' só vale em sessões novas."
fi
log "Verifique com:  clipb-paste doctor"
log "Teste a digitação com:  clipb-paste type --backend ydotool 'teste'"