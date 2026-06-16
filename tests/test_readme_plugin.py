"""README claims for the visibility layer: the mypy plugin (via the in-process
``mypy_check`` fixture from tests/conftest.py) and the runtime helpers.

Complements tests/test_plugin.py — focuses on the exact snippets and promises in
README.md (the hero signature, the quickstart, "subclass Effect anywhere",
effects_of's declaration order, and the effect-reference table / hierarchy).
"""

from __future__ import annotations

import re
from typing import get_args

from efflux import Effects, Logs, Raises, WritesDB, effects_of


class PaymentError(Exception):
    """Module-level so annotations resolve under get_type_hints / mypy."""


class Receipt: ...


def test_readme_hero_signature_erases_to_return_type(mypy_check):
    # The README hero: the effects ride along as metadata; to mypy and callers,
    # charge still returns Receipt.
    out, status = mypy_check(
        """
        from efflux import Effects, Raises, WritesDB, Logs
        class Receipt: ...
        class PaymentError(Exception): ...
        def charge(user_id: int) -> Effects[Receipt, Raises[PaymentError], WritesDB, Logs]:
            return Receipt()
        reveal_type(charge(1))
        x: Receipt = charge(1)   # non-invasive: assigns straight to the real type
        """
    )
    assert status == 0, out
    assert re.search(r'Revealed type is "(?:\w+\.)?Receipt"', out), out


def test_readme_quickstart_optional_none_return(mypy_check):
    # README quickstart: def save_user(u) -> Effects[None, WritesDB].
    out, status = mypy_check(
        """
        from efflux import Effects, WritesDB
        def save_user(u: int) -> Effects[None, WritesDB]:
            return None
        reveal_type(save_user(0))
        """
    )
    assert status == 0, out
    assert 'Revealed type is "None"' in out, out


def test_readme_user_effect_subclass_of_builtin_typechecks(mypy_check):
    # README "Your own effects": class WritesPostgres(WritesDB)  # implies WritesDB.
    # A subclass of a concrete built-in effect is a valid effect argument.
    out, status = mypy_check(
        """
        from efflux import Effects, WritesDB
        class WritesPostgres(WritesDB): ...
        def f() -> Effects[int, WritesPostgres]:
            return 1
        reveal_type(f())
        """
    )
    assert status == 0, out
    assert 'Revealed type is "int"' in out, out


def test_readme_effects_of_declaration_order():
    # README: effects_of(charge) -> (Raises[PaymentError], WritesDB, Logs), in
    # declaration order.
    def charge() -> Effects[int, Raises[PaymentError], WritesDB, Logs]: ...

    effs = effects_of(charge)
    assert len(effs) == 3
    assert get_args(effs[0]) == (PaymentError,)  # effs[0] is Raises[PaymentError]
    assert effs[1] is WritesDB
    assert effs[2] is Logs


def test_readme_effect_reference_table_and_hierarchy():
    # Every effect named in the README reference table is importable from the
    # top-level package and is an Effect; the IO subtree matches the diagram.
    import efflux
    from efflux._core import Effect

    table = [
        "IO",
        "Network",
        "ReadsEnv",
        "Filesystem",
        "ReadsFS",
        "WritesFS",
        "Database",
        "ReadsDB",
        "WritesDB",
        "Process",
        "Raises",
        "Logs",
        "Emits",
        "Random",
        "Clock",
        "MutatesGlobal",
        "Blocks",
    ]
    for name in table:
        cls = getattr(efflux, name)
        assert isinstance(cls, type) and issubclass(cls, Effect), name

    from efflux import (
        IO,
        Database,
        Filesystem,
        Network,
        Process,
        ReadsDB,
        ReadsEnv,
        ReadsFS,
        WritesDB,
        WritesFS,
    )

    assert issubclass(Network, IO)
    assert issubclass(ReadsEnv, IO)
    assert issubclass(Process, IO)
    assert issubclass(Filesystem, IO) and issubclass(Database, IO)
    assert issubclass(ReadsFS, Filesystem) and issubclass(WritesFS, Filesystem)
    assert issubclass(ReadsDB, Database) and issubclass(WritesDB, Database)
