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
        'm.py:3: error: "f" has undeclared effect "WritesDB" (from "m.g")  [undeclared-effect]'
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


def test_diagnostic_format_for_raise_provenance():
    from efflux.check.model import RaiseSite

    m = FunctionModel(fullname="m.c", file="m.py", line=1, declared=frozenset())
    d = Diagnostic(
        function=m,
        effect=EffectRef("efflux.effects.Raises", "builtins.ValueError"),
        call=RaiseSite(EffectRef("efflux.effects.Raises", "builtins.ValueError"), 4),
    )
    assert d.format() == (
        'm.py:4: error: "c" has undeclared effect "Raises[ValueError]"  [undeclared-effect]'
    )


def test_diagnostic_format_uses_effectref_short():
    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=frozenset())
    d = Diagnostic(
        function=m,
        effect=EffectRef("efflux.effects.Raises", "builtins.ValueError"),
        call=CallSite("m.g", 3),
    )
    assert d.format() == (
        'm.py:3: error: "f" has undeclared effect "Raises[ValueError]" (from "m.g")  '
        "[undeclared-effect]"
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


def test_callsite_unresolved_hint_defaults_none():
    assert CallSite("m.g", 3).unresolved_hint is None
    assert CallSite(None, 3, unresolved_hint="do_io").unresolved_hint == "do_io"


def test_unresolved_call_format_with_hint():
    from efflux.check.model import UnresolvedCall

    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=None)
    u = UnresolvedCall(function=m, call=CallSite(None, 5, unresolved_hint="do_io"))
    assert u.format() == (
        'm.py:5: note: unresolved call to `do_io()` in "f" '
        "— effects assumed pure  [unresolved-call]"
    )


def test_unresolved_call_format_without_hint():
    from efflux.check.model import UnresolvedCall

    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=None)
    u = UnresolvedCall(function=m, call=CallSite(None, 5))
    assert u.format() == (
        'm.py:5: note: unresolved call in "f" — effects assumed pure  [unresolved-call]'
    )


def test_unresolved_call_format_falls_back_to_bare_callee():
    from efflux.check.model import UnresolvedCall

    m = FunctionModel(fullname="m.f", file="m.py", line=1, declared=None)
    u = UnresolvedCall(function=m, call=CallSite("cb", 4))  # a callback: callee is the bare name
    assert u.format() == (
        'm.py:4: note: unresolved call to `cb()` in "f" — effects assumed pure  [unresolved-call]'
    )


def test_raise_site_defaults():
    from efflux.check.model import RaiseSite

    r = RaiseSite(effect=EffectRef("efflux.effects.Raises", "builtins.ValueError"), line=5)
    assert r.effect == EffectRef("efflux.effects.Raises", "builtins.ValueError")
    assert r.line == 5
    assert r.caught == frozenset()
    assert r.allowed == frozenset()


def test_function_model_raises_defaults_empty():
    m = FunctionModel("m.f", "m.py", 1, declared=None)
    assert m.raises == []


def test_unused_declaration_format_tag():
    from efflux.check.model import UnusedDeclaration

    m = FunctionModel(fullname="m.b", file="m.py", line=4, declared=frozenset())
    u = UnusedDeclaration(function=m, effect=EffectRef("efflux.effects.WritesDB"))
    assert u.format() == ('m.py:4: warning: "b" declares unused effect "WritesDB"  [unused-effect]')


def test_unused_declaration_format_raises():
    from efflux.check.model import UnusedDeclaration

    m = FunctionModel(fullname="m.b", file="m.py", line=4, declared=frozenset())
    u = UnusedDeclaration(
        function=m, effect=EffectRef("efflux.effects.Raises", "builtins.ValueError")
    )
    assert u.format() == (
        'm.py:4: warning: "b" declares unused effect "Raises[ValueError]"  [unused-effect]'
    )


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
    assert "app/domain.py:5:" in msg  # points at the call line, not the def line
    assert 'breaks boundary "app.domain.*"' in msg
    assert 'forbidden effect "Network"' in msg
    assert "requests.api.get" in msg
    assert '"f"' in msg and '"app.domain.f"' not in msg  # short name, no module
