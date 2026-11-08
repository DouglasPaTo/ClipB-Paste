"""Backend ``uinput``: escreve eventos direto em ``/dev/uinput``.

Equivalente mais próximo do ``SendInput`` do Windows: cria um teclado virtual no
kernel e injeta os eventos. Precisa de permissão de escrita no ``/dev/uinput``
(por padrão é ``root:root 0600``; a regra udev do setup libera para o grupo
``input``).

Dois caminhos de implementação:

* ``uinput`` em Python, se estiver instalado (``pip install python-uinput``);
* senão, um pequeno helper em C (``scripts/uinput-type.c``) compilado no setup.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .. import procutil
from . import BackendStatus, TypingBackend

log = logging.getLogger("clipbpaste")

BACKEND_NAME = "uinput"
UINPUT_DEVICE = "/dev/uinput"
HELPER_CANDIDATES = (
    Path.home() / ".local/share/clipb-paste/bin/uinput-type",
    Path("/usr/local/bin/clipb-paste-uinput-type"),
    Path(__file__).resolve().parents[3] / "bin" / "uinput-type",
)

# --- constantes do kernel (linux/uinput.h e linux/input-event-codes.h) ---
EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
BUS_USB = 0x03
KEY_LEFTSHIFT = 42
KEY_ESC = 1
KEY_ENTER = 28

# Mapa ASCII → (keycode evdev, precisa shift)
_ASCII = {}
for _i, _ch in enumerate("1234567890"):
    _ASCII[_ch] = (2 + _i, 0)
    _ASCII["!@#$%^&*()"[_i]] = (2 + _i, 1)
for _i, _ch in enumerate("qwertyuiop"):
    _ASCII[_ch] = (16 + _i, 0)
for _i, _ch in enumerate("asdfghjkl"):
    _ASCII[_ch] = (30 + _i, 0)
for _i, _ch in enumerate("zxcvbnm"):
    _ASCII[_ch] = (44 + _i, 0)
_ASCII.update({
    ",": (51, 0), "<": (51, 1), ".": (52, 0), ">": (52, 1),
    "/": (53, 0), "?": (53, 1), ";": (39, 0), ":": (39, 1),
    "'": (40, 0), '"': (40, 1), "[": (26, 0), "{": (26, 1),
    "]": (27, 0), "}": (27, 1), "\\": (43, 0), "|": (43, 1),
    "`": (41, 0), "~": (41, 1), "-": (12, 0), "_": (12, 1),
    "=": (13, 0), "+": (13, 1), " ": (57, 0), "\n": (28, 0), "\t": (15, 0),
    "!": (2, 1),
})

_NAMED = {
    "RETURN": KEY_ENTER, "ENTER": KEY_ENTER, "ESCAPE": KEY_ESC, "TAB": 15,
    "BACKSPACE": 14, "SPACE": 57,
}


def active_layout() -> str:
    """Layout de teclado ativo segundo o KDE ("br", "us"…), ou "" se desconhecido.

    Necessário porque a acentuação por dead key depende do layout real em uso —
    o KWin é a fonte confiável (setxkbmap pode divergir do que o compositor usa).
    """
    try:
        import dbus

        bus = dbus.SessionBus()
        obj = bus.get_object("org.kde.keyboard", "/Layouts", introspect=False)
        iface = dbus.Interface(obj, "org.kde.KeyboardLayouts")
        layouts = iface.getLayoutsList()
        indice = int(iface.getLayout())
        if 0 <= indice < len(layouts):
            return str(layouts[indice][0])
    except Exception as exc:
        log.debug("não consegui ler o layout do KDE: %s", exc)
    return ""


def pode_ler_teclado() -> bool:
    """True se temos permissão de ler /dev/input (para o 'pare com qualquer tecla')."""
    import glob

    for dev in glob.glob("/dev/input/event*"):
        try:
            import os

            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
            os.close(fd)
            return True
        except (PermissionError, OSError):
            continue
    return False


def _writable() -> bool:
    try:
        return os.access(UINPUT_DEVICE, os.W_OK)
    except OSError:
        return False


def _helper() -> Path | None:
    for candidate in HELPER_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return procutil.which("clipb-paste-uinput-type")


def probe() -> BackendStatus:
    if not os.path.exists(UINPUT_DEVICE):
        return BackendStatus(BACKEND_NAME, False, "/dev/uinput não existe (módulo 'uinput' não carregado?)")
    if not _writable():
        return BackendStatus(
            BACKEND_NAME, False,
            "/dev/uinput não é gravável pelo seu usuário — rode scripts/enable-uinput.sh (pede sudo uma vez)",
        )
    if not _helper():
        try:
            import uinput  # noqa: F401
        except ImportError:
            return BackendStatus(
                BACKEND_NAME, False,
                "sem o helper 'uinput-type' compilado e sem o pacote python-uinput",
            )
    return BackendStatus(BACKEND_NAME, True)


class UinputBackend(TypingBackend):
    name = BACKEND_NAME
    # Digita ASCII + acentos do ABNT2 (via dead key) + ´ ° ª º (AltGr).
    supports_unicode = False

    # O que o helper REALMENTE digita, medido no ABNT2:
    _SUPORTADOS = set(
        "áàâãäéèêëíìîïóòôõöúùûüçñ"
        "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ"
        "´°ºª"
    )

    # Tipográficos pulados CALADO (sem aviso): bullet, travessões, aspas curvas,
    # reticências. Não têm uso em senha e o aviso só polui.
    _IRRELEVANTES = set("•◦▪▫–—“”‘’…►▶")

    def unsupported_chars(self, text: str) -> str:
        """Caracteres perdidos que valem avisar.

        Acentos, ´, °, ª e º funcionam. Bullet/travessão/emoji são pulados sem
        aviso.
        """
        faltando = set()
        for c in text:
            if c.isascii() or c in self._SUPORTADOS or c in self._IRRELEVANTES:
                continue
            if c.isspace():
                continue
            faltando.add(c)
        return "".join(sorted(faltando))

    def __init__(self, helper: Path | None) -> None:
        self._helper = helper
        self._device = None

    @classmethod
    def probe(cls) -> BackendStatus:
        return probe()

    def _ensure_device(self):
        if self._device is not None or self._helper is not None:
            return self._device
        import uinput

        keys = [uinput.KEY_A + i for i in range(58)]
        self._device = uinput.Device(flag=uinput.KEYBOARD, events={0x01: keys})
        time.sleep(0.2)  # o kernel precisa registrar o dispositivo
        return self._device

    def type_text(self, text: str, *, key_delay_ms: int = 15, should_stop=None) -> None:
        if not text:
            return
        if self._helper is not None:
            import os
            import signal
            import subprocess

            env = dict(os.environ)
            layout = active_layout()
            if layout:
                env["CLIPBPASTE_LAYOUT"] = layout
            # O helper monitora este PID: se o app morrer, ele para de digitar.
            env["CLIPBPASTE_PARENT_PID"] = str(os.getpid())

            proc = subprocess.Popen(
                [str(self._helper), str(max(0, int(key_delay_ms)))],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, env=env, start_new_session=True,
            )
            self._proc = proc    # permite matar de outra thread (stop())
            try:
                proc.communicate(text.encode("utf-8"),
                                 timeout=max(30.0, len(text) * 0.15 + 15.0))
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError("uinput-type travou e foi encerrado")
            finally:
                self._proc = None

            if should_stop is not None and should_stop():
                return
            if proc.returncode not in (0, -signal.SIGTERM, -signal.SIGKILL):
                raise RuntimeError(f"uinput-type terminou com código {proc.returncode}")
            return

        device = self._ensure_device()
        delay = max(0.001, key_delay_ms / 1000.0)
        for ch in text:
            if should_stop is not None and should_stop():
                return
            mapping = _ASCII.get(ch)
            if mapping is None:
                continue  # uinput sem mapa para este caractere (acentos vão pelo ydotool)
            code, shift = mapping
            if shift:
                device.emit(KEY_LEFTSHIFT, 1)
            device.emit(code, 1)
            device.emit(code, 0)
            if shift:
                device.emit(KEY_LEFTSHIFT, 0)
            device.emit(EV_SYN, SYN_REPORT)
            time.sleep(delay)

    def stop(self) -> None:
        """Encerra a digitação em andamento (seguro a partir de outra thread)."""
        proc = getattr(self, "_proc", None)
        if proc is not None and proc.poll() is None:
            try:
                import os
                import signal

                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def send_key(self, key: str) -> bool:
        code = _NAMED.get(key.upper())
        if code is None:
            return False
        if self._helper is not None:
            return False
        device = self._ensure_device()
        device.emit(code, 1)
        device.emit(code, 0)
        device.emit(EV_SYN, SYN_REPORT)
        return True

    def flush(self) -> None:
        if self._device is not None:
            try:
                self._device.destroy()
            except Exception:
                pass
            self._device = None


def create() -> TypingBackend:
    helper = _helper()
    if helper is None and not _writable():
        raise RuntimeError("uinput indisponível")
    return UinputBackend(helper)