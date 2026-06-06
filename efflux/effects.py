from __future__ import annotations

from typing import Generic, TypeVar

from efflux._core import Effect

E = TypeVar("E", bound=BaseException)


class Raises(Effect, Generic[E]):
    """The function may raise ``E`` (or a subclass)."""


class IO(Effect):
    """Interacts with the outside world (network, filesystem, database, env)."""


# I/O subcategories
class Filesystem(IO):
    """Touches the local filesystem (umbrella for ReadsFS / WritesFS)."""


class Database(IO):
    """Touches a database (umbrella for ReadsDB / WritesDB)."""


# I/O direct children (no subcategory)
class Network(IO): ...


class ReadsEnv(IO): ...


class ReadsFS(Filesystem): ...


class WritesFS(Filesystem): ...


# Data stores
class ReadsDB(Database): ...


class WritesDB(Database): ...


# Observability
class Logs(Effect): ...


class Emits(Effect): ...


# Nondeterminism
class Random(Effect): ...


class Clock(Effect): ...


# State / scheduling
class MutatesGlobal(Effect): ...


class Blocks(Effect): ...
