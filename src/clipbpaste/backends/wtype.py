"""Backend ``wtype``: protocolo ``zwp_virtual_keyboard_v1``.

É o caminho "sem root" mais elegante, mas depende do compositor implementar o
protocolo. **O KWin 6.6 não implementa** — verificamos nesta máquina::

    $ wtype "teste"
    Compositor does not support the virtual keyboard protocol

Fica aqui porque funciona em outros compositores (Sway, Hyprland, GNOME) e porque,
se um dia o KWin ganhar suporte, o backend passa a ser usado sozinho.
"""

from __future__ import annotations

import logging
import os

from .. import procutil
from . import BackendStatus, TypingBackend

log = logging.getLogger("clipbpaste")

BACKEND_NAME = "wtype"


def _client() -> str | None:
    return procutil.which("wtype")


def compositor_supports_virtual_keyboard() -> bool:
    """Sonda o protocolo com uma digitação vazia e vê se o compositor aceita."""
    client = _client()
    if not client:
        return False
    res = procutil.run([client, ""], timeout=3.0)
    if res.returncode == 0:
        return True
    msg = (res.stderr or "").lower()
    return "does not support" not in msg


def probe() -> BackendStatus:
    client = _client()
    if not client:
        return BackendStatus(BACKEND_NAME, False, "pacote 'wtype' não instalado")
    if not os.environ.get("WAYLAND_DISPLAY"):
        return BackendStatus(BACKEND_NAME, False, "sem sessão Wayland")
    if not compositor_supports_virtual_keyboard():
        return BackendStatus(
            BACKEND_NAME, False,
            "o compositor não implementa zwp_virtual_keyboard_v1 (o KWin não implementa)",
        )
    return BackendStatus(BACKEND_NAME, True)


class WtypeBackend(TypingBackend):
    name = BACKEND_NAME

    def __init__(self, client: str) -> None:
        self._client = client

    @classmethod
    def probe(cls) -> BackendStatus:
        return probe()

    def type_text(self, text: str, *, key_delay_ms: int = 15) -> None:
        if not text:
            return
        delay = max(1, int(key_delay_ms))
        res = procutil.run(
            [self._client, "-d", str(delay), "--", text],
            timeout=max(10.0, len(text) * (delay + 20) / 1000.0 + 5.0),
            stdin="",
        )
        if not res.ok:
            raise RuntimeError(f"wtype falhou: {res.stderr.strip() or res.returncode}")

    def send_key(self, key: str) -> bool:
        from ..kwin import key_symbols

        symbols = key_symbols(key)
        res = procutil.run([self._client, "-k", symbols[0]], timeout=3.0, stdin="")
        return res.ok


def create() -> TypingBackend:
    client = _client()
    if not client:
        raise RuntimeError("wtype indisponível")
    return WtypeBackend(client)