"""Backends de digitação — o equivalente Linux do ``SendInput`` do Windows.

No original, ``Native.SendCharViaScanCode`` usava ``SendInput``/``VkKeyScanEx`` para
sintetizar teclas. No Wayland isso é proibido para apps comuns, então existem alguns
caminhos possíveis; cada um vira um backend aqui:

====================  ==================  ====================================
backend               precisa de root?    observação
====================  ==================  ====================================
``eis``               não                 protocolo EIS (KWin 6.x); precisa de
                                          portal RemoteDesktop
``ydotool``           sim (uinput)        daemon + /dev/uinput liberado
``wtype``             não                 protocolo virtual-keyboard; o KWin
                                          não implementa hoje
``uinput``            sim                 escreve direto em /dev/uinput
``stdout``            não                 não digita: imprime (para testes)
====================  ==================  ====================================
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger("clipbpaste")


@dataclass
class BackendStatus:
    name: str
    available: bool
    reason: str = ""

    def describe(self) -> str:
        if self.available:
            return f"{self.name}: disponível"
        return f"{self.name}: indisponível ({self.reason})"


class TypingBackend:
    """Interface de um backend de digitação."""

    name = "base"
    supports_unicode = True   # backends que só fazem ASCII sobrescrevem isto

    @classmethod
    def probe(cls) -> BackendStatus:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return self.probe().available

    def type_text(self, text: str, *, key_delay_ms: int = 15, should_stop=None) -> None:
        """Digita ``text`` caractere a caractere, respeitando ``key_delay_ms``.

        ``should_stop`` é uma função que devolve True quando o usuário pediu para
        parar. O backend deve interromper o mais rápido possível — em textos
        longos, poder parar é mais importante que terminar.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Aborta uma digitação em andamento (chamado de outra thread)."""

    def send_key(self, key: str) -> bool:
        """Envia uma tecla nomeada (``RETURN``, ``ESCAPE``, ``F12``…)."""
        return False

    def flush(self) -> None:
        """Garante que a entrada chegou (chamado antes de encerrar)."""

    def unsupported_chars(self, text: str) -> str:
        """Caracteres que este backend não consegue digitar (vazio = todos ok)."""
        if self.supports_unicode:
            return ""
        return "".join(sorted({c for c in text if ord(c) > 127}))


def available_backends() -> list[TypingBackend]:
    """Instancia todos os backends cuja dependência está presente."""
    from . import eis, uinput, wtype, ydotool

    backends: list[TypingBackend] = []
    for module in (eis, ydotool, wtype, uinput):
        if module.probe().available:
            try:
                backends.append(module.create())
            except Exception as exc:  # backend quebrado não deve derrubar o app
                log.warning("backend %s falhou ao iniciar: %s", module.BACKEND_NAME, exc)
    return backends


def resolve(preference: str = "auto") -> tuple[TypingBackend | None, list[BackendStatus]]:
    """Escolhe o backend pedido (ou o melhor disponível) e devolve o relatório."""
    from . import eis, uinput, wtype, ydotool

    modules = {"eis": eis, "ydotool": ydotool, "wtype": wtype, "uinput": uinput}
    report = [m.probe() for m in (eis, ydotool, wtype, uinput)]

    if preference == "stdout":
        from .stdout import StdoutBackend

        return StdoutBackend(), report

    if preference in modules:
        module = modules[preference]
        status = module.probe()
        if not status.available:
            return None, report
        return module.create(), report

    # auto: EIS (sem root) > ydotool (mais completo) > wtype > uinput (helper C)
    for module in (eis, ydotool, wtype, uinput):
        if module.probe().available:
            try:
                return module.create(), report
            except Exception as exc:
                log.warning("backend %s falhou: %s", module.BACKEND_NAME, exc)
    return None, report


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")