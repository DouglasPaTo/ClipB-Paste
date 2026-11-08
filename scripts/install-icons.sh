#!/usr/bin/env bash
# install-icons.sh — instala os ícones do ClipB-Paste no tema do usuário.
#
# Por que isto é necessário: o KDE Plasma resolve o ícone da bandeja pelo NOME no
# tema (ex.: "video-display"), não por caminho de arquivo. Expor um caminho
# absoluto em IconName faz o Plasma desenhar um ícone VAZIO — o app fica invisível
# entre dois ícones da bandeja.
#
# Instala em ~/.local/share/icons/hicolor/<tamanho>/apps/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ICON_SRC="$ROOT_DIR/data/icons"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"

blue() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
green() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "$ICON_SRC/clipb-paste-32.png" ]] || die "ícones não encontrados em $ICON_SRC"

blue "instalando ícones em $DEST"

# Para cada tamanho, copia o PNG correspondente com o nome que o tema entende.
# "clipb-paste"        -> ícone para bandeja ESCURA (traço branco)
# "clipb-paste-light"  -> ícone para bandeja CLARA  (traço preto)
# "clipb-paste-typing" -> estado "digitando"
for size in 16 22 24 32 48 64 128; do
    target_dir="$DEST/${size}x${size}/apps"
    mkdir -p "$target_dir"
    for variant in "" "-light"; do
        src="$ICON_SRC/clipb-paste${variant}-${size}.png"
        out_name="clipb-paste${variant}"
        if [[ -f "$src" ]]; then
            cp -f "$src" "$target_dir/${out_name}.png"
        else
            # falta este tamanho específico: usa o 32 como fallback
            cp -f "$ICON_SRC/clipb-paste${variant}-32.png" "$target_dir/${out_name}.png"
        fi
    done
    # o estado "digitando" reaproveita o ícone normal (o ClinB-Paste não tem outro)
    cp -f "$ICON_SRC/clipb-paste-32.png" "$target_dir/clipb-paste-typing.png"
done

if command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -f -t "$DEST" >/dev/null 2>&1 || true
fi

green "instalado: clipb-paste, clipb-paste-light, clipb-paste-typing"
echo
echo "  Reinicie o app para o ícone aparecer:"
echo "    ./bin/clipb-paste daemon"