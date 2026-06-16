"""Integration tests for the built-in external map against *real* third-party
libraries. They assert the shipped fullnames actually match what mypy resolves —
the keys are definition-site fullnames that can drift between library versions, so
these guard against silent rot. Skipped when a library (or its types) is absent."""

from __future__ import annotations

import importlib.util

import pytest

from efflux.check.default_externals import DEFAULT_EXTERNAL_MAP
from efflux.check.engine import analyze
from efflux.check.inference import infer
from efflux.check.model import EffectRef


def _external() -> dict[str, frozenset[EffectRef]]:
    return {
        callee: frozenset(EffectRef(name) for name in names)
        for callee, names in DEFAULT_EXTERNAL_MAP.items()
    }


def _inferred_effects(tmp_path, source: str) -> set[str]:
    (tmp_path / "m.py").write_text(source)
    external = _external()
    functions, ancestors, exc = analyze([str(tmp_path / "m.py")], external=external)
    return {e.short for e in infer(functions, external, ancestors, exc)["m.f"]}


def _missing(*modules: str) -> bool:
    return any(importlib.util.find_spec(m) is None for m in modules)


@pytest.mark.skipif(_missing("requests"), reason="requests (and types-requests) not installed")
def test_requests_get_is_network(tmp_path):
    effects = _inferred_effects(
        tmp_path,
        "import requests\nfrom efflux import Effects\n"
        "def f() -> Effects[object]:\n    return requests.get('http://x')\n",
    )
    assert "Network" in effects


@pytest.mark.skipif(_missing("httpx"), reason="httpx not installed")
def test_httpx_get_is_network(tmp_path):
    effects = _inferred_effects(
        tmp_path,
        "import httpx\nfrom efflux import Effects\n"
        "def f() -> Effects[object]:\n    return httpx.get('http://x')\n",
    )
    assert "Network" in effects


@pytest.mark.skipif(_missing("sqlalchemy"), reason="sqlalchemy not installed")
def test_sqlalchemy_create_engine_is_database(tmp_path):
    effects = _inferred_effects(
        tmp_path,
        "import sqlalchemy\nfrom efflux import Effects\n"
        "def f() -> Effects[object]:\n    return sqlalchemy.create_engine('sqlite://')\n",
    )
    assert "Database" in effects
