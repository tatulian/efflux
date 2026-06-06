from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_type_hints

from efflux._core import EffectSpec


def effects_of(func: Callable[..., Any]) -> tuple[object, ...]:
    """Return the declared effects of ``func`` in declaration order.

    Reads the ``Effects[...]`` metadata off the return annotation. Returns
    an empty tuple if the function has no effect annotation.
    """
    hints = get_type_hints(func, include_extras=True)
    ret = hints.get("return")
    for meta in getattr(ret, "__metadata__", ()):
        if isinstance(meta, EffectSpec):
            return meta.effects
    return ()
