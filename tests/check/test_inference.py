from efflux.check.inference import check, infer
from efflux.check.model import CallSite, EffectRef, FunctionModel


def _fns(*models):
    return {m.fullname: m for m in models}


def test_infer_propagates_through_undeclared_intermediate():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    mid = FunctionModel("m.mid", "m.py", 4, declared=None, calls=[CallSite("m.leaf", 5)])
    top = FunctionModel("m.top", "m.py", 7, declared=None, calls=[CallSite("m.mid", 8)])
    inferred = infer(_fns(leaf, mid, top), external={}, ancestors={}, exc_ancestors={})
    assert inferred["m.mid"] == frozenset({EffectRef(W)})
    assert inferred["m.top"] == frozenset({EffectRef(W)})


def test_infer_uses_declared_contract_not_body_for_declared_callee():
    W = "efflux.effects.WritesDB"
    N = "efflux.effects.Network"
    h = FunctionModel("m.h", "m.py", 1, declared=frozenset({EffectRef(N)}))
    g = FunctionModel(
        "m.g", "m.py", 3, declared=frozenset({EffectRef(W)}), calls=[CallSite("m.h", 4)]
    )
    f = FunctionModel("m.f", "m.py", 6, declared=None, calls=[CallSite("m.g", 7)])
    inferred = infer(_fns(h, g, f), external={}, ancestors={}, exc_ancestors={})
    assert inferred["m.f"] == frozenset({EffectRef(W)})  # not N — g's contract hides it


def test_infer_unresolved_and_external_calls_are_pure():
    f = FunctionModel(
        "m.f",
        "m.py",
        1,
        declared=None,
        calls=[CallSite(None, 2), CallSite("requests.get", 3)],
    )
    inferred = infer(_fns(f), external={}, ancestors={}, exc_ancestors={})
    assert inferred["m.f"] == frozenset()


def test_infer_terminates_on_cycle():
    W = "efflux.effects.WritesDB"
    a = FunctionModel("m.a", "m.py", 1, declared=None, calls=[CallSite("m.b", 2)])
    b = FunctionModel(
        "m.b", "m.py", 3, declared=None, calls=[CallSite("m.a", 4), CallSite("m.leaf", 5)]
    )
    leaf = FunctionModel("m.leaf", "m.py", 7, declared=frozenset({EffectRef(W)}))
    inferred = infer(_fns(a, b, leaf), external={}, ancestors={}, exc_ancestors={})
    assert inferred["m.a"] == frozenset({EffectRef(W)})
    assert inferred["m.b"] == frozenset({EffectRef(W)})


def test_check_reports_undeclared_effect():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel("m.f", "m.py", 3, declared=frozenset(), calls=[CallSite("m.leaf", 4)])
    diags = check(_fns(leaf, f), ancestors={W: frozenset({W})}, exc_ancestors={}, external={})
    assert len(diags) == 1
    assert diags[0].effect == EffectRef(W)
    assert diags[0].function.fullname == "m.f"
    assert diags[0].call.callee == "m.leaf"


def test_check_declared_function_is_ok_when_it_declares_the_effect():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel(
        "m.f", "m.py", 3, declared=frozenset({EffectRef(W)}), calls=[CallSite("m.leaf", 4)]
    )
    diags = check(_fns(leaf, f), ancestors={W: frozenset({W})}, exc_ancestors={}, external={})
    assert diags == []


def test_check_subsumption_broad_declaration_covers_narrow():
    W = "efflux.effects.WritesDB"
    IO = "efflux.effects.IO"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel(
        "m.f", "m.py", 3, declared=frozenset({EffectRef(IO)}), calls=[CallSite("m.leaf", 4)]
    )
    diags = check(_fns(leaf, f), ancestors={W: frozenset({W, IO})}, exc_ancestors={}, external={})
    assert diags == []


def test_check_ignores_functions_without_declaration():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel("m.f", "m.py", 3, declared=None, calls=[CallSite("m.leaf", 4)])
    diags = check(_fns(leaf, f), ancestors={W: frozenset({W})}, exc_ancestors={}, external={})
    assert diags == []


def test_check_attributes_each_effect_to_its_introducing_call():
    W = "efflux.effects.WritesDB"
    N = "efflux.effects.Network"
    lw = FunctionModel("m.lw", "m.py", 1, declared=frozenset({EffectRef(W)}))
    ln = FunctionModel("m.ln", "m.py", 2, declared=frozenset({EffectRef(N)}))
    f = FunctionModel(
        "m.f", "m.py", 4, declared=frozenset(), calls=[CallSite("m.lw", 5), CallSite("m.ln", 6)]
    )
    diags = check(
        _fns(lw, ln, f),
        ancestors={W: frozenset({W}), N: frozenset({N})},
        exc_ancestors={},
        external={},
    )
    by_effect = {d.effect: d.call.callee for d in diags}
    assert by_effect == {EffectRef(W): "m.lw", EffectRef(N): "m.ln"}


def test_check_effect_absent_from_ancestors_covers_only_itself():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel(
        "m.f", "m.py", 3, declared=frozenset({EffectRef(W)}), calls=[CallSite("m.leaf", 4)]
    )
    # ancestors map is EMPTY -> effect covers only itself; declared {W} still covers W
    diags = check(_fns(leaf, f), ancestors={}, exc_ancestors={}, external={})
    assert diags == []


def test_infer_self_recursion_terminates():
    W = "efflux.effects.WritesDB"
    f = FunctionModel(
        "m.f", "m.py", 1, declared=None, calls=[CallSite("m.f", 2), CallSite("m.leaf", 3)]
    )
    leaf = FunctionModel("m.leaf", "m.py", 5, declared=frozenset({EffectRef(W)}))
    inferred = infer(_fns(f, leaf), external={}, ancestors={}, exc_ancestors={})
    assert inferred["m.f"] == frozenset({EffectRef(W)})


def test_check_declared_function_in_cycle_is_ok():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    a = FunctionModel(
        "m.a", "m.py", 3, declared=frozenset({EffectRef(W)}), calls=[CallSite("m.b", 4)]
    )
    b = FunctionModel(
        "m.b", "m.py", 6, declared=None, calls=[CallSite("m.a", 7), CallSite("m.leaf", 8)]
    )
    diags = check(_fns(leaf, a, b), ancestors={W: frozenset({W})}, exc_ancestors={}, external={})
    assert diags == []


def test_infer_external_map_contributes_effects():
    N = "efflux.effects.Network"
    f = FunctionModel("m.f", "m.py", 1, declared=None, calls=[CallSite("requests.get", 2)])
    inferred = infer(
        _fns(f),
        external={"requests.get": frozenset({EffectRef(N)})},
        ancestors={},
        exc_ancestors={},
    )
    assert inferred["m.f"] == frozenset({EffectRef(N)})


def test_check_raises_exception_subsumption():
    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf", "m.py", 1, declared=frozenset({EffectRef(R, "builtins.ValueError")})
    )
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset({EffectRef(R, "builtins.Exception")}),
        calls=[CallSite("m.leaf", 4)],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    diags = check(_fns(leaf, f), ancestors={}, exc_ancestors=exc_anc, external={})
    assert diags == []


def test_check_raises_sibling_not_covered():
    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf", "m.py", 1, declared=frozenset({EffectRef(R, "builtins.KeyError")})
    )
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset({EffectRef(R, "builtins.ValueError")}),
        calls=[CallSite("m.leaf", 4)],
    )
    exc_anc = {
        "builtins.KeyError": frozenset(
            {
                "builtins.KeyError",
                "builtins.LookupError",
                "builtins.Exception",
                "builtins.BaseException",
            }
        )
    }
    diags = check(_fns(leaf, f), ancestors={}, exc_ancestors=exc_anc, external={})
    assert len(diags) == 1
    assert diags[0].effect == EffectRef(R, "builtins.KeyError")


def test_check_bare_raises_covers_parameterized():
    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf", "m.py", 1, declared=frozenset({EffectRef(R, "builtins.ValueError")})
    )
    f = FunctionModel(
        "m.f", "m.py", 3, declared=frozenset({EffectRef(R)}), calls=[CallSite("m.leaf", 4)]
    )
    diags = check(_fns(leaf, f), ancestors={}, exc_ancestors={}, external={})
    assert diags == []


def test_check_boundaries_forbids_descendant_effect():
    from efflux.check.inference import check_boundaries

    N = "efflux.effects.Network"
    IO = "efflux.effects.IO"
    f = FunctionModel("app.domain.f", "app/domain.py", 3, declared=None, calls=[CallSite("net", 5)])
    functions = {"app.domain.f": f}
    external = {"net": frozenset({EffectRef(N)})}
    ancestors = {N: frozenset({N, IO})}
    boundaries = {"app.domain.*": frozenset({IO})}  # forbid IO

    violations = check_boundaries(functions, ancestors, {}, external, boundaries)
    assert len(violations) == 1
    assert violations[0].effect == EffectRef(N)
    assert violations[0].boundary == "app.domain.*"


def test_check_boundaries_ignores_non_matching_module():
    from efflux.check.inference import check_boundaries

    N = "efflux.effects.Network"
    f = FunctionModel(
        "app.adapters.f", "app/adapters.py", 3, declared=None, calls=[CallSite("net", 5)]
    )
    functions = {"app.adapters.f": f}
    external = {"net": frozenset({EffectRef(N)})}
    ancestors = {N: frozenset({N, "efflux.effects.IO"})}
    boundaries = {"app.domain.*": frozenset({"efflux.effects.IO"})}

    assert check_boundaries(functions, ancestors, {}, external, boundaries) == []


def test_infer_try_except_discharges_raises():
    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf", "m.py", 1, declared=frozenset({EffectRef(R, "builtins.ValueError")})
    )
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset(),
        calls=[CallSite("m.leaf", 4, caught=frozenset({"builtins.ValueError"}))],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    inferred = infer(_fns(leaf, f), external={}, ancestors={}, exc_ancestors=exc_anc)
    assert inferred["m.f"] == frozenset()


def test_infer_try_except_broad_catch_discharges():
    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf", "m.py", 1, declared=frozenset({EffectRef(R, "builtins.ValueError")})
    )
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset(),
        calls=[CallSite("m.leaf", 4, caught=frozenset({"builtins.Exception"}))],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    inferred = infer(_fns(leaf, f), external={}, ancestors={}, exc_ancestors=exc_anc)
    assert inferred["m.f"] == frozenset()


def test_infer_wrong_catch_does_not_discharge():
    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf", "m.py", 1, declared=frozenset({EffectRef(R, "builtins.ValueError")})
    )
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset(),
        calls=[CallSite("m.leaf", 4, caught=frozenset({"builtins.KeyError"}))],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    inferred = infer(_fns(leaf, f), external={}, ancestors={}, exc_ancestors=exc_anc)
    assert inferred["m.f"] == frozenset({EffectRef(R, "builtins.ValueError")})


def test_infer_allow_discharges_tag_via_subsumption():
    W = "efflux.effects.WritesDB"
    leaf = FunctionModel("m.leaf", "m.py", 1, declared=frozenset({EffectRef(W)}))
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset(),
        calls=[CallSite("m.leaf", 4, allowed=frozenset({"efflux.effects.IO"}))],
    )
    anc = {W: frozenset({W, "efflux.effects.Database", "efflux.effects.IO"})}
    inferred = infer(_fns(leaf, f), external={}, ancestors=anc, exc_ancestors={})
    assert inferred["m.f"] == frozenset()
