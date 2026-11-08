"""Testes que NÃO dependem de permissões especiais nem de sessão gráfica.

Rode com:  python3 -m pytest tests/ -v
       ou: python3 tests/test_all.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from clipbpaste import config, kwin  # noqa: E402
from clipbpaste.backends import stdout as stdout_backend  # noqa: E402
from clipbpaste.typing import Typer  # noqa: E402


class TestConfig(unittest.TestCase):
    def test_defaults_espelham_o_original(self):
        cfg = config.Config()
        self.assertEqual(cfg.key_delay_ms, 15)     # KeyDelayMS do App.config
        self.assertEqual(cfg.start_delay_ms, 0)    # StartDelayMS
        self.assertEqual(cfg.confirm_over, 100)    # ConfirmOver
        self.assertFalse(cfg.confirm)              # Confirm






    def test_ida_e_volta_por_arquivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = config.Config(language="en", key_delay_ms=42, backend="ydotool")
            cfg.validate()
            cfg.save(path)
            loaded = config.Config.load(path)
            self.assertEqual(loaded.language, "en")
            self.assertEqual(loaded.key_delay_ms, 42)
            self.assertEqual(loaded.backend, "ydotool")

    def test_arquivo_corrompido_nao_quebra(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{ isto não é json", encoding="utf-8")
            cfg = config.Config.load(path)  # não deve levantar
            self.assertEqual(cfg.backend, "auto")  # volta ao padrão

    def test_extra_nao_aninha_ao_salvar(self):
        """Bug real: asdict() já traz 'extra', e sobrescrever com self.extra
        fazia cada salvamento aninhar mais um nível."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = config.Config()
            cfg.extra["chave"] = 1
            for _ in range(5):        # salvar várias vezes não pode aninhar
                cfg.save(path)
                cfg = config.Config.load(path)
            self.assertEqual(cfg.extra, {"chave": 1})

    def test_corrige_arquivo_com_extra_aninhado(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"extra": {"extra": {"extra": {"x": 9}}}}), encoding="utf-8")
            cfg = config.Config.load(path)
            self.assertEqual(cfg.extra, {"x": 9})

    def test_chaves_desconhecidas_vao_para_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"backend": "wtype", "chave_nova": 7}), encoding="utf-8")
            cfg = config.Config.load(path)
            self.assertEqual(cfg.backend, "wtype")
            self.assertEqual(cfg.extra["chave_nova"], 7)


class TestKWinModel(unittest.TestCase):
    SAMPLE = {
        "id": "{04c62a02-2f5b-4b6e-9e71-f02e6f43cbd9}",
        "caption": "~ : bash — Konsole com um título bem comprido para truncar",
        "class": "org.kde.konsole",
        "name": "konsole",
        "pid": 5003,
        "x": 100, "y": 200, "w": 800, "h": 600,
        "ox": 0, "oy": 28,
        "active": True,
        "skip": False,
    }

    def test_parse_janela(self):
        win = kwin.KWinWindow.parse(json.dumps(self.SAMPLE))
        self.assertIsNotNone(win)
        self.assertEqual(win.app_id, "org.kde.konsole")
        self.assertEqual(win.pid, 5003)
        self.assertTrue(win.active)
        self.assertEqual((win.width, win.height), (800, 600))
        self.assertEqual((win.offset_x, win.offset_y), (0, 28))

    def test_parse_payload_invalido(self):
        for payload in ("", "não é json", "{}", None):
            self.assertIsNone(kwin.KWinWindow.parse(payload))

    def test_parse_lista_de_janelas(self):
        # O script devolve uma linha JSON por janela.
        payload = "\n".join(json.dumps({**self.SAMPLE, "id": f"{{{i}}}", "pid": i})
                            for i in range(3))
        windows = kwin.parse_window_list(payload)
        self.assertEqual(len(windows), 3)
        self.assertEqual([w.pid for w in windows], [0, 1, 2])

    def test_truncar_caption(self):
        win = kwin.KWinWindow.parse(json.dumps(self.SAMPLE))
        self.assertLessEqual(len(win.truncated_caption(20)), 20)
        self.assertTrue(win.truncated_caption(20).endswith("…"))

    def test_contains(self):
        win = kwin.KWinWindow.parse(json.dumps(self.SAMPLE))
        self.assertTrue(win.contains((100, 200)))
        self.assertTrue(win.contains((899, 799)))
        self.assertFalse(win.contains((900, 800)))  # borda é exclusiva
        self.assertFalse(win.contains((99, 200)))

    def test_identidade_ida_e_volta(self):
        win = kwin.KWinWindow.parse(json.dumps(self.SAMPLE))
        identity = kwin.WindowIdentity.from_window(win)
        recovered = kwin.WindowIdentity.parse(identity.to_json())
        self.assertEqual(identity, recovered)

    def test_identidade_aceita_uuid_puro(self):
        identity = kwin.WindowIdentity.parse("{abc-123}")
        self.assertEqual(identity.ks, "{abc-123}")


class TestTeclas(unittest.TestCase):
    def test_key_hid_letras(self):
        # 'A' maiúsculo é a posição A + Shift; 'a' é só a posição.
        self.assertEqual(kwin.key_hid("A"), (0x04, 0x02))
        self.assertEqual(kwin.key_hid("a"), (0x04, 0x00))
        self.assertEqual(kwin.key_hid("V"), (0x19, 0x02))
        self.assertEqual(kwin.key_hid("v"), (0x19, 0x00))

    def test_key_hid_especiais(self):
        self.assertEqual(kwin.key_hid("RETURN")[0], 0x28)
        self.assertEqual(kwin.key_hid("ESCAPE")[0], 0x29)
        self.assertEqual(kwin.key_hid("F12")[0], 0x45)

    def test_key_symbols(self):
        self.assertEqual(kwin.key_symbols("V"), ["v"])
        self.assertEqual(kwin.key_symbols("RETURN"), ["Return"])
        self.assertEqual(kwin.key_symbols("PAGEUP"), ["Prior"])


class FakeBackend(stdout_backend.StdoutBackend):
    def __init__(self) -> None:
        self.received: list[str] = []
        self.flushed = False

    def type_text(self, text: str, *, key_delay_ms: int = 15, should_stop=None) -> None:
        self.received.append(text)

    def flush(self) -> None:
        self.flushed = True


class TestCancelamento(unittest.TestCase):
    """Parar no meio do texto precisa funcionar de verdade.

    Antes o cancel() só marcava uma flag: o helper já estava rodando numa única
    chamada e não checava nada, então o texto continuava saindo até o fim.
    """

    def test_backend_declara_should_stop(self):
        from clipbpaste.backends import TypingBackend
        import inspect

        assinatura = inspect.signature(TypingBackend.type_text)
        self.assertIn("should_stop", assinatura.parameters)

    def test_cli_tem_comando_abort(self):
        """A terceira saída de emergência, para quando a interface não responde."""
        from clipbpaste.cli import build_parser

        parser = build_parser()
        for action in parser._subparsers._group_actions:
            self.assertIn("abort", action.choices)

    def test_backend_tem_stop(self):
        from clipbpaste.backends import TypingBackend

        self.assertTrue(hasattr(TypingBackend, "stop"))

    def test_typer_para_apos_cancel(self):
        """Depois de cancel(), a digitação termina em 'cancelada', não normal."""
        from clipbpaste.typing import TypingCancelled

        class BackendQuePara(stdout_backend.StdoutBackend):
            def __init__(self):
                self.parou = False

            def type_text(self, text, *, key_delay_ms=15, should_stop=None):
                # simula o backend percebendo o pedido de parada
                if should_stop is not None and should_stop():
                    self.parou = True
                else:
                    self.parou = True

            def stop(self):
                pass

        backend = BackendQuePara()
        typer = Typer(backend)
        typer.cancel()   # pede para parar antes de começar
        with self.assertRaises(TypingCancelled):
            typer.type_text_blocking("texto longo", key_delay_ms=10)

    def test_uinput_mata_o_processo(self):
        """O helper roda como subprocesso: cancelar precisa matá-lo."""
        src = (ROOT / "src" / "clipbpaste" / "backends" / "uinput.py").read_text(encoding="utf-8")
        self.assertIn("def stop", src)
        self.assertIn("SIGTERM", src)
        self.assertIn("start_new_session=True", src)


class TestTyping(unittest.TestCase):
    def test_digita_texto_completo_em_uma_chamada(self):
        """Antes o texto era fatiado, criando/destruindo um teclado virtual por
        fatia — as transições perdiam caracteres ("Tarball" -> "Tarbal")."""
        backend = FakeBackend()
        typer = Typer(backend)
        typer.type_text_blocking("a" * 250, key_delay_ms=100)
        self.assertEqual(backend.received, ["a" * 250])  # uma única chamada
        self.assertTrue(backend.flushed)

    def test_letra_dobrada_preservada(self):
        backend = FakeBackend()
        Typer(backend).type_text_blocking("Tarball", key_delay_ms=15)
        self.assertEqual(backend.received, ["Tarball"])

    def test_texto_vazio_nao_chama_backend(self):
        backend = FakeBackend()
        Typer(backend).type_text_blocking("")
        self.assertEqual(backend.received, [])

    def test_cancelamento_interrompe(self):
        backend = FakeBackend()
        typer = Typer(backend)
        typer.cancel()
        from clipbpaste.typing import TypingCancelled

        with self.assertRaises(TypingCancelled):
            typer.type_text_blocking("texto", key_delay_ms=1000)

    def test_backend_name(self):
        self.assertEqual(Typer(FakeBackend()).backend_name, "stdout")


class TestMapaDeTeclasUinput(unittest.TestCase):
    """O helper C já mapeou errado uma vez: usava ordem alfabética em vez de QWERTY."""

    C_SOURCE = (ROOT / "scripts" / "uinput-type.c").read_text(encoding="utf-8")

    # keycodes reais, tirados de /usr/include/linux/input-event-codes.h
    ESPERADO = {
        "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22,
        "i": 23, "o": 24, "p": 25, "a": 30, "s": 31, "d": 32, "f": 33,
        "g": 34, "h": 35, "j": 36, "k": 37, "l": 38, "z": 44, "x": 45,
        "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    }

    def test_tabela_de_letras_cobre_o_alfabeto(self):
        import re

        pares = re.findall(r"\{'([a-z])', KEY_([A-Z])\}", self.C_SOURCE)
        mapeado = {ch: nome for ch, nome in pares}
        self.assertEqual(len(mapeado), 26, "o alfabeto precisa estar completo")
        self.assertEqual(set(mapeado), set(self.ESPERADO))

    def test_keycodes_batem_com_o_kernel(self):
        import re

        header = Path("/usr/include/linux/input-event-codes.h")
        if not header.is_file():
            self.skipTest("headers do kernel não disponíveis")
        src = header.read_text(encoding="utf-8", errors="replace")
        pares = re.findall(r"\{'([a-z])', KEY_([A-Z])\}", self.C_SOURCE)
        for ch, nome in pares:
            achado = re.search(rf"#define KEY_{nome}\s+(\d+)", src)
            self.assertIsNotNone(achado, nome)
            self.assertEqual(
                int(achado.group(1)), self.ESPERADO[ch],
                f"'{ch}' aponta para KEY_{nome} = {achado.group(1)}, esperado {self.ESPERADO[ch]}",
            )

    def test_nao_usa_ordem_alfabetica(self):
        # A armadilha: KEY_A + (ch - 'a') só funciona em teclado alfabético.
        # Ignoramos comentários, onde o bug está documentado de propósito.
        import re

        codigo = re.sub(r"/\*.*?\*/", "", self.C_SOURCE, flags=re.S)
        self.assertNotIn("KEY_A + (ch - 'a')", codigo)


class TestIdioma(unittest.TestCase):
    def test_normaliza_codigos(self):
        from clipbpaste.i18n import normalize

        self.assertEqual(normalize("en-US"), "en")
        self.assertEqual(normalize("en_US"), "en")
        self.assertEqual(normalize("EN"), "en")
        self.assertEqual(normalize("pt-BR"), "pt_BR")
        self.assertEqual(normalize("pt_br"), "pt_BR")
        self.assertEqual(normalize("xx"), "en")      # desconhecido -> padrão (en)
        self.assertEqual(normalize(None), "en")

    def test_traducao_nos_dois_idiomas(self):
        from clipbpaste import i18n

        i18n.set_language("en")
        self.assertEqual(i18n.tr("settings.title"), "ClipB-Paste — Settings")
        self.assertEqual(i18n.tr("tray.menu.quit"), "Quit ClipB-Paste")
        i18n.set_language("pt_BR")
        self.assertEqual(i18n.tr("settings.title"), "ClipB-Paste — Configurações")
        self.assertEqual(i18n.tr("tray.menu.quit"), "Sair do ClipB-Paste")

    def test_chave_inexistente_devolve_a_chave(self):
        from clipbpaste import i18n

        self.assertEqual(i18n.tr("nao.existe"), "nao.existe")

    def test_interpolacao(self):
        from clipbpaste import i18n

        i18n.set_language("pt_BR")
        self.assertIn("1.4.4", i18n.tr("settings.version", version="1.4.4"))

    def test_todas_as_strings_tem_os_dois_idiomas(self):
        from clipbpaste.i18n import STRINGS

        for chave, entrada in STRINGS.items():
            self.assertIn("pt_BR", entrada, f"{chave} sem PT-BR")
            self.assertIn("en", entrada, f"{chave} sem EN")

    def test_config_persiste_idioma(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = config.Config(language="en")
            cfg.validate()
            cfg.save(path)
            self.assertEqual(config.Config.load(path).language, "en")

    def test_config_normaliza_idioma_invalido(self):
        self.assertEqual(config.Config(language="klingon").validate().language, "en")


class TestSemAtalho(unittest.TestCase):
    """O atalho global foi retirado do produto: o uso é pelo ícone da bandeja.

    Estes testes impedem que ele volte por acidente.
    """

    def test_config_nao_tem_campo_hotkey(self):
        self.assertFalse(hasattr(config.Config(), "hotkey"))
        self.assertFalse(hasattr(config.Config(), "hotkey_mode"))

    def test_cli_nao_tem_comando_hotkey(self):
        from clipbpaste.cli import build_parser

        parser = build_parser()
        for action in parser._subparsers._group_actions:
            self.assertNotIn("hotkey", action.choices)

    def test_kwin_nao_expoe_register_hotkey(self):
        src = (ROOT / "src" / "clipbpaste" / "kwin.py").read_text(encoding="utf-8")
        self.assertNotIn("def register_hotkey", src)
        self.assertNotIn("KGlobalAccel", src)

    def test_daemon_nao_registra_atalho(self):
        src = (ROOT / "src" / "clipbpaste" / "daemon.py").read_text(encoding="utf-8")
        self.assertNotIn("register_hotkey", src)
        self.assertNotIn("hotkey", src)

    def test_script_do_atalho_nao_existe(self):
        self.assertFalse((ROOT / "data" / "kwin" / "clipb-paste-hotkey.js").exists())


class TestRepeticao(unittest.TestCase):
    """Bug real: teclas repetidas colapsavam ("Tarball" -> "Tarbal", "999" -> "99").

    O libinput funde dois downs da mesma tecla em sequência (auto-repeat).
    O helper precisa forçar um release extra entre eles.
    """

    FONTE = (ROOT / "scripts" / "uinput-type.c").read_text(encoding="utf-8")

    def test_helper_detecta_repeticao(self):
        self.assertIn("int repetida = (code == anterior);", self.FONTE)

    def test_helper_emite_release_extra_na_repeticao(self):
        trecho = self.FONTE[self.FONTE.index("int repetida"):]
        trecho = trecho[:trecho.index("emit(EV_KEY, code, 1);")]
        self.assertIn("emit(EV_KEY, code, 0);", trecho,
                      "repetição precisa de um 'up' extra antes do novo 'down'")

    def test_pausa_maior_na_repeticao(self):
        self.assertIn("repetida ?", self.FONTE)


class TestBackendSeguro(unittest.TestCase):
    """O ydotool 0.1.8 para no primeiro acento e perde o resto do texto.

    Um backend que trunca silenciosamente é pior que um que pula caracteres,
    então o modo automático não pode escolhê-lo.
    """

    def test_ydotool_nao_e_escolhido_no_auto(self):
        from clipbpaste.backends import resolve

        backend, report = resolve("auto")
        nomes = {r.name: r for r in report}
        if nomes["ydotool"].available:
            self.fail("ydotool 0.1.8 não deveria ser considerado disponível")
        if backend is not None:
            self.assertNotEqual(backend.name, "ydotool")

    def test_ydotool_explica_o_motivo(self):
        """O motivo pode variar (não instalado, daemon parado, versão antiga),
        mas sempre deve explicar algo - nunca aparecer indisponível sem motivo."""
        from clipbpaste.backends import ydotool

        status = ydotool.probe()
        if not status.available:
            self.assertTrue(status.reason.strip(),
                            "backend indisponível precisa explicar o motivo")
            # se as dependências estão ok, o motivo é a limitação do 0.1.8
            if ydotool._client() and ydotool._socket_path():
                self.assertIn("acento", status.reason.lower())


class TestAcentosABNT2(unittest.TestCase):
    """Os keycodes de acento foram MEDIDOS no teclado real, não deduzidos.

    Método: enviar cada keycode seguido de "a"/"e" e ler o resultado.
      evdev 26 -> agudo ("á"); com Shift vira crase ("à")
      evdev 40 -> til ("ã");   com Shift vira circunflexo ("ê")
      evdev 39 -> cedilha
    """

    FONTE = (ROOT / "scripts" / "uinput-type.c").read_text(encoding="utf-8")

    def test_keycodes_medidos(self):
        self.assertIn("#define KEY_ABNT2_DEAD_ACUTE   26", self.FONTE)
        self.assertIn("#define KEY_ABNT2_DEAD_TILDE   40", self.FONTE)
        self.assertIn("#define KEY_ABNT2_CEDILLA", self.FONTE)

    def test_cobre_agudo_til_circunflexo_crase(self):
        # á ã â à (0xA1, 0xA3, 0xA2, 0xA0)
        for byte in ("0xA1", "0xA3", "0xA2", "0xA0", "0xA7"):
            self.assertIn(f"{{{byte},", self.FONTE, f"acento {byte} ausente da tabela")

    def test_simbolos_literais(self):
        """` ~ ^ são dead keys no ABNT2: precisam do cancelamento com espaço."""
        self.assertIn("eh_dead_literal", self.FONTE)
        self.assertIn("KEY_SPACE", self.FONTE)

    def test_agudo_literal_usa_altgr(self):
        """´ (U+00B4) só sai com AltGr em 26 — confirmado via XKB."""
        self.assertIn("tap_altgr", self.FONTE)
        self.assertIn("0xB4", self.FONTE)

    def test_crase_e_circunflexo_usam_shift(self):
        t = self.FONTE
        # à = 0xA0 com dead_shift=1
        self.assertIn("{0xA0, KEY_ABNT2_DEAD_ACUTE, 1,", t)
        # â = 0xA2 com dead_shift=1
        self.assertIn("{0xA2, KEY_ABNT2_DEAD_TILDE, 1,", t)


class TestMapaSenha(unittest.TestCase):
    """Símbolos de senha: o mapa foi MEDIDO tecla por tecla no ABNT2 real.

    Os nomes do kernel enganam — KEY_SEMICOLON é 39 (que no ABNT2 é o ç) e
    KEY_SLASH é 53 (que no ABNT2 é o ;). Por isso o helper usa números.
    """

    FONTE = (ROOT / "scripts" / "uinput-type.c").read_text(encoding="utf-8")

    def test_usa_constantes_posicionais(self):
        for nome in ("12_MINUS", "27_BRACKET", "39_CEDILLA", "41_QUOTE",
                     "43_BRACKET", "51_COMMA", "52_DOT", "53_SEMICOLON",
                     "86_BACKSLASH", "89_SLASH"):
            self.assertIn(f"KEY_ABNT2_{nome}", self.FONTE)

    def test_dois_pontos_nao_usa_key_semicolon_do_kernel(self):
        # KEY_SEMICOLON do kernel = 39 = ç no ABNT2. Seria o bug clássico.
        trecho = self.FONTE[self.FONTE.index("case ':'"):]
        self.assertNotIn("return KEY_SEMICOLON", trecho[:80])

    def test_tipograficos_tem_politica_clara(self):
        """Três categorias: pular, substituir por equivalente, ou avisar.

        Aspas curvas -> retas e travessão -> hífen PRESERVAM o significado do
        texto. Já trocar o conteúdo de uma senha seria corrupção — por isso a
        substituição só existe para pontuação tipográfica.
        """
        self.assertIn("eh_tipografico_puro", self.FONTE)     # ✓ • ... -> pular
        self.assertIn("ascii_equivalente", self.FONTE)        # “ ” -> "
        self.assertIn("sem equivalente", self.FONTE)          # emoji -> avisar

    def test_substituicao_nao_mexe_em_letras(self):
        """Só pontuação é substituída; letras nunca viram outra coisa."""
        trecho = self.FONTE[self.FONTE.index("ascii_equivalente"):]
        trecho = trecho[:trecho.index("static void tap")]
        import re
        for letra in re.findall(r'case 0x[0-9A-F]+:.*?return "([a-zA-Z0-9])"', trecho):
            self.fail(f"substituição de letra/dígito não é permitida: {letra!r}")


class TestAvisoInteligente(unittest.TestCase):
    """Acentos e símbolos comuns não devem gerar aviso; bullet não atrapalha."""

    def backend(self):
        from clipbpaste.backends import uinput as ub

        helper = ub._helper()
        if helper is None:
            self.skipTest("helper não compilado")
        return ub.UinputBackend(helper)

    def test_nao_avisa_bullet(self):
        self.assertEqual(self.backend().unsupported_chars("texto • com bullet"), "")

    def test_nao_avisa_travessao(self):
        self.assertEqual(self.backend().unsupported_chars("a — b – c"), "")

    def test_nao_avisa_acentos(self):
        self.assertEqual(self.backend().unsupported_chars("Cabeçalho Tião Você"), "")

    def test_nao_avisa_grau_e_ordinal(self):
        self.assertEqual(self.backend().unsupported_chars("30° 1ª 2º"), "")

    def test_avisa_emoji(self):
        faltando = self.backend().unsupported_chars("oi 😀")
        self.assertIn("😀", faltando or "")


class TestInstalador(unittest.TestCase):
    """O install.sh precisa ser seguro: não apagar configs e ter os modos certos."""

    FONTE = (ROOT / "install.sh").read_text(encoding="utf-8")

    def test_executavel(self):
        import os
        import stat

        path = ROOT / "install.sh"
        self.assertTrue(os.access(path, os.X_OK), "install.sh precisa ser executável")

    def test_tem_todos_os_modos(self):
        for flag in ("--autostart", "--uninstall", "--status", "--no-autostart",
                     "--remove-uinput", "--help"):
            self.assertIn(flag, self.FONTE, f"falta o modo {flag}")

    def test_desinstalar_preserva_configuracoes(self):
        # o bloco de uninstall não pode apagar ~/.config/clipb-paste
        trecho = self.FONTE[self.FONTE.index("do_uninstall()"):]
        trecho = trecho[:trecho.index("do_remove_uinput")]
        self.assertNotIn('rm -rf "$HOME/.config/clipb-paste"', trecho)
        self.assertIn("preservadas", trecho)

    def test_checa_dependencias_antes(self):
        self.assertIn("check_deps", self.FONTE)
        self.assertIn("python3-gi", self.FONTE)

    def test_instala_e_inicia(self):
        """Instalar deve deixar o app rodando, sem abrir duas instâncias."""
        self.assertIn("do_start", self.FONTE)
        # não inicia se já houver um rodando
        self.assertIn("já está rodando", self.FONTE)
        # não tenta iniciar sem sessão gráfica
        self.assertIn("WAYLAND_DISPLAY", self.FONTE)
        self.assertIn("sem sessão gráfica", self.FONTE)

    def test_permite_instalar_sem_iniciar(self):
        self.assertIn("--no-start", self.FONTE)

    def test_avisa_uinput_apos_instalar(self):
        self.assertIn("avisar_uinput", self.FONTE)
        self.assertIn("enable-uinput.sh", self.FONTE)

    def test_autostart_usa_desktop_entry(self):
        self.assertIn(".desktop", self.FONTE)
        self.assertIn("X-GNOME-Autostart-enabled=true", self.FONTE)


class TestFeedbackVisual(unittest.TestCase):
    """O ícone precisa mostrar que está digitando, e o usuário precisa saber
    que pode parar."""

    TRAY = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
    DAEMON = (ROOT / "src" / "clipbpaste" / "daemon.py").read_text(encoding="utf-8")

    def test_icone_pisca_ao_digitar(self):
        self.assertIn("_iniciar_pisca", self.TRAY)
        self.assertIn("_parar_pisca", self.TRAY)
        # alterna entre verde e vermelho
        self.assertIn('"blinking"', self.TRAY)
        self.assertIn("clipb-paste-alert", self.TRAY)

    def test_pisca_para_ao_terminar(self):
        """O timer não pode continuar rodando depois da digitação."""
        self.assertIn('state != "typing"', self.TRAY)
        self.assertIn("GLib.source_remove", self.TRAY)

    def test_dica_de_abortar_na_primeira_vez(self):
        cfg = config.Config()
        self.assertTrue(cfg.show_abort_hint)
        self.assertGreater(cfg.abort_hint_over, 0)
        self.assertIn("mostrar_dica_abortar", self.DAEMON)

    def test_configuracoes_bloqueiam_digitacao(self):
        """Clicar no ícone com as configurações abertas jogava texto nos campos."""
        self.assertIn("_settings_open", self.DAEMON)
        self.assertIn("configurações abertas — digitação ignorada", self.DAEMON)

    def test_icones_de_estado_existem(self):
        for nome in ("clipb-paste", "clipb-paste-light", "clipb-paste-typing",
                     "clipb-paste-alert"):
            achou = any((ROOT / "data" / "icons" / f"{nome}-{sz}.png").is_file()
                        for sz in (16, 32, 64))
            self.assertTrue(achou, f"ícone {nome} não existe")

    def test_install_copia_todas_as_variantes(self):
        inst = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('"-typing"', inst)
        self.assertIn('"-alert"', inst)


class TestBotaoDePanico(unittest.TestCase):
    """O cenário de desgraça completa: app digitando, sem ícone, e o usuário
    não consegue nem digitar um comando para matar o processo."""

    FONTE = (ROOT / "scripts" / "uinput-type.c").read_text(encoding="utf-8")

    def test_qualquer_tecla_fisica_para(self):
        self.assertIn("tecla_fisica_pressionada", self.FONTE)
        self.assertIn("tecla pressionada, parando", self.FONTE)

    def test_ignora_o_proprio_teclado_virtual(self):
        """Sem isso o app pararia a si mesmo (lê o próprio uinput)."""
        for virtual in ("ClipB-Paste", "uinput", "ydotoold", "virtual"):
            self.assertIn(virtual, self.FONTE)

    def test_helper_para_se_o_daemon_morrer(self):
        """Matar o app não pode deixar o texto saindo até o fim."""
        self.assertIn("daemon_vivo", self.FONTE)
        self.assertIn("CLIPBPASTE_PARENT_PID", self.FONTE)
        self.assertIn("daemon encerrado, parando", self.FONTE)

    def test_backend_passa_o_pid(self):
        src = (ROOT / "src" / "clipbpaste" / "backends" / "uinput.py").read_text(encoding="utf-8")
        self.assertIn("CLIPBPASTE_PARENT_PID", src)

    def test_deteccao_de_leitura(self):
        src = (ROOT / "src" / "clipbpaste" / "backends" / "uinput.py").read_text(encoding="utf-8")
        self.assertIn("pode_ler_teclado", src)


class TestPacoteDeb(unittest.TestCase):
    """O .deb instala no sistema (/usr), diferente do install.sh (~/.local)."""

    def test_build_script_existe(self):
        script = ROOT / "packaging" / "build-deb.sh"
        self.assertTrue(script.is_file())
        import os
        self.assertTrue(os.access(script, os.X_OK), "precisa ser executável")

    def test_declara_dependencias(self):
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        # sem estas o app não roda; o apt precisa saber
        for dep in ("python3-gi", "python3-dbus", "wl-clipboard"):
            self.assertIn(dep, src)

    def test_instala_nos_caminhos_de_sistema(self):
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        for caminho in ("/usr/bin", "/usr/lib", "/usr/share"):
            self.assertIn(caminho, src)
        # NÃO pode instalar em ~/.local
        self.assertNotIn("$HOME/.local", src)

    def test_script_do_kwin_vai_para_usr_share(self):
        """script_path() procura em /usr/share/clipb-paste/kwin/."""
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        self.assertIn("usr/share/$PKG/kwin", src)
        kwin = (ROOT / "src" / "clipbpaste" / "kwin.py").read_text(encoding="utf-8")
        self.assertIn("/usr/share/clipb-paste/kwin/clipb-paste.js", kwin)

    def test_comando_enable_uinput_existe(self):
        """O postinst manda rodar 'sudo clipb-paste enable-uinput'."""
        from clipbpaste.cli import build_parser

        parser = build_parser()
        for action in parser._subparsers._group_actions:
            self.assertIn("enable-uinput", action.choices)

    def test_normaliza_permissoes(self):
        """Bug real: dpkg-deb --root-owner-group muda o dono mas NÃO as permissões.

        Arquivos copiados do ~ vinham 600 (-rw-------) e o app instalado não
        conseguia se ler: PermissionError em cli.py ao rodar como usuário comum.
        """
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        self.assertIn("chmod 644", src)
        self.assertIn("chmod 755", src)
        # deve rodar ANTES do dpkg-deb --build
        self.assertLess(src.index("normalizando permissões"),
                        src.index("dpkg-deb --build"))

    def test_copyright_em_formato_dep5(self):
        """Sem 'Format:' no copyright, o Discover mostra 'License: Unknown'."""
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        self.assertIn("Format: https://www.debian.org/doc/packaging-manuals", src)
        self.assertIn("License: BSD-3-clause", src)

    def test_pacote_gerado_tem_arquivos_legiveis(self):
        """Verifica o .deb de verdade, se ele existir."""
        import subprocess

        deb = sorted((ROOT / "dist").glob("clipb-paste_*_all.deb"))
        if not deb:
            self.skipTest("pacote não gerado")
        saida = subprocess.run(["dpkg-deb", "--contents", str(deb[-1])],
                               capture_output=True, text=True).stdout
        for linha in saida.splitlines():
            partes = linha.split()
            if len(partes) < 6:
                continue
            perm, caminho = partes[0], partes[-1]
            if caminho.endswith("/") or not caminho.startswith("./usr"):
                continue
            # todo arquivo precisa ser legível pelos outros (o 4º char não pode ser '-')
            self.assertNotEqual(perm[7], "-",
                                f"{caminho} não é legível por outros ({perm})")

    def test_postinst_libera_uinput(self):
        """O postinst roda como root: aproveita para criar a regra udev,
        para o usuário não precisar rodar nada depois."""
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        trecho = src[src.index("POSTINST"):]
        self.assertIn("60-uinput-clipb-paste.rules", trecho)
        self.assertIn("udevadm", trecho)
        self.assertIn("usermod -aG input", trecho)

    def test_postinst_nao_roda_como_root(self):
        """O app NÃO pode iniciar como root: criaria config em /root e um tray
        icon no barramento errado."""
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        trecho = src[src.index("POSTINST"):]
        self.assertIn("SUDO_USER", trecho)
        # deve lançar COMO o usuário, nunca direto
        self.assertIn("COMO_USUARIO", trecho)
        # e nunca executar /usr/bin/clipb-paste daemon sem o wrapper
        for linha in trecho.splitlines():
            if "clipb-paste daemon" in linha and "COMO_USUARIO" not in linha:
                if linha.strip().startswith("echo"):
                    continue
                self.assertIn("$COMO_USUARIO", trecho)

    def test_postinst_detecta_sessao_grafica(self):
        """runuser + sh -c NÃO herda DISPLAY/WAYLAND_DISPLAY: precisa usar
        systemctl --user show-environment ou o socket no runtime dir."""
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        trecho = src[src.index("POSTINST"):]
        self.assertIn("show-environment", trecho)
        self.assertIn("wayland-*", trecho)

    def test_preserva_configuracoes_ao_remover(self):
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        self.assertIn("preservadas", src)


class TestVersao(unittest.TestCase):
    """A versão do ClipB-Paste é própria, não herdada do projeto de origem."""

    def test_versao_e_propria(self):
        from clipbpaste import __version__

        # 1.4.4 era a versão do projeto que serviu de inspiração
        self.assertNotEqual(__version__, "1.4.4",
                            "a versão deve ser própria, não herdada")
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$", "deve ser SemVer")

    def test_cli_le_a_versao(self):
        """Antes a CLI tinha '1.4.4-linux' hardcoded, ignorando __version__."""
        from clipbpaste import __version__
        from clipbpaste.cli import build_parser

        parser = build_parser()
        acoes = [a for a in parser._actions if "--version" in a.option_strings]
        self.assertTrue(acoes)
        # a versão exibida deve vir de __version__
        stdout = __import__("io").StringIO()
        import contextlib
        import sys as _sys

        try:
            with contextlib.redirect_stdout(stdout):
                parser.parse_args(["--version"])
        except SystemExit:
            pass
        saida = stdout.getvalue()
        self.assertIn(__version__, saida)
        self.assertNotIn("1.4.4", saida)

    def test_deb_usa_a_versao_do_codigo(self):
        src = (ROOT / "packaging" / "build-deb.sh").read_text(encoding="utf-8")
        # deve extrair de __init__.py, não ter número fixo
        self.assertIn("__version__", src)
        self.assertNotIn("VERSION=\"1.4.4\"", src)


class TestDocumentacao(unittest.TestCase):
    """O README já citou comandos que não existiam ('clipb-paste --abort').
    Estes testes impedem que isso volte."""

    README = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_comandos_da_cli_existem(self):
        import re

        from clipbpaste.cli import build_parser

        parser = build_parser()
        comandos = set()
        for action in parser._subparsers._group_actions:
            comandos.update(action.choices)

        # comandos citados como `clipb-paste <algo>` no README
        citados = set(re.findall(r"clipb-paste ([a-z][a-z-]*)", self.README))
        # ignora nomes de arquivo/pacote
        citados -= {"daemon", "doctor", "windows", "target", "type", "settings",
                    "abort", "enable-uinput", "kwin-install"}
        for citado in re.findall(r"`clipb-paste ([a-z][a-z-]*)`", self.README):
            self.assertIn(citado, comandos,
                          f"README cita 'clipb-paste {citado}' que não existe")

    def test_nao_usa_hifen_em_subcomando(self):
        # '--abort' seria flag de opção, não subcomando
        self.assertNotIn("clipb-paste --abort", self.README)

    def test_scripts_citados_existem(self):
        import re

        for script in set(re.findall(r"\./(scripts/[a-z-]+\.sh|packaging/[a-z-]+\.sh|install\.sh)", self.README)):
            self.assertTrue((ROOT / script).is_file(), f"README cita {script}, que não existe")

    def test_versao_no_readme_bate_com_o_codigo(self):
        from clipbpaste import __version__

        # se o README cita um .deb, o nome deve ter a versão atual
        if "clipb-paste_" in self.README:
            self.assertIn(f"clipb-paste_{__version__}_all.deb", self.README)


class TestArtefatos(unittest.TestCase):
    """Confere que os arquivos que o app carrega existem e são válidos."""

    def test_helper_espera_antes_de_destruir(self):
        """Bug real: com 50 ms de espera o fim do texto se perdia (-777 virava -7)."""
        src = (ROOT / "scripts" / "uinput-type.c").read_text(encoding="utf-8")
        # olha só o FINAL do arquivo (o cleanup), não o loop
        trecho = src[src.rindex("destroy_device();"):]
        antes = src[:src.rindex("destroy_device();")]
        espera = __import__("re").search(r"sleep_ms\((\d+)\);\s*\n(?:\s*fechar_teclados\(\);\s*\n)?\s*$", antes)
        self.assertIsNotNone(espera, "o helper precisa esperar antes de destruir o dispositivo")
        self.assertGreaterEqual(
            int(espera.group(1)), 200,
            "espera curta faz os últimos eventos se perderem",
        )



    def test_script_do_kwin_existe(self):
        path = ROOT / "data" / "kwin" / "clipb-paste.js"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        # Nada de APIs que não existem no scripting do KWin (ignorando comentários)
        code = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("//")
        )
        self.assertNotIn("registerPointerFilter(", code)
        self.assertNotIn("Qt.point", code)
        # Todos os callDBus precisam ter aridade fixa
        self.assertIn("function callBack3(", text)

    def test_icone_usa_nome_de_tema_nao_caminho(self):
        """Caminho absoluto em IconName faz o Plasma desenhar ícone vazio."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        trecho = src[src.index("def icon_for"):src.index("def install_icons")]
        self.assertNotIn("str(candidate)", trecho)
        self.assertNotIn(".png\"", trecho.split("return")[0])
        # os nomes vêm de ICONES_ESTADO; o que importa é não haver caminho
        self.assertIn("ICONES_ESTADO", src)
        self.assertIn('"clipb-paste-typing"', src)
        self.assertIn('"clipb-paste-light"', src)

    def test_pisca_durante_digitacao(self):
        """O ícone alterna verde/vermelho enquanto digita."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        self.assertIn("_iniciar_pisca", src)
        self.assertIn("_piscar", src)
        self.assertIn("blinking", src)
        self.assertIn("GLib.timeout_add", src)

    def test_um_unico_register_object_por_caminho(self):
        """GDBus apaga o registro anterior se o mesmo caminho for registrado de novo.

        Era isso que sumia com o menu de botão direito: registrávamos
        org.freedesktop.DBus.Properties em /StatusNotifierItem DEPOIS da interface
        do item, e o segundo registro substituía o primeiro.
        """
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        import re

        registros = re.findall(r"register_object\(\s*([A-Z_]+)", src)
        self.assertEqual(sorted(registros), ["ITEM_PATH", "MENU_PATH"],
                         f"esperado um registro por caminho, achei: {registros}")

    def test_get_devolve_variant_cru(self):
        """Com <property> no XML o GDBus empacota; devolver '(v)' dupla-embalava."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        trecho = src[src.index("def _on_item_get"):src.index("def _on_item_call")]
        # remove comentários antes de olhar o código
        codigo = "\n".join(l for l in trecho.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn('"(v)"', codigo)
        self.assertIn("return props[prop]", codigo)

    def test_propriedades_dbus_declaradas(self):
        """O Plasma lê IconName/ToolTip por org.freedesktop.DBus.Properties."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        self.assertIn('name="IconName"', src)
        self.assertIn('name="ToolTip"', src)
        self.assertIn('name="GetAll"', src)
        # a saída de Get é (v), então o valor precisa ser empacotado
        self.assertIn('GLib.Variant("v"', src)

    def test_menu_tem_parar_configuracoes_e_sair(self):
        """O menu é enxuto. "Parar digitação" só aparece DURANTE a digitação:
        fora disso seria um botão sem efeito.

        Ele continua existindo porque é a rede de segurança caso o clique no
        ícone não funcione (ícone sumiu, Plasma travou)."""
        from clipbpaste import i18n
        from clipbpaste.tray import Tray

        chaves = [item[1] for item in Tray.ITEMS if item[1]]
        self.assertEqual(chaves, ["tray.menu.stop", "tray.menu.settings", "tray.menu.quit"])

        i18n.set_language("pt_BR")
        rotulos = [i18n.tr(k) for k in chaves]
        self.assertEqual(rotulos, ["Parar digitação", "Configurações…", "Sair do ClipB-Paste"])

        i18n.set_language("en")
        rotulos_en = [i18n.tr(k) for k in chaves]
        self.assertEqual(rotulos_en, ["Stop typing", "Settings…", "Quit ClipB-Paste"])
        i18n.set_language("pt_BR")

        # o item "Parar" e o separador dele são condicionais ao estado
        condicionais = [item[0] for item in Tray.ITEMS if item[4]]
        self.assertEqual(condicionais, [2, 5])   # Parar + o separador abaixo dele
        # Configurações e Sair NUNCA são condicionais
        fixos = [item[1] for item in Tray.ITEMS if not item[4] and item[1]]
        self.assertEqual(fixos, ["tray.menu.settings", "tray.menu.quit"])

    def test_menu_declara_propriedades(self):
        """Sem Version/Status o Plasma não monta o dbusmenu."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        for prop in ("Version", "TextDirection", "Status", "IconThemePath"):
            self.assertIn(f'name="{prop}"', src)

    def test_itemismenu_false(self):
        """ItemIsMenu=True faz o Plasma desviar o clique esquerdo para o menu."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        inicio = src.index('"ItemIsMenu": GLib.Variant')
        trecho = src[inicio:src.index("\n", inicio)]
        self.assertIn("False", trecho)


    def test_icones_png(self):
        """Só os ícones do ClipB-Paste são usados; os do projeto original saíram."""
        for name in ("clipb-paste", "clipb-paste-light"):
            for size in (16, 32, 64):
                path = ROOT / "data" / "icons" / f"{name}-{size}.png"
                self.assertTrue(path.is_file(), path)
                self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_idioma_padrao_e_ingles(self):
        self.assertEqual(config.Config().language, "en")

    def test_bandeja_troca_idioma_ao_vivo(self):
        """O menu precisa ser reemitido, senão fica no idioma antigo."""
        src = (ROOT / "src" / "clipbpaste" / "tray.py").read_text(encoding="utf-8")
        self.assertIn("def set_language", src)
        self.assertIn("LayoutUpdated", src)
        daemon = (ROOT / "src" / "clipbpaste" / "daemon.py").read_text(encoding="utf-8")
        self.assertIn("tray.set_language", daemon)

    def test_licenca_preservada(self):
        self.assertTrue((ROOT / "LICENSE").is_file())

    def test_helper_c_compila(self):
        """O helper uinput é opcional, mas o código tem de estar presente."""
        self.assertTrue((ROOT / "scripts" / "uinput-type.c").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)