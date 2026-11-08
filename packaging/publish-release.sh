#!/usr/bin/env bash
# publish-release.sh — publica a release nos DOIS servidores (Gitea e GitHub).
#
# Por que existe: o GitHub Actions constrói e publica a release sozinho quando
# uma tag é empurrada. O Gitea deste servidor NÃO tem runners, então as actions
# de lá nunca executam — a release do Gitea precisa ser criada por este script.
#
# O que ele faz:
#   1. confere que a tag está empurrada nos dois remotes
#   2. constrói o .deb e o tarball A PARTIR DA TAG (não do working tree)
#   3. cria (ou atualiza) a release no Gitea e no GitHub
#   4. anexa os dois arquivos nos dois lugares
#
# Uso:
#   ./packaging/publish-release.sh              publica a versão do código
#   ./packaging/publish-release.sh v1.0.1       publica uma tag específica
#   ./packaging/publish-release.sh --check      só confere o que já existe
#
# Tokens (nunca no código):
#   Gitea : ~/.git-credentials (usado pelo git) ou $GITEA_TOKEN
#   GitHub: $GITHUB_TOKEN ou gh CLI autenticado

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GITEA_API="https://gitea.rdepaiva.ca/api/v1/repos/DougPaTo/ClipB-Paste"
GITEA_URL="https://gitea.rdepaiva.ca/DougPaTo/ClipB-Paste"
GITHUB_API="https://api.github.com/repos/DouglasPaTo/ClipB-Paste"
GITHUB_URL="https://github.com/DouglasPaTo/ClipB-Paste"

blue()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
green() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

for cmd in curl jq git; do
    command -v "$cmd" >/dev/null || die "'$cmd' não encontrado"
done

# ---------------------------------------------------------------- tokens
GITEA_TOKEN="${GITEA_TOKEN:-}"
if [[ -z "$GITEA_TOKEN" ]]; then
    # tenta o .git-credentials (armazenado pelo git)
    GITEA_TOKEN=$(awk -F'[:@]' '/gitea.rdepaiva.ca/ {print $3}' ~/.git-credentials 2>/dev/null | head -1)
fi

GITHUB_TOKEN="${GITHUB_TOKEN:-}"
if [[ -z "$GITHUB_TOKEN" ]] && command -v gh >/dev/null; then
    GITHUB_TOKEN=$(gh auth token 2>/dev/null || true)
fi

# ---------------------------------------------------------------- versão
if [[ "${1:-}" == "--check" ]]; then
    blue "estado atual das releases"
    echo
    echo "Gitea:"
    curl -sf -A "ClipB-Paste" -H "Authorization: token ${GITEA_TOKEN:-}" \
        "$GITEA_API/releases" 2>/dev/null \
        | jq -r '.[] | "  \(.name) (\(.tag_name)) — \(.assets | length) anexo(s)"' \
        || warn "não consegui consultar (repo privado? defina GITEA_TOKEN)"
    echo
    echo "GitHub:"
    curl -sf -A "ClipB-Paste" -H "Authorization: token ${GITHUB_TOKEN:-}" \
        "$GITHUB_API/releases" 2>/dev/null \
        | jq -r '.[] | "  \(.name) (\(.tag_name)) — \(.assets | length) anexo(s)"' \
        || warn "não consegui consultar"
    exit 0
fi

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
    VERSAO=$(python3 -c "
import re, pathlib
src = pathlib.Path('src/clipbpaste/__init__.py').read_text()
print(re.search(r'__version__ = \"([^\"]+)\"', src).group(1))
")
    TAG="v$VERSAO"
elif [[ "$TAG" != v* ]]; then
    TAG="v$TAG"
fi
VERSAO="${TAG#v}"

blue "publicando $TAG (versão $VERSAO)"

# ---------------------------------------------------------------- conferências
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || die "tag $TAG não existe localmente"

LOCAL=$(git rev-parse "$TAG^{commit}")
for remote in origin github; do
    REMOTO=$(git ls-remote --tags "$remote" "refs/tags/$TAG" 2>/dev/null | awk '{print $1}' | head -1)
    if [[ -z "$REMOTO" ]]; then
        die "tag $TAG não está no remote '$remote' — rode: git pushall"
    fi
done
green "tag $TAG está nos dois remotes (${LOCAL:0:7})"

# ---------------------------------------------------------------- build
blue "construindo a partir da tag $TAG"
rm -rf build/release && mkdir -p build/release dist

# código exatamente como está na tag
git archive --prefix=ClipB-Paste/ "$TAG" -o "dist/clipb-paste-$VERSAO.tar.gz"

# .deb: o script sempre usa o working tree, então extraímos a tag e construímos lá
git archive "$TAG" | tar -x -C build/release
( cd build/release && ./packaging/build-deb.sh >/dev/null )
cp "build/release/dist/clipb-paste_${VERSAO}_all.deb" dist/

DEB="dist/clipb-paste_${VERSAO}_all.deb"
TGZ="dist/clipb-paste-${VERSAO}.tar.gz"
[[ -f "$DEB" && -f "$TGZ" ]] || die "falha ao gerar os artefatos"
green ".deb  : $(du -h "$DEB" | cut -f1)"
green "tarball: $(du -h "$TGZ" | cut -f1)"

# sanity: o pacote tem que funcionar
# `| grep -q` fecha o pipe e o tar do dpkg-deb recebe SIGPIPE (exit 2);
# com o `set -e` isso parecia falha. Capturamos a saída primeiro.
CONTEUDO_DEB=$(dpkg-deb --contents "$DEB")
if echo "$CONTEUDO_DEB" | grep -q 'xdg/autostart'; then
    green "autostart presente no pacote"
else
    warn "o .deb não contém /etc/xdg/autostart (autostart ausente!)"
fi

# ---------------------------------------------------------------- Gitea
publicar_gitea() {
    [[ -n "$GITEA_TOKEN" ]] || { warn "sem token do Gitea — pulando"; return 0; }

    blue "publicando no Gitea"
    local existente
    existente=$(curl -sf -A "ClipB-Paste" -H "Authorization: token $GITEA_TOKEN" \
        "$GITEA_API/releases" | jq -r --arg t "$TAG" '.[] | select(.tag_name==$t) | .id' | head -1)

    local corpo
    corpo=$(git tag -l --format='%(contents)' "$TAG" | python3 -c "
import json,sys
print(json.dumps({'tag_name':'$TAG','name':'ClipB-Paste $VERSAO',
                  'body':sys.stdin.read(),'draft':False,'prerelease':False}))
")

    if [[ -z "$existente" ]]; then
        existente=$(curl -sf -X POST -A "ClipB-Paste" -H "Authorization: token $GITEA_TOKEN" \
            -H "Content-Type: application/json" -d "$corpo" "$GITEA_API/releases" | jq -r '.id')
        green "release criada (id $existente)"
    else
        curl -sf -X PATCH -A "ClipB-Paste" -H "Authorization: token $GITEA_TOKEN" \
            -H "Content-Type: application/json" -d "$corpo" \
            "$GITEA_API/releases/$existente" >/dev/null
        green "release atualizada (id $existente)"
        # remove anexos antigos para não acumular
        for aid in $(curl -sf -A "ClipB-Paste" -H "Authorization: token $GITEA_TOKEN" \
                     "$GITEA_API/releases/$existente/assets" | jq -r '.[].id'); do
            curl -sf -X DELETE -A "ClipB-Paste" -H "Authorization: token $GITEA_TOKEN" \
                "$GITEA_API/releases/$existente/assets/$aid" >/dev/null
        done
    fi

    for f in "$DEB" "$TGZ"; do
        local nome; nome=$(basename "$f")
        curl -sf -X POST -A "ClipB-Paste" -H "Authorization: token $GITEA_TOKEN" \
            -F "attachment=@$f" \
            "$GITEA_API/releases/$existente/assets?name=$nome" >/dev/null \
            && green "  anexado: $nome" \
            || warn "  falha ao anexar $nome"
    done
}

# ---------------------------------------------------------------- GitHub
publicar_github() {
    [[ -n "$GITHUB_TOKEN" ]] || { warn "sem token do GitHub — pulando"; return 0; }

    blue "publicando no GitHub"
    local existente
    existente=$(curl -sf -A "ClipB-Paste" -H "Authorization: token $GITHUB_TOKEN" \
        "$GITHUB_API/releases" | jq -r --arg t "$TAG" '.[] | select(.tag_name==$t) | .id' | head -1)

    local corpo
    corpo=$(git tag -l --format='%(contents)' "$TAG" | python3 -c "
import json,sys
print(json.dumps({'tag_name':'$TAG','name':'ClipB-Paste $VERSAO',
                  'body':sys.stdin.read(),'draft':False,'prerelease':False}))
")

    if [[ -z "$existente" ]]; then
        existente=$(curl -sf -X POST -A "ClipB-Paste" -H "Authorization: token $GITHUB_TOKEN" \
            -H "Content-Type: application/json" -d "$corpo" "$GITHUB_API/releases" | jq -r '.id')
        green "release criada (id $existente)"
    else
        curl -sf -X PATCH -A "ClipB-Paste" -H "Authorization: token $GITHUB_TOKEN" \
            -H "Content-Type: application/json" -d "$corpo" \
            "$GITHUB_API/releases/$existente" >/dev/null
        green "release atualizada (id $existente)"
        for aid in $(curl -sf -A "ClipB-Paste" -H "Authorization: token $GITHUB_TOKEN" \
                     "$GITHUB_API/releases/$existente/assets" | jq -r '.[].id'); do
            curl -sf -X DELETE -A "ClipB-Paste" -H "Authorization: token $GITHUB_TOKEN" \
                "$GITHUB_API/releases/assets/$aid" >/dev/null
        done
    fi

    local upload="https://uploads.github.com/repos/DouglasPaTo/ClipB-Paste/releases/$existente/assets"
    for f in "$DEB" "$TGZ"; do
        local nome; nome=$(basename "$f")
        curl -sf -X POST -A "ClipB-Paste" -H "Authorization: token $GITHUB_TOKEN" \
            -H "Content-Type: application/octet-stream" \
            --data-binary "@$f" "$upload?name=$nome" >/dev/null \
            && green "  anexado: $nome" \
            || warn "  falha ao anexar $nome"
    done
}

publicar_gitea
publicar_github

echo
green "pronto"
echo "  Gitea : $GITEA_URL/releases/tag/$TAG"
echo "  GitHub: $GITHUB_URL/releases/tag/$TAG"