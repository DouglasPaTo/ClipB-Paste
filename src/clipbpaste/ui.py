"""Janela de configurações (equivalente ao ``SettingsForm`` do original).

O original usava WinForms; aqui usamos GTK4 direto, que é o que o TUXEDO OS já tem
instalado (python3-gi). O diálogo de confirmação também mora aqui.

Detalhe herdado do original: o rodapé esquerdo mostra a versão, com fonte menor que
os demais rótulos (lá era ``versionLabel``, 8pt, ancorado em Bottom|Left).
"""

from __future__ import annotations

import logging
from typing import Callable

from . import __version__
from .config import Config
from .i18n import current_language, normalize, set_language, tr, ui_languages

log = logging.getLogger("clipb-paste")

_CSS = b"""
window { background: @theme_bg_color; }
.title { font-size: 1.15em; font-weight: bold; }
.hint { opacity: 0.7; font-size: 0.9em; }
.version { opacity: 0.6; font-size: 0.8em; }
.card { padding: 12px; border-radius: 8px; background: alpha(currentColor, 0.05); }
"""


def app_title() -> str:
    return tr("settings.title")


def _gi():
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    return Gtk


def run_settings(cfg: Config, on_saved: Callable[[], None] | None = None) -> bool:
    """Abre a janela de configurações. Retorna True se o usuário salvou."""
    Gtk = _gi()

    set_language(cfg.language)
    app = Gtk.Application(application_id="org.clipbpaste.Linux.Settings")
    saved = {"value": False}

    def on_activate(application):
        window = SettingsWindow(
            cfg, on_saved=on_saved,
            on_close=lambda ok: (saved.__setitem__("value", ok), application.quit()),
        )
        window.present()

    app.connect("activate", on_activate)
    app.run([])
    return saved["value"]


class SettingsWindow:
    """Constrói a janela e mantém o estado dos widgets."""

    def __init__(self, cfg: Config, *, on_saved=None, on_close=None) -> None:
        Gtk = _gi()

        # O idioma vem da config: aplica ANTES de montar qualquer texto.
        set_language(cfg.language)

        self.Gtk = Gtk
        self.cfg = cfg
        self.on_saved = on_saved
        self.on_close = on_close
        self.saved = False

        self.window = Gtk.ApplicationWindow(title=app_title())
        self.window.set_default_size(520, 620)

        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.window.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.set_child(outer)

        # ---- conteúdo rolável (a janela ficou mais alta com a seção de idioma) ----
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        outer.append(scroll)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_top(18)
        box.set_margin_bottom(6)
        box.set_margin_start(18)
        box.set_margin_end(18)
        scroll.set_child(box)

        box.append(self._title("ClipB-Paste"))
        box.append(self._hint(tr("settings.intro")))

        box.append(self._timing_card())
        box.append(self._confirm_card())
        box.append(self._language_card())

        # ---- rodapé: botões à direita, versão à esquerda ----
        outer.append(self._footer())

    # ---------------------------------------------------------------- widgets
    def _title(self, text: str):
        Gtk = self.Gtk
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("title")
        return label

    def _hint(self, text: str):
        Gtk = self.Gtk
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class("hint")
        return label

    def _card(self, title_key: str):
        Gtk = self.Gtk
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        frame.add_css_class("card")
        heading = Gtk.Label(label=tr(title_key), xalign=0)
        heading.add_css_class("title")
        frame.append(heading)
        return frame

    def _row(self, label_key: str, widget):
        Gtk = self.Gtk
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        text = Gtk.Label(label=tr(label_key), xalign=0)
        text.set_hexpand(True)
        row.append(text)
        row.append(widget)
        return row

    def _spin(self, value: int, lower: int = 0, upper: int = 10000, step: int = 5):
        Gtk = self.Gtk
        spin = Gtk.SpinButton.new_with_range(lower, upper, step)
        spin.set_value(value)
        spin.set_digits(0)
        return spin

    def _timing_card(self):
        card = self._card("settings.section.typing")
        self.delay = self._spin(self.cfg.key_delay_ms, 0, 1000, 1)
        card.append(self._row("settings.key_delay", self.delay))
        self.start_delay = self._spin(self.cfg.start_delay_ms, 0, 5000, 50)
        card.append(self._row("settings.start_delay", self.start_delay))
        card.append(self._hint(tr("settings.delay_hint")))

        # Só oferecemos métodos que funcionam nesta plataforma.
        from .backends import resolve as _resolve

        _backend, _report = _resolve("auto")
        disponiveis = {s.name for s in _report if s.available}
        opcoes = [("auto", tr("backend.auto"))]
        if "ydotool" in disponiveis:
            opcoes.append(("ydotool", tr("backend.ydotool")))
        if "uinput" in disponiveis:
            opcoes.append(("uinput", tr("backend.uinput")))
        if "wtype" in disponiveis:
            opcoes.append(("wtype", tr("backend.wtype")))
        opcoes.append(("stdout", tr("backend.stdout")))

        self._backend_order = [key for key, _ in opcoes]
        self.backend = self.Gtk.DropDown.new_from_strings([label for _, label in opcoes])
        current = self._backend_order.index(self.cfg.backend) if self.cfg.backend in self._backend_order else 0
        self.backend.set_selected(current)
        card.append(self._row("settings.backend", self.backend))
        card.append(self._hint(tr("settings.backend_hint")))
        return card

    def _confirm_card(self):
        card = self._card("settings.section.confirm")
        self.confirm = self.Gtk.CheckButton(label=tr("settings.confirm_enable"))
        self.confirm.set_active(self.cfg.confirm)
        card.append(self.confirm)
        self.confirm_over = self._spin(self.cfg.confirm_over, 1, 100000, 10)
        card.append(self._row("settings.confirm_over", self.confirm_over))
        self.confirm.connect("toggled", lambda btn: self.confirm_over.set_sensitive(btn.get_active()))
        self.confirm_over.set_sensitive(self.cfg.confirm)
        return card

    def _language_card(self):
        card = self._card("settings.section.language")
        self._language_keys = [code for code, _ in ui_languages()]
        self.language = self.Gtk.DropDown.new_from_strings([label for _, label in ui_languages()])
        atual = normalize(self.cfg.language)
        self.language.set_selected(
            self._language_keys.index(atual) if atual in self._language_keys else 0
        )
        card.append(self._row("settings.language", self.language))
        card.append(self._hint(tr("settings.language_hint")))
        return card

    def _footer(self):
        Gtk = self.Gtk
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_start(18)
        footer.set_margin_end(18)
        footer.set_margin_top(6)
        footer.set_margin_bottom(14)

        # Versão: canto inferior esquerdo, fonte menor que a dos rótulos.
        version = Gtk.Label(label=tr("settings.version", version=__version__), xalign=0)
        version.add_css_class("version")
        version.set_hexpand(True)
        version.set_valign(Gtk.Align.END)
        footer.append(version)

        cancel = Gtk.Button(label=tr("settings.cancel"))
        cancel.connect("clicked", lambda *_: self._close(False))
        save = Gtk.Button(label=tr("settings.save"))
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *_: self._save())
        footer.append(cancel)
        footer.append(save)
        return footer

    # ---------------------------------------------------------------- ações
    def present(self) -> None:
        self.window.present()

    def _save(self) -> None:
        self.cfg.key_delay_ms = int(self.delay.get_value())
        self.cfg.start_delay_ms = int(self.start_delay.get_value())
        self.cfg.confirm = self.confirm.get_active()
        self.cfg.confirm_over = int(self.confirm_over.get_value())
        self.cfg.backend = self._backend_order[self.backend.get_selected()]
        self.cfg.language = self._language_keys[self.language.get_selected()]
        self.cfg.validate()
        self.cfg.save()

        set_language(self.cfg.language)
        log.info("idioma definido para %s", current_language())

        self.saved = True
        if self.on_saved:
            self.on_saved()
        self._close(True)

    def _close(self, ok: bool) -> None:
        self.window.close()
        if self.on_close:
            self.on_close(ok)


def confirm_typing(count: int, target: str) -> bool:
    """Diálogo "Confirmar digitação de N caracteres?" (equivale ao MessageBox original)."""
    Gtk = _gi()

    dialog = Gtk.AlertDialog()
    dialog.set_message(tr("confirm.title", count=count))
    dialog.set_detail(tr("confirm.body", target=target))
    dialog.set_buttons([tr("confirm.cancel"), tr("confirm.ok")])
    dialog.set_cancel_button(0)
    dialog.set_default_button(1)

    holder: dict = {}

    def on_choice(_dialog, result):
        try:
            choice = _dialog.choose_finish(result)
        except Exception:
            choice = 0
        holder["choice"] = int(choice)
        holder["loop"].quit()

    from gi.repository import GLib

    loop = holder["loop"] = GLib.MainLoop()
    dialog.choose(None, None, on_choice)
    loop.run()
    return holder.get("choice", 0) == 1

def mostrar_dica_abortar() -> bool:
    """Aviso único explicando como parar a digitação.

    Aparece na primeira vez que um texto longo é digitado. Tem a caixa
    "Não mostrar novamente", que fica salva na configuração.

    Retorna True se o usuário quer continuar digitando.
    """
    Gtk = _gi()
    cfg = Config.load()

    dialog = Gtk.AlertDialog()
    dialog.set_message(tr("hint.abort.title"))
    dialog.set_detail(tr("hint.abort.body"))
    dialog.set_buttons([tr("hint.abort.cancel"), tr("hint.abort.continue")])
    dialog.set_cancel_button(0)
    dialog.set_default_button(1)

    # AlertDialog não tem checkbox; usamos uma janela própria para permitir
    # a opção "não mostrar novamente".
    window = Gtk.Window()
    window.set_title(tr("hint.abort.title"))
    window.set_default_size(520, 250)
    window.set_modal(False)

    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    caixa.set_margin_top(20); caixa.set_margin_bottom(20)
    caixa.set_margin_start(20); caixa.set_margin_end(20)
    window.set_child(caixa)

    titulo = Gtk.Label(xalign=0, wrap=True)
    titulo.set_markup(f"<b>{tr('hint.abort.title')}</b>")
    titulo.add_css_class("title")
    caixa.append(titulo)

    corpo = Gtk.Label(label=tr("hint.abort.body"), xalign=0, wrap=True)
    caixa.append(corpo)

    nao_mostrar = Gtk.CheckButton(label=tr("hint.abort.dont_show"))
    caixa.append(nao_mostrar)

    botoes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    botoes.set_halign(Gtk.Align.END)
    continuar = Gtk.Button(label=tr("hint.abort.continue"))
    continuar.add_css_class("suggested-action")

    resultado = {"continuar": True}

    def fechar(vai_continuar: bool) -> None:
        resultado["continuar"] = vai_continuar
        if nao_mostrar.get_active():
            cfg2 = Config.load()
            cfg2.show_abort_hint = False
            cfg2.save()
        window.close()

    continuar.connect("clicked", lambda *_: fechar(True))
    botoes.append(continuar)
    caixa.append(botoes)

    def on_close(*_):
        pass
    window.connect("close-request", lambda *_: (fechar(True), False)[1])

    app = Gtk.Application(application_id="org.clipbpaste.Linux.Hint")

    def on_activate(application):
        application.add_window(window)
        window.present()

    app.connect("activate", on_activate)
    app.run([])
    return resultado["continuar"]
