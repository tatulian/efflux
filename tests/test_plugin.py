def test_effects_erases_to_return_type(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, WritesDB
        def f() -> Effects[int, WritesDB]:
            return 1
        reveal_type(f())
        """
    )
    # mypy 2.x reveals builtins by short name ("int"), not "builtins.int".
    assert 'Revealed type is "int"' in out, out
    assert status == 0, out


def test_return_type_is_non_invasive(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, Logs
        def f() -> Effects[str, Logs]:
            return ""
        x: str = f()
        """
    )
    assert status == 0, out


def test_multiple_effects_still_erase(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, WritesDB, Logs, Network
        def f() -> Effects[bytes, WritesDB, Logs, Network]:
            return b""
        reveal_type(f())
        """
    )
    # mypy 2.x reveals builtins by short name ("bytes"), not "builtins.bytes".
    assert 'Revealed type is "bytes"' in out, out
    assert status == 0, out


def test_bare_effects_is_rejected(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects
        x: Effects
        """
    )
    assert status == 1, out
    assert "Effects[...] requires a return type as its first argument" in out, out


def test_erased_type_is_exact_not_any(mypy_check):
    # If the plugin returned AnyType instead of the real return type, this
    # would wrongly pass. Assigning Effects[str, ...] to int must be an error.
    out, status = mypy_check(
        """
        from efflux import Effects, Logs
        def f() -> Effects[str, Logs]:
            return ""
        x: int = f()
        """
    )
    assert status == 1, out
    assert "Incompatible types in assignment" in out, out


def test_non_effect_arg_is_rejected(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects
        def f() -> Effects[int, str]:
            return 1
        """
    )
    assert status == 1, out
    assert "is not a valid effect" in out, out


def test_user_defined_effect_is_accepted(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, Effect
        class WritesKafka(Effect): ...
        def f() -> Effects[int, WritesKafka]:
            return 1
        reveal_type(f())
        """
    )
    assert status == 0, out
    assert 'Revealed type is "int"' in out, out


def test_raises_accepts_exception_subclass(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, Raises
        def f() -> Effects[int, Raises[ValueError]]:
            return 1
        reveal_type(f())
        """
    )
    assert status == 0, out
    assert 'Revealed type is "int"' in out, out


def test_raises_rejects_non_exception(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, Raises
        def f() -> Effects[int, Raises[int]]:
            return 1
        """
    )
    assert status == 1, out
    assert "Raises[...] type argument must subclass BaseException" in out, out


def test_bare_raises_is_accepted(mypy_check):
    out, status = mypy_check(
        """
        from efflux import Effects, Raises
        def f() -> Effects[int, Raises]:
            return 1
        reveal_type(f())
        """
    )
    assert status == 0, out
    assert 'Revealed type is "int"' in out, out


def test_non_instance_arg_is_rejected(mypy_check):
    # Any (and other non-Instance types) reach the not-an-effect branch of
    # _is_effect and must be rejected, not silently accepted.
    out, status = mypy_check(
        """
        from typing import Any
        from efflux import Effects
        def f() -> Effects[int, Any]:
            return 1
        """
    )
    assert status == 1, out
    assert "is not a valid effect" in out, out
