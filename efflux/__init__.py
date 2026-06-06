"""efflux — side effects made visible in return-type annotations."""

from efflux._core import Effect, Effects, EffectSpec
from efflux.allow import allow
from efflux.effects import (
    IO,
    Blocks,
    Clock,
    Database,
    Emits,
    Filesystem,
    Logs,
    MutatesGlobal,
    Network,
    Raises,
    Random,
    ReadsDB,
    ReadsEnv,
    ReadsFS,
    WritesDB,
    WritesFS,
)
from efflux.introspect import effects_of

__all__ = [
    "IO",
    "Blocks",
    "Clock",
    "Database",
    "Effect",
    "EffectSpec",
    "Effects",
    "Emits",
    "Filesystem",
    "Logs",
    "MutatesGlobal",
    "Network",
    "Raises",
    "Random",
    "ReadsDB",
    "ReadsEnv",
    "ReadsFS",
    "WritesDB",
    "WritesFS",
    "allow",
    "effects_of",
]
