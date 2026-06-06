from __future__ import annotations

import contextlib
from collections.abc import Iterator

from efflux._core import Effect


@contextlib.contextmanager
def allow(*effects: type[Effect]) -> Iterator[None]:
    """Mark a block as intentionally performing `effects` so `efflux check` does
    not propagate them out. A runtime no-op — purely a static marker."""
    yield
