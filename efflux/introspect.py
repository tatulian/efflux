from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_type_hints

from efflux._core import EffectSpec


def effects_of(func: Callable[..., Any]) -> tuple[object, ...]:
    """Return the declared effects of ``func`` in declaration order.

    Reads the ``Effects[...]`` metadata off the return annotation. Returns
    an empty tuple if the function has no effect annotation.

    Robust to ``from __future__ import annotations`` combined with names that are
    only importable under ``TYPE_CHECKING``: if full resolution fails (e.g. the
    return type ``T`` is a type-only import), the effects are still recovered by
    evaluating the return annotation with placeholders for the unresolved names.
    """
    try:
        ret = get_type_hints(func, include_extras=True).get("return")
    except Exception:
        ret = _lenient_return_annotation(func)
    for meta in getattr(ret, "__metadata__", ()):
        if isinstance(meta, EffectSpec):
            return meta.effects
    return ()


def _lenient_return_annotation(func: Callable[..., Any]) -> object:
    """Best-effort evaluation of ``func``'s (stringized) return annotation when
    ``get_type_hints`` cannot resolve every name. Unresolved names are bound to
    throwaway placeholder classes so ``Effects[...]`` still builds and its
    ``EffectSpec`` (with the real, importable effect classes) is recoverable.
    Returns ``None`` if the annotation can't be evaluated at all."""
    annotation = getattr(func, "__annotations__", {}).get("return")
    if not isinstance(annotation, str):
        return annotation  # already evaluated (no stringized annotations) — nothing to do
    namespace = dict(getattr(func, "__globals__", {}))
    for _ in range(100):  # bounded: bind one missing name per iteration, then retry
        try:
            return eval(annotation, namespace)  # the function's own annotation, not user input
        except NameError as exc:
            name = getattr(exc, "name", None)
            if not name or name in namespace:
                return None
            namespace[name] = type(name, (), {})  # placeholder so the subscript still builds
        except Exception:
            return None
    return None
