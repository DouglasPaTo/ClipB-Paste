"""Daemon do ClipB-Paste: bandeja, atalho global KWin e digitação.

Equivale ao ``TrayApplicationContext`` do original, mas separado em partes:

* :mod:`clipbpaste.tray` — ícone e menu (StatusNotifierItem);
* :mod:`clipbpaste.kwin` — atalho global e identificação da janela alvo;
* :mod:`clipbpaste.typing` — a digitação em si.

O daemon também expõe o serviço D-Bus ``org.clipbpaste.Linux`` que o script do KWin
usa para avisar "o atalho foi apertado". Sem esse serviço, o atalho não faz nada.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time

from . import clipboard, config, kwin, typing
from .i18n import set_language, tr
from .backends import resolve as resolve_backend

log = logging.getLogger("clipbpaste")


class Daemon:
    def __init__(self, cfg: config.Config | None = None) -> None:
        self.cfg = cfg or config.Config.load()
        self.typer: typing.Typer | None = None
        self.backend = None
        self._stop = threading.Event()
        self._bus = None
        self._bus_name = None
        self._host = None
        self._bridge: kwin.KWinBridge | None = None
        self._picking = False

    # ---------------------------------------------------------------- ciclo
    def run(self) -> int:
        set_language(self.cfg.language)   # textos da bandeja/mensagens
        self._attach_mainloop()
        self._check_single_instance()
        self._pick_backend()
        tray = self._start_tray()
        tray.publish()          # dona do nome org.clipbpaste.Linux
        self._start_dbus_service()  # exporta /ClipB-Paste nessa conexão
        self._install_signals()

        log.info("ClipB-Paste pronto (backend=%s)",
                 self.backend.name if self.backend else "NENHUM")
        if self.backend is None:
            log.warning("nenhum backend de digitação disponível — o app abre, mas não digita")
        try:
            tray.run()  # bloqueia até o "Sair"
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        log.info("encerrando")
        self._stop.set()
        if self.typer:
            self.typer.cancel()
        if self._host is not None:
            try:
                self._host.remove_from_connection()
            except Exception:
                pass

    def _install_signals(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self._stop.set())

    def _check_single_instance(self) -> None:
        """Equivalente ao Mutex do original: só um ClipB-Paste por vez."""
        pid_file = config.pid_path()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        if pid_file.exists():
            try:
                other = int(pid_file.read_text().strip())
                os.kill(other, 0)
                raise SystemExit(f"já existe um ClipB-Paste rodando (pid {other})")
            except (ValueError, ProcessLookupError, PermissionError):
                pass
        pid_file.write_text(str(os.getpid()))
        import atexit

        atexit.register(lambda: pid_file.exists() and pid_file.unlink())

    def _pick_backend(self) -> None:
        backend, report = resolve_backend(self.cfg.backend)
        for status in report:
            log.debug("%s", status.describe())
        self.backend = backend
        if backend is not None:
            self.typer = typing.Typer(backend)

    # ---------------------------------------------------------------- D-Bus
    @staticmethod
    def _attach_mainloop() -> None:
        """O dbus-python exige um main loop para exportar objetos e receber chamadas."""
        try:
            import dbus
            import dbus.mainloop.glib

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        except Exception as exc:
            log.warning("não consegui anexar o loop GLib ao D-Bus: %s", exc)

    def _start_dbus_service(self) -> None:
        """Liga o objeto /ClipB-Paste à conexão da bandeja (que é dona do nome)."""
        self._bridge = kwin.KWinBridge.create()
        if self._bridge is None:
            log.warning("KWin/D-Bus indisponível: o atalho global não vai funcionar")
            return
        self._bridge.set_abort_callback(lambda: self.typer and self.typer.cancel())
        if self._tray is not None:
            self._bridge.set_gdbus_connection(self._tray.connection)
        self._bridge.export_host()
        log.info("serviço D-Bus %s pronto", kwin.CP_SERVICE)

    # ---------------------------------------------------------------- KWin
    # ---------------------------------------------------------------- ações
    def start_typing(self) -> None:
        """Lê o clipboard e digita na janela alvo."""
        if self.typer is None:
            self._notify_error(tr("error.no_backend.title"), tr("error.no_backend.body"))
            return
        try:
            text = typing.read_clipboard_text()
        except typing.ClipboardError as exc:
            self._notify_error(tr("error.no_clipboard.title"), str(exc))
            return
        if not text:
            content = clipboard.read()
            if content.is_image:
                    self._notify_error(
                    tr("error.image_clipboard.title"), tr("error.image_clipboard.body")
                )
            else:
                log.info("clipboard vazio — nada a digitar")
            return

        # Clicar no ícone da bandeja manda o foco para o painel do Plasma, então a
        # "janela ativa" deixa de ser a que o usuário quer. Ativamos a janela sob o
        # ponteiro ANTES de digitar — é o equivalente do "clique no alvo" original.
        self._activate_target()

        # Avisa quando o backend não dá conta de algum caractere (acentos no uinput),
        # para o texto não sair silenciosamente errado.
        faltando = self.typer._backend.unsupported_chars(text)
        if faltando:
            log.warning("o backend %s não digita: %s", self.typer.backend_name, faltando)
            from .i18n import tr as _tr

            self._notify_error(
                _tr("error.unicode.title", backend=self.typer.backend_name),
                _tr("error.unicode.body", chars=faltando),
            )

        if self.cfg.confirm and len(text) > self.cfg.confirm_over:
            target = self._target_description()
            if not self._ask_confirm(len(text), target):
                log.info("digitação cancelada pelo usuário")
                return

        log.info("digitando %d caracteres com %s", len(text), self.typer.backend_name)
        self._set_tray_state("typing")
        self.typer.type_text_async(
            text,
            key_delay_ms=self.cfg.key_delay_ms,
            start_delay_ms=self.cfg.start_delay_ms,
            on_done=lambda: self._set_tray_state("idle"),
            on_error=lambda exc: (
                self._notify_error(tr("error.typing.title"), str(exc)),
                self._set_tray_state("idle"),
            ),
        )

    def _activate_target(self) -> None:
        """Foca a janela sob o ponteiro, para a digitação cair no lugar certo."""
        if self._bridge is None:
            return
        try:
            win = self._bridge.window_under_cursor()
        except kwin.KWinError as exc:
            log.debug("não consegui ler a janela sob o cursor: %s", exc)
            return
        if win is None:
            log.info("nenhuma janela sob o ponteiro; usando a janela ativa")
            return
        try:
            self._bridge.activate(win.id)
            log.info("alvo: %s", win.describe())
            # Dá tempo do compositor processar a troca de foco antes das teclas.
            time.sleep(0.15)
        except kwin.KWinError as exc:
            log.warning("não consegui ativar %s: %s", win.describe(), exc)

    def _target_description(self) -> str:
        if self._bridge:
            try:
                win = self._bridge.window_under_cursor() or self._bridge.active_window()
                if win:
                    return win.describe()
            except kwin.KWinError:
                pass
        return "janela ativa"

    def _ask_confirm(self, count: int, target: str) -> bool:
        try:
            from . import ui

            return ui.confirm_typing(count, target)
        except Exception as exc:
            log.warning("sem diálogo de confirmação (%s); digitando mesmo assim", exc)
            return True

    # ---------------------------------------------------------------- utilitários
    def _start_tray(self):
        from . import tray

        return tray.create(self)

    def _set_tray_state(self, state: str) -> None:
        tray = getattr(self, "_tray", None)
        if tray is not None:
            tray.set_state(state)

    def _notify_error(self, title: str, body: str) -> None:
        log.error("%s: %s", title, body)
        tray = getattr(self, "_tray", None)
        if tray is not None:
            tray.notify(title, body)

    def show_doctor(self) -> None:
        """Roda o diagnóstico e mostra o resultado numa notificação."""
        from .cli import cmd_doctor

        import io
        import contextlib

        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                cmd_doctor(None)
        except Exception as exc:
            log.error("diagnóstico falhou: %s", exc)
            return
        report = buffer.getvalue()
        log.info("diagnóstico:\n%s", report)
        self._notify_error("Diagnóstico do ClipB-Paste", report.strip()[-400:])

    def open_settings(self) -> None:
        from . import ui

        ui.run_settings(self.cfg, on_saved=self._reload_settings)

    def _reload_settings(self) -> None:
        """Reaplica o que a janela de configurações pode ter mudado.

        O backend era escolhido só no arranque, então trocar "Como digitar" na
        interface não tinha efeito nenhum. Aqui ele é reescolhido de fato.
        """
        set_language(self.cfg.language)
        log.info("configurações alteradas; reaplicando")

        # --- backend de digitação ---
        previous = self.backend.name if self.backend else None
        backend, report = resolve_backend(self.cfg.backend)
        if backend is not None and backend.name != previous:
            self.backend = backend
            self.typer = typing.Typer(backend)
            log.info("backend de digitação: %s -> %s", previous or "nenhum", backend.name)
        elif backend is None:
            log.warning("o backend pedido (%s) não está disponível", self.cfg.backend)
            for status in report:
                if not status.available:
                    log.warning("  %s", status.describe())

        # --- estado da bandeja (inclui os textos traduzidos) ---
        tray = getattr(self, "_tray", None)
        if tray is not None:
            tray.set_backend(self.backend.name if self.backend else "nenhum")
            tray.set_language(self.cfg.language)

    def quit(self) -> None:
        self._shutdown()
        from gi.repository import GLib

        GLib.idle_add(lambda: (self._loop_quit(), False)[1])

    def _loop_quit(self) -> None:
        tray = getattr(self, "_tray", None)
        if tray is not None:
            tray.quit()