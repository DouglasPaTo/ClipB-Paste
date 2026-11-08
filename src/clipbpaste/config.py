"""Configuração persistida do ClipB-Paste (equivalente ao Settings.settings/App.config do original)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

APP_ID = "clipb-paste"
APP_NAME = "ClipB-Paste"


def _xdg_dir(var: str, default: str) -> Path:
    base = os.environ.get(var)
    if base:
        return Path(base).expanduser()
    return Path.home() / default


def config_dir() -> Path:
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_ID


def state_dir() -> Path:
    return _xdg_dir("XDG_STATE_HOME", ".local/state") / APP_ID


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / APP_ID
    return Path(tempfile.gettempdir()) / f"{APP_ID}-{os.getuid()}"


def config_path() -> Path:
    return config_dir() / "config.json"


def log_path() -> Path:
    return state_dir() / f"{APP_ID}.log"


def pid_path() -> Path:
    return runtime_dir() / "daemon.pid"


@dataclass
class Config:
    # --- comportamento de tipagem (nomes espelham o original) ---
    key_delay_ms: int = 15          # KeyDelayMS
    start_delay_ms: int = 0         # StartDelayMS
    confirm: bool = False           # Confirm
    confirm_over: int = 100         # ConfirmOver

    # --- backend de digitação: auto | eis | ydotool | wtype | uinput | stdout ---
    backend: str = "auto"

    # --- idioma da interface: pt_BR | en ---
    language: str = "en"

    # --- aviso "como abortar" na primeira vez com texto longo ---
    show_abort_hint: bool = True     # desmarcado = não mostrar de novo
    abort_hint_over: int = 500       # a partir de quantos caracteres avisar

    # --- janela de seleção ---
    crosshair: bool = True

    # --- ativação da janela alvo ---
    activate_target: bool = True

    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def _known(cls) -> set[str]:
        return {f.name for f in fields(cls)} - {"extra"}

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or config_path()
        cfg = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cfg
        except (OSError, ValueError):
            return cfg
        if not isinstance(raw, dict):
            return cfg
        known = cls._known()
        for key, value in raw.items():
            if key in known:
                setattr(cfg, key, value)
            else:
                cfg.extra[key] = value

        # Corrige arquivos afetados pelo bug de aninhamento ('extra' dentro de
        # 'extra' dentro de 'extra'...).
        while set(cfg.extra) == {"extra"} and isinstance(cfg.extra.get("extra"), dict):
            cfg.extra = cfg.extra["extra"]
        cfg.validate()
        return cfg

    def validate(self) -> "Config":
        self.key_delay_ms = max(0, int(self.key_delay_ms))
        self.start_delay_ms = max(0, int(self.start_delay_ms))
        self.confirm_over = max(0, int(self.confirm_over))
        from .i18n import normalize as _norm_lang

        self.language = _norm_lang(self.language)
        return self

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # asdict() já traz 'extra'; sobrescrever com self.extra evita que os
        # campos desconhecidos se aninhem um nível a cada salvamento.
        data["extra"] = dict(self.extra)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
