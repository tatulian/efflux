import json
import subprocess
import sys


def test_cli_runs_and_reports_no_violations_on_empty(tmp_path):
    (tmp_path / "m.py").write_text("def f() -> int:\n    return 1\n")
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "no effect violations" in proc.stdout.lower()


def _run(tmp_path, *files):
    paths = []
    for name, src in files:
        p = tmp_path / name
        p.write_text(src)
        paths.append(str(p))
    return subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", *paths],
        capture_output=True,
        text=True,
    )


def _cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", *args],
        capture_output=True,
        text=True,
    )


def test_cli_help_exits_zero():
    proc = _cli("--help")
    assert proc.returncode == 0
    assert "efflux" in proc.stdout


def test_cli_unknown_flag_exits_two(tmp_path):
    proc = _cli("--nope", str(tmp_path))
    assert proc.returncode == 2


def test_cli_no_args_exits_two():
    proc = _cli()
    assert proc.returncode == 2


def test_cli_builtin_external_map_flags_stdlib_effect(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    proc = _cli(str(tmp_path / "m.py"))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Clock" in proc.stdout


def test_cli_no_builtins_disables_default_map(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    proc = _cli("--no-builtins", str(tmp_path / "m.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no effect violations found" in proc.stdout


def test_cli_user_config_overrides_builtin(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = ["Network"]\n')
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects, Network\n"
        "def f() -> Effects[float, Network]:\n    return time.time()\n"
    )
    proc = _cli(str(tmp_path / "m.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_report_lists_inferred_effects(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    proc = _cli("--report", str(tmp_path / "m.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "m.f" in proc.stdout
    assert "Clock" in proc.stdout


def test_cli_json_violations(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    proc = _cli("--json", str(tmp_path / "m.py"))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is False
    assert any(v["effect"] == "Clock" for v in data["violations"])


def test_cli_json_report(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    proc = _cli("--report", "--json", str(tmp_path / "m.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    names = {fn["function"]: fn["effects"] for fn in data["functions"]}
    assert "Clock" in names["m.f"]


def test_cli_boundary_allows_non_io_effect(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.efflux.boundaries]\n"m.*" = { forbid = ["IO"] }\n'
    )
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects, Clock\n"
        "def f() -> Effects[float, Clock]:\n    return time.time()\n"
    )
    proc = _cli(str(tmp_path / "m.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr  # Clock is not under IO


def test_cli_boundary_forbids_io(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.efflux.boundaries]\n"m.*" = { forbid = ["IO"] }\n'
    )
    (tmp_path / "m.py").write_text(
        "import os\nfrom efflux import Effects, ReadsEnv\n"
        "def f() -> Effects[str | None, ReadsEnv]:\n    return os.getenv('X')\n"
    )
    proc = _cli(str(tmp_path / "m.py"))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "breaks boundary" in proc.stdout
    assert "ReadsEnv" in proc.stdout


def test_cli_baseline_update_then_suppress(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    bl = tmp_path / "bl.json"
    upd = _cli(str(tmp_path / "m.py"), "--baseline", str(bl), "--update")
    assert upd.returncode == 0, upd.stdout + upd.stderr
    assert bl.exists()
    proc = _cli(str(tmp_path / "m.py"), "--baseline", str(bl))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_update_requires_baseline(tmp_path):
    proc = _cli(str(tmp_path), "--update")
    assert proc.returncode == 2


def test_cli_fix_adds_missing_effect(tmp_path):
    m = tmp_path / "m.py"
    m.write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    return time.time()\n"
    )
    proc = _cli("--fix", str(m))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Effects[float, Clock]" in m.read_text()
    assert _cli(str(m)).returncode == 0  # re-run: now clean


def test_cli_fix_aggressive_wraps_plain(tmp_path):
    m = tmp_path / "m.py"
    m.write_text("import time\ndef f() -> float:\n    return time.time()\n")
    proc = _cli("--fix", "--unsafe", str(m))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "-> Effects[float, Clock]:" in m.read_text()


def test_cli_walks_overload_impl(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom typing import overload\n"
        "@overload\ndef ov(x: int) -> int: ...\n"
        "@overload\ndef ov(x: str) -> str: ...\n"
        "def ov(x):\n    time.time()\n    return x\n"
    )
    proc = _cli("--report", str(tmp_path / "m.py"))
    assert "m.ov -> Clock" in proc.stdout, proc.stdout + proc.stderr


def test_cli_walks_closure(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def outer() -> Effects[float]:\n"
        "    def inner() -> float:\n        return time.time()\n"
        "    return inner()\n"
    )
    proc = _cli("--report", str(tmp_path / "m.py"))
    assert "m.outer -> Clock" in proc.stdout, proc.stdout + proc.stderr


def test_cli_walks_lambda_body(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "def f() -> Effects[float]:\n    g = lambda: time.time()\n    return g()\n"
    )
    proc = _cli("--report", str(tmp_path / "m.py"))
    assert "m.f -> Clock" in proc.stdout, proc.stdout + proc.stderr


def test_cli_walks_async_await(tmp_path):
    (tmp_path / "m.py").write_text(
        "import time\nfrom efflux import Effects\n"
        "async def ag() -> float:\n    return time.time()\n"
        "async def af() -> Effects[float]:\n    return await ag()\n"
    )
    proc = _cli("--report", str(tmp_path / "m.py"))
    assert "m.af -> Clock" in proc.stdout, proc.stdout + proc.stderr


def test_cli_allow_in_string_literal_does_not_discharge(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "def leaf(msg: str) -> Effects[int, WritesDB]:\n    return 1\n"
        "def f() -> Effects[int]:\n"
        '    return leaf("# efflux: allow WritesDB here")\n'  # marker in a string on the call line
    )
    proc = _cli(str(tmp_path / "m.py"))
    assert proc.returncode == 1, proc.stdout + proc.stderr  # string marker must NOT discharge
    assert "WritesDB" in proc.stdout


def test_cli_reports_undeclared_effect_across_module(tmp_path):
    proc = _run(
        tmp_path,
        (
            "repo.py",
            "from efflux import Effects, WritesDB\n"
            "def save() -> Effects[int, WritesDB]:\n    return 1\n",
        ),
        (
            "svc.py",
            "from efflux import Effects\n"
            "import repo\n"
            "def charge() -> Effects[int]:\n    return repo.save()\n",
        ),
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'has undeclared effect "WritesDB"' in proc.stdout
    assert '"charge" has undeclared effect' in proc.stdout  # short name, no module prefix
    assert "svc.charge" not in proc.stdout


def test_cli_passes_when_effect_declared(tmp_path):
    proc = _run(
        tmp_path,
        (
            "repo.py",
            "from efflux import Effects, WritesDB\n"
            "def save() -> Effects[int, WritesDB]:\n    return 1\n",
        ),
        (
            "svc.py",
            "from efflux import Effects, WritesDB\n"
            "import repo\n"
            "def charge() -> Effects[int, WritesDB]:\n    return repo.save()\n",
        ),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no effect violations" in proc.stdout.lower()


def test_cli_handles_build_error_gracefully(tmp_path):
    # A file with a syntax error makes mypy.build raise CompileError; the CLI
    # must surface it and exit non-zero, NOT crash with a traceback.
    proc = _run(tmp_path, ("bad.py", "def f(:\n    pass\n"))
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback (most recent call last)" not in proc.stderr
    assert "efflux: could not analyze" in proc.stderr
    assert "bad.py" in proc.stderr


def test_cli_within_module_violation(tmp_path):
    proc = _run(
        tmp_path,
        (
            "m.py",
            "from efflux import Effects, WritesDB\n"
            "def helper() -> Effects[int, WritesDB]:\n    return 1\n"
            "def caller() -> Effects[int]:\n    return helper()\n",
        ),
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'has undeclared effect "WritesDB"' in proc.stdout
    assert '"caller" has undeclared effect' in proc.stdout


def test_cli_handles_empty_directory_gracefully(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(empty)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback (most recent call last)" not in proc.stderr


def test_cli_external_map_flags_mapped_call(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = ["Clock"]\n')
    (tmp_path / "m.py").write_text(
        "from efflux import Effects\n"
        "import time\n"
        "def f() -> Effects[int]:\n"
        "    return int(time.time())\n"
    )
    # mypy's stdlib stubs resolve time.time() to the callee fullname "time.time"
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'has undeclared effect "Clock"' in proc.stdout


def test_cli_handles_invalid_config_gracefully(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.efflux.external]\n"x" = "Network"\n'  # value is a str, not a list
    )
    (tmp_path / "m.py").write_text(
        "from efflux import Effects\ndef f() -> Effects[int]:\n    return 1\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback (most recent call last)" not in proc.stderr


def test_cli_external_map_passes_when_mapped_effect_declared(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = ["Clock"]\n')
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Clock\n"
        "import time\n"
        "def f() -> Effects[int, Clock]:\n"
        "    return int(time.time())\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_broad_declaration_covers_mapped_effect(tmp_path):
    # time.time mapped to WritesDB; f declares IO -> IO covers WritesDB via the
    # hierarchy (ancestors folded from the external map) -> no violation.
    (tmp_path / "pyproject.toml").write_text('[tool.efflux.external]\n"time.time" = ["WritesDB"]\n')
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, IO\n"
        "import time\n"
        "def f() -> Effects[int, IO]:\n"
        "    return int(time.time())\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_handles_unknown_effect_name_gracefully(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.efflux.external]\n"time.time" = ["network"]\n'  # wrong case
    )
    (tmp_path / "m.py").write_text(
        "from efflux import Effects\ndef f() -> Effects[int]:\n    return 1\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback (most recent call last)" not in proc.stderr
    assert "unknown effect" in proc.stderr


def test_method_call_effect_is_detected(tmp_path):
    proc = _run(
        tmp_path,
        (
            "m.py",
            "from efflux import Effects, WritesDB\n"
            "class Repo:\n"
            "    def save(self) -> Effects[int, WritesDB]:\n        return 1\n"
            "def charge(r: Repo) -> Effects[int]:\n    return r.save()\n",
        ),
    )
    assert proc.returncode == 1
    assert 'has undeclared effect "WritesDB"' in proc.stdout


def test_cli_method_effect_passes_when_declared(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "class Repo:\n"
        "    def save(self) -> Effects[int, WritesDB]:\n"
        "        return 1\n"
        "def charge(r: Repo) -> Effects[int, WritesDB]:\n"
        "    return r.save()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_raises_exception_subsumption_passes(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> Effects[int, Raises[Exception]]:\n"  # broad covers narrow
        "    return leaf()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_raises_sibling_reported(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[KeyError]]:\n"
        "    return 1\n"
        "def f() -> Effects[int, Raises[ValueError]]:\n"  # does not cover KeyError
        "    return leaf()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'has undeclared effect "Raises[KeyError]"' in proc.stdout


def test_cli_try_except_discharges_raises(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> Effects[int]:\n"
        "    try:\n"
        "        return leaf()\n"
        "    except ValueError:\n"
        "        return 0\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_uncaught_raises_still_reported(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, Raises\n"
        "def leaf() -> Effects[int, Raises[ValueError]]:\n"
        "    return 1\n"
        "def f() -> Effects[int]:\n"
        "    return leaf()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'has undeclared effect "Raises[ValueError]"' in proc.stdout


def test_cli_allow_context_manager_discharges(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB, allow\n"
        "def leaf() -> Effects[int, WritesDB]:\n"
        "    return 1\n"
        "def f() -> Effects[int]:\n"
        "    with allow(WritesDB):\n"
        "        return leaf()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


_STRICT_CASE1 = (
    "from efflux import Effects, Raises\n"
    "def a() -> Effects[None, Raises[ValueError]]:\n"
    "    raise ValueError()\n"
    "def b() -> Effects[None, Raises[ValueError]]:\n"  # declares it, but swallows it
    "    try:\n"
    "        return a()\n"
    "    except ValueError:\n"
    "        pass\n"
)


def test_cli_strict_warns_unused_declaration(tmp_path):
    (tmp_path / "c1.py").write_text(_STRICT_CASE1)
    proc = _cli("--strict", str(tmp_path / "c1.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr  # advisory only
    assert '"b" declares unused effect "Raises[ValueError]"' in proc.stdout
    assert "warning:" in proc.stdout
    assert "[unused-effect]" in proc.stdout
    # a actually raises ValueError -> its declaration is justified, not flagged
    assert "c1.a" not in proc.stdout


def test_cli_strict_unused_is_silent_without_flag(tmp_path):
    (tmp_path / "c1.py").write_text(_STRICT_CASE1)
    proc = _cli(str(tmp_path / "c1.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no effect violations found" in proc.stdout
    assert "unused" not in proc.stdout


def test_cli_strict_reports_escaping_reraise(tmp_path):
    (tmp_path / "c2.py").write_text(
        "from efflux import Effects, Raises\n"
        "def a() -> Effects[None, Raises[ValueError]]:\n"
        "    raise ValueError()\n"
        "def c() -> Effects[None]:\n"
        "    try:\n"
        "        return a()\n"
        "    except ValueError:\n"
        "        raise\n"  # re-raise escapes
    )
    proc = _cli("--strict", str(tmp_path / "c2.py"))
    assert proc.returncode == 1, proc.stdout + proc.stderr  # a real violation
    assert '"c" has undeclared effect "Raises[ValueError]"' in proc.stdout
    assert "c2.py:8: error:" in proc.stdout  # points at the re-raise line, not the def line


def test_cli_strict_json_carries_unused(tmp_path):
    (tmp_path / "c1.py").write_text(_STRICT_CASE1)
    proc = _cli("--strict", "--json", str(tmp_path / "c1.py"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True  # unused warnings do not flip ok
    assert any(
        u["effect"] == "Raises[ValueError]" and u["function"] == "c1.b" for u in data["unused"]
    )


def test_cli_allow_comment_discharges(tmp_path):
    (tmp_path / "m.py").write_text(
        "from efflux import Effects, WritesDB\n"
        "def leaf() -> Effects[int, WritesDB]:\n"
        "    return 1\n"
        "def f() -> Effects[int]:\n"
        "    return leaf()  # efflux: allow WritesDB\n"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "efflux.check.cli", str(tmp_path / "m.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
