from efflux import IO, Database, Effect, Filesystem, Logs, Network, Raises, ReadsFS, WritesDB


def test_builtin_effects_subclass_effect():
    assert issubclass(WritesDB, Effect)
    assert issubclass(Raises, Effect)
    assert issubclass(Logs, Effect)


def test_user_effect_subclasses_effect():
    class WritesKafka(Effect): ...

    assert issubclass(WritesKafka, Effect)


def test_effect_subsumption_via_inheritance():
    class WritesPostgres(WritesDB): ...

    assert issubclass(WritesPostgres, WritesDB)
    assert issubclass(WritesPostgres, Effect)


def test_builtin_hierarchy_relationships():
    assert issubclass(WritesDB, Database)
    assert issubclass(Database, IO)
    assert issubclass(WritesDB, IO)
    assert issubclass(ReadsFS, Filesystem)
    assert issubclass(Filesystem, IO)
    assert issubclass(Network, IO)


def test_umbrellas_are_effects():
    from efflux import Effect

    assert issubclass(IO, Effect)
    assert issubclass(Filesystem, Effect)
    assert issubclass(Database, Effect)


def test_flat_effects_are_not_under_io():
    from efflux import IO, Blocks, Clock, Emits, Logs, MutatesGlobal, Random

    for effect in (Logs, Emits, Random, Clock, MutatesGlobal, Blocks):
        assert not issubclass(effect, IO)
