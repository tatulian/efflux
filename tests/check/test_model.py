from efflux.check.model import CallSite, Diagnostic, EffectRef, FunctionModel


def test_function_model_defaults():
    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=None)
    assert m.calls == []
    assert m.declared is None


def test_call_site_holds_callee_and_line():
    c = CallSite(callee="m.g", line=3)
    assert c.callee == "m.g"
    assert c.line == 3


def test_diagnostic_message_format():
    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=frozenset())
    d = Diagnostic(function=m, effect=EffectRef("efflux.effects.WritesDB"), call=CallSite("m.g", 3))
    assert d.format() == (
        'm.py:1: error: function "m.f" has undeclared effect "WritesDB" '
        '(introduced by call to "m.g" at line 3)'
    )


def test_declared_none_vs_empty_are_distinct():
    no_decl = FunctionModel("m.f", "m.py", 1, declared=None)
    declared_pure = FunctionModel("m.g", "m.py", 2, declared=frozenset())
    assert no_decl.declared is None
    assert declared_pure.declared is not None
    assert len(declared_pure.declared) == 0


def test_effectref_short_tag():
    assert EffectRef("efflux.effects.WritesDB").short == "WritesDB"


def test_effectref_short_raises():
    assert EffectRef("efflux.effects.Raises", "builtins.ValueError").short == "Raises[ValueError]"


def test_effectref_is_hashable_and_eq():
    a = EffectRef("efflux.effects.Raises", "builtins.ValueError")
    b = EffectRef("efflux.effects.Raises", "builtins.ValueError")
    assert a == b and hash(a) == hash(b)
    assert {a, b} == {a}


def test_diagnostic_format_uses_effectref_short():
    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=frozenset())
    d = Diagnostic(
        function=m,
        effect=EffectRef("efflux.effects.Raises", "builtins.ValueError"),
        call=CallSite("m.g", 3),
    )
    assert d.format() == (
        'm.py:1: error: function "m.f" has undeclared effect "Raises[ValueError]" '
        '(introduced by call to "m.g" at line 3)'
    )


def test_callsite_discharge_defaults_empty():
    c = CallSite("m.g", 3)
    assert c.caught == frozenset()
    assert c.allowed == frozenset()


def test_callsite_carries_discharge_context():
    c = CallSite(
        "m.g",
        3,
        caught=frozenset({"builtins.ValueError"}),
        allowed=frozenset({"efflux.effects.WritesDB"}),
    )
    assert c.caught == frozenset({"builtins.ValueError"})
    assert c.allowed == frozenset({"efflux.effects.WritesDB"})


def test_boundary_violation_format():
    from efflux.check.model import BoundaryViolation

    m = FunctionModel(fullname="app.domain.f", file="app/domain.py", line=3, declared=frozenset())
    v = BoundaryViolation(
        function=m,
        boundary="app.domain.*",
        effect=EffectRef("efflux.effects.Network"),
        call=CallSite("requests.api.get", 5),
    )
    msg = v.format()
    assert "app/domain.py:3:" in msg
    assert 'breaks boundary "app.domain.*"' in msg
    assert 'forbidden effect "Network"' in msg
    assert "requests.api.get" in msg
