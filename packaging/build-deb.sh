#!/usr/bin/env bash
# build-deb.sh — gera o pacote .deb do ClipB-Paste.
#
# Uso:
#   ./packaging/build-deb.sh            gera dist/clipb-paste_<versão>_all.deb
#   ./packaging/build-deb.sh --check    só valida o pacote gerado
#
# O .deb instala para TODO o sistema (/usr), diferente do install.sh, que
# instala por usuário (~/.local). As dependências Python ficam declaradas, então
# `apt install ./clipb-paste_*.deb` traz o que falta automaticamente.
#
# Estrutura do pacote:
#   /usr/bin/clipb-paste                      lançador
#   /usr/lib/clipb-paste/                     código Python + helper
#   /usr/share/clipb-paste/kwin/              script do KWin
#   /usr/share/applications/                  entrada no menu
#   /usr/share/icons/hicolor/                 ícones
#   /usr/share/doc/clipb-paste/               documentação e copyright

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 -c "
import re, pathlib
src = pathlib.Path('$ROOT/src/clipbpaste/__init__.py').read_text()
print(re.search(r'__version__ = \"([^\"]+)\"', src).group(1))
")"
PKG="clipb-paste"
APP_NAME="ClipB-Paste"
ARCH="all"
BUILD="$ROOT/build/deb"
OUT="$ROOT/dist"
DEB_FILE="$OUT/${PKG}_${VERSION}_${ARCH}.deb"

blue()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
green() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

command -v dpkg-deb >/dev/null || die "dpkg-deb não encontrado (instale dpkg)"
command -v fakeroot >/dev/null || die "fakeroot não encontrado (instale fakeroot)"

if [[ "${1:-}" == "--check" ]]; then
    [[ -f "$DEB_FILE" ]] || die "pacote não existe: $DEB_FILE"
    blue "validando $DEB_FILE"
    dpkg-deb --info "$DEB_FILE"
    echo
    # `| head` fecha o pipe e o tar do dpkg-deb recebe SIGPIPE (exit 2),
    # que com `set -e` aborta o script. Capturamos a saída inteira primeiro.
    CONTEUDO=$(dpkg-deb --contents "$DEB_FILE")
    echo "$CONTEUDO" | head -30
    echo "  ..."
    echo "  total: $(echo "$CONTEUDO" | wc -l) arquivos"
    exit 0
fi

blue "ClipB-Paste $VERSION — construindo pacote .deb"

# ---------------------------------------------------------------- limpeza
rm -rf "$BUILD"
mkdir -p "$BUILD/DEBIAN"
mkdir -p "$OUT"

# ---------------------------------------------------------------- arquivos
blue "copiando arquivos"

# código Python
mkdir -p "$BUILD/usr/lib/$PKG/src"
cp -r "$ROOT/src/clipbpaste" "$BUILD/usr/lib/$PKG/src/"
find "$BUILD/usr/lib/$PKG/src" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$BUILD/usr/lib/$PKG/src" -name '*.pyc' -delete 2>/dev/null || true

# script do KWin
mkdir -p "$BUILD/usr/share/$PKG/kwin"
cp "$ROOT/data/kwin/"*.js "$BUILD/usr/share/$PKG/kwin/"

# helper de digitação (compilado)
mkdir -p "$BUILD/usr/lib/$PKG/bin"
if command -v cc >/dev/null; then
    cc -O2 -Wall -o "$BUILD/usr/lib/$PKG/bin/uinput-type" "$ROOT/scripts/uinput-type.c" \
        2>/dev/null || die "falha ao compilar o helper"
    green "helper compilado"
else
    warn "sem 'cc': o pacote vai precisar compilar o helper na instalação"
fi

# ícones
for size in 16 22 24 32 48 64 128; do
    for variante in "" "-light" "-typing" "-alert"; do
        src="$ROOT/data/icons/${PKG}${variante}-${size}.png"
        [[ -f "$src" ]] && install -Dm644 "$src" \
            "$BUILD/usr/share/icons/hicolor/${size}x${size}/apps/${PKG}${variante}.png"
    done
done

# entrada no menu E autostart de sistema.
# /etc/xdg/autostart/ é o padrão freedesktop: todo desktop o executa no login
# gráfico, para qualquer usuário. Um serviço systemd de sistema NÃO serve aqui,
# porque rodaria antes da sessão gráfica existir (sem WAYLAND_DISPLAY, sem
# barramento D-Bus do usuário).
mkdir -p "$BUILD/etc/xdg/autostart"
cat > "$BUILD/etc/xdg/autostart/$PKG.desktop" <<AUTOSTART
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Inicia o ClipB-Paste com a sessão gráfica
Comment[en]=Starts ClipB-Paste with the desktop session
Exec=/usr/bin/$PKG daemon
Icon=$PKG
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
StartupNotify=false
AUTOSTART

mkdir -p "$BUILD/usr/share/applications"
cat > "$BUILD/usr/share/applications/$PKG.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ClipB-Paste
GenericName=Paste as keystrokes
Comment=Type the clipboard content into the window you point at
Comment[pt_BR]=Digita o conteúdo do clipboard na janela que você apontar
Exec=/usr/bin/$PKG daemon
Icon=$PKG
Terminal=false
Categories=Utility;
Keywords=clipboard;paste;type;colar;digitar;
StartupNotify=false
EOF

# documentação
mkdir -p "$BUILD/usr/share/doc/$PKG"
cp "$ROOT/README.md" "$BUILD/usr/share/doc/$PKG/"
gzip -9 -n -c "$ROOT/README.md" > "$BUILD/usr/share/doc/$PKG/README.md.gz" 2>/dev/null || true
# Formato DEP-5: é o que o Discover (e o apt) leem para mostrar a licença.
# Sem o cabeçalho "Format:", aparece "License: Unknown" no Discover.
cat > "$BUILD/usr/share/doc/$PKG/copyright" <<'COPYRIGHT'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ClipB-Paste
Upstream-Contact: DougPaTo <douglas@rdepaiva.ca>
Source: https://gitea.rdepaiva.ca/DougPaTo/ClipB-Paste

Files: *
Copyright: 2026 Collective Software LLC
           2026 DougPaTo
License: BSD-3-clause

License: BSD-3-clause
 Redistribution and use in source and binary forms, with or without
 modification, are permitted provided that the following conditions are met:
 .
 1. Redistributions of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.
 .
 2. Redistributions in binary form must reproduce the above copyright notice,
    this list of conditions and the following disclaimer in the documentation
    and/or other materials provided with the distribution.
 .
 3. Neither the name of the copyright holder nor the names of its contributors
    may be used to endorse or promote products derived from this software
    without specific prior written permission.
 .
 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 POSSIBILITY OF SUCH DAMAGE.
COPYRIGHT

# ---------------------------------------------------------------- scripts
blue "instalando scripts de manutenção"

# lançador
mkdir -p "$BUILD/usr/bin"
cat > "$BUILD/usr/bin/$PKG" <<'LAUNCHER'
#!/usr/bin/env python3
"""ClipB-Paste — lançador instalado pelo pacote .deb."""
import sys

sys.path.insert(0, "/usr/lib/clipb-paste/src")

from clipbpaste.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
LAUNCHER
chmod 755 "$BUILD/usr/bin/$PKG"

# pós-instalação
cat > "$BUILD/DEBIAN/postinst" <<'POSTINST'
#!/bin/bash
set -e

# Atualiza o cache de ícones para o ícone aparecer na bandeja/menu.
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
fi

echo
echo "ClipB-Paste instalado."

# ------------------------------------------------------------------ liberar uinput
# Este script roda como ROOT (via sudo apt install). Aproveitamos para criar a
# regra udev do /dev/uinput, que é a única parte que precisa de privilégio.
# Assim o usuário não precisa rodar mais nada depois.
if [ ! -f /etc/udev/rules.d/60-uinput-clipb-paste.rules ]; then
    echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
        > /etc/udev/rules.d/60-uinput-clipb-paste.rules 2>/dev/null || true
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules 2>/dev/null || true
        udevadm trigger --name-match=uinput 2>/dev/null || true
    fi
    echo "  /dev/uinput liberado para o grupo 'input'"
fi

# garante que o usuário que chamou o sudo está no grupo input
USUARIO="${SUDO_USER:-}"
if [ -n "$USUARIO" ] && [ "$USUARIO" != "root" ]; then
    if ! id -nG "$USUARIO" 2>/dev/null | tr ' ' '\n' | grep -qx input; then
        usermod -aG input "$USUARIO" 2>/dev/null || true
        echo "  $USUARIO adicionado ao grupo 'input' (pode exigir logout/login)"
    fi
fi
# aplica na hora, sem esperar o udev
chgrp input /dev/uinput 2>/dev/null || true
chmod 0660 /dev/uinput 2>/dev/null || true

echo

# ------------------------------------------------------------------ iniciar
# NÃO iniciamos o app aqui como root: ele criaria configuração em /root e um
# tray icon no barramento errado. Lançamos como o usuário que chamou o sudo,
# com o ambiente gráfico dele.
# Escolhe como executar comandos como outro usuário. O postinst roda como root,
# então runuser e sudo -u funcionam; se nenhum existir, usamos su.
COMO_USUARIO=""
if command -v runuser >/dev/null 2>&1; then
    COMO_USUARIO="runuser -u"
elif command -v sudo >/dev/null 2>&1; then
    COMO_USUARIO="sudo -u"
elif command -v su >/dev/null 2>&1; then
    COMO_USUARIO="su -s /bin/sh -c"
fi

if [ -n "$USUARIO" ] && [ "$USUARIO" != "root" ] && [ -n "$COMO_USUARIO" ]; then
    UID_USUARIO=$(id -u "$USUARIO" 2>/dev/null || echo "")
    if [ -n "$UID_USUARIO" ]; then
        RUNTIME="/run/user/$UID_USUARIO"

        # Descobre o ambiente gráfico real do usuário.
        # `runuser ... sh -c` NÃO serve: inicia um shell limpo sem as variáveis
        # da sessão gráfica. A fonte confiável é o ambiente do systemd --user.
        AMB=$(env XDG_RUNTIME_DIR="$RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" \
              $COMO_USUARIO "$USUARIO" systemctl --user show-environment 2>/dev/null || true)

        WAYLAND_USUARIO=$(echo "$AMB" | sed -n 's/^WAYLAND_DISPLAY=//p' | head -1)
        DISPLAY_USUARIO=$(echo "$AMB" | sed -n 's/^DISPLAY=//p' | head -1)

        # fallback: descobre pelo socket que existe no runtime dir
        if [ -z "$WAYLAND_USUARIO" ]; then
            for sock in "$RUNTIME"/wayland-*; do
                case "$sock" in *.lock) continue ;; esac
                [ -S "$sock" ] && WAYLAND_USUARIO=$(basename "$sock") && break
            done
        fi

        if [ -n "$WAYLAND_USUARIO" ] || [ -n "$DISPLAY_USUARIO" ]; then
            if [ -n "$WAYLAND_USUARIO" ] && [ -S "$RUNTIME/$WAYLAND_USUARIO" ]; then
                echo "  iniciando o ClipB-Paste na sessão gráfica de $USUARIO"
                env XDG_RUNTIME_DIR="$RUNTIME" \
                    WAYLAND_DISPLAY="$WAYLAND_USUARIO" \
                    DISPLAY="${DISPLAY_USUARIO:-:0}" \
                    XDG_SESSION_TYPE=wayland \
                    DBUS_SESSION_BUS_ADDRESS="unix:path=$RUNTIME/bus" \
                    $COMO_USUARIO "$USUARIO" setsid /usr/bin/clipb-paste daemon \
                    >/dev/null 2>&1 < /dev/null &
                sleep 2
                if pgrep -u "$UID_USUARIO" -f "clipb-paste daemon" >/dev/null 2>&1; then
                    echo "  ClipB-Paste em execução — procure o ícone na bandeja"
                else
                    echo "  (não iniciou automaticamente; abra pelo menu de aplicativos)"
                fi
            else
                echo "  Sessão gráfica não detectada — abra pelo menu de aplicativos."
            fi
        else
            echo "  Sessão gráfica não detectada — abra pelo menu de aplicativos."
        fi
    fi
fi

echo
echo "  Comandos úteis:"
echo "    clipb-paste doctor     # diagnóstico"
echo "    clipb-paste daemon     # iniciar manualmente"
echo
POSTINST
chmod 755 "$BUILD/DEBIAN/postinst"

# pré-remoção
cat > "$BUILD/DEBIAN/prerm" <<'PRERM'
#!/bin/bash
set -e

# Encerra o app se estiver rodando, para não deixar processo órfão.
for pid in $(pgrep -f "^python3 /usr/bin/clipb-paste daemon" 2>/dev/null || true); do
    kill "$pid" 2>/dev/null || true
done

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
PRERM
chmod 755 "$BUILD/DEBIAN/prerm"

# pós-remoção
cat > "$BUILD/DEBIAN/postrm" <<'POSTRM'
#!/bin/bash
set -e

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

if [ "$1" = "purge" ]; then
    echo "Configurações de usuário preservadas em ~/.config/clipb-paste/"
    echo "A regra udev do /dev/uinput NÃO foi removida (use: sudo rm /etc/udev/rules.d/60-uinput-clipb-paste.rules)"
fi
POSTRM
chmod 755 "$BUILD/DEBIAN/postrm"

# ---------------------------------------------------------------- controle
INSTALLED_SIZE=$(du -sk "$BUILD/usr" | cut -f1)

cat > "$BUILD/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-gi, python3-dbus, wl-clipboard, python3-gi-cairo
Recommends: ydotool
Suggests: fonts-noto-color-emoji
Installed-Size: $INSTALLED_SIZE
Maintainer: DougPaTo <douglas@rdepaiva.ca>
Homepage: https://gitea.rdepaiva.ca/DougPaTo/ClipB-Paste
Description: type the clipboard content as keystrokes on KDE Plasma
 ClipB-Paste types the clipboard content into the window you point at,
 character by character, as if you were using the keyboard.
 .
 Useful to paste into fields that reject Ctrl+V: remote consoles, virtual
 machines, terminals and validated forms.
 .
 Works on KDE Plasma 6 with KWin on Wayland. Shows a tray icon; a left click
 types into the window under the pointer, and clicking again stops the typing.
 Pressing any physical key also stops it.
 .
 After installing, run once (needs sudo):
   sudo clipb-paste enable-uinput
EOF

# ---------------------------------------------------------------- permissões
# CRÍTICO: dpkg-deb --root-owner-group muda o dono para root mas NÃO ajusta as
# permissões. Arquivos copiados do home vinham 600 (-rw-------) e o app não
# conseguia se ler ao ser executado por um usuário comum.
blue "normalizando permissões"
find "$BUILD/usr/lib" -type f -exec chmod 644 {} +
find "$BUILD/usr/lib" -type d -exec chmod 755 {} +
find "$BUILD/usr/share" -type f -exec chmod 644 {} +
find "$BUILD/etc" -type f -exec chmod 644 {} +
find "$BUILD/usr/share" -type d -exec chmod 755 {} +
chmod 755 "$BUILD/usr/bin/$PKG"
[[ -f "$BUILD/usr/lib/$PKG/bin/uinput-type" ]] && chmod 755 "$BUILD/usr/lib/$PKG/bin/uinput-type"
# scripts de manutenção precisam ser executáveis
chmod 755 "$BUILD/DEBIAN"/postinst "$BUILD/DEBIAN"/prerm "$BUILD/DEBIAN"/postrm 2>/dev/null || true
green "permissões normalizadas"

# ---------------------------------------------------------------- build
blue "gerando o pacote"
fakeroot dpkg-deb --build --root-owner-group "$BUILD" "$DEB_FILE" >/dev/null

green "pacote criado: ${DEB_FILE#$ROOT/}"
echo
dpkg-deb --info "$DEB_FILE" | grep -E 'Package|Version|Architecture|Installed-Size|Depends' | sed 's/^/  /'
echo
echo "  Instalar:      sudo apt install ${DEB_FILE#$ROOT/}"
echo "  Ver conteúdo:  dpkg-deb --contents ${DEB_FILE#$ROOT/}"
echo "  Validar:       ${BASH_SOURCE[0]} --check"