import pytest

from efflux.check.engine import _build_trees, _declared_effects, _iter_funcdefs, analyze
from efflux.check.inference import check
from efflux.check.model import EffectRef


def test_build_and_enumerate_functions(tmp_path):
    (tmp_path / "m.py").write_text(
        "def f() -> int:\n    return g()\ndef g() -> int:\n    return 1\n"
    )
    trees = _build_trees([str(tmp_path / "m.py")])
    names = sorted(fd.fullname for _file, fd in _iter_funcdefs(trees))
    assert names == ["m.f", "m.g"]


def test_directory_path_is_expanded(tmp_path):
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    trees = _build_trees([str(tmp_path)])  # a directory, not a file
    names = sorted(fd.fullname for _file, fd in _iter_funcdefs(trees))
    assert names == ["m.f"]


def test_class_methods_are_enumerated(tmp_path):
    (tmp_path / "m.py").write_text("class C:\n    def method(self) -> int:\n        return 1\n")
    trees = _build_trees([str(tmp_path / "m.py")])
    names = sorted(fd.fullname for _file, fd in _iter_funcdefs(trees))
    assert names == ["m.C.method"]


def test_read_declared_effects(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB, Logs\n"
        "def f() -> Effects[int, WritesDB, Logs]:\n"
        "    return 1\n"
        "def g() -> int:\n"
        "    return 1\n"
    )
    trees = _build_trees([str(tmp_path / "m.py")])
    funcs = {fd.fullname: fd for _file, fd in _iter_funcdefs(trees)}
    assert _declared_effects(funcs["m.f"], trees["m"], {}) == frozenset(
        {EffectRef("efflux.effects.WritesDB"), EffectRef("efflux.effects.Logs")}
    )
    assert _declared_effects(funcs["m.g"], trees["m"], {}) is None


def test_aliased_effect_import_resolves(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB as DB\ndef f() -> Effects[int, DB]:\n    return 1\n"
    )
    trees = _build_trees([str(tmp_path / "m.py")])
    funcs = {fd.fullname: fd for _file, fd in _iter_funcdefs(trees)}
    assert _declared_effects(funcs["m.f"], trees["m"], {}) == frozenset(
        {EffectRef("efflux.effects.WritesDB")}
    )


def test_dotted_effect_reference_resolves(tmp_path):
    (tmp_path / "m.py").write_text(
        "import efflux\ndef f() -> efflux.Effects[int, efflux.WritesDB]:\n    return 1\n"
    )
    trees = _build_trees([str(tmp_path / "m.py")])
    funcs = {fd.fullname: fd for _file, fd in _iter_funcdefs(trees)}
    assert _declared_effects(funcs["m.f"], trees["m"], {}) == frozenset(
        {EffectRef("efflux.effects.WritesDB")}
    )


def test_reads_raises_with_exception(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def f() -> Effects[int, Raises[ValueError]]:\n    return 1\n"
    )
    trees = _build_trees([str(tmp_path / "m.py")])
    funcs = {fd.fullname: fd for _file, fd in _iter_funcdefs(trees)}
    assert _declared_effects(funcs["m.f"], trees["m"], {}) == frozenset(
        {EffectRef("efflux.effects.Raises", "builtins.ValueError")}
    )


def test_fully_unannotated_function_returns_none(tmp_path):
    (tmp_path / "m.py").write_text("def g(a, b):\n    return 1\n")
    trees = _build_trees([str(tmp_path / "m.py")])
    funcs = {fd.fullname: fd for _file, fd in _iter_funcdefs(trees)}
    assert _declared_effects(funcs["m.g"], trees["m"], {}) is None


def test_user_defined_effect_resolves(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Effect\n"
        "class MyEffect(Effect): ...\n"
        "def f() -> Effects[int, MyEffect]:\n    return 1\n"
    )
    trees = _build_trees([str(tmp_path / "m.py")])
    funcs = {fd.fullname: fd for _file, fd in _iter_funcdefs(trees)}
    assert _declared_effects(funcs["m.f"], trees["m"], {}) == frozenset({EffectRef("m.MyEffect")})


def test_analyze_builds_function_models_with_calls(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "def leaf() -> Effects[int, WritesDB]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    return leaf()\n"
    )
    functions, ancestors, _exc = analyze([str(tmp_path / "m.py")])
    assert functions["m.f"].declared is None
    assert [c.callee for c in functions["m.f"].calls] == ["m.leaf"]
    assert functions["m.leaf"].declared == frozenset({EffectRef("efflux.effects.WritesDB")})
    assert "efflux.effects.WritesDB" in ancestors
    assert "efflux.effects.WritesDB" in ancestors["efflux.effects.WritesDB"]


def test_ancestors_map_reflects_hierarchy(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "def leaf() -> Effects[int, WritesDB]:\n    return 1\n"
    )
    _functions, ancestors, _exc = analyze([str(tmp_path / "m.py")])
    assert ancestors["efflux.effects.WritesDB"] == frozenset(
        {
            "efflux.effects.WritesDB",
            "efflux.effects.Database",
            "efflux.effects.IO",
        }
    )


_PRELUDE = (
    "from efflux import Effects, WritesDB\n"
    "def leaf() -> Effects[int, WritesDB]:\n"
    "    return 1\n"
    "def cond() -> bool:\n"
    "    return True\n"
)


@pytest.mark.parametrize(
    "body",
    [
        "    leaf()",
        "    x = leaf() + leaf()",
        "    x = leaf() if cond() else leaf()",
        "    x = [leaf() for _ in range(1)]",
        "    x = {leaf(): 1}",
        "    x = {1: leaf()}",
        "    x = {leaf() for _ in range(1)}",
        "    x = list(leaf() for _ in range(1))",
        "    x = cond() and leaf()",
        "    x = f'{leaf()}'",
        "    match 0:\n        case _:\n            leaf()",
        "    match leaf():\n        case _:\n            pass",
        "    match 0:\n        case _ if leaf():\n            pass",
        "    try:\n        leaf()\n    finally:\n        pass",
        "    with open('x'):\n        leaf()",
        "    raise RuntimeError() from leaf()",
        "    assert leaf()",
    ],
)
def test_walker_captures_call_under_construct(tmp_path, body):
    (tmp_path / "m.py").write_text(_PRELUDE + "def f():\n" + body + "\n")
    functions, _ancestors, _exc = analyze([str(tmp_path / "m.py")])
    callees = [c.callee for c in functions["m.f"].calls]
    assert "m.leaf" in callees, f"leaf() not captured under construct; got {callees}"


def test_declaring_io_covers_writesdb(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, IO, WritesDB\n"
        "def leaf() -> Effects[int, WritesDB]:\n    return 1\n"
        "def f() -> Effects[int, IO]:\n    return leaf()\n"
    )
    functions, ancestors, exc_ancestors = analyze([str(tmp_path / "m.py")])
    assert check(functions, ancestors=ancestors, exc_ancestors=exc_ancestors, external={}) == []


def test_declaring_database_does_not_cover_network(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Database, Network\n"
        "def leaf() -> Effects[int, Network]:\n    return 1\n"
        "def f() -> Effects[int, Database]:\n    return leaf()\n"
    )
    functions, ancestors, exc_ancestors = analyze([str(tmp_path / "m.py")])
    diags = check(functions, ancestors=ancestors, exc_ancestors=exc_ancestors, external={})
    assert len(diags) == 1
    assert diags[0].effect == EffectRef("efflux.effects.Network")


def test_analyze_folds_external_effects_into_ancestors(tmp_path):
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    _functions, ancestors, _exc = analyze(
        [str(tmp_path / "m.py")],
        external={"time.time": frozenset({EffectRef("efflux.effects.WritesDB")})},
    )
    assert ancestors["efflux.effects.WritesDB"] == frozenset(
        {
            "efflux.effects.WritesDB",
            "efflux.effects.Database",
            "efflux.effects.IO",
        }
    )


def test_resolves_method_call_on_typed_receiver(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "class Repo:\n"
        "    def save(self) -> Effects[int, WritesDB]:\n"
        "        return 1\n"
        "def f(r: Repo) -> int:\n"
        "    return r.save()\n"
    )
    functions, _ancestors, _exc = analyze([str(tmp_path / "m.py")])
    assert [c.callee for c in functions["m.f"].calls] == ["m.Repo.save"]


def test_resolves_chained_method_call(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "class Repo:\n"
        "    def save(self) -> Effects[int, WritesDB]:\n"
        "        return 1\n"
        "def get() -> Repo:\n"
        "    return Repo()\n"
        "def f() -> int:\n"
        "    return get().save()\n"
    )
    functions, _ancestors, _exc = analyze([str(tmp_path / "m.py")])
    callees = [c.callee for c in functions["m.f"].calls]
    assert "m.Repo.save" in callees  # chained receiver resolved via the type map
    assert "m.get" in callees


def test_resolves_self_method_call(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "class Repo:\n"
        "    def save(self) -> Effects[int, WritesDB]:\n"
        "        return 1\n"
        "    def both(self) -> int:\n"
        "        return self.save()\n"
    )
    functions, _ancestors, _exc = analyze([str(tmp_path / "m.py")])
    assert [c.callee for c in functions["m.Repo.both"].calls] == ["m.Repo.save"]


def test_resolves_inherited_method_call(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "class Base:\n"
        "    def save(self) -> Effects[int, WritesDB]:\n"
        "        return 1\n"
        "class Repo(Base):\n"
        "    pass\n"
        "def f(r: Repo) -> int:\n"
        "    return r.save()\n"
    )
    functions, _ancestors, _exc = analyze([str(tmp_path / "m.py")])
    assert [c.callee for c in functions["m.f"].calls] == ["m.Base.save"]


def test_analyze_builds_exc_ancestors_for_raises(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def f() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
    )
    _functions, _ancestors, exc_ancestors = analyze([str(tmp_path / "m.py")])
    assert exc_ancestors["builtins.ValueError"] == frozenset(
        {"builtins.ValueError", "builtins.Exception", "builtins.BaseException"}
    )


def test_analyze_resolves_user_exception(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "class MyErr(Exception): ...\n"
        "def f() -> Effects[int, Raises[MyErr]]:\n"
        "    return 1\n"
    )
    functions, _ancestors, exc_ancestors = analyze([str(tmp_path / "m.py")])
    assert functions["m.f"].declared == frozenset({EffectRef("efflux.effects.Raises", "m.MyErr")})
    assert "builtins.Exception" in exc_ancestors["m.MyErr"]


def test_collect_calls_marks_caught_in_try(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    try:\n"
        "        return leaf()\n"
        "    except ValueError:\n"
        "        return 0\n"
    )
    functions, _a, _e = analyze([str(tmp_path / "m.py")])
    leaf_calls = [c for c in functions["m.f"].calls if c.callee == "m.leaf"]
    assert leaf_calls and leaf_calls[0].caught == frozenset({"builtins.ValueError"})


def test_collect_calls_bare_except_catches_baseexception(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    try:\n"
        "        return leaf()\n"
        "    except:\n"
        "        return 0\n"
    )
    functions, _a, _e = analyze([str(tmp_path / "m.py")])
    leaf_calls = [c for c in functions["m.f"].calls if c.callee == "m.leaf"]
    assert leaf_calls and leaf_calls[0].caught == frozenset({"builtins.BaseException"})


def test_collect_calls_handler_body_not_caught(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    try:\n"
        "        return 0\n"
        "    except ValueError:\n"
        "        return leaf()\n"
    )
    functions, _a, _e = analyze([str(tmp_path / "m.py")])
    leaf_calls = [c for c in functions["m.f"].calls if c.callee == "m.leaf"]
    assert leaf_calls and leaf_calls[0].caught == frozenset()


def test_collect_calls_with_allow_block(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB, allow\n"
        "def leaf() -> Effects[int, WritesDB]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    with allow(WritesDB):\n"
        "        return leaf()\n"
    )
    functions, _a, _e = analyze([str(tmp_path / "m.py")])
    leaf_calls = [c for c in functions["m.f"].calls if c.callee == "m.leaf"]
    assert leaf_calls and leaf_calls[0].allowed == frozenset({"efflux.effects.WritesDB"})


def test_collect_calls_allow_comment(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "def leaf() -> Effects[int, WritesDB]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    return leaf()  # efflux: allow WritesDB\n"
    )
    functions, _a, _e = analyze([str(tmp_path / "m.py")])
    leaf_calls = [c for c in functions["m.f"].calls if c.callee == "m.leaf"]
    assert leaf_calls and leaf_calls[0].allowed == frozenset({"efflux.effects.WritesDB"})


def test_collect_calls_else_body_not_caught(tmp_path):
    # An exception raised in a try...else clause is NOT routed through the try's
    # except handlers, so a call there must NOT inherit the try's caught set.
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> int:\n"
        "    try:\n"
        "        x = 0\n"
        "    except ValueError:\n"
        "        x = 1\n"
        "    else:\n"
        "        return leaf()\n"
    )
    functions, _a, _e = analyze([str(tmp_path / "m.py")])
    leaf_calls = [c for c in functions["m.f"].calls if c.callee == "m.leaf"]
    assert leaf_calls and leaf_calls[0].caught == frozenset()
