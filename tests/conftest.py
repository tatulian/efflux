from __future__ import annotations

import textwrap

import pytest
from mypy import api


@pytest.fixture
def mypy_check(tmp_path):
    """Return a function that type-checks a snippet with the efflux plugin.

    Usage: out, status = mypy_check("...code...")
    `out` is mypy stdout, `status` is the exit code (0 == clean).
    """

    def check(code: str) -> tuple[str, int]:
        sample = tmp_path / "sample.py"
        sample.write_text(textwrap.dedent(code))
        config = tmp_path / "mypy.ini"
        config.write_text("[mypy]\nplugins = efflux.mypy_plugin\n")
        stdout, _stderr, status = api.run(
            [
                str(sample),
                "--config-file",
                str(config),
                "--no-incremental",
                "--no-error-summary",
                "--hide-error-context",
            ]
        )
        return stdout, status

    return check
