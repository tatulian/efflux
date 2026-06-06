from efflux.check.default_externals import DEFAULT_EXTERNAL_MAP


def test_map_includes_stdlib_and_http_libs():
    assert DEFAULT_EXTERNAL_MAP["time.time"] == frozenset({"efflux.effects.Clock"})
    assert DEFAULT_EXTERNAL_MAP["time.sleep"] == frozenset({"efflux.effects.Blocks"})
    assert DEFAULT_EXTERNAL_MAP["os.getenv"] == frozenset({"efflux.effects.ReadsEnv"})
    assert DEFAULT_EXTERNAL_MAP["requests.api.get"] == frozenset({"efflux.effects.Network"})
    assert DEFAULT_EXTERNAL_MAP["httpx.get"] == frozenset({"efflux.effects.Network"})


def test_map_values_are_frozensets_of_effect_fullnames():
    for effects in DEFAULT_EXTERNAL_MAP.values():
        assert isinstance(effects, frozenset)
        assert all(name.startswith("efflux.effects.") for name in effects)
