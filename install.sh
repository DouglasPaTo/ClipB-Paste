#!/usr/bin/env bash
# install.sh — instala, atualiza ou remove o ClipB-Paste.
#
# Uso:
#   ./install.sh              instala (ou atualiza) para o usuário atual
#   ./install.sh --autostart  instala e adiciona à inicialização
#   ./install.sh --uninstall  remove tudo
#   ./install.sh --status     mostra o que está instalado
#
# Não precisa de sudo, exceto o passo de permissão do /dev/uinput, que é
# justamente o que habilita a digitação (o instalador avisa e oferece).
#
# O que é instalado:
#   ~/.local/bin/clipb-paste            executável
#   ~/.local/share/clipb-paste/         código Python + script do KWin
#   ~/.local/share/icons/hicolor/       ícones da bandeja
#   ~/.local/share/applications/        entrada no menu de aplicativos
#   ~/.config/autostart/                (opcional) início automático

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$PREFIX/clipb-paste"
ICON_DIR="$PREFIX/icons/hicolor"
DESKTOP_DIR="$PREFIX/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

APP_NAME="ClipB-Paste"
DESKTOP_FILE="clipb-paste.desktop"

blue()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
green() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- dependências
check_deps() {
    blue "verificando dependências"
    local falta=0
    for cmd in python3 wl-paste; do
        if ! command -v "$cmd" >/dev/null; then
            warn "'$cmd' não encontrado"
            falta=1
        fi
    done
    python3 -c "import gi; gi.require_version('Gtk','4.0')" 2>/dev/null \
        || { warn "python3-gi (GTK4) não encontrado"; falta=1; }
    python3 -c "import dbus" 2>/dev/null \
        || { warn "python3-dbus não encontrado"; falta=1; }

    if [[ "$falta" == "1" ]]; then
        echo
        echo "  Instale com:"
        echo "    sudo apt install python3-gi python3-dbus wl-clipboard"
        die "dependências faltando"
    fi
    green "dependências ok"
}

# ---------------------------------------------------------------- instalação
do_install() {
    check_deps

    blue "instalando em $PREFIX"

    # --- código ---
    mkdir -p "$APP_DIR"
    rm -rf "$APP_DIR/src" "$APP_DIR/data"
    cp -r "$ROOT/src" "$APP_DIR/src"
    cp -r "$ROOT/data" "$APP_DIR/data"
    find "$APP_DIR/src" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    green "código copiado para $APP_DIR"

    # --- executável ---
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/clipb-paste" <<LAUNCHER
#!/usr/bin/env python3
"""ClipB-Paste — lançador instalado por install.sh."""
import sys
from pathlib import Path

APP = Path("$APP_DIR")
sys.path.insert(0, str(APP / "src"))

from clipbpaste.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
LAUNCHER
    chmod +x "$BIN_DIR/clipb-paste"
    green "executável: $BIN_DIR/clipb-paste"

    # --- helper de digitação (compilado) ---
    if command -v cc >/dev/null; then
        mkdir -p "$APP_DIR/bin"
        cc -O2 -o "$APP_DIR/bin/uinput-type" "$ROOT/scripts/uinput-type.c" \
            && green "helper de digitação compilado"
    else
        warn "compilador 'cc' ausente — a digitação não vai funcionar"
        warn "instale build-essential e rode o instalador de novo"
    fi

    # --- ícones ---
    install_icons

    # --- entrada no menu ---
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
GenericName=Paste as keystrokes
Comment=Digita o conteúdo do clipboard na janela que você apontar
Comment[pt_BR]=Digita o conteúdo do clipboard na janela que você apontar
Exec=$BIN_DIR/clipb-paste daemon
Icon=clipb-paste
Terminal=false
Categories=Utility;
Keywords=clipboard;paste;type;colar;digitar;
StartupNotify=false
DESKTOP
    green "entrada no menu de aplicativos"

    # --- PATH ---
    if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
        warn "$BIN_DIR não está no PATH"
        echo "     Adicione ao ~/.profile:"
        echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi

    echo
    green "instalação concluída"
    echo
}

# Verifica se o /dev/uinput está liberado; se não, avisa com o comando pronto.
avisar_uinput() {
    if [[ -w /dev/uinput ]]; then
        return 0
    fi
    echo
    warn "A digitação AINDA NÃO vai funcionar: /dev/uinput está sem permissão."
    echo "     Rode uma vez (pede sudo):"
    echo "       sudo $ROOT/scripts/enable-uinput.sh"
    echo
}

install_icons() {
    local src="$ROOT/data/icons"
    [[ -f "$src/clipb-paste-32.png" ]] || { warn "ícones não encontrados em $src"; return 1; }
    for size in 16 22 24 32 48 64 128; do
        mkdir -p "$ICON_DIR/${size}x${size}/apps"
        # variantes: padrão, claro (tema claro), digitando (verde), alerta (vermelho)
        for variante in "" "-light" "-typing" "-alert"; do
            local f="$src/clipb-paste${variante}-${size}.png"
            [[ -f "$f" ]] || f="$src/clipb-paste${variante}-32.png"
            [[ -f "$f" ]] || continue
            cp -f "$f" "$ICON_DIR/${size}x${size}/apps/clipb-paste${variante}.png"
        done
    done
    command -v gtk-update-icon-cache >/dev/null \
        && gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true
    green "ícones instalados (padrão, claro, digitando, alerta)"
}

# ---------------------------------------------------------------- executar
do_start() {
    # Se já estiver rodando, não abre outra instância (o app também se protege,
    # mas avisar aqui deixa a mensagem clara).
    if pgrep -f "clipb-paste daemon" >/dev/null 2>&1; then
        warn "o ClipB-Paste já está rodando (pid $(pgrep -f 'clipb-paste daemon' | head -1))"
        return 0
    fi

    # Sem sessão gráfica (ex.: instalando por SSH) não há bandeja para mostrar.
    if [[ -z "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]]; then
        warn "sem sessão gráfica — não vou iniciar agora"
        echo "     Rode depois, na sessão do desktop:  clipb-paste daemon"
        return 0
    fi

    blue "iniciando o ClipB-Paste"
    # setsid + nohup: o app continua rodando depois que o instalador terminar.
    nohup setsid "$BIN_DIR/clipb-paste" daemon >/dev/null 2>&1 < /dev/null &
    disown 2>/dev/null || true

    # Confirma que subiu de fato
    local esperou=0
    while [[ $esperou -lt 30 ]]; do
        if pgrep -f "clipb-paste daemon" >/dev/null 2>&1; then
            green "iniciado (pid $(pgrep -f 'clipb-paste daemon' | head -1)) — veja o ícone na bandeja"
            return 0
        fi
        sleep 0.2
        esperou=$((esperou + 1))
    done
    warn "o app não confirmou a inicialização"
    echo "     Tente manualmente:  clipb-paste daemon"
    echo "     E veja o que falta: clipb-paste doctor"
}

# ---------------------------------------------------------------- autostart
do_autostart_enable() {
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_DIR/$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Inicia o ClipB-Paste com a sessão
Exec=$BIN_DIR/clipb-paste daemon
Icon=clipb-paste
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
DESKTOP
    green "iniciará automaticamente ao entrar na sessão"
    echo "     arquivo: $AUTOSTART_DIR/$DESKTOP_FILE"
}

do_autostart_disable() {
    if [[ -f "$AUTOSTART_DIR/$DESKTOP_FILE" ]]; then
        rm -f "$AUTOSTART_DIR/$DESKTOP_FILE"
        green "início automático desativado"
    else
        warn "o início automático já estava desativado"
    fi
}

# ---------------------------------------------------------------- remoção
do_uninstall() {
    blue "removendo o ClipB-Paste"

    # encerra se estiver rodando
    if pgrep -f "$BIN_DIR/clipb-paste daemon" >/dev/null 2>&1; then
        blue "encerrando o app em execução"
        pkill -f "$BIN_DIR/clipb-paste daemon" 2>/dev/null || true
        sleep 1
    fi

    rm -f "$BIN_DIR/clipb-paste"
    rm -rf "$APP_DIR"
    rm -f "$DESKTOP_DIR/$DESKTOP_FILE"
    rm -f "$AUTOSTART_DIR/$DESKTOP_FILE"
    for size in 16 22 24 32 48 64 128; do
        rm -f "$ICON_DIR/${size}x${size}/apps/clipb-paste"*.png
    done
    command -v gtk-update-icon-cache >/dev/null \
        && gtk-update-icon-cache -f -t "$ICON_DIR" >/dev/null 2>&1 || true

    green "programa, ícones e entradas removidos"
    echo
    warn "Suas configurações foram preservadas em:"
    echo "       ~/.config/clipb-paste/          (ajustes)"
    echo "       ~/.local/state/clipb-paste/     (logs)"
    echo "     Para apagar tudo:"
    echo "       rm -rf ~/.config/clipb-paste ~/.local/state/clipb-paste"
    echo
    warn "A regra udev do /dev/uinput continua ativa (use --remove-uinput para tirar)"
}

do_remove_uinput() {
    local rule="/etc/udev/rules.d/60-uinput-clipb-paste.rules"
    if [[ -f "$rule" ]]; then
        blue "removendo a regra udev do /dev/uinput"
        sudo rm -f "$rule"
        sudo udevadm control --reload-rules
        sudo udevadm trigger --name-match=uinput || true
        green "regra removida"
    else
        warn "regra udev não encontrada (já removida?)"
    fi
}

# ---------------------------------------------------------------- status
do_status() {
    echo "ClipB-Paste — estado da instalação"
    echo

    # Alinha as colunas em CARACTERES (não bytes): "ç"/"ã" ocupam 2 bytes em
    # UTF-8 e desalinhavam o printf %-Ns.
    linha() {
        local marca="$1" rotulo="$2" valor="$3" cor="$4"
        python3 -c '
import sys
marca, rotulo, valor = sys.argv[1], sys.argv[2], sys.argv[3]
cor = sys.argv[4]
cores = {"ok": "\033[1;32m", "no": "\033[1;31m", "meh": "\033[1;33m"}
print(f"  {cores[cor]}{marca}\033[0m {rotulo:<26} {valor}")
' "$marca" "$rotulo" "$valor" "$cor"
    }

    existe() { [[ -e "$2" ]] && linha "✓" "$1" "$2" ok || linha "✗" "$1" ausente no; }

    existe "executável"            "$BIN_DIR/clipb-paste"
    existe "código instalado"      "$APP_DIR/src/clipbpaste"
    existe "helper de digitação"   "$APP_DIR/bin/uinput-type"
    existe "entrada no menu"       "$DESKTOP_DIR/$DESKTOP_FILE"
    existe "ícone"                 "$ICON_DIR/32x32/apps/clipb-paste.png"

    if [[ -f "$AUTOSTART_DIR/$DESKTOP_FILE" ]]; then
        linha "✓" "início automático" "ativado" ok
    else
        linha "-" "início automático" "desativado" meh
    fi

    if pgrep -f "clipb-paste daemon" >/dev/null 2>&1; then
        linha "✓" "processo" "rodando (pid $(pgrep -f 'clipb-paste daemon' | head -1))" ok
    else
        linha "-" "processo" "parado" meh
    fi

    if [[ -w /dev/uinput ]]; then
        linha "✓" "/dev/uinput" "liberado" ok
    else
        linha "✗" "/dev/uinput" "sem permissão" no
        echo "      A digitação não vai funcionar. Rode: ./scripts/enable-uinput.sh"
    fi

    echo
    if command -v clipb-paste >/dev/null 2>&1; then
        echo "  Diagnóstico completo:  clipb-paste doctor"
    elif [[ -x "$BIN_DIR/clipb-paste" ]]; then
        echo "  Diagnóstico completo:  $BIN_DIR/clipb-paste doctor"
    fi
}

# ---------------------------------------------------------------- CLI
mostrar_ajuda() {
    cat <<EOF
ClipB-Paste — instalador

Uso: ./install.sh [opção]

  (sem opção)          instala ou atualiza e INICIA o app
  --autostart          instala, adiciona à inicialização e inicia agora
  --no-start           instala sem iniciar
  --start              só inicia o app (sem instalar), se não estiver rodando
  --uninstall          remove o programa (mantém suas configurações)
  --remove-uinput      remove também a regra udev do /dev/uinput (pede sudo)
  --status             mostra o que está instalado
  -h, --help           esta ajuda

Exemplos:
  ./install.sh                 # instalar, iniciar e usar
  ./install.sh --autostart     # instalar e iniciar também ao ligar o computador
  ./install.sh --status        # conferir se está tudo no lugar

Depois de instalar:
  clipb-paste daemon           # iniciar agora
  clipb-paste doctor           # verificar o ambiente
EOF
}

case "${1:-}" in
    "")               do_install
                      avisar_uinput
                      do_start
                      if [[ ! -f "$AUTOSTART_DIR/$DESKTOP_FILE" ]]; then
                          echo
                          echo "  Para iniciar junto com a sessão:"
                          echo "    ./install.sh --autostart"
                      fi
                      ;;
    --autostart)      do_install
                      do_autostart_enable
                      avisar_uinput
                      do_start
                      ;;
    --no-autostart)   do_autostart_disable ;;
    --start)          do_start ;;
    --no-start)       do_install ;;
    --uninstall)      do_uninstall ;;
    --remove-uinput)  do_remove_uinput ;;
    --status)         do_status ;;
    -h|--help)        mostrar_ajuda ;;
    *)                die "opção desconhecida: $1 (use --help)" ;;
esac