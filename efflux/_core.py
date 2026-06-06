from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated


class Effect:
    """Base class for all effects.

    Declare a new effect by subclassing it::

        class WritesKafka(Effect): ...

    Inheritance is both registration (the mypy plugin recognises any
    ``Effect`` subclass) and subsumption (``WritesPostgres`` subclassing
    ``WritesDB`` means the former implies the latter).
    """


@dataclass(frozen=True)
class EffectSpec:
    """Runtime payload attached to a return type via ``Annotated``.

    Holds the declared effects of a function in declaration order.
    """

    effects: tuple[object, ...]


class Effects:
    """Return-type form declaring a function's side effects.

    Use as ``Effects[ReturnType, *effects]``. The first subscript argument
    is the real return type; the rest are effect classes. At runtime this
    reduces to ``Annotated[ReturnType, EffectSpec(effects)]`` so the type is
    unchanged for callers and introspectable via ``effects_of``.

    The mypy plugin teaches the type checker that ``Effects[ReturnType, ...]``
    *is* ``ReturnType`` (non-invasive) and validates the effects.
    """

    def __class_getitem__(cls, item: object) -> object:
        params = item if isinstance(item, tuple) else (item,)
        if not params:
            raise TypeError("Effects[...] requires a return type")
        return_type, *effects = params
        return Annotated[return_type, EffectSpec(tuple(effects))]
