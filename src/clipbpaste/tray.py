"""Bandeja do ClipB-Paste via StatusNotifierItem (o ``NotifyIcon`` do Windows).

O KDE Plasma mostra ícones pelo protocolo StatusNotifierItem, não pelo XEmbed
antigo. Publicamos o item em ``org.kde.StatusNotifierItem-<pid>-1`` e registramos no
``org.kde.StatusNotifierWatcher``.

Por que GDBus (Gio) e não dbus-python: o dbus-python 1.3 desta máquina falha ao
fazer marshalling de ``a{sv}``/``a(ia{sv}av)`` quando o dicionário mistura tipos
(ex.: string + bool ou string + int) — o erro é o enigmático "Expected a string or
unicode object". O menu da bandeja usa exatamente essas estruturas, então todo o
StatusNotifierItem e o dbusmenu são servidos por uma conexão GDBus que é dona do
nome no barramento.

Ícones: reaproveitamos ``Target``/``TargetDark``/``Typing`` do original, convertidos
para PNG em ``data/icons``. O Plasma aceita ``IconName`` com caminho absoluto.
"""

from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .i18n import tr

log = logging.getLogger("clipbpaste")

if TYPE_CHECKING:  # pragma: no cover
    from .daemon import Daemon

ICON_DIR_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "data" / "icons",
    Path.home() / ".local/share/clipb-paste/icons",
    Path("/usr/share/clipb-paste/icons"),
)

WATCHER_SERVICE = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"


def icon_dir() -> Path:
    for candidate in ICON_DIR_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return ICON_DIR_CANDIDATES[0]


def _system_uses_dark_tray() -> bool:
    """Lê a preferência do Plasma (equivale ao SystemUsesLightTheme do Windows)."""
    config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    path = Path(config_home) / "kdeglobals"
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "ColorScheme":
                scheme = value.strip().lower()
                return "dark" in scheme
    except OSError:
        pass
    return True  # o Plasma moderno usa tema escuro por padrão


def icon_for(state: str) -> str:
    """Nome do ícone no tema (o Plasma resolve nomes, não caminhos de arquivo).

    Descobrimos observando os outros itens da bandeja: eles expõem ``IconName``
    como "video-display", "update-high"… Um caminho absoluto de PNG faz o Plasma
    desenhar um ícone VAZIO — o app fica invisível, "entre dois ícones".

    Os PNGs são instalados pelo ``scripts/install-icons.sh`` em
    ~/.local/share/icons/hicolor/<tam>/apps/.
    """
    if state == "typing":
        return "clipb-paste-typing"
    return "clipb-paste" if _system_uses_dark_tray() else "clipb-paste-light"


def install_icons() -> list[str]:
    """Copia os PNGs do projeto para o tema hicolor do usuário. Retorna o que instalou."""
    import shutil

    theme = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "icons" / "hicolor"
    sources = {
        "clipbpaste": "Target-32.png",
        "clipb-paste-light": "TargetDark-32.png",
        "clipb-paste-typing": "Typing-32.png",
    }
    installed: list[str] = []
    for name, base in sources.items():
        src = icon_dir() / base
        if not src.is_file():
            continue
        for size in (16, 22, 24, 32, 48, 64):
            target_dir = theme / f"{size}x{size}" / "apps"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{name}.png"
            if not target.exists() or target.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, target)
            installed.append(str(target))
    return installed


# ------------------------------------------------------------------ XML
ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="Activate">
      <arg type="i" direction="in"/><arg type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" direction="in"/><arg type="i" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" direction="in"/><arg type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" direction="in"/><arg type="s" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus"><arg type="s"/></signal>
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
  </interface>
</node>
"""

PROPERTIES_XML = """
<node>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg type="s" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="out"/>
    </method>
    <method name="GetAll">
      <arg type="s" direction="in"/><arg type="a{sv}" direction="out"/>
    </method>
    <method name="Set">
      <arg type="s" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="in"/>
    </method>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/>
      <arg type="as" direction="in"/>
      <arg type="u" direction="out"/>
      <arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetChildren">
      <arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="a(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="as" direction="in"/><arg type="as" direction="in"/>
      <arg type="a{sv}" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/>
      <arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" direction="in"/><arg type="b" direction="out"/>
    </method>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})"/><arg type="a(ias)"/>
    </signal>
    <!-- O Plasma lê estas propriedades para saber se pode montar o menu. -->
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
  </interface>
</node>
"""


class Tray:
    """Ícone, menu e o loop principal do app."""

    # Menu enxuto: só o que o usuário pediu. O comportamento principal é o
    # clique esquerdo no ícone; o menu serve para configuração e saída.
    # Os rótulos são resolvidos por tr() em tempo de construção do menu, então
    # trocar o idioma nas Configurações já reflete no próximo menu aberto.
    ITEMS = (
        (2, "tray.menu.stop", False, True),
        (5, "", True, True),
        (4, "tray.menu.settings", False, True),
        (6, "", True, True),
        (7, "tray.menu.quit", False, True),
    )

    def __init__(self, daemon: "Daemon") -> None:
        self.daemon = daemon
        self._state = "idle"
        self._backend_name = daemon.backend.name if daemon.backend else "nenhum"
        self._loop: Any = None
        self._conn: Any = None
        self._item_info = None
        self._menu_info = None
        self._registration = None
        self._menu_registration = None
        self._revision = 0

    # ---------------------------------------------------------------- estado
    @property
    def state(self) -> str:
        return self._state

    def title(self) -> str:
        if self._state == "typing":
            return tr("tray.tooltip.typing")
        if self._backend_name == "nenhum":
            return tr("tray.tooltip.no_backend")
        return tr("tray.tooltip.idle")

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._emit("NewIcon")
        self._emit("NewToolTip")

    def set_backend(self, name: str) -> None:
        self._backend_name = name
        self._emit("NewToolTip")

    def set_language(self, code: str) -> None:
        """Reaplica os textos quando o idioma muda nas Configurações.

        O Plasma lê os rótulos do menu uma vez; sem avisar, o menu continuaria no
        idioma antigo. Emitimos LayoutUpdated para ele recarregar a árvore, e
        NewToolTip para o tooltip.
        """
        from .i18n import set_language

        set_language(code)
        self._revision += 1
        self._emit("NewToolTip", "org.kde.StatusNotifierItem")
        self._emit_layout_updated()

    def notify(self, title: str, body: str) -> None:
        try:
            from gi.repository import Gio, GLib

            conn = self._conn or Gio.bus_get_sync(Gio.BusType.SESSION, None)
            params = GLib.Variant("(susssasa{sv}i)", (
                "ClipB-Paste", 0, "dialog-warning", title, body, [], {}, 5000,
            ))
            conn.call(
                "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "Notify", params, None,
                Gio.DBusCallFlags.NONE, 2000, None, None,
            )
        except Exception as exc:
            log.debug("notificação indisponível: %s", exc)

    def _emit(self, signal: str, iface: str = "org.kde.StatusNotifierItem") -> None:
        try:
            if self._conn is not None:
                self._conn.emit_signal(None, ITEM_PATH, iface, signal, None)
        except Exception as exc:
            log.debug("sinal %s falhou: %s", signal, exc)

    def _emit_layout_updated(self) -> None:
        """Avisa o dbusmenu de que a árvore mudou (usado ao trocar de idioma)."""
        from gi.repository import GLib

        try:
            if self._conn is not None:
                self._conn.emit_signal(
                    None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                    GLib.Variant("(ui)", (self._revision, 0)),
                )
        except Exception as exc:
            log.debug("LayoutUpdated falhou: %s", exc)

    # ---------------------------------------------------------------- ciclo
    @property
    def connection(self):
        """Conexão GDBus dona do nome org.clipbpaste.Linux (None antes de publish)."""
        return self._conn

    def publish(self) -> None:
        """Toma posse de ``org.clipbpaste.Linux`` e exporta ícone e menu.

        Precisa acontecer ANTES de o KWinBridge exportar ``/ClipB-Paste``: o
        ``register_object`` só funciona na conexão dona do nome.
        """
        from gi.repository import Gio

        self._conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._owner = Gio.bus_own_name_on_connection(
            self._conn, "org.clipbpaste.Linux", Gio.BusNameOwnerFlags.NONE, None, None
        )

        # ATENÇÃO: GDBus mantém UM registro por caminho — um segundo register_object
        # no mesmo path apaga o primeiro. Por isso as propriedades e os métodos do
        # item ficam na MESMA interface declarada em ITEM_XML.
        node = Gio.DBusNodeInfo.new_for_xml(ITEM_XML)
        self._item_info = node.interfaces[0]
        self._registration = self._conn.register_object(
            ITEM_PATH, self._item_info, self._on_item_call, self._on_item_get, None
        )
        self._menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self._menu_registration = self._conn.register_object(
            MENU_PATH, self._menu_info, self._on_menu_call, self._on_menu_get, None
        )

    def run(self) -> None:
        """Roda o GLib até ``quit`` (assume que ``publish`` já rodou)."""
        from gi.repository import GLib

        if self._conn is None:
            self.publish()

        self._loop = GLib.MainLoop()
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        signal.signal(signal.SIGTERM, lambda *_: self.quit())

        GLib.idle_add(self._register_with_watcher)
        self._loop.run()

    def quit(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.quit()

    def _register_with_watcher(self) -> bool:
        from gi.repository import Gio, GLib

        try:
            self._conn.call(
                WATCHER_SERVICE, WATCHER_PATH, WATCHER_SERVICE,
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (ITEM_PATH,)),
                None, Gio.DBusCallFlags.NONE, 3000, None, self._on_registered,
            )
        except Exception as exc:
            log.warning("não consegui registrar o ícone na bandeja: %s", exc)
        return False

    def _on_registered(self, conn, result) -> None:
        try:
            conn.call_finish(result)
            log.info("ícone registrado na bandeja (StatusNotifierItem)")
        except Exception as exc:
            log.warning("registro na bandeja falhou: %s", exc)

    # ---------------------------------------------------------------- item
    def _item_properties(self) -> dict[str, Any]:
        from gi.repository import GLib

        title = self.title()
        return {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "clipb-paste"),
            "Title": GLib.Variant("s", "ClipB-Paste"),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", icon_for(self._state)),
            "IconThemePath": GLib.Variant("s", str(icon_dir())),
            # False = clique ESQUERDO ativa o item (cola); clique DIREITO abre o
            # menu declarado em "Menu". Com True, o Plasma trata o esquerdo como
            # "abrir menu" e o Activate nunca chega — foi o que fez "parar de colar".
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
            "ToolTip": GLib.Variant("(sa(iiay)ss)",
                                    (icon_for(self._state), [], "ClipB-Paste", title)),
        }

    def _on_properties_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        from gi.repository import Gio, GLib

        props = self._item_properties()
        if method == "GetAll":
            invocation.return_value(GLib.Variant.new_tuple(GLib.Variant("a{sv}", props)))
        elif method == "Get":
            # assinatura: Get(interface_name, property_name)
            _iface_name, name = params.unpack()
            name = str(name)
            if name in props:
                # a saída é (v): o valor precisa estar empacotado num variant
                invocation.return_value(GLib.Variant.new_tuple(
                    GLib.Variant("v", props[name])
                ))
            else:
                invocation.return_error_literal(
                    Gio.io_error_quark(), Gio.IOErrorEnum.NOT_FOUND,
                    f"propriedade desconhecida: {name}",
                )
        else:
            invocation.return_value(None)

    def _on_item_get(self, _conn, _sender, _path, _iface, prop, *_args):
        from gi.repository import GLib

        props = self._item_properties()
        if prop not in props:
            return None
        # Com a propriedade declarada no XML, o GDBus empacota sozinho: devolvemos
        # o GLib.Variant cru. (Devolver "(v)" aqui resultava em vídeo empacotado.)

        return props[prop]

    def _on_item_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        from gi.repository import GLib

        if method == "Activate":
            # Clicar no ícone ENQUANTO digita para a digitação em andamento.
            # É a saída de emergência: colou no lugar errado, clique e parou.
            if self.daemon.typing_now:
                log.info("ícone clicado durante a digitação — parando")
                self.daemon.stop_typing()
            else:
                log.info("ícone clicado — iniciando digitação")
                self.daemon.start_typing()
            invocation.return_value(None)
        elif method == "SecondaryActivate":
            self.daemon.open_settings()
            invocation.return_value(None)
        elif method in ("ContextMenu", "Scroll"):
            invocation.return_value(None)
        else:
            invocation.return_value(GLib.Variant("()", ()))

    # ---------------------------------------------------------------- menu
    def _props_for(self, item_id: int, label: str, separator: bool, enabled: bool):
        from gi.repository import GLib

        if separator:
            return {"type": GLib.Variant("s", "separator")}
        return {
            # `label` é a CHAVE de tradução (tray.menu.*), resolvida aqui para que
            # a troca de idioma valha no próximo menu aberto.
            "label": GLib.Variant("s", tr(label)),
            "enabled": GLib.Variant("b", enabled),
            "visible": GLib.Variant("b", True),
        }

    def _item_struct(self, item_id: int, label: str, sep: bool, en: bool):
        """Um item (ia{sv}av), montado com VariantBuilder."""
        from gi.repository import GLib

        props = GLib.Variant("a{sv}", self._props_for(item_id, label, sep, en))
        b = GLib.VariantBuilder.new(GLib.VariantType.new("(ia{sv}av)"))
        b.add_value(GLib.Variant("i", item_id))
        b.add_value(props)
        b.add_value(GLib.Variant("av", []))
        return b.end()

    def _children_array(self):
        """a(ia{sv}av) com todos os itens do menu."""
        from gi.repository import GLib

        b = GLib.VariantBuilder.new(GLib.VariantType.new("a(ia{sv}av)"))
        for item_id, label, sep, en in self.ITEMS:
            b.add_value(self._item_struct(item_id, label, sep, en))
        return b.end()

    def _layout_variant(self, parent_id: int):
        """(ia{sv}av) da raiz: os filhos vão empacotados como variants no ``av``."""
        from gi.repository import GLib

        b = GLib.VariantBuilder.new(GLib.VariantType.new("(ia{sv}av)"))
        b.add_value(GLib.Variant("i", parent_id))
        b.add_value(GLib.Variant("a{sv}", {
            "children-display": GLib.Variant("s", "submenu"),
        }))
        av = GLib.VariantBuilder.new(GLib.VariantType.new("av"))
        for item_id, label, sep, en in self.ITEMS:
            av.add_value(GLib.Variant("v", self._item_struct(item_id, label, sep, en)))
        b.add_value(av.end())
        return b.end()

    def _on_menu_get(self, _conn, _sender, _path, _iface, prop, *_args):
        return self._menu_properties().get(prop)

    def _on_menu_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        from gi.repository import Gio, GLib

        try:
            if method == "GetLayout":
                parent = params.unpack()[0]
                if parent == 0:
                    # (ia{sv}av) da raiz, com os filhos reais
                    raiz = self._layout_variant(parent)
                else:
                    raiz = GLib.Variant("(ia{sv}av)", (parent, {}, []))
                invocation.return_value(GLib.Variant.new_tuple(
                    GLib.Variant("u", self._revision), raiz
                ))
            elif method == "GetChildren":
                parent = params.unpack()[0]
                children = self._children_array() if parent == 0 \
                    else GLib.Variant.new_array(GLib.VariantType.new("(ia{sv}av)"))
                invocation.return_value(GLib.Variant.new_tuple(children))
            elif method == "GetGroupProperties":
                ids = set(params.unpack()[0])
                wanted = ids or {i for i, *_ in self.ITEMS}
                group_builder = GLib.VariantBuilder.new(GLib.VariantType.new("a{sv}"))
                for item_id, label, sep, en in self.ITEMS:
                    if item_id in wanted:
                        group_builder.add_value(GLib.Variant(
                            "{sv}", {str(item_id): GLib.Variant("a{sv}", self._props_for(item_id, label, sep, en))}
                        ))
                invocation.return_value(GLib.Variant.new_tuple(group_builder.end()))
            elif method == "Event":
                unpacked = params.unpack()
                item_id, event_id = unpacked[0], unpacked[1]
                if event_id == "clicked":
                    self._dispatch(item_id)
                invocation.return_value(None)
            elif method == "AboutToShow":
                invocation.return_value(GLib.Variant.new_tuple(GLib.Variant("b", False)))
            else:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                    f"método desconhecido: {method}",
                )
        except Exception as exc:
            log.error("menu: %s falhou: %s", method, exc)
            try:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(), Gio.DBusError.FAILED, str(exc)
                )
            except Exception:
                pass

    def _dispatch(self, item_id: int) -> None:
        try:
            if item_id == 2:
                log.info("menu: parar digitação")
                self.daemon.stop_typing()
            elif item_id == 4:
                log.info("menu: configurações")
                self.daemon.open_settings()
            elif item_id == 7:
                log.info("menu: sair")
                self.daemon.quit()
        except Exception as exc:
            log.error("ação do menu %s falhou: %s", item_id, exc)


def create(daemon: "Daemon") -> Tray:
    tray = Tray(daemon)
    daemon._tray = tray
    return tray