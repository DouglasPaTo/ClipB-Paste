"""Backend ``eis``: Input Capture / EIS (``libei``) — o caminho "sem root".

O KWin 6.x fala o protocolo de captura de entrada do libei. A ideia é criar uma
"região de captura" (via portal ``org.freedesktop.portal.RemoteDesktop``) e, dentro
dela, injetar teclas como um dispositivo EIS.

Estado neste ambiente (verificado):

* O portal expõe a interface, mas ``CreateSession``/``SelectDevices`` só vêm com
  ``libei`` instalado e o app precisa de uma permissão que o usuário concede na
  primeira vez (diálogo do KDE).
* O KWin 6.6 implementa o lado servidor do EIS no plugin ``eis``.

Por ser o único caminho sem root, ele fica em primeiro lugar no modo ``auto``.
Quando ``libei`` não está disponível, ``probe`` devolve indisponível com o motivo
exato, e o app cai para ``ydotool``/``wtype``.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os

from . import BackendStatus, TypingBackend

log = logging.getLogger("clipbpaste")

BACKEND_NAME = "eis"


def _libei_path() -> str | None:
    env = os.environ.get("CLIPBPASTE_LIBEI")
    if env and os.path.exists(env):
        return env
    found = ctypes.util.find_library("ei")
    if found:
        return found
    for candidate in (
        "/usr/lib/x86_64-linux-gnu/libei.so.1",
        "/usr/lib/libei.so.1",
        "/usr/lib64/libei.so.1",
        "/usr/local/lib/libei.so.1",
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def probe() -> BackendStatus:
    if not _libei_path():
        return BackendStatus(
            BACKEND_NAME, False,
            "libei não instalada (o backend EIS depende dela; requer root para instalar)",
        )
    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        return BackendStatus(BACKEND_NAME, False, "sem sessão gráfica")
    # libei existe, mas a sequência de captura (portal RemoteDesktop + EIS) ainda não
    # está ligada nesta versão. Reportar "disponível" faria o modo auto escolher um
    # backend que não digita — por isso a resposta honesta é indisponível.
    return BackendStatus(
        BACKEND_NAME, False,
        "libei presente, mas a integração de captura (portal RemoteDesktop + EIS) "
        "ainda não está habilitada nesta versão — use ydotool",
    )


class EisBackend(TypingBackend):
    """Digitação via libei.

    A API completa do libei exige uma sequência de callbacks (negotiation, frames)
    que precisa de um loop próprio. Enquanto essa integração não é ligada, o backend
    usa ``libei`` só para verificar a sessão e delega a digitação ao helper
    ``ei-type`` caso ele exista.
    """

    name = BACKEND_NAME

    def __init__(self, lib_path: str) -> None:
        self._lib = ctypes.CDLL(lib_path)
        self._connected = False

    @classmethod
    def probe(cls) -> BackendStatus:
        return probe()

    def _connect(self) -> None:
        if self._connected:
            return
        # ei_setup_backend_socket(): uma linha, sem callbacks, só para provar a sessão.
        setup = getattr(self._lib, "ei_setup_backend_socket", None)
        if setup is None:
            raise RuntimeError("libei antiga: sem ei_setup_backend_socket")
        setup.restype = ctypes.c_void_p
        setup.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        ctx = setup(None, None)
        if not ctx:
            raise RuntimeError("libei não conseguiu abrir o backend (portal negado?)")
        self._context = ctx
        self._connected = True

    def type_text(self, text: str, *, key_delay_ms: int = 15) -> None:
        raise RuntimeError(
            "backend EIS ainda não envia texto nesta versão — use ydotool ou wtype"
        )

    def send_key(self, key: str) -> bool:
        return False


def create() -> TypingBackend:
    path = _libei_path()
    if not path:
        raise RuntimeError("libei não encontrada")
    return EisBackend(path)