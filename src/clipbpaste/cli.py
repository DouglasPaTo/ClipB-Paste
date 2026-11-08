"""CLI do ClipB-Paste — diagnóstico, testes e controle.

Comandos::

    clipb-paste daemon                 # roda o app (bandeja + atalho)
    clipb-paste doctor                 # checklist do ambiente
    clipb-paste windows                # lista janelas do KWin
    clipb-paste target                 # mostra a janela sob o ponteiro
    clipb-paste type "texto"           # digita um texto qualquer
    clipb-paste type --clipboard       # digita o conteúdo do clipboard
    clipb-paste kwin-install           # carrega o script no KWin
    clipb-paste settings               # abre as configurações
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import clipboard, config

log = logging.getLogger("clipbpaste")

OK = "\033[32m✓\033[0m"
NO = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(stream)

    path = config.log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        handlers.append(file_handler)
    except OSError:
        pass

    logging.basicConfig(level=level, handlers=handlers, force=True)


# ------------------------------------------------------------------ doctor
def cmd_doctor(_args) -> int:
    from . import kwin
    from .backends import resolve

    print("ClipB-Paste — diagnóstico\n")

    def line(ok: bool, label: str, detail: str = "") -> None:
        mark = OK if ok else NO
        if ok is None:
            mark = WARN
        print(f"  {mark} {label}" + (f"\n      {detail}" if detail else ""))

    session = os.environ.get("XDG_SESSION_TYPE", "?")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "?")
    line(True, f"Sessão: {desktop} / {session}")

    clipboard_ok = clipboard.has_clipboard()
    line(clipboard_ok, "Clipboard (wl-paste)", "" if clipboard_ok else "instale wl-clipboard")
    if clipboard_ok:
        text = clipboard.read_text()
        line(True, f"Texto disponível: {len(text)} caractere(s)")

    kde_ok = kwin.is_kde()
    line(kde_ok, "KDE/Plasma detectado", "" if kde_ok else "a integração usa APIs do KWin")

    bridge = kwin.KWinBridge.create() if kde_ok else None
    if bridge is None:
        line(False, "KWin D-Bus", "não respondeu (python3-dbus instalado?)")
    else:
        try:
            windows = bridge.windows()
            line(True, f"Script do KWin ativo ({len(windows)} janela(s) visíveis)")
        except kwin.KWinError as exc:
            line(False, "Script do KWin", str(exc))

    backend, report = resolve("auto")
    print()
    print("  Backends de digitação:")
    for status in report:
        line(status.available, status.name, "" if status.available else status.reason)
    print()
    if backend is not None:
        line(True, f"Backend escolhido: {backend.name}")
    else:
        line(
            False,
            "Nenhum backend de digitação disponível",
            "Rode: ./scripts/enable-uinput.sh   (pede sudo uma vez e já testa)",
        )

    cfg = config.Config.load()
    print()
    line(True, f"Configuração: {config.config_path()}")
    line(True, f"Atraso entre teclas: {cfg.key_delay_ms} ms")
    line(True, f"Idioma: {cfg.language}")
    return 0 if backend is not None else 1


# ------------------------------------------------------------------ KWin
def _bridge():
    from . import kwin

    bridge = kwin.KWinBridge.create()
    if bridge is None:
        print("KWin não disponível (precisa de Plasma e python3-dbus).", file=sys.stderr)
        raise SystemExit(2)
    return bridge


def cmd_windows(_args) -> int:
    bridge = _bridge()
    try:
        windows = bridge.windows()
    except Exception as exc:
        print(f"Erro ao listar janelas: {exc}", file=sys.stderr)
        return 1
    if not windows:
        print("Nenhuma janela.")
        return 0
    for win in windows:
        marker = "*" if win.active else " "
        print(f"{marker} {win.truncated_caption(50):<52} {win.app_id:<22} pid={win.pid}")
    return 0


def cmd_target(_args) -> int:
    bridge = _bridge()
    win = bridge.window_under_cursor()
    if win is None:
        print("Nenhuma janela sob o ponteiro.")
        return 1
    print(f"{win.truncated_caption(60)}  [{win.app_id}]  pid={win.pid}  {win.width}x{win.height}")
    return 0


def cmd_kwin_install(_args) -> int:
    from . import kwin

    bridge = kwin.KWinBridge.create()
    if bridge is None:
        print("KWin não disponível.", file=sys.stderr)
        return 2
    try:
        ok = bridge.hello()
    except kwin.KWinError as exc:
        print(f"Falha: {exc}", file=sys.stderr)
        return 1
    print("Script do KWin respondendo." if ok else "O script carregou, mas não respondeu.")
    return 0 if ok else 1


# ------------------------------------------------------------------ digitação
def cmd_type(args) -> int:
    from .backends import resolve
    from .typing import Typer

    if args.clipboard:
        text = clipboard.read_text()
        if not text:
            print("O clipboard não tem texto.", file=sys.stderr)
            return 1
    else:
        text = " ".join(args.text) if args.text else sys.stdin.read()
    if not text:
        print("Nada para digitar.", file=sys.stderr)
        return 1

    backend, report = resolve(args.backend or config.Config.load().backend)
    if backend is None:
        print("Nenhum backend de digitação disponível:", file=sys.stderr)
        for status in report:
            if not status.available:
                print(f"  - {status.describe()}", file=sys.stderr)
        return 1

    print(f"Digitando {len(text)} caractere(s) com '{backend.name}'…", file=sys.stderr)
    typer = Typer(backend)
    typer.type_text_blocking(text, key_delay_ms=args.delay if args.delay is not None else 15)
    print("Pronto.", file=sys.stderr)
    return 0


# ------------------------------------------------------------------ app
def cmd_daemon(args) -> int:
    from .daemon import Daemon

    cfg = config.Config.load()
    if args.backend:
        cfg.backend = args.backend
    return Daemon(cfg).run()


def cmd_abort(_args) -> int:
    """Para a digitação em andamento (via D-Bus, falando com o daemon)."""
    from . import kwin

    if not kwin.is_kde():
        print("Precisa do KDE para falar com o daemon.", file=sys.stderr)
        return 2
    try:
        import dbus
        import dbus.mainloop.glib

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        proxy = dbus.Interface(
            bus.get_object(kwin.CP_SERVICE, kwin.CP_OBJECT, introspect=False), kwin.CP_IFACE
        )
        proxy.abort()
        print("Digitação interrompida.")
        return 0
    except Exception as exc:
        print(f"Não há digitação em andamento ({exc}).", file=sys.stderr)
        return 1


def cmd_autostart(args) -> int:
    """Liga ou desliga a inicialização automática com a sessão gráfica.

    Instala um .desktop em ~/.config/autostart, que é o mecanismo padrão
    (freedesktop) para iniciar aplicativos de bandeja no login. Funciona com
    ou sem .deb, e não exige sudo.
    """
    import os

    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    destino = Path(config_home) / "autostart" / "clipb-paste.desktop"

    # Se o .deb instalou o autostart de sistema, desligar exige bloquear por
    # usuário (Hidden=true), não só apagar o arquivo.
    sistema = Path("/etc/xdg/autostart/clipb-paste.desktop")

    if args.enable:
        executavel = sys.argv[0]
        if not executavel.startswith("/"):
            executavel = shutil_which("clipb-paste") or "/usr/bin/clipb-paste"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=ClipB-Paste\n"
            "Comment=Inicia o ClipB-Paste com a sessão gráfica\n"
            f"Exec={executavel} daemon\n"
            "Icon=clipb-paste\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n"
            "StartupNotify=false\n",
            encoding="utf-8",
        )
        print(f"início automático ativado: {destino}")
        return 0

    if args.disable:
        if sistema.is_file():
            # bloqueia o autostart de sistema só para este usuário
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=ClipB-Paste\n"
                "Exec=/usr/bin/clipb-paste daemon\n"
                "Hidden=true\n",
                encoding="utf-8",
            )
            print(f"início automático desativado para este usuário: {destino}")
        elif destino.is_file():
            destino.unlink()
            print("início automático desativado")
        else:
            print("o início automático já estava desativado")
        return 0

    # sem --enable/--disable: mostra o estado
    if destino.is_file() and "Hidden=true" in destino.read_text(encoding="utf-8"):
        print("início automático: desativado (bloqueado pelo usuário)")
    elif destino.is_file():
        print(f"início automático: ativado ({destino})")
    elif sistema.is_file():
        print(f"início automático: ativado pelo pacote ({sistema})")
    else:
        print("início automático: desativado")
        print("  Ative com: clipb-paste autostart --enable")
    return 0


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def cmd_enable_uinput(_args) -> int:
    """Cria a regra udev que libera /dev/uinput (precisa de sudo).

    Equivale ao scripts/enable-uinput.sh, mas disponível como subcomando do app
    instalado — o usuário do .deb não tem o script à mão.
    """
    import os
    import subprocess
    import tempfile

    if os.geteuid() != 0:
        print("Este comando precisa de root. Rode:", file=sys.stderr)
        print("  sudo clipb-paste enable-uinput", file=sys.stderr)
        return 2

    regra = (
        'KERNEL=="uinput", GROUP="input", MODE="0660", '
        'OPTIONS+="static_node=uinput"\n'
    )
    destino = Path("/etc/udev/rules.d/60-uinput-clipb-paste.rules")

    print(f"criando {destino}")
    destino.write_text(regra, encoding="utf-8")

    print("recarregando as regras do udev")
    for cmd in (["udevadm", "control", "--reload-rules"],
                ["udevadm", "trigger", "--name-match=uinput"]):
        try:
            subprocess.run(cmd, check=False, capture_output=True)
        except FileNotFoundError:
            print(f"aviso: {cmd[0]} não encontrado", file=sys.stderr)

    # aplica na hora, mesmo que o udev demore
    for cmd in (["chgrp", "input", "/dev/uinput"], ["chmod", "0660", "/dev/uinput"]):
        subprocess.run(cmd, check=False, capture_output=True)

    # o usuário precisa estar no grupo input
    usuario = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
    if usuario:
        grupos = subprocess.run(["id", "-nG", usuario], capture_output=True, text=True)
        if "input" not in grupos.stdout.split():
            print(f"adicionando {usuario} ao grupo 'input'")
            subprocess.run(["usermod", "-aG", "input", usuario], check=False)
            print()
            print("!! Faça LOGOUT e LOGIN para o grupo valer em sessões novas.")
    print()
    print("Pronto. Verifique com: clipb-paste doctor")
    return 0


def cmd_settings(_args) -> int:
    from . import ui

    cfg = config.Config.load()
    ui.run_settings(cfg)
    return 0


def cmd_show_settings(_args) -> int:
    return cmd_settings(_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipbpaste",
        description="ClipB-Paste — digita o conteúdo do clipboard na janela que você apontar (Linux/KDE).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    from . import __version__

    parser.add_argument(
        "--version", action="version",
        version=f"ClipB-Paste {__version__}",
    )

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("daemon", help="roda a bandeja (ícone de digitação)")
    p.add_argument("--backend", choices=["auto", "ydotool", "wtype", "uinput", "eis", "stdout"])
    p.set_defaults(func=cmd_daemon)

    p = sub.add_parser("doctor", help="verifica o ambiente")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("windows", help="lista as janelas do KWin")
    p.set_defaults(func=cmd_windows)

    p = sub.add_parser("target", help="mostra a janela sob o ponteiro")
    p.set_defaults(func=cmd_target)

    p = sub.add_parser("type", help="digita um texto")
    p.add_argument("text", nargs="*", help="texto a digitar (ou use o stdin)")
    p.add_argument("--clipboard", action="store_true", help="usa o conteúdo do clipboard")
    p.add_argument("--backend", choices=["auto", "ydotool", "wtype", "uinput", "eis", "stdout"])
    p.add_argument("--delay", type=int, help="atraso entre teclas (ms)")
    p.set_defaults(func=cmd_type)

    p = sub.add_parser("kwin-install", help="carrega o script no KWin")
    p.set_defaults(func=cmd_kwin_install)

    p = sub.add_parser("autostart", help="iniciar junto com a sessão gráfica")
    p.add_argument("--enable", action="store_true", help="ativar")
    p.add_argument("--disable", action="store_true", help="desativar")
    p.set_defaults(func=cmd_autostart)

    p = sub.add_parser("enable-uinput", help="libera /dev/uinput (precisa de sudo)")
    p.set_defaults(func=cmd_enable_uinput)

    p = sub.add_parser("abort", help="para uma digitação em andamento")
    p.set_defaults(func=cmd_abort)

    p = sub.add_parser("settings", help="abre as configurações")
    p.set_defaults(func=cmd_settings)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # erro amigável em vez de traceback
        if args.verbose:
            raise
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())