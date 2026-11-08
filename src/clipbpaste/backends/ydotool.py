"""Backend ``ydotool``: digitação via daemon ``ydotoold`` (uinput).

É o caminho mais comum no caminho "com root": o ``ydotoold`` roda como serviço e
abre o ``/dev/uinput``; o cliente fala com ele por socket, sem privilégios.

Instalação do lado do sistema (uma vez, com sudo)::

    sudo install -d -m 755 /etc/udev/rules.d
    echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' \\
      | sudo tee /etc/udev/rules.d/60-uinput-clipbpaste.rules
    sudo usermod -aG input "$USER"
    # depois de relogar:
    systemctl --user enable --now ydotool   # ou: ydotoold --socket-path=$XDG_RUNTIME_DIR/.ydotool_socket

Ver ``scripts/setup-ydotool.sh`` no projeto.
"""

from __future__ import annotations

import logging
import os
import time

from .. import procutil
from . import BackendStatus, TypingBackend

log = logging.getLogger("clipbpaste")

BACKEND_NAME = "ydotool"
# O ydotoold desta distro ignora --socket-path e sempre usa /tmp/.ydotool_socket;
# por isso os candidatos cobrem os três caminhos possíveis.
DEFAULT_SOCKETS = (
    "{XDG_RUNTIME_DIR}/.ydotool_socket",
    "/run/user/{UID}/.ydotool_socket",
    "/tmp/.ydotool_socket",
)

# --delay em ms. O ydotool desta versão usa "--delay" (não "--key-delay").
_DELAY_FLAG = "--delay"


def _client() -> str | None:
    return procutil.which("ydotool")


def _candidate_sockets() -> list[str]:
    env = os.environ.get("YDOTOOL_SOCKET")
    if env:
        return [env]
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return [tpl.format(XDG_RUNTIME_DIR=runtime, UID=os.getuid()) for tpl in DEFAULT_SOCKETS]


def _socket_path() -> str | None:
    for path in _candidate_sockets():
        if os.path.exists(path):
            return path
    return None


def _daemon_running() -> bool:
    res = procutil.run(["pgrep", "-x", "ydotoold"], timeout=2.0)
    return res.ok and bool(res.stdout.strip())


def probe() -> BackendStatus:
    client = _client()
    if not client:
        return BackendStatus(BACKEND_NAME, False, "pacote 'ydotool' não instalado")
    if not _daemon_running():
        return BackendStatus(
            BACKEND_NAME, False,
            "o daemon ydotoold não está rodando (veja scripts/setup-ydotool.sh)",
        )
    if not _socket_path():
        return BackendStatus(BACKEND_NAME, False, "socket do ydotoold não encontrado")
    return BackendStatus(BACKEND_NAME, False,
                         "a versão 0.1.8 para no primeiro acento e perde o resto do "
                         "texto — use o uinput, que acerta acentuação neste layout")


class YdotoolBackend(TypingBackend):
    name = BACKEND_NAME

    def __init__(self, client: str, socket_path: str) -> None:
        self._client = client
        self._socket = socket_path

    @classmethod
    def probe(cls) -> BackendStatus:
        return probe()

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["YDOTOOL_SOCKET"] = self._socket
        return env

    def type_text(self, text: str, *, key_delay_ms: int = 15) -> None:
        if not text:
            return
        # --key-delay em ms; -e evita que o ydotool tente traduzir layouts.
        delay = max(1, int(key_delay_ms))
        res = procutil.run(
            [self._client, "type", _DELAY_FLAG, str(delay), "--", text],
            env=self._env(),
            timeout=max(10.0, len(text) * (delay + 20) / 1000.0 + 5.0),
            stdin="",
        )
        if not res.ok:
            raise RuntimeError(f"ydotool type falhou: {res.stderr.strip() or res.returncode}")

    def send_key(self, key: str) -> bool:
        res = procutil.run([self._client, "key", key], env=self._env(), timeout=3.0, stdin="")
        return res.ok


def create() -> TypingBackend:
    client = _client()
    socket_path = _socket_path()
    if not client or not socket_path:
        raise RuntimeError("ydotool indisponível")
    return YdotoolBackend(client, socket_path)