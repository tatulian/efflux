from __future__ import annotations

import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _resolve_effect(name: str) -> str:
    """Resolve a config effect name to a class fullname. A dotted name is taken
    as a fullname already; a bare name must be a built-in effect (e.g. Network).
    An unknown bare name is a config error."""
    if "." in name:
        return name
    import efflux.effects as builtins_

    cls = getattr(builtins_, name, None)
    if cls is None:
        raise ValueError(
            f"unknown effect {name!r} in [tool.efflux.external]: use a built-in "
            f"effect name (e.g. Network) or a dotted fullname (e.g. myapp.effects.Foo)"
        )
    return f"{cls.__module__}.{cls.__qualname__}"


def _find_pyproject(paths: list[str]) -> str | None:
    first = os.path.realpath(paths[0]) if paths else os.getcwd()
    current = first if os.path.isdir(first) else os.path.dirname(first)
    while True:
        candidate = os.path.join(current, "pyproject.toml")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def load_external_map(paths: list[str]) -> dict[str, frozenset[str]]:
    """Load ``[tool.efflux.external]`` from the nearest pyproject.toml above the
    first analyzed path, as ``{callee_fullname: frozenset(effect_fullnames)}``.
    Returns an empty map when there is no config."""
    pyproject = _find_pyproject(paths)
    if pyproject is None:
        return {}
    with open(pyproject, "rb") as handle:
        data = tomllib.load(handle)
    raw = data.get("tool", {}).get("efflux", {}).get("external", {})
    result: dict[str, frozenset[str]] = {}
    for callee, names in raw.items():
        if not isinstance(names, list):
            raise TypeError(
                f"[tool.efflux.external]: value for {callee!r} must be a list of "
                f"effect names, got {type(names).__name__}"
            )
        result[callee] = frozenset(_resolve_effect(name) for name in names)
    return result


def load_boundaries(paths: list[str]) -> dict[str, frozenset[str]]:
    """Load ``[tool.efflux.boundaries]`` as ``{glob: frozenset(forbidden_effect_fullnames)}``.
    Each value is a table ``{ forbid = [<effect names>] }``. Empty when unconfigured."""
    pyproject = _find_pyproject(paths)
    if pyproject is None:
        return {}
    with open(pyproject, "rb") as handle:
        data = tomllib.load(handle)
    raw = data.get("tool", {}).get("efflux", {}).get("boundaries", {})
    result: dict[str, frozenset[str]] = {}
    for pattern, spec in raw.items():
        if not isinstance(spec, dict):
            raise TypeError(
                f"[tool.efflux.boundaries]: value for {pattern!r} must be a table "
                f"like {{ forbid = [...] }}, got {type(spec).__name__}"
            )
        forbid = spec.get("forbid", [])
        if not isinstance(forbid, list):
            raise TypeError(f"[tool.efflux.boundaries]: 'forbid' for {pattern!r} must be a list")
        result[pattern] = frozenset(_resolve_effect(name) for name in forbid)
    return result
