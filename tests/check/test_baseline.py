from efflux.check.baseline import (
    diagnostic_key,
    filter_diagnostics,
    load_keys,
    write_baseline,
)
from efflux.check.model import CallSite, Diagnostic, EffectRef, FunctionModel


def _diag(fn, effect, callee):
    m = FunctionModel(fn, "m.py", 1, declared=frozenset())
    return Diagnostic(function=m, effect=EffectRef(effect), call=CallSite(callee, 2))


def test_write_then_filter_round_trip(tmp_path):
    d = _diag("m.f", "efflux.effects.WritesDB", "db.save")
    path = tmp_path / "bl.json"
    write_baseline(str(path), [d])
    keys = load_keys(str(path))
    assert diagnostic_key(d) in keys
    assert filter_diagnostics([d], keys) == []


def test_filter_keeps_new_violations(tmp_path):
    old = _diag("m.f", "efflux.effects.WritesDB", "db.save")
    new = _diag("m.g", "efflux.effects.Network", "http.get")
    path = tmp_path / "bl.json"
    write_baseline(str(path), [old])
    keys = load_keys(str(path))
    assert filter_diagnostics([old, new], keys) == [new]
