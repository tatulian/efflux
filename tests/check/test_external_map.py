from efflux.check.external_map import load_external_map


def test_load_external_map_resolves_builtin_and_fullname(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.efflux.external]\n"
        '"time.time" = ["Clock"]\n'
        '"requests.api.get" = ["Network", "myapp.effects.Custom"]\n'
    )
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    mapping = load_external_map([str(tmp_path / "m.py")])
    assert mapping["time.time"] == frozenset({"efflux.effects.Clock"})
    assert mapping["requests.api.get"] == frozenset(
        {"efflux.effects.Network", "myapp.effects.Custom"}
    )


def test_load_external_map_absent_returns_empty(tmp_path):
    sub = tmp_path / "proj"
    sub.mkdir()
    (sub / "m.py").write_text("def f() -> int:\n    return 1\n")
    assert load_external_map([str(sub / "m.py")]) == {}


def test_load_external_map_no_efflux_section(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.other]\nx = 1\n")
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    assert load_external_map([str(tmp_path / "m.py")]) == {}


def test_load_external_map_finds_pyproject_in_directory_arg(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = ["Clock"]\n')
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    mapping = load_external_map([str(tmp_path)])  # directory, not a file
    assert mapping["time.time"] == frozenset({"efflux.effects.Clock"})


def test_load_external_map_walks_up_from_nested_file(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = ["Clock"]\n')
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    (nested / "m.py").write_text("def f() -> int:\n    return 1\n")
    mapping = load_external_map([str(nested / "m.py")])
    assert mapping["time.time"] == frozenset({"efflux.effects.Clock"})


def test_load_external_map_rejects_non_list_value(tmp_path):
    import pytest

    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = "Clock"\n')
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    with pytest.raises(TypeError):
        load_external_map([str(tmp_path / "m.py")])


def test_load_external_map_rejects_unknown_bare_name(tmp_path):
    import pytest

    (tmp_path / "pyproject.toml").write_text(
        '[tool.efflux.external]\n"time.time" = ["Clok"]\n'  # typo for Clock
    )
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    with pytest.raises(ValueError, match="unknown effect"):
        load_external_map([str(tmp_path / "m.py")])


def test_load_boundaries(tmp_path):
    from efflux.check.external_map import load_boundaries

    (tmp_path / "pyproject.toml").write_text(
        '[tool.efflux.boundaries]\n"app.domain.*" = { forbid = ["IO", "Raises"] }\n'
    )
    (tmp_path / "m.py").write_text("x = 1\n")
    result = load_boundaries([str(tmp_path / "m.py")])
    assert result == {"app.domain.*": frozenset({"efflux.effects.IO", "efflux.effects.Raises"})}


def test_load_boundaries_rejects_non_table(tmp_path):
    import pytest

    from efflux.check.external_map import load_boundaries

    (tmp_path / "pyproject.toml").write_text('[tool.efflux.boundaries]\n"a.*" = ["IO"]\n')
    (tmp_path / "m.py").write_text("x = 1\n")
    with pytest.raises(TypeError):
        load_boundaries([str(tmp_path / "m.py")])
