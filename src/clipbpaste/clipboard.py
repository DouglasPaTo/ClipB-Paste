"""Leitura do clipboard em Wayland (wl-paste) e X11 (xsel/xclip), texto e imagem."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import procutil

log = logging.getLogger("clipbpaste")

BINARY_MIME_PREFIXES = ("image/", "application/octet-stream", "audio/", "video/")

# Ordem de preferência ao procurar texto no clipboard.
_TEXT_MIME_ORDER = (
    "text/plain;charset=utf-8",
    "text/plain",
    "UTF8_STRING",
    "STRING",
    "TEXT",
)


@dataclass
class ClipboardContent:
    text: str = ""
    mime: str = ""
    binary: bytes | None = None

    @property
    def is_image(self) -> bool:
        return self.binary is not None and self.mime.startswith("image/")

    def __bool__(self) -> bool:
        return bool(self.text) or bool(self.binary)


def _wayland_tools() -> bool:
    return bool(procutil.which("wl-paste"))


def list_mime_types() -> list[str]:
    if not _wayland_tools():
        return []
    res = procutil.run(["wl-paste", "--list-types"], timeout=2.0)
    if not res.ok:
        return []
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def read_text() -> str:
    """Equivalente a Clipboard.GetText(): texto simples, "" se não houver.

    Quando o clipboard contém uma imagem, ``wl-paste`` sem ``--type`` devolve os
    bytes crus do PNG/JPEG — decodificá-los como UTF-8 quebra. Por isso só pedimos
    tipos textuais e decodificamos com ``errors="replace"``.
    """
    if _wayland_tools():
        types = list_mime_types()
        for mime in _TEXT_MIME_ORDER:
            if types and mime not in types:
                continue
            res = procutil.run(["wl-paste", "--no-newline", "--type", mime], timeout=3.0)
            if res.ok and res.stdout:
                return res.stdout
        # Clipboard com apenas tipos não-textuais (imagem, arquivos binários).
        return ""
    for tool, args in (("xsel", ["--clipboard", "--output"]), ("xclip", ["-selection", "clipboard", "-o"])):
        if procutil.which(tool):
            res = procutil.run([tool, *args], timeout=3.0)
            if res.ok:
                return res.stdout
    return ""


def read_image() -> tuple[str, bytes] | None:
    if _wayland_tools():
        for mime in list_mime_types():
            if mime.startswith("image/"):
                res = procutil.run(["wl-paste", "--type", mime], stdin="", timeout=10.0)
                if res.ok and res.stdout:
                    return mime, res.stdout.encode() if isinstance(res.stdout, str) else res.stdout
    if procutil.which("xclip"):
        res = procutil.run(["xclip", "-selection", "clipboard", "-o", "-t", "image/png"], timeout=10.0)
        if res.ok and res.stdout:
            return "image/png", res.stdout.encode()
    return None


def read() -> ClipboardContent:
    text = read_text()
    if text:
        return ClipboardContent(text=text, mime="text/plain;charset=utf-8")
    img = read_image()
    if img:
        return ClipboardContent(mime=img[0], binary=img[1])
    return ClipboardContent()


def write_text(text: str) -> bool:
    if _wayland_tools():
        res = procutil.run(["wl-copy"], stdin=text, timeout=3.0)
        return res.ok
    if procutil.which("xsel"):
        return procutil.run(["xsel", "--clipboard", "--input"], stdin=text, timeout=3.0).ok
    return False


def has_clipboard() -> bool:
    return _wayland_tools() or bool(procutil.which("xsel") or procutil.which("xclip"))