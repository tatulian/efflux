from __future__ import annotations

import json
from pathlib import Path

from efflux.check.model import Diagnostic

Key = tuple[str, str, str | None]


def diagnostic_key(d: Diagnostic) -> Key:
    return (d.function.fullname, d.effect.short, getattr(d.call, "callee", None))


def write_baseline(path: str, diagnostics: list[Diagnostic]) -> None:
    entries = sorted(
        (
            {
                "function": d.function.fullname,
                "effect": d.effect.short,
                "callee": getattr(d.call, "callee", None),
            }
            for d in diagnostics
        ),
        key=lambda e: (e["function"] or "", e["effect"] or "", e["callee"] or ""),
    )
    Path(path).write_text(json.dumps(entries, indent=2) + "\n")


def load_keys(path: str) -> set[Key]:
    data = json.loads(Path(path).read_text())
    return {(e["function"], e["effect"], e["callee"]) for e in data}


def filter_diagnostics(diagnostics: list[Diagnostic], keys: set[Key]) -> list[Diagnostic]:
    return [d for d in diagnostics if diagnostic_key(d) not in keys]
