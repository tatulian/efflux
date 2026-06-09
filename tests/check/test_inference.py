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


def test_check_unused_reports_dead_declaration():
    from efflux.check.inference import check_unused

    R = "efflux.effects.Raises"
    # b declares Raises[ValueError] but has no calls -> inferred empty -> unused.
    b = FunctionModel("m.b", "m.py", 4, declared=frozenset({EffectRef(R, "builtins.ValueError")}))
    unused = check_unused(_fns(b), ancestors={}, exc_ancestors={}, external={})
    assert len(unused) == 1
    assert unused[0].function.fullname == "m.b"
    assert unused[0].effect == EffectRef(R, "builtins.ValueError")


def test_check_unused_skips_used_and_subsumed_declarations():
    from efflux.check.inference import check_unused

    W = "efflux.effects.WritesDB"
    IO = "efflux.effects.IO"
    # f declares IO and uses WritesDB (from an external call) -> IO covers it -> NOT unused.
    f = FunctionModel(
        "m.f", "m.py", 3, declared=frozenset({EffectRef(IO)}), calls=[CallSite("db.write", 4)]
    )
    unused = check_unused(
        _fns(f),
        ancestors={W: frozenset({W, IO})},
        exc_ancestors={},
        external={"db.write": frozenset({EffectRef(W)})},
    )
    assert unused == []


def test_check_unused_flags_only_the_dead_one_of_several():
    from efflux.check.inference import check_unused

    W = "efflux.effects.WritesDB"
    Rd = "efflux.effects.ReadsDB"
    # f declares ReadsDB + WritesDB but only WritesDB flows in -> ReadsDB is dead.
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset({EffectRef(Rd), EffectRef(W)}),
        calls=[CallSite("db.write", 4)],
    )
    anc = {W: frozenset({W}), Rd: frozenset({Rd})}
    unused = check_unused(
        _fns(f), ancestors=anc, exc_ancestors={}, external={"db.write": frozenset({EffectRef(W)})}
    )
    assert [u.effect for u in unused] == [EffectRef(Rd)]


def test_check_unused_broad_raises_covering_narrow_is_not_flagged():
    from efflux.check.inference import check_unused
    from efflux.check.model import RaiseSite

    R = "efflux.effects.Raises"
    # f declares Raises[Exception] and actually raises ValueError -> covered -> NOT unused.
    f = FunctionModel(
        "m.f",
        "m.py",
        3,
        declared=frozenset({EffectRef(R, "builtins.Exception")}),
        raises=[RaiseSite(EffectRef(R, "builtins.ValueError"), 4)],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    unused = check_unused(
        _fns(f), ancestors={}, exc_ancestors=exc_anc, external={}, include_raises=True
    )
    assert unused == []


def test_check_unused_ignores_functions_without_declaration():
    from efflux.check.inference import check_unused

    # declared is None -> inferred-and-propagated, never reported (gradual).
    f = FunctionModel("m.f", "m.py", 1, declared=None, calls=[])
    unused = check_unused(_fns(f), ancestors={}, exc_ancestors={}, external={})
    assert unused == []


def test_infer_include_raises_folds_and_propagates():
    from efflux.check.model import RaiseSite

    R = "efflux.effects.Raises"
    leaf = FunctionModel(
        "m.leaf",
        "m.py",
        1,
        declared=None,
        raises=[RaiseSite(EffectRef(R, "builtins.ValueError"), 2)],
    )
    caller = FunctionModel("m.caller", "m.py", 4, declared=None, calls=[CallSite("m.leaf", 5)])
    fns = _fns(leaf, caller)
    # default: raises ignored -> both pure
    base = infer(fns, external={}, ancestors={}, exc_ancestors={})
    assert base["m.leaf"] == frozenset()
    assert base["m.caller"] == frozenset()
    # include_raises: leaf's raise is folded in and propagates to caller
    inf = infer(fns, external={}, ancestors={}, exc_ancestors={}, include_raises=True)
    assert inf["m.leaf"] == frozenset({EffectRef(R, "builtins.ValueError")})
    assert inf["m.caller"] == frozenset({EffectRef(R, "builtins.ValueError")})


def test_infer_include_raises_self_caught_is_discharged():
    from efflux.check.model import RaiseSite

    R = "efflux.effects.Raises"
    # raise ValueError() inside try/except ValueError -> caught on the raise site -> discharged
    f = FunctionModel(
        "m.f",
        "m.py",
        1,
        declared=None,
        raises=[
            RaiseSite(
                EffectRef(R, "builtins.ValueError"), 3, caught=frozenset({"builtins.ValueError"})
            )
        ],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    inf = infer(_fns(f), external={}, ancestors={}, exc_ancestors=exc_anc, include_raises=True)
    assert inf["m.f"] == frozenset()


def test_check_include_raises_reports_undeclared_escaping_raise():
    from efflux.check.model import RaiseSite

    R = "efflux.effects.Raises"
    # c declares no effects but raises ValueError (uncaught on the raise site) -> reported.
    c = FunctionModel(
        "m.c",
        "m.py",
        1,
        declared=frozenset(),
        raises=[RaiseSite(EffectRef(R, "builtins.ValueError"), 4)],
    )
    diags = check(_fns(c), ancestors={}, exc_ancestors={}, external={}, include_raises=True)
    assert len(diags) == 1
    assert diags[0].effect == EffectRef(R, "builtins.ValueError")
    assert diags[0].function.fullname == "m.c"
    assert diags[0].call.line == 4  # provenance points at the raise


def test_check_without_include_raises_ignores_raises():
    from efflux.check.model import RaiseSite

    R = "efflux.effects.Raises"
    c = FunctionModel(
        "m.c",
        "m.py",
        1,
        declared=frozenset(),
        raises=[RaiseSite(EffectRef(R, "builtins.ValueError"), 4)],
    )
    assert check(_fns(c), ancestors={}, exc_ancestors={}, external={}) == []


def test_unresolved_calls_lists_callee_none_sites():
    from efflux.check.inference import unresolved_calls

    f = FunctionModel(
        "m.f",
        "m.py",
        1,
        declared=None,
        calls=[CallSite("m.g", 2), CallSite(None, 3, unresolved_hint="do_io")],
    )
    g = FunctionModel("m.g", "m.py", 5, declared=None, calls=[CallSite(None, 6)])
    out = unresolved_calls(_fns(f, g))
    assert {(u.function.fullname, u.call.line) for u in out} == {("m.f", 3), ("m.g", 6)}


def test_call_coverage_counts_resolved_vs_total():
    from efflux.check.inference import call_coverage

    # m.g (qualified) and requests.get (qualified external) resolve; None does not.
    f = FunctionModel(
        "m.f",
        "m.py",
        1,
        declared=None,
        calls=[CallSite("m.g", 2), CallSite(None, 3), CallSite("requests.get", 4)],
    )
    assert call_coverage(_fns(f)) == (2, 3)


def test_unresolved_calls_flags_bare_callback_not_nested_function():
    from efflux.check.inference import unresolved_calls

    # "inner" is a bare-keyed nested function -> resolved; "cb" is a callback -> not.
    inner = FunctionModel("inner", "m.py", 2, declared=None)
    outer = FunctionModel(
        "m.outer", "m.py", 1, declared=None, calls=[CallSite("inner", 3), CallSite("cb", 4)]
    )
    out = unresolved_calls(_fns(inner, outer))
    assert [(u.function.fullname, u.call.callee) for u in out] == [("m.outer", "cb")]


def test_call_coverage_no_calls_is_zero_zero():
    from efflux.check.inference import call_coverage

    assert call_coverage(_fns(FunctionModel("m.f", "m.py", 1, declared=None))) == (0, 0)


def test_check_unused_flags_dead_raises_but_not_the_justified_one():
    from efflux.check.inference import check_unused
    from efflux.check.model import RaiseSite

    R = "efflux.effects.Raises"
    # a actually raises ValueError -> its declaration is justified.
    a = FunctionModel(
        "m.a",
        "m.py",
        1,
        declared=frozenset({EffectRef(R, "builtins.ValueError")}),
        raises=[RaiseSite(EffectRef(R, "builtins.ValueError"), 2)],
    )
    # b calls a inside try/except ValueError and swallows it -> b raises nothing -> dead decl.
    b = FunctionModel(
        "m.b",
        "m.py",
        4,
        declared=frozenset({EffectRef(R, "builtins.ValueError")}),
        calls=[CallSite("m.a", 5, caught=frozenset({"builtins.ValueError"}))],
    )
    exc_anc = {
        "builtins.ValueError": frozenset(
            {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
        )
    }
    unused = check_unused(
        _fns(a, b), ancestors={}, exc_ancestors=exc_anc, external={}, include_raises=True
    )
    assert [(u.function.fullname, u.effect) for u in unused] == [
        ("m.b", EffectRef(R, "builtins.ValueError"))
    ]
