"""Orquestração da digitação (equivalente ao ``StartTyping`` do Program.cs original).

Fluxo no original:

1. ler o clipboard;
2. se ``Confirm`` e o texto passou de ``ConfirmOver`` caracteres, pedir confirmação;
3. esperar ``StartDelayMS``;
4. digitar caractere a caractere com ``KeyDelayMS`` entre eles;
5. cancelar se o usuário apertar Esc.

Tudo isso é preservado aqui, em cima dos backends de ``backends/``.
"""

from __future__ import annotations

import logging
import threading
import time

from . import clipboard
from .backends import TypingBackend

log = logging.getLogger("clipbpaste")


class TypingCancelled(RuntimeError):
    pass


class Typer:
    """Executa uma sessão de digitação cancelável."""

    def __init__(self, backend: TypingBackend) -> None:
        self._backend = backend
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    def type_text_async(
        self,
        text: str,
        *,
        key_delay_ms: int = 15,
        start_delay_ms: int = 0,
        on_done=None,
        on_error=None,
    ) -> None:
        """Digita em background (a GUI nunca pode bloquear)."""
        self._cancel.clear()

        def worker() -> None:
            try:
                self.type_text_blocking(text, key_delay_ms=key_delay_ms, start_delay_ms=start_delay_ms)
                if on_done:
                    on_done()
            except TypingCancelled:
                log.info("digitação cancelada pelo usuário")
                if on_done:
                    on_done()
            except Exception as exc:
                log.error("falha ao digitar: %s", exc)
                if on_error:
                    on_error(exc)

        self._thread = threading.Thread(target=worker, name="clipb-paste-typing", daemon=True)
        self._thread.start()

    def type_text_blocking(
        self,
        text: str,
        *,
        key_delay_ms: int = 15,
        start_delay_ms: int = 0,
    ) -> None:
        if not text:
            return
        # StartDelayMS dá tempo do usuário soltar as teclas do atalho.
        waited = 0
        while waited < start_delay_ms:
            if self._cancel.is_set():
                raise TypingCancelled()
            time.sleep(0.05)
            waited += 50
        if self._cancel.is_set():
            raise TypingCancelled()

        # O backend já aplica o atraso entre caracteres. Fatiar o texto em vários
        # processos (o que acontecia antes) cria e destrói um teclado virtual a cada
        # fatia, e as transições podiam perder caracteres. Mandamos tudo de uma vez;
        # o cancelamento interrompe entre blocos grandes só se o texto for enorme.
        if self._cancel.is_set():
            raise TypingCancelled()
        self._backend.type_text(text, key_delay_ms=key_delay_ms)
        self._backend.flush()


class ClipboardError(RuntimeError):
    pass


def read_clipboard_text() -> str:
    if not clipboard.has_clipboard():
        raise ClipboardError("nenhuma ferramenta de clipboard encontrada (instale wl-clipboard)")
    return clipboard.read_text()