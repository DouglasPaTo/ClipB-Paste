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
    dpkg-deb --contents "$DEB_FILE" | head -30
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

# entrada no menu
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
echo
echo "  Para a digitação funcionar, rode UMA vez (precisa de sudo):"
echo "    sudo clipb-paste enable-uinput"
echo
echo "  Ou crie a regra udev manualmente:"
echo "    echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\", OPTIONS+=\"static_node=uinput\"' \\"
echo "      | sudo tee /etc/udev/rules.d/60-uinput-clipb-paste.rules"
echo "    sudo udevadm control --reload-rules && sudo udevadm trigger"
echo "    sudo usermod -aG input \$USER   # depois faça logout/login"
echo
echo "  Inicie com:  clipb-paste daemon"
echo "  Diagnóstico: clipb-paste doctor"
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