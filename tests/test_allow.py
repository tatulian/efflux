from efflux import allow


def test_allow_is_a_noop_context_manager():
    from efflux import WritesDB

    ran = False
    with allow(WritesDB):
        ran = True
    assert ran  # body executes; allow does nothing at runtime
