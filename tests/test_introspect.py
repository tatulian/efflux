import importlib.util
from typing import get_args

from efflux import Effects, Logs, Raises, WritesDB, effects_of
from efflux._core import EffectSpec


def test_effects_reduces_to_annotated():
    t = Effects[int, WritesDB, Logs]
    args = get_args(t)  # Annotated[int, EffectSpec(...)] -> (int, EffectSpec(...))
    assert args[0] is int
    assert isinstance(args[1], EffectSpec)
    assert args[1].effects == (WritesDB, Logs)


def test_effects_of_reads_effects():
    def f() -> Effects[int, WritesDB, Logs]: ...

    assert effects_of(f) == (WritesDB, Logs)


def test_effects_of_with_parameterized_raises():
    def f() -> Effects[int, Raises[ValueError]]: ...

    (eff,) = effects_of(f)
    assert get_args(eff) == (ValueError,)  # this is Raises[ValueError]


def test_effects_of_plain_return_is_empty():
    def f() -> int: ...

    assert effects_of(f) == ()


def test_effects_of_resolves_string_annotations(tmp_path):
    # PEP 563 / lazy annotations: the annotation is a string and must
    # still resolve when effects_of calls get_type_hints.
    p = tmp_path / "future_sample.py"
    p.write_text(
        "from __future__ import annotations\n"
        "from efflux import Effects, WritesDB\n"
        "def g() -> Effects[int, WritesDB]: ...\n"
    )
    spec = importlib.util.spec_from_file_location("future_sample", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert effects_of(mod.g) == (WritesDB,)
