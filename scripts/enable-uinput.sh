#!/usr/bin/env bash
# enable-uinput.sh — UMA vez que precisa de sudo. Habilita a digitação no ClipB-Paste.
#
# O que ele faz (e por que cada passo):
#
#   1. Regra udev liberando /dev/uinput para o grupo "input".
#      Por padrão o /dev/uinput é root:root 0600 — nenhum app do usuário pode
#      escrever nele. Você JÁ está no grupo "input", então só falta a regra.
#
#   2. Aplica a regra na hora (sem precisar reiniciar).
#
#   3. Testa de verdade: roda o helper do ClipB-Paste e confirma que abriu o
#      dispositivo. Se falhar, nada de falso positivo.
#
# Uso:  ./scripts/enable-uinput.sh
#       ./scripts/enable-uinput.sh --uninstall
#
# Depois dele, `./bin/clipb-paste doctor` deve mostrar o backend uinput disponível.

set -euo pipefail

RULE_FILE="/etc/udev/rules.d/60-uinput-clipbpaste.rules"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
HELPER="$ROOT_DIR/bin/uinput-type"

blue() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
green() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERRO:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
    blue "removendo a regra udev"
    sudo rm -f "$RULE_FILE"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --name-match=uinput || true
    green "regra removida. A digitação do ClipB-Paste deixa de funcionar."
    exit 0
fi

[[ "$(id -u)" -ne 0 ]] || die "rode sem sudo — o script pede a senha quando precisar"

# ---------------------------------------------------------------- diagnóstico
blue "verificando o ambiente"

if [[ ! -e /dev/uinput ]]; then
    warn "/dev/uinput não existe; carregando o módulo uinput"
    sudo modprobe uinput || die "não consegui carregar o módulo uinput"
fi

if id -nG | tr ' ' '\n' | grep -qx input; then
    green "seu usuário já está no grupo 'input'"
    NEED_RELOGIN=0
else
    warn "seu usuário NÃO está no grupo 'input'; adicionando"
    sudo usermod -aG input "$USER"
    NEED_RELOGIN=1
fi

if [[ -x "$HELPER" ]]; then
    green "helper de digitação presente: ${HELPER#$ROOT_DIR/}"
else
    warn "helper não compilado; compilando agora"
    command -v cc >/dev/null || die "compilador 'cc' não encontrado (instale build-essential)"
    mkdir -p "$(dirname "$HELPER")"
    cc -O2 -o "$HELPER" "$ROOT_DIR/scripts/uinput-type.c"
    green "helper compilado"
fi

# ---------------------------------------------------------------- regra udev
blue "criando a regra udev em $RULE_FILE"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \
    | sudo tee "$RULE_FILE" >/dev/null

blue "recarregando as regras"
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput
# Garante já nesta sessão, mesmo que o udev demore:
sudo chgrp input /dev/uinput
sudo chmod 0660 /dev/uinput

echo
blue "testando o acesso de verdade"
if echo "" | "$HELPER" 5 2>/dev/null; then
    green "/dev/uinput abriu e fechou sem erro"
else
    warn "o helper ainda não conseguiu abrir /dev/uinput"
    warn "permissões atuais: $(stat -c '%U:%G %a' /dev/uinput)"
    if [[ "$NEED_RELOGIN" == "1" ]]; then
        warn "faça LOGOUT e LOGIN (o grupo só vale em sessões novas) e rode de novo"
    fi
    exit 1
fi

echo
green "pronto! Digitação habilitada."
if [[ "$NEED_RELOGIN" == "1" ]]; then
    warn "IMPORTANTE: faça logout/login — o grupo 'input' só vale em sessões novas."
fi
echo
echo "  Verifique:      ./bin/clipb-paste doctor"
echo "  Teste a digitação: ./bin/clipb-paste type --backend uinput 'funcionou'"
echo "  Reinicie o app:  ./bin/clipb-paste daemon"