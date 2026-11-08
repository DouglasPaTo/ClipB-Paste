"""Backend ``stdout``: não digita nada, só imprime. Serve para testes e diagnóstico."""

from __future__ import annotations

import sys

from . import BackendStatus, TypingBackend

BACKEND_NAME = "stdout"


def probe() -> BackendStatus:
    return BackendStatus(BACKEND_NAME, True)


class StdoutBackend(TypingBackend):
    name = BACKEND_NAME

    def type_text(self, text: str, *, key_delay_ms: int = 15) -> None:
        for ch in text:
            sys.stdout.write(ch)
            sys.stdout.flush()

    def send_key(self, key: str) -> bool:
        sys.stdout.write(f"\n[{key}]\n")
        sys.stdout.flush()
        return True


def create() -> TypingBackend:
    return StdoutBackend()