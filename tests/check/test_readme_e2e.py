"""End-to-end coverage of every scenario documented in README.md, plus the
corner cases that keep each promise honest.

These run the real CLI in-process via ``cli.main(argv)`` (capturing stdout with
``capsys``) — the full pipeline of engine → inference → reporting behind the
``efflux`` console script. In-process is fast and lets coverage see ``cli.py``;
``pyproject.toml`` discovery is path-based, so each ``tmp_path`` is isolated from
the repo's own config. The few cases that need a fresh interpreter (a
user-defined effect that must be importable at runtime; the "import efflux does
not import mypy" claim) shell out to a subprocess.

The companion ``tests/check/test_cli.py`` already covers many CLI surfaces
(flags, --json, --report, baseline, --fix, discharge, build errors); this file
deliberately fills the README-scenario gaps rather than duplicating them.
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap

from efflux.check.cli import main


def _write(tmp_path, src: str, name: str = "m.py"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(src))
    return path


def _run(capsys, *argv) -> tuple[int, str, str]:
    """Run the CLI in-process; return (exit_code, stdout, stderr)."""
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- #
# Hierarchy subsumption — "Declaring a parent covers its children"            #
# --------------------------------------------------------------------------- #


def test_parent_effects_cover_their_children(tmp_path, capsys):
    # README: "Declare Database and both ReadsDB and WritesDB are covered;
    # declare IO and you've covered the lot." Filesystem covers ReadsFS/WritesFS.
    m = _write(
        tmp_path,
        """
        from efflux import (
            Effects, ReadsDB, WritesDB, ReadsFS, WritesFS, Network, ReadsEnv,
            Database, Filesystem, IO,
        )
        def reads_db() -> Effects[int, ReadsDB]: return 1
        def writes_db() -> Effects[int, WritesDB]: return 1
        def reads_fs() -> Effects[int, ReadsFS]: return 1
        def writes_fs() -> Effects[int, WritesFS]: return 1
        def nets() -> Effects[int, Network]: return 1
        def env() -> Effects[int, ReadsEnv]: return 1

        def db_layer() -> Effects[int, Database]:        # Database covers Reads/WritesDB
            return reads_db() + writes_db()
        def fs_layer() -> Effects[int, Filesystem]:      # Filesystem covers Reads/WritesFS
            return reads_fs() + writes_fs()
        def io_layer() -> Effects[int, IO]:              # IO covers the lot
            return reads_db() + writes_fs() + nets() + env()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 0, out + err
    assert "no effect violations found" in out


def test_sibling_and_child_do_not_cover(tmp_path, capsys):
    # Subsumption is directional: a sibling never covers a sibling, and a child
    # never covers its parent (the parent is broader than what you declared).
    m = _write(
        tmp_path,
        """
        from efflux import Effects, ReadsDB, WritesDB, Database
        def writes_db() -> Effects[int, WritesDB]: return 1
        def broad() -> Effects[int, Database]: return 1

        def sibling() -> Effects[int, ReadsDB]:    # ReadsDB does NOT cover WritesDB
            return writes_db()
        def narrow() -> Effects[int, WritesDB]:    # WritesDB does NOT cover Database
            return broad()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert '"sibling" has undeclared effect "WritesDB"' in out
    assert '"narrow" has undeclared effect "Database"' in out


# --------------------------------------------------------------------------- #
# Raises subsumption — exception MRO and bare Raises                          #
# --------------------------------------------------------------------------- #


def test_raises_exception_subsumption_and_bare_raises(tmp_path, capsys):
    # README: "Raises[ConnectionError] is covered by Raises[OSError]; bare Raises
    # covers anything." (ConnectionError subclasses OSError.)
    m = _write(
        tmp_path,
        """
        from efflux import Effects, Raises
        def conn_err() -> Effects[int, Raises[ConnectionError]]: return 1
        def val_err() -> Effects[int, Raises[ValueError]]: return 1

        def covers_subclass() -> Effects[int, Raises[OSError]]:   # OSError ⊇ ConnectionError
            return conn_err()
        def bare_covers_any() -> Effects[int, Raises]:            # bare Raises ⊇ Raises[E]
            return val_err()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 0, out + err
    assert "no effect violations found" in out


def test_raises_unrelated_exception_is_reported(tmp_path, capsys):
    # The flip side: a Raises[E] that is neither equal nor a superclass is a leak.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, Raises
        def leaf() -> Effects[int, Raises[KeyError]]: return 1
        def f() -> Effects[int, Raises[ValueError]]:   # ValueError does not cover KeyError
            return leaf()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert 'has undeclared effect "Raises[KeyError]"' in out


# --------------------------------------------------------------------------- #
# Gradual adoption — only Effects[...]-declared functions are enforced        #
# --------------------------------------------------------------------------- #


def test_gradual_undeclared_not_reported_but_effects_propagate(tmp_path, capsys):
    # README/FAQ: "Only functions you annotate with Effects[...] are enforced;
    # the rest are inferred and propagated silently." `loner`/`noisy` carry no
    # Effects[...] so they are never reported, yet `noisy`'s Clock still
    # propagates into its declared caller.
    m = _write(
        tmp_path,
        """
        import time
        from efflux import Effects
        def loner() -> int:                  # undeclared: uses Clock, never reported
            return int(time.time())
        def noisy() -> int:                  # undeclared: uses Clock
            return int(time.time())
        def clean_caller() -> Effects[int]:  # declared (empty): Clock leaks in -> reported
            return noisy()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert '"clean_caller" has undeclared effect "Clock"' in out
    assert '(from "m.noisy")' in out  # propagated through the undeclared callee
    # gradual: an undeclared function is never the *subject* of a diagnostic
    # (noisy appears only as the callee in clean_caller's message above).
    assert '"loner" has undeclared' not in out
    assert '"noisy" has undeclared' not in out


def test_partial_declaration_reports_only_the_missing_effect(tmp_path, capsys):
    # Declaring some-but-not-all effects reports exactly the uncovered remainder.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, WritesDB, Network
        def leaf() -> Effects[int, WritesDB, Network]: return 1
        def caller() -> Effects[int, WritesDB]:   # WritesDB covered; Network is not
            return leaf()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert 'has undeclared effect "Network"' in out
    assert 'has undeclared effect "WritesDB"' not in out  # the declared one is covered


# --------------------------------------------------------------------------- #
# Narrowing — try/except and allow(...) discharge, with their boundaries      #
# --------------------------------------------------------------------------- #


def test_try_except_discharge_scope_and_subsumption(tmp_path, capsys):
    # README: "A try/except discharges the matching Raises." Corner cases:
    #   * except OSError discharges Raises[ConnectionError] (caught superclass);
    #   * except KeyError does NOT discharge Raises[ValueError] (sibling);
    #   * a call in the *handler* body is not protected by its own try.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, Raises
        def conn() -> Effects[int, Raises[ConnectionError]]: return 1
        def verr() -> Effects[int, Raises[ValueError]]: return 1

        def caught_by_super() -> Effects[int]:
            try:
                return conn()
            except OSError:
                return 0
        def sibling_not_caught() -> Effects[int]:
            try:
                return verr()
            except KeyError:
                return 0
        def handler_not_protected() -> Effects[int]:
            try:
                return 0
            except Exception:
                return verr()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert '"caught_by_super"' not in out  # discharged by the caught superclass
    assert '"sibling_not_caught" has undeclared effect "Raises[ValueError]"' in out
    assert '"handler_not_protected" has undeclared effect "Raises[ValueError]"' in out


def test_allow_discharges_via_subsumption_but_not_the_wrong_effect(tmp_path, capsys):
    # README: allow(...) "discharges any effect you intentionally contain."
    # allow(IO) covers a child WritesDB (ancestor match); allow(Network) does not.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, WritesDB, Network, IO, allow
        def leaf() -> Effects[int, WritesDB]: return 1

        def discharged() -> Effects[int]:
            with allow(IO):              # IO is an ancestor of WritesDB -> discharged
                return leaf()
        def not_discharged() -> Effects[int]:
            with allow(Network):        # Network is unrelated to WritesDB -> still leaks
                return leaf()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert '"not_discharged" has undeclared effect "WritesDB"' in out
    assert '"discharged" has undeclared' not in out


# --------------------------------------------------------------------------- #
# Built-in external effect map — applied by default                          #
# --------------------------------------------------------------------------- #


def test_builtin_external_map_attributes_stdlib_effects(tmp_path, capsys):
    # README lists open/os/logging/time/random/socket among the built-ins. Use
    # --report to read each function's inferred effect straight from the map.
    m = _write(
        tmp_path,
        """
        import logging
        import random
        import socket
        import subprocess
        import time
        import uuid
        from pathlib import Path
        def uses_open() -> None: open("x")
        def uses_log() -> None: logging.info("hi")
        def uses_rand() -> None: random.random()
        def uses_sock() -> None: socket.socket()
        def uses_sleep() -> None: time.sleep(0)
        def uses_proc() -> None: subprocess.run(["ls"])
        def uses_uuid() -> None: uuid.uuid4()
        def uses_path(p: Path) -> None: p.mkdir()
        """,
    )
    code, out, err = _run(capsys, "--report", m)
    assert code == 0, out + err
    assert "m.uses_open -> Filesystem" in out  # open()'s direction is unknown -> umbrella
    assert "m.uses_log -> Logs" in out
    assert "m.uses_rand -> Random" in out
    assert "m.uses_sock -> Network" in out
    assert "m.uses_sleep -> Blocks" in out
    assert "m.uses_proc -> Process" in out  # subprocess.run -> the new Process effect
    assert "m.uses_uuid -> Random" in out
    assert "m.uses_path -> WritesFS" in out  # pathlib method resolved via receiver type


# --------------------------------------------------------------------------- #
# Custom effects — "subclass Effect anywhere"                                 #
# --------------------------------------------------------------------------- #


def test_brand_new_effect_propagates_and_must_be_declared(tmp_path, capsys):
    # README: "An effect is a class — subclass Effect anywhere." A brand-new
    # effect propagates like any other and must be declared by callers.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, Effect
        class WritesKafka(Effect): ...
        def emit() -> Effects[int, WritesKafka]: return 1
        def caller_good() -> Effects[int, WritesKafka]:  # declares it -> clean
            return emit()
        def caller_bad() -> Effects[int]:                # omits it -> reported
            return emit()
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert '"caller_bad" has undeclared effect "WritesKafka"' in out
    assert '"caller_good"' not in out


def test_user_effect_subclass_gets_subsumption(tmp_path):
    # README: "class WritesPostgres(WritesDB): ...  # implies WritesDB" — declaring
    # the parent (WritesDB) covers the user subclass. Subsumption reads the effect
    # class's runtime MRO, so the defining module must be importable; we run from
    # cwd=tmp_path (python -m puts cwd on sys.path) to mirror a real installed pkg.
    src = textwrap.dedent(
        """
        from efflux import Effects, WritesDB
        class WritesPostgres(WritesDB): ...
        def leaf() -> Effects[int, WritesPostgres]: return 1
        def caller_ok() -> Effects[int, WritesDB]:   # parent covers the user child
            return leaf()
        def caller_bad() -> Effects[int]:            # declares nothing -> reported
            return leaf()
        """
    )
    (tmp_path / "m.py").write_text(src)
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", "m.py"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert '"caller_bad" has undeclared effect "WritesPostgres"' in proc.stdout
    assert '"caller_ok"' not in proc.stdout  # WritesDB covered the WritesPostgres child


# --------------------------------------------------------------------------- #
# The worked example, and the documented diagnostic format                    #
# --------------------------------------------------------------------------- #


def test_worked_example_charge_passes_clean(tmp_path, capsys):
    # The README "worked example": a billing function that reads/writes the DB,
    # hits the network, can raise, and logs — all declared in one signature.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, Raises, ReadsDB, WritesDB, Network, Logs

        class PaymentError(Exception): ...
        class Receipt: ...

        def load_account(uid: int) -> Effects[int, ReadsDB]: return 0
        def capture(cents: int) -> Effects[Receipt, Network]: return Receipt()
        def save_receipt(r: Receipt) -> Effects[None, WritesDB]: ...
        def log_charge(uid: int) -> Effects[None, Logs]: ...

        def charge(user_id: int, cents: int) -> Effects[
            Receipt, Raises[PaymentError], ReadsDB, WritesDB, Network, Logs
        ]:
            bal = load_account(user_id)          # ReadsDB
            if bal < cents:
                raise PaymentError("insufficient funds")
            receipt = capture(cents)             # Network
            save_receipt(receipt)                # WritesDB
            log_charge(user_id)                  # Logs
            return receipt
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 0, out + err
    assert "no effect violations found" in out


def test_diagnostic_message_format_is_mypy_like(tmp_path, capsys):
    # mypy-style anatomy: "file:line: error: <msg>  [code]". The line points at the
    # introducing call; the function is named short (no module); the callee keeps
    # its fullname; an error code closes the line.
    m = _write(
        tmp_path,
        """
        from efflux import Effects, ReadsDB
        def is_enabled(flag: str) -> Effects[bool, ReadsDB]:
            return True
        def price_basket() -> Effects[int]:
            return 1 if is_enabled("x") else 0
        """,
    )
    code, out, err = _run(capsys, m)
    assert code == 1, out + err
    assert re.search(
        r"/m\.py:\d+: error: "
        r'"price_basket" has undeclared effect "ReadsDB" '
        r'\(from "m\.is_enabled"\)  \[undeclared-effect\]',
        out,
    ), out
    assert '"m.price_basket"' not in out  # the module prefix is gone


# --------------------------------------------------------------------------- #
# Running on a package directory; --fix safety; import purity                 #
# --------------------------------------------------------------------------- #


def test_runs_on_a_package_directory(tmp_path, capsys):
    # README invocation: `efflux path/to/your/package`. A directory argument
    # analyzes the whole package and resolves cross-module calls.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "repo.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "def save() -> Effects[int, WritesDB]:\n"
        "    return 1\n"
    )
    (pkg / "svc.py").write_text(
        "from efflux import Effects\n"
        "from . import repo\n"
        "def charge() -> Effects[int]:\n"
        "    return repo.save()\n"
    )
    code, out, err = _run(capsys, pkg)
    assert code == 1, out + err
    assert '"charge" has undeclared effect "WritesDB"' in out  # short subject name
    assert "svc.py:" in out  # located in the module that made the call


def test_fix_safe_does_not_wrap_plain_annotations(tmp_path, capsys):
    # README: plain `efflux --fix` only completes existing Effects[...]; wrapping a
    # bare `-> T` requires --unsafe. So a plain function is left untouched.
    m = _write(tmp_path, "import time\ndef f() -> float:\n    return time.time()\n")
    code, out, err = _run(capsys, "--fix", m)
    assert code == 0, out + err
    assert "Effects[" not in m.read_text()  # untouched: safe --fix never wraps a plain `-> T`
    assert "fixed 0 file(s)" in out  # nothing eligible -> no rewrite


def test_import_efflux_does_not_import_mypy():
    # README FAQ + a load-bearing invariant: `import efflux` is cheap and must not
    # pull in mypy (mypy is a check-time-only concern). Needs a fresh interpreter.
    proc = subprocess.run(
        [sys.executable, "-c", "import efflux, sys; assert 'mypy' not in sys.modules"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
