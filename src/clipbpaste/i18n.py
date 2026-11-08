"""Internacionalização do ClipB-Paste (PT-BR e EN-US).

Arquivo de strings simples, sem dependência de gettext: são poucos textos e um
dicionário resolve. Se o idioma configurado não tiver tradução, cai no PT-BR.

Uso::

    from .i18n import tr, set_language
    set_language("en")        # na primeira execução ou ao salvar as configurações
    tr("settings.title")      # -> "ClipB-Paste — Settings"
"""

from __future__ import annotations

import logging

log = logging.getLogger("clipb-paste")

DEFAULT_LANGUAGE = "en"
LANGUAGES = {
    "pt_BR": "Português (Brasil)",
    "en": "English (US)",
}

# Código ISO curto -> chave interna (valores salvos na config)
ALIASES = {
    "pt": "pt_BR",
    "pt_br": "pt_BR",
    "pt-br": "pt_BR",
    "en": "en",
    "en_us": "en",
    "en-us": "en",
}

STRINGS: dict[str, dict[str, str]] = {
    # --- janela de configurações ---
    "settings.title": {
        "pt_BR": "ClipB-Paste — Configurações",
        "en": "ClipB-Paste — Settings",
    },
    "settings.intro": {
        "pt_BR": "Passe o mouse sobre a janela onde o texto deve ser digitado e clique "
                 "no ícone da bandeja. O texto do clipboard é digitado tecla por tecla.",
        "en": "Hover the window where the text should be typed and click the tray icon. "
              "The clipboard content is typed key by key.",
    },
    "settings.section.typing": {"pt_BR": "Digitação", "en": "Typing"},
    "settings.key_delay": {"pt_BR": "Atraso entre teclas (ms)", "en": "Delay between keys (ms)"},
    "settings.start_delay": {"pt_BR": "Atraso antes de começar (ms)", "en": "Delay before start (ms)"},
    "settings.delay_hint": {
        "pt_BR": "Aumente o atraso entre teclas se a janela alvo perder caracteres.",
        "en": "Increase the delay between keys if the target window drops characters.",
    },
    "settings.backend": {"pt_BR": "Como digitar", "en": "How to type"},
    "settings.backend_hint": {
        "pt_BR": "Muda na hora ao salvar. O modo automático usa ydotool quando disponível "
                 "e cai para o uinput.",
        "en": "Applies immediately on save. Automatic mode uses ydotool when available "
              "and falls back to uinput.",
    },
    "settings.section.confirm": {"pt_BR": "Confirmação", "en": "Confirmation"},
    "settings.confirm_enable": {
        "pt_BR": "Pedir confirmação para textos longos",
        "en": "Ask for confirmation on long text",
    },
    "settings.confirm_over": {"pt_BR": "A partir de (caracteres)", "en": "Over (characters)"},
    "settings.section.language": {"pt_BR": "Idioma", "en": "Language"},
    "settings.language": {"pt_BR": "Idioma da interface", "en": "Interface language"},
    "settings.language_hint": {
        "pt_BR": "A mudança vale na hora; reabra esta janela para ver tudo traduzido.",
        "en": "Takes effect immediately; reopen this window to see everything translated.",
    },
    "settings.cancel": {"pt_BR": "Cancelar", "en": "Cancel"},
    "settings.save": {"pt_BR": "Salvar", "en": "Save"},
    "settings.version": {"pt_BR": "versão {version}", "en": "version {version}"},

    # --- backend: rótulos no seletor ---
    "backend.auto": {"pt_BR": "automático", "en": "automatic"},
    "backend.ydotool": {"pt_BR": "ydotool (teclado completo)", "en": "ydotool (full keyboard)"},
    "backend.uinput": {"pt_BR": "uinput (direto no kernel)", "en": "uinput (straight to kernel)"},
    "backend.wtype": {"pt_BR": "wtype (compositor)", "en": "wtype (compositor)"},
    "backend.eis": {"pt_BR": "EIS (experimental)", "en": "EIS (experimental)"},
    "backend.stdout": {"pt_BR": "somente imprimir (teste)", "en": "print only (test)"},

    # --- diálogo de confirmação ---
    "confirm.title": {"pt_BR": "Digitar {count} caracteres?", "en": "Type {count} characters?"},
    "confirm.body": {
        "pt_BR": "O texto do clipboard será digitado em {target}.",
        "en": "The clipboard text will be typed into {target}.",
    },
    "confirm.cancel": {"pt_BR": "Cancelar", "en": "Cancel"},
    "confirm.ok": {"pt_BR": "Digitar", "en": "Type"},

    # --- bandeja ---
    "tray.title": {"pt_BR": "ClipB-Paste", "en": "ClipB-Paste"},
    "tray.tooltip.idle": {
        "pt_BR": "ClipB-Paste: Clique para digitar na janela ativa.",
        "en": "ClipB-Paste: Click to type into the active window.",
    },
    "tray.tooltip.typing": {
        "pt_BR": "ClipB-Paste: digitando… (clique para parar)",
        "en": "ClipB-Paste: typing… (click to stop)",
    },
    "tray.tooltip.no_backend": {
        "pt_BR": "ClipB-Paste: sem backend de digitação",
        "en": "ClipB-Paste: no typing backend",
    },
    "tray.menu.stop": {"pt_BR": "Parar digitação", "en": "Stop typing"},
    "tray.menu.settings": {"pt_BR": "Configurações…", "en": "Settings…"},
    "tray.menu.quit": {"pt_BR": "Sair do ClipB-Paste", "en": "Quit ClipB-Paste"},

    # --- mensagens do daemon ---
    "error.no_backend.title": {
        "pt_BR": "Nenhum backend de digitação disponível",
        "en": "No typing backend available",
    },
    "error.no_backend.body": {
        "pt_BR": "Rode 'clipb-paste doctor' para ver o que falta.",
        "en": "Run 'clipb-paste doctor' to see what is missing.",
    },
    "error.no_clipboard.title": {"pt_BR": "Sem acesso ao clipboard", "en": "No clipboard access"},
    "error.image_clipboard.title": {"pt_BR": "O clipboard tem uma imagem", "en": "Clipboard holds an image"},
    "error.image_clipboard.body": {
        "pt_BR": "O ClipB-Paste digita texto. Copie um texto para colar.",
        "en": "ClipB-Paste types text. Copy some text to paste.",
    },
    "error.typing.title": {"pt_BR": "Falha ao digitar", "en": "Typing failed"},
    "error.unicode.title": {
        "pt_BR": "O método '{backend}' não digita acentos",
        "en": "The '{backend}' method cannot type accents",
    },
    "error.unicode.body": {
        "pt_BR": "Estes caracteres serão perdidos: {chars}. Para acentuação, instale o "
                 "ydotool (veja o README).",
        "en": "These characters will be dropped: {chars}. For accents, install ydotool "
              "(see the README).",
    },
}

_current = DEFAULT_LANGUAGE


def normalize(code: str | None) -> str:
    """Converte 'en-US', 'en_US', 'EN'… para a chave interna."""
    if not code:
        return DEFAULT_LANGUAGE
    key = str(code).strip().lower().replace("-", "_")
    mapped = ALIASES.get(key)
    if mapped:
        return mapped
    if key in LANGUAGES:
        return key
    return DEFAULT_LANGUAGE


def set_language(code: str | None) -> str:
    """Define o idioma corrente. Devolve a chave efetivamente usada."""
    global _current
    _current = normalize(code)
    return _current


def current_language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    """Traduz uma chave; faz interpolação simples com ``str.format``."""
    entry = STRINGS.get(key)
    if entry is None:
        log.debug("string sem tradução: %s", key)
        return key
    texto = entry.get(_current) or entry.get(DEFAULT_LANGUAGE) or key
    if kwargs:
        try:
            return texto.format(**kwargs)
        except (KeyError, IndexError):
            return texto
    return texto


def ui_languages() -> list[tuple[str, str]]:
    """(código, rótulo) na ordem em que aparecem no seletor."""
    return list(LANGUAGES.items())