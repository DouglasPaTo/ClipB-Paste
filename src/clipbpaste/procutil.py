"""Utilitários de processo: localizar binários e executar comandos curtos sem travar a GUI."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("clipbpaste")

# Diretórios extras, cobrindo instalações em /usr/local e wrappers distrobox/flatpak expostos pelo host
_EXTRA_PATHS = ("/usr/local/bin", "/usr/bin", "/bin", "/usr/local/sbin", "/usr/sbin")
_WRAPPER_DIRS = ("~/.local/bin", "~/.local/share/clipb-paste/bin", "~/bin")


def search_paths() -> list[str]:
    seen: list[str] = []
    entries = os.environ.get("PATH", "").split(os.pathsep)
    entries += [os.path.expanduser(p) for p in _WRAPPER_DIRS]
    entries += list(_EXTRA_PATHS)
    for e in entries:
        if e and e not in seen:
            seen.append(e)
    return seen


def which(name: str) -> str | None:
    """Procura um executável no PATH e nos diretórios extras."""
    found = shutil.which(name)
    if found:
        return found
    for d in search_paths():
        cand = Path(d) / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def run(argv: list[str], *, stdin: str | bytes | None = None, timeout: float = 5.0,
        env: dict[str, str] | None = None) -> RunResult:
    """Executa um comando curto. Nunca levanta exceção: devolve RunResult."""
    try:
        as_text = isinstance(stdin, str) or stdin is None
        proc = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            text=as_text,
            errors="replace" if as_text else None,
            timeout=timeout,
            env=env,
            start_new_session=True,
        )
        return RunResult(
            proc.returncode,
            proc.stdout if isinstance(proc.stdout, str) else proc.stdout.decode("utf-8", "replace"),
            proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace"),
        )
    except FileNotFoundError:
        return RunResult(127, "", f"comando não encontrado: {argv[0]}")
    except subprocess.TimeoutExpired:
        return RunResult(124, "", f"timeout após {timeout}s: {' '.join(argv[:3])}…", timed_out=True)
    except OSError as exc:
        return RunResult(126, "", f"{argv[0]}: {exc}")


def spawn(argv: list[str], *, stdin: bytes | None = None) -> subprocess.Popen[bytes] | None:
    """Dispara um processo em background, sem bloquear."""
    try:
        return subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        log.debug("falha ao executar %s: %s", argv[:2], exc)
        return None