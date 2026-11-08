"""Integração com o KWin via D-Bus (validado no KWin 6.6.6 desta máquina).

O que descobrimos na prática e que dita a arquitetura deste módulo:

* Um script de *scripting* do KWin **não expõe objeto D-Bus próprio** — só os
  métodos ``run``/``stop``. O único canal contínuo é ``callDBus``, do compositor
  para o app.
* ``readConfig`` lê a seção ``[Script-<pluginName>]`` do kwinrc, mas só no
  carregamento; ``run()`` não re-executa o corpo do script.
* Recarregar o script (``unloadScript`` + ``loadScript`` + ``start``) re-executa o
  corpo e custa ~30ms.

Logo o protocolo é: o app grava ``cmd``/``arg`` no kwinrc, recarrega o script, e o
script responde chamando ``reply``/``activated`` no app.

ATENÇÃO ao modelo de threads: as chamadas D-Bus de retorno são entregues no thread
do loop GLib (MainThread). Bloquear esse thread com ``Event.wait()`` impede a
entrega e o comando "trava" até o timeout. Por isso ``KWinBridge.execute_async``
dispara e retorna imediatamente; quem espera é sempre um thread que NÃO é o dono
do loop (a CLI e o daemon usam ``execute_threadsafe``).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("clipbpaste")

KWIN_SERVICE = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_IFACE = "org.kde.kwin.Scripting"
SCRIPT_NAME = "clipb-paste-linux"          # comandos (recarregado a cada uso)
SCRIPT_GROUP = f"Script-{SCRIPT_NAME}"

CP_SERVICE = "org.clipbpaste.Linux"
CP_OBJECT = "/ClipBPaste"  # object path não aceita "-"
CP_IFACE = "org.clipbpaste.Linux"

# usage HID USB → tecla do atalho (para o backend EIS, que fala em códigos HID)
HID_KEYS = {
    "A": 0x04, "B": 0x05, "C": 0x06, "D": 0x07, "E": 0x08, "F": 0x09, "G": 0x0A,
    "H": 0x0B, "I": 0x0C, "J": 0x0D, "K": 0x0E, "L": 0x0F, "M": 0x10, "N": 0x11,
    "O": 0x12, "P": 0x13, "Q": 0x14, "R": 0x15, "S": 0x16, "T": 0x17, "U": 0x18,
    "V": 0x19, "W": 0x1A, "X": 0x1B, "Y": 0x1C, "Z": 0x1D,
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22, "6": 0x23, "7": 0x24,
    "8": 0x25, "9": 0x26, "0": 0x27,
    "RETURN": 0x28, "ENTER": 0x28, "ESCAPE": 0x29, "BACKSPACE": 0x2A, "TAB": 0x2B,
    "SPACE": 0x2C, "INSERT": 0x49, "HOME": 0x4A, "PAGEUP": 0x4B, "DELETE": 0x4C,
    "END": 0x4D, "PAGEDOWN": 0x4E, "RIGHT": 0x4F, "LEFT": 0x50, "DOWN": 0x51,
    "UP": 0x52,
}
for _i in range(1, 13):
    HID_KEYS[f"F{_i}"] = 0x3A + _i - 1

# Nomes xkb das teclas especiais (para o backend wtype)
KEY_SYMBOLS = {
    "RETURN": "Return", "ENTER": "Return", "ESCAPE": "Escape", "BACKSPACE": "BackSpace",
    "TAB": "Tab", "SPACE": "space", "INSERT": "Insert", "DELETE": "Delete",
    "HOME": "Home", "END": "End", "PAGEUP": "Prior", "PAGEDOWN": "Next",
    "UP": "Up", "DOWN": "Down", "LEFT": "Left", "RIGHT": "Right",
}

# Qt::Key — usado quando o atalho é registrado dentro do script do KWin
QT_KEYS = {
    "RETURN": 0x01000004, "ENTER": 0x01000004, "ESCAPE": 0x01000000, "TAB": 0x01000001,
    "BACKSPACE": 0x01000003, "SPACE": 0x20, "INSERT": 0x01000006, "DELETE": 0x01000007,
    "HOME": 0x01000010, "END": 0x01000011, "PAGEUP": 0x01000016, "PAGEDOWN": 0x01000017,
    "UP": 0x01000013, "DOWN": 0x01000015, "LEFT": 0x01000012, "RIGHT": 0x01000014,
}
for _i in range(1, 13):
    QT_KEYS[f"F{_i}"] = 0x0100002F + _i - 1


def key_symbols(key: str) -> list[str]:
    up = key.upper()
    if up in KEY_SYMBOLS:
        return [KEY_SYMBOLS[up]]
    return [up.lower()]


def key_hid(key: str) -> tuple[int, int]:
    """(usage HID, modificadores USB: 0x02 = shift) para uma tecla nomeada.

    Letras maiúsculas exigem shift; as minúsculas não. Teclas nomeadas
    (``RETURN``, ``F1``…) vão sem shift.
    """
    raw = key if len(key) == 1 else key.upper()
    usage = HID_KEYS.get(key.upper())
    shift = 0
    if len(raw) == 1:
        if raw.isalpha():
            usage = 0x04 + "ABCDEFGHIJKLMNOPQRSTUVWXYZ".index(raw.upper())
            # 'A' é a letra maiúscula: no teclado físico isso exige Shift;
            # 'a' é a posição sem Shift.
            shift = 0x02 if raw.isupper() else 0
        elif raw in "1234567890":
            usage = 0x1E + "1234567890".index(raw)
    return (usage if usage is not None else 0x2C), shift


def key_qt(key: str) -> int:
    up = key.upper()
    return QT_KEYS.get(up, ord(up) if len(up) == 1 else ord("V"))


# ------------------------------------------------------------------ modelo
@dataclass
class KWinWindow:
    id: str
    caption: str = ""
    resource_class: str = ""
    resource_name: str = ""
    pid: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    offset_x: int = 0
    offset_y: int = 0
    active: bool = False
    skip_taskbar: bool = False

    @property
    def app_id(self) -> str:
        return (self.resource_class or self.resource_name or "").lower()

    @property
    def caption_text(self) -> str:
        return (self.caption or self.app_id or "janela").strip()

    def truncated_caption(self, limit: int = 50) -> str:
        cap = self.caption_text
        return cap if len(cap) <= limit else cap[: max(1, limit - 1)] + "…"

    def describe(self) -> str:
        return f"'{self.truncated_caption()}'"

    def contains(self, point: tuple[int, int]) -> bool:
        px, py = point
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KWinWindow":
        return cls(
            id=str(data.get("id", "")),
            caption=str(data.get("caption", "")),
            resource_class=str(data.get("class", "")),
            resource_name=str(data.get("name", "")),
            pid=int(data.get("pid", 0) or 0),
            x=int(data.get("x", 0) or 0),
            y=int(data.get("y", 0) or 0),
            width=int(data.get("w", 0) or 0),
            height=int(data.get("h", 0) or 0),
            offset_x=int(data.get("ox", 0) or 0),
            offset_y=int(data.get("oy", 0) or 0),
            active=bool(data.get("active", False)),
            skip_taskbar=bool(data.get("skip", False)),
        )

    @classmethod
    def parse(cls, payload: str | None) -> "KWinWindow | None":
        if not payload:
            return None
        text = payload.strip()
        if not text.startswith("{"):
            return None
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return cls.from_dict(data)


@dataclass(frozen=True)
class WindowIdentity:
    """Identidade estável de uma janela (id é UUID no KWin, estável entre recargas)."""

    ks: str
    app_id: str = ""
    caption: str = ""
    pid: int = 0

    @classmethod
    def from_window(cls, win: KWinWindow) -> "WindowIdentity":
        return cls(win.id, win.app_id, win.caption_text, win.pid)

    def to_json(self) -> str:
        return json.dumps({"ks": self.ks, "app": self.app_id,
                           "caption": self.caption, "pid": self.pid}, ensure_ascii=False)

    @classmethod
    def parse(cls, value: str | None) -> "WindowIdentity | None":
        text = (value or "").strip()
        if not text:
            return None
        # Pode ser um UUID puro ("{04c6...}") ou o JSON completo da identidade.
        if text.startswith("{") and ":" in text and "ks" in text:
            try:
                data = json.loads(text)
            except ValueError:
                return None
            return cls(str(data.get("ks", "")), str(data.get("app", "")),
                       str(data.get("caption", "")), int(data.get("pid", 0) or 0))
        return cls(text)


def parse_window_list(payload: str | None) -> list[KWinWindow]:
    windows: list[KWinWindow] = []
    for line in (payload or "").splitlines():
        win = KWinWindow.parse(line)
        if win is not None:
            windows.append(win)
    return windows


# ------------------------------------------------------------------ ambiente
class KWinError(RuntimeError):
    pass


def is_kde() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "kde" in desktop or "plasma" in desktop or bool(os.environ.get("KDE_FULL_SESSION"))


def script_path() -> Path:
    env = os.environ.get("CLIPBPASTE_KWIN_SCRIPT")
    if env:
        return Path(env).expanduser()
    for candidate in (
        Path(__file__).resolve().parents[2] / "data" / "kwin" / "clipb-paste.js",
        Path.home() / ".local/share/clipb-paste/kwin/clipb-paste.js",
        Path("/usr/share/clipb-paste/kwin/clipb-paste.js"),
    ):
        if candidate.is_file():
            return candidate
    return Path("/usr/share/clipb-paste/kwin/clipb-paste.js")


def _kwriteconfig_in(group: str, key: str, value: str) -> None:
    tool = "kwriteconfig6" if _which("kwriteconfig6") else "kwriteconfig5"
    path = _which(tool)
    if not path:
        raise KWinError(f"{tool} não encontrado — não é possível configurar o script do KWin")
    proc = subprocess.run([path, "--file", "kwinrc", "--group", group, "--key", key, value],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise KWinError(f"{tool} falhou: {proc.stderr.strip()}")


def _kwriteconfig(key: str, value: str) -> None:
    tool = "kwriteconfig6" if _which("kwriteconfig6") else "kwriteconfig5"
    path = _which(tool)
    if not path:
        raise KWinError(f"{tool} não encontrado — não é possível configurar o script do KWin")
    proc = subprocess.run([path, "--file", "kwinrc", "--group", SCRIPT_GROUP, "--key", key, value],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise KWinError(f"{tool} falhou: {proc.stderr.strip()}")


def _which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep) + ["/usr/bin", "/usr/local/bin"]:
        cand = Path(directory) / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


# ------------------------------------------------------------------ callbacks
@dataclass
class DbusCalls:
    """Callbacks que o script do KWin dispara no app."""

    on_activated: Callable[[], None] | None = None
    on_reply: Callable[[str, str, str], None] | None = None

    def activated(self, name: str = "", x: int = 0, y: int = 0) -> bool:
        if self.on_activated:
            self.on_activated()
        return True

    def reply(self, command: str, status: str, payload: str) -> bool:
        if self.on_reply:
            self.on_reply(str(command), str(status), str(payload))
        return True


# ------------------------------------------------------------------ bridge
class KWinBridge:
    """Executa comandos no KWin pelo protocolo config + recarga + callback."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._bus = None
        self._scripting = None
        self._host = None
        self._bus_name = None
        self._on_activated = None
        self._gdbus = None
        self._on_abort = None
        self._results: dict[str, tuple[str, str]] = {}
        self._pending_external: dict[str, tuple[str, float]] = {}

    # ---- infraestrutura D-Bus ----
    def set_abort_callback(self, cb) -> None:
        """Quem é avisado quando o app pede para cancelar a digitação."""
        self._on_abort = cb

    def set_activated_callback(self, cb) -> None:
        """Registra quem é avisado quando o atalho global é acionado."""
        self._on_activated = cb

    def set_gdbus_connection(self, conn) -> None:
        """Usa a conexão GDBus da bandeja (que é dona do nome do serviço).

        O objeto ``/ClipB-Paste`` é exportado nela em ``export_host``, e as respostas
        do script do KWin chegam por ali.
        """
        self._gdbus = conn

    def export_host(self) -> bool:
        """Exporta ``/ClipB-Paste`` na conexão GDBus, se houver uma."""
        conn = getattr(self, "_gdbus", None)
        if conn is None or self._host is not None:
            return self._host is not None
        from gi.repository import Gio, GLib

        bridge = self

        def on_call(_conn, _sender, _path, _iface, method, params, invocation):
            try:
                if method == "ping":
                    invocation.return_value(GLib.Variant("(b)", (True,)))
                elif method == "reply":
                    command, status, payload = params.unpack()
                    bridge._deliver(command, status, payload)
                    invocation.return_value(GLib.Variant("(b)", (True,)))
                elif method == "activated":
                    callback = getattr(bridge, "_on_activated", None)
                    if callback is not None:
                        try:
                            callback()
                        except Exception as exc:
                            log.error("callback do atalho falhou: %s", exc)
                    invocation.return_value(GLib.Variant("(b)", (True,)))
                elif method == "pasteNow":
                    callback = getattr(bridge, "_on_activated", None)
                    if callback is not None:
                        callback()
                    invocation.return_value(GLib.Variant("(b)", (True,)))
                elif method == "abort":
                    callback = getattr(bridge, "_on_abort", None)
                    if callback is not None:
                        callback()
                    invocation.return_value(GLib.Variant("(b)", (True,)))
                elif method == "execute":
                    # Permite que OUTRO processo (a CLI) rode comandos no KWin
                    # mesmo quando o daemon é o dono do nome do serviço.
                    command, arg = params.unpack()
                    bridge._pending_external[command] = (str(arg), time.monotonic())
                    try:
                        bridge._dispatch(str(command), str(arg))
                        # O script recarregou: reaplica o atalho depois que a
                        # resposta for coletada (senão o atalho fica desligado).
                        invocation.return_value(GLib.Variant("(b)", (True,)))
                    except Exception as exc:
                        log.error("execute(%s) falhou: %s", command, exc)
                        invocation.return_value(GLib.Variant("(b)", (False,)))
                elif method == "fetchResult":
                    command = str(params.unpack()[0])
                    entry = bridge._results.pop(command, None)
                    if entry is None:
                        invocation.return_value(GLib.Variant("(bss)", (False, "", "")))
                    else:
                        invocation.return_value(GLib.Variant("(bss)", (True, entry[0], entry[1])))
                else:
                    invocation.return_value(GLib.Variant("(b)", (False,)))
            except Exception as exc:
                log.error("chamada D-Bus %s falhou: %s", method, exc)
                invocation.return_value(GLib.Variant("(b)", (False,)))

        xml = """
        <node>
          <interface name="org.clipbpaste.Linux">
            <method name="ping"><arg type="b" direction="out"/></method>
            <method name="reply">
              <arg type="s" direction="in"/><arg type="s" direction="in"/>
              <arg type="s" direction="in"/><arg type="b" direction="out"/>
            </method>
            <method name="activated">
              <arg type="s" direction="in"/><arg type="i" direction="in"/>
              <arg type="i" direction="in"/><arg type="b" direction="out"/>
            </method>
            <method name="pasteNow"><arg type="b" direction="out"/></method>
            <method name="abort"><arg type="b" direction="out"/></method>
            <method name="execute">
              <arg type="s" direction="in"/><arg type="s" direction="in"/>
              <arg type="b" direction="out"/>
            </method>
            <method name="fetchResult">
              <arg type="s" direction="in"/><arg type="b" direction="out"/>
              <arg type="s" direction="out"/><arg type="s" direction="out"/>
            </method>
          </interface>
        </node>
        """
        info = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]
        conn.register_object(CP_OBJECT, info, on_call, None, None)
        self._host = True
        self._exported = True
        log.debug("objeto %s exportado via GDBus", CP_OBJECT)
        return True

    def _ensure_host(self) -> None:
        """Fallback: exporta o host via dbus-python quando não há conexão GDBus."""
        if self._host is not None or getattr(self, "_gdbus", None) is not None:
            return
        import dbus
        import dbus.service

        bus = self._bus
        bridge = self
        try:
            name = dbus.service.BusName(CP_SERVICE, bus, do_not_queue=True,
                                        allow_replacement=False, replace_existing=False)
        except dbus.exceptions.NameExistsException:
            return

        class Host(dbus.service.Object):
            @dbus.service.method(CP_IFACE, in_signature="", out_signature="b")
            def ping(self):  # noqa: N802
                return True

            @dbus.service.method(CP_IFACE, in_signature="sss", out_signature="b")
            def reply(self, command, status, payload):  # noqa: N802
                bridge._deliver(str(command), str(status), str(payload))
                return True

            @dbus.service.method(CP_IFACE, in_signature="sii", out_signature="b")
            def activated(self, name_, x, y):  # noqa: N802
                callback = getattr(bridge, "_on_activated", None)
                if callback is not None:
                    callback()
                return True

        self._host = Host(bus, CP_OBJECT)
        self._bus_name = name

    def _ensure_bus(self):
        if self._bus is not None:
            return self._bus
        import dbus

        # O dbus-python SÓ entrega callbacks/respostas se a conexão estiver presa a um
        # main loop. Sem isto, um processo de CLI (sem loop do GTK) nunca receberia as
        # respostas do script do KWin — e o comando "travaria" até o timeout.
        try:
            import dbus.mainloop.glib

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        except Exception as exc:  # pragma: no cover
            log.debug("mainloop glib para D-Bus indisponível: %s", exc)

        self._bus = dbus.SessionBus()
        self._bus.set_exit_on_disconnect(False)
        self._ensure_host()
        self._scripting = dbus.Interface(
            self._bus.get_object(KWIN_SERVICE, KWIN_SCRIPTING_PATH, introspect=False),
            KWIN_SCRIPTING_IFACE,
        )
        return self._bus

    @classmethod
    def create(cls) -> "KWinBridge | None":
        if not is_kde():
            return None
        bridge = cls()
        try:
            bridge._ensure_bus()
            bridge._scripting.isScriptLoaded(SCRIPT_NAME)
        except ImportError:
            log.warning("python3-dbus não instalado: integração com KWin desativada")
            return None
        except Exception as exc:
            log.debug("KWin indisponível: %s", exc)
            return None
        return bridge

    def is_loaded(self) -> bool:
        try:
            self._ensure_bus()
            return bool(self._scripting.isScriptLoaded(SCRIPT_NAME))
        except Exception:
            return False

    # ---- execução de comando ----
    def _dispatch(self, command: str, arg: str) -> None:
        """Grava o comando e recarrega o script. Não bloqueia esperando resposta.

        A resposta volta por ``/ClipB-Paste.reply``, servido por QUEM é dono do nome
        ``org.clipbpaste.Linux``. Se outro processo (o daemon) é o dono, ele
        repassa a resposta para nós por meio de um arquivo de correio no runtime dir
        — assim CLI e daemon convivem sem disputar o barramento.
        """
        self._ensure_bus()
        _kwriteconfig("clipb-pasteService", CP_SERVICE)
        _kwriteconfig("cmd", command)
        _kwriteconfig("arg", arg)
        path = script_path()
        try:
            self._scripting.unloadScript(SCRIPT_NAME)
            self._scripting.loadScript(str(path), SCRIPT_NAME)
            self._scripting.start()
        except Exception as exc:
            raise KWinError(f"falha ao recarregar o script no KWin: {exc}") from exc

    def execute(self, command: str, arg: str = "", *, timeout: float = 4.0) -> tuple[str, str]:
        """Executa um comando e espera a resposta.

        NÃO chame isto do thread que roda o loop GLib: a resposta seria entregue
        justamente nele. Use ``execute_threadsafe`` nesse caso.
        """
        if self._host_is_foreign():
            return self._execute_remote(command, arg, timeout)

        event = threading.Event()
        box: dict[str, Any] = {}
        with self._lock:
            self._pending[command] = (event, box)
        try:
            self._dispatch(command, arg)
            self._pump_until(event, timeout)
            if not event.is_set():
                raise KWinError(
                    f"o script do KWin não respondeu a '{command}' em {timeout:.0f}s "
                    "(veja `journalctl --user -b | grep clipb-paste`)"
                )
        finally:
            with self._lock:
                self._pending.pop(command, None)
        return str(box.get("status", "")), str(box.get("payload", ""))

    def execute_threadsafe(self, command: str, arg: str = "", *, timeout: float = 4.0) -> tuple[str, str]:
        """Alias de ``execute``: ``execute`` já bombeia o loop e não trava a GUI."""
        return self.execute(command, arg, timeout=timeout)

    def _host_is_foreign(self) -> bool:
        """True quando outro processo (o daemon) é dono de org.clipbpaste.Linux."""
        if getattr(self, "_gdbus", None) is not None:
            return False
        if getattr(self, "_exported", False):
            return False
        try:
            import dbus

            bus = self._bus
            return bool(bus.name_has_owner(CP_SERVICE))
        except Exception:
            return False

    def _execute_remote(self, command: str, arg: str, timeout: float) -> tuple[str, str]:
        """Pede ao processo que é dono do serviço para rodar o comando e espera o resultado."""
        import dbus

        self._results.pop(command, None)
        try:
            proxy = dbus.Interface(
                self._bus.get_object(CP_SERVICE, CP_OBJECT, introspect=False), CP_IFACE
            )
            proxy.execute(command, arg)
        except Exception as exc:
            raise KWinError(f"não consegui falar com o processo ClipB-Paste: {exc}") from exc

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                found, status, payload = proxy.fetchResult(command)
            except Exception:
                found, status, payload = False, "", ""
            if found:
                return str(status), str(payload)
            self._sleep_pumping(0.03)
        raise KWinError(f"o script do KWin não respondeu a '{command}' em {timeout:.0f}s")

    def _sleep_pumping(self, seconds: float) -> None:
        """Dorme girando o loop GLib (necessário para receber mensagens D-Bus)."""
        try:
            from gi.repository import GLib
        except ImportError:
            time.sleep(seconds)
            return
        loop = GLib.MainLoop()
        GLib.timeout_add(int(seconds * 1000), lambda: (loop.quit(), False)[1])
        loop.run()

    def _deliver(self, command: str, status: str, payload: str) -> None:
        # Guarda para quem pediu por D-Bus (outro processo).
        self._results[command] = (status, payload)
        pending = self._pending.get(command)
        if pending is None:
            log.debug("resposta descartada (sem pedido pendente): %s %s", command, status)
            return
        event, box = pending
        box["status"] = status
        box["payload"] = payload
        event.set()

    def _pump_until(self, done: threading.Event, timeout: float) -> None:
        """Bombeia um loop GLib privado até ``done`` — as respostas D-Bus chegam nele.

        Sem isso, um processo sem loop principal (a CLI) nunca receberia a resposta:
        o objeto dbus-python só entrega callbacks quando um loop está girando.
        """
        try:
            from gi.repository import GLib
        except ImportError:
            done.wait(timeout)
            return

        sentinel: dict[str, Any] = {}
        loop = GLib.MainLoop()

        def check() -> bool:
            if done.is_set() or sentinel.get("timed_out"):
                loop.quit()
                return False
            return True

        def on_timeout() -> bool:
            sentinel["timed_out"] = True
            loop.quit()
            return False

        GLib.timeout_add(20, check)
        GLib.timeout_add(int(timeout * 1000), on_timeout)
        loop.run()

    # ---- comandos ----
    def _cmd(self, command: str, arg: str = "", timeout: float = 4.0) -> tuple[str, str]:
        """Executa um comando no KWin e espera a resposta sem travar o app.

        O truque: o loop GLib da aplicação pode estar rodando no MainThread, e a
        resposta chega justamente ali. Então rodamos um GLib.MainLoop *privado* num
        thread auxiliar enquanto esperamos — assim a resposta é processada mesmo que
        o loop principal esteja ocupado/idle.
        """
        if threading.current_thread() is threading.main_thread():
            # Não podemos join() do MainThread: isso trava o loop GLib que entrega
            # a resposta. Se já houver loop rodando, quem chama deve usar um worker.
            return self.execute_threadsafe(command, arg, timeout=timeout)
        return self.execute(command, arg, timeout=timeout)

    def hello(self, timeout: float = 4.0) -> bool:
        try:
            status, _ = self._cmd("hello", timeout=timeout)
            return status == "ok"
        except KWinError:
            return False

    def windows(self, timeout: float = 4.0) -> list[KWinWindow]:
        status, payload = self._cmd("windows", timeout=timeout)
        if status != "ok":
            raise KWinError(f"listagem de janelas falhou: {status}")
        return parse_window_list(payload)

    def active_window(self, timeout: float = 4.0) -> KWinWindow | None:
        status, payload = self._cmd("active", timeout=timeout)
        return KWinWindow.parse(payload) if status == "ok" else None

    def window_under_cursor(self, timeout: float = 4.0) -> KWinWindow | None:
        status, payload = self._cmd("cursor", timeout=timeout)
        return KWinWindow.parse(payload) if status == "ok" else None

    def activate(self, window_id: str, timeout: float = 4.0) -> bool:
        status, _ = self._cmd("activate", window_id, timeout=timeout)
        return status == "ok"

    def reset_cursor(self) -> None:
        """Não há cursor a restaurar no Wayland (mantido por compatibilidade)."""
        return None

    def reset_cursor(self) -> None:
        """Não há cursor a restaurar no Wayland (mantido por compatibilidade)."""
        return None

