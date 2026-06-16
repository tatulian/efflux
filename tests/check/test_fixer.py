import textwrap

from efflux.check.fixer import FunctionFix, fix_file, plan_fixes
from efflux.check.model import CallSite, EffectRef, FunctionModel, RaiseSite


def _fns(*models):
    return {m.fullname: m for m in models}


def test_plan_fixes_safe_extends_declared():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel("m.f", "m.py", 3, declared=frozenset(), calls=[CallSite("m.leaf", 4)])
    by_file = plan_fixes(_fns(leaf, f), {W: frozenset({W})}, {}, {}, aggressive=False)
    fixes = by_file["m.py"]
    assert len(fixes) == 1
    assert fixes[0].model.fullname == "m.f"
    assert fixes[0].add == [EffectRef(W)]
    assert fixes[0].wrap is False


def test_plan_fixes_safe_ignores_undeclared():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel("m.f", "m.py", 3, declared=None, calls=[CallSite("m.leaf", 4)])
    by_file = plan_fixes(_fns(leaf, f), {W: frozenset({W})}, {}, {}, aggressive=False)
    assert by_file == {}


def test_plan_fixes_aggressive_wraps_undeclared():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel("m.f", "m.py", 3, declared=None, calls=[CallSite("m.leaf", 4)])
    by_file = plan_fixes(_fns(leaf, f), {W: frozenset({W})}, {}, {}, aggressive=True)
    fixes = by_file["m.py"]
    assert len(fixes) == 1
    assert fixes[0].wrap is True
    assert fixes[0].add == [EffectRef(W)]


def _src(text):
    return textwrap.dedent(text).lstrip("\n")


def test_fix_file_extends_existing_effects():
    source = _src(
        """
        from efflux import Effects

        def f() -> Effects[int]:
            return leaf()
        """
    )
    model = FunctionModel("m.f", "m.py", 3, declared=frozenset())
    fix = FunctionFix(model, [EffectRef("efflux.effects.WritesDB")], wrap=False)
    new_source, skipped = fix_file(source, [fix])
    assert "Effects[int, WritesDB]" in new_source
    assert "WritesDB" in new_source.splitlines()[0]  # added to the efflux import
    assert skipped == []


def test_fix_file_wraps_plain_annotation():
    source = _src(
        """
        from efflux import Effects

        def f() -> int:
            return leaf()
        """
    )
    model = FunctionModel("m.f", "m.py", 3, declared=None)
    fix = FunctionFix(model, [EffectRef("efflux.effects.WritesDB")], wrap=True)
    new_source, skipped = fix_file(source, [fix])
    assert "-> Effects[int, WritesDB]:" in new_source
    assert skipped == []


def test_fix_file_skips_unannotated():
    source = _src(
        """
        def f():
            return leaf()
        """
    )
    model = FunctionModel("m.f", "m.py", 1, declared=None)
    fix = FunctionFix(model, [EffectRef("efflux.effects.WritesDB")], wrap=True)
    new_source, skipped = fix_file(source, [fix])
    assert skipped == ["m.f"]
    assert new_source == source


def test_fix_file_imports_exception_for_raises():
    # Adding Raises[PaymentError] must also import PaymentError, or the generated
    # annotation references an undefined name.
    source = _src(
        """
        from efflux import Effects

        def f() -> Effects[int]:
            return leaf()
        """
    )
    model = FunctionModel("m.f", "m.py", 3, declared=frozenset())
    fix = FunctionFix(
        model, [EffectRef("efflux.effects.Raises", "myapp.errors.PaymentError")], wrap=False
    )
    new_source, skipped = fix_file(source, [fix])
    assert "Effects[int, Raises[PaymentError]]" in new_source
    assert "from myapp.errors import PaymentError" in new_source
    assert skipped == []


def test_fix_file_does_not_import_builtin_exception():
    # A builtin exception in Raises[E] needs no import (would be an error to import).
    source = _src(
        """
        from efflux import Effects

        def f() -> Effects[int]:
            return leaf()
        """
    )
    model = FunctionModel("m.f", "m.py", 3, declared=frozenset())
    fix = FunctionFix(
        model, [EffectRef("efflux.effects.Raises", "builtins.ValueError")], wrap=False
    )
    new_source, _ = fix_file(source, [fix])
    assert "Effects[int, Raises[ValueError]]" in new_source
    assert "import ValueError" not in new_source


def test_fix_file_imports_user_effect_from_its_own_module():
    # A user-defined effect must be imported from its defining module, not efflux.
    source = _src(
        """
        from efflux import Effects

        def f() -> Effects[int]:
            return leaf()
        """
    )
    model = FunctionModel("m.f", "m.py", 3, declared=frozenset())
    fix = FunctionFix(model, [EffectRef("myapp.effects.WritesKafka")], wrap=False)
    new_source, _ = fix_file(source, [fix])
    assert "Effects[int, WritesKafka]" in new_source
    assert "from myapp.effects import WritesKafka" in new_source
    assert "from efflux import WritesKafka" not in new_source


def test_plan_fixes_includes_raises_under_strict():
    # Under --strict, an explicit-raise effect must be planned too (was ignored).
    R = "efflux.effects.Raises"
    f = FunctionModel(
        "m.f",
        "m.py",
        1,
        declared=frozenset(),
        raises=[RaiseSite(EffectRef(R, "builtins.ValueError"), 2)],
    )
    by_file = plan_fixes(
        _fns(f),
        {},
        {"builtins.ValueError": frozenset({"builtins.ValueError"})},
        {},
        aggressive=False,
        include_raises=True,
    )
    assert by_file["m.py"][0].add == [EffectRef(R, "builtins.ValueError")]
