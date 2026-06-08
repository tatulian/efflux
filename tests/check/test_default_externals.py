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


def test_map_includes_processes_and_expanded_stdlib():
    assert DEFAULT_EXTERNAL_MAP["subprocess.run"] == frozenset({"efflux.effects.Process"})
    assert DEFAULT_EXTERNAL_MAP["os.system"] == frozenset({"efflux.effects.Process"})
    assert DEFAULT_EXTERNAL_MAP["pathlib.Path.exists"] == frozenset({"efflux.effects.ReadsFS"})
    assert DEFAULT_EXTERNAL_MAP["pathlib.Path.mkdir"] == frozenset({"efflux.effects.WritesFS"})
    assert DEFAULT_EXTERNAL_MAP["shutil.copy"] == frozenset({"efflux.effects.WritesFS"})
    # os.path.* resolves through genericpath/posixpath in typeshed
    assert DEFAULT_EXTERNAL_MAP["genericpath.exists"] == frozenset({"efflux.effects.ReadsFS"})
    assert DEFAULT_EXTERNAL_MAP["http.client.HTTPConnection"] == frozenset(
        {"efflux.effects.Network"}
    )
    assert DEFAULT_EXTERNAL_MAP["uuid.uuid4"] == frozenset({"efflux.effects.Random"})
    assert DEFAULT_EXTERNAL_MAP["datetime.date.today"] == frozenset({"efflux.effects.Clock"})
    # asyncio.sleep re-exports from asyncio.tasks
    assert DEFAULT_EXTERNAL_MAP["asyncio.tasks.sleep"] == frozenset({"efflux.effects.Blocks"})


def test_map_includes_third_party_db_and_network():
    db = frozenset({"efflux.effects.Database"})
    net = frozenset({"efflux.effects.Network"})
    assert DEFAULT_EXTERNAL_MAP["sqlalchemy.orm.Session.execute"] == db
    assert DEFAULT_EXTERNAL_MAP["redis.Redis.get"] == db
    assert DEFAULT_EXTERNAL_MAP["pymongo.collection.Collection.find"] == db
    assert DEFAULT_EXTERNAL_MAP["aiohttp.ClientSession.get"] == net
    assert DEFAULT_EXTERNAL_MAP["boto3.client"] == net


def test_every_mapped_effect_is_a_real_effect_class():
    # Guards against typos in effect fullnames (e.g. "efflux.effects.Proces").
    import efflux.effects as fx
    from efflux._core import Effect

    for effects in DEFAULT_EXTERNAL_MAP.values():
        for fullname in effects:
            cls = getattr(fx, fullname.rsplit(".", 1)[-1], None)
            assert isinstance(cls, type) and issubclass(cls, Effect), fullname
