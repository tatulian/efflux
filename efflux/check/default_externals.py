from __future__ import annotations

_NET = "efflux.effects.Network"
_LOGS = "efflux.effects.Logs"
_CLOCK = "efflux.effects.Clock"
_BLOCKS = "efflux.effects.Blocks"
_RANDOM = "efflux.effects.Random"
_READS_ENV = "efflux.effects.ReadsEnv"
_READS_FS = "efflux.effects.ReadsFS"
_WRITES_FS = "efflux.effects.WritesFS"
_FILESYSTEM = "efflux.effects.Filesystem"


def _m(*effects: str) -> frozenset[str]:
    return frozenset(effects)


# Curated starter map: callee fullname -> declared effects. Applied by default;
# user [tool.efflux.external] entries override per callee, and --no-builtins
# disables it entirely. open() maps to Filesystem because the direction depends
# on the runtime mode argument, which static analysis cannot see.
DEFAULT_EXTERNAL_MAP: dict[str, frozenset[str]] = {
    # filesystem
    "builtins.open": _m(_FILESYSTEM),
    "io.open": _m(_FILESYSTEM),
    "pathlib.Path.read_text": _m(_READS_FS),
    "pathlib.Path.read_bytes": _m(_READS_FS),
    "pathlib.Path.write_text": _m(_WRITES_FS),
    "pathlib.Path.write_bytes": _m(_WRITES_FS),
    "os.listdir": _m(_READS_FS),
    "os.scandir": _m(_READS_FS),
    "os.stat": _m(_READS_FS),
    "os.remove": _m(_WRITES_FS),
    "os.unlink": _m(_WRITES_FS),
    "os.mkdir": _m(_WRITES_FS),
    "os.makedirs": _m(_WRITES_FS),
    "os.rename": _m(_WRITES_FS),
    "os.replace": _m(_WRITES_FS),
    # environment
    "os.getenv": _m(_READS_ENV),
    "os.getenvb": _m(_READS_ENV),
    # network
    "socket.socket": _m(_NET),
    "socket.create_connection": _m(_NET),
    "urllib.request.urlopen": _m(_NET),
    "requests.api.get": _m(_NET),
    "requests.api.post": _m(_NET),
    "requests.api.put": _m(_NET),
    "requests.api.patch": _m(_NET),
    "requests.api.delete": _m(_NET),
    "requests.api.head": _m(_NET),
    "requests.api.options": _m(_NET),
    "requests.api.request": _m(_NET),
    "httpx.get": _m(_NET),
    "httpx.post": _m(_NET),
    "httpx.put": _m(_NET),
    "httpx.patch": _m(_NET),
    "httpx.delete": _m(_NET),
    "httpx.head": _m(_NET),
    "httpx.options": _m(_NET),
    "httpx.request": _m(_NET),
    # logging
    "logging.debug": _m(_LOGS),
    "logging.info": _m(_LOGS),
    "logging.warning": _m(_LOGS),
    "logging.error": _m(_LOGS),
    "logging.critical": _m(_LOGS),
    "logging.exception": _m(_LOGS),
    "logging.log": _m(_LOGS),
    "logging.Logger.debug": _m(_LOGS),
    "logging.Logger.info": _m(_LOGS),
    "logging.Logger.warning": _m(_LOGS),
    "logging.Logger.error": _m(_LOGS),
    "logging.Logger.critical": _m(_LOGS),
    "logging.Logger.exception": _m(_LOGS),
    "logging.Logger.log": _m(_LOGS),
    # time / clock
    "time.time": _m(_CLOCK),
    "time.time_ns": _m(_CLOCK),
    "time.monotonic": _m(_CLOCK),
    "time.perf_counter": _m(_CLOCK),
    "time.process_time": _m(_CLOCK),
    "time.sleep": _m(_BLOCKS),
    "datetime.datetime.now": _m(_CLOCK),
    "datetime.datetime.today": _m(_CLOCK),
    "datetime.datetime.utcnow": _m(_CLOCK),
    # randomness
    "random.random": _m(_RANDOM),
    "random.randint": _m(_RANDOM),
    "random.randrange": _m(_RANDOM),
    "random.choice": _m(_RANDOM),
    "random.choices": _m(_RANDOM),
    "random.shuffle": _m(_RANDOM),
    "random.sample": _m(_RANDOM),
    "random.uniform": _m(_RANDOM),
    "random.getrandbits": _m(_RANDOM),
    "secrets.token_bytes": _m(_RANDOM),
    "secrets.token_hex": _m(_RANDOM),
    "secrets.token_urlsafe": _m(_RANDOM),
    "secrets.choice": _m(_RANDOM),
    "secrets.randbelow": _m(_RANDOM),
}
