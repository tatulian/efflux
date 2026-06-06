---
name: efflux-annotate
description: Use when adding efflux Effects[...] annotations to existing Python code — infer each function's side effects, declare them in the return type, and verify with the efflux checker until clean.
---

# Annotating code with efflux effects

Make a codebase's side effects visible by declaring them in return types:
`def charge(uid: int) -> Effects[Receipt, Raises[PaymentError], WritesDB, Logs]`.
To mypy and to callers the function still returns `Receipt`; the effects ride
along as metadata and are checked by `efflux`.

**Core loop: you infer, `efflux` verifies.** You read each function and declare
the effects you see; then the checker reports any *declared* function that uses
an effect it didn't declare. Fix the gaps and re-run until clean.

## Preconditions

- efflux is installed in the project's environment. Run the checker as
  `efflux <path>` (or `uv run efflux <path>` in a uv project).
- The mypy plugin is enabled so `Effects[...]` type-checks. In `pyproject.toml`:
  ```toml
  [tool.mypy]
  plugins = ["efflux.mypy_plugin"]
  ```
  (or `plugins = efflux.mypy_plugin` in `mypy.ini`). Add it first if missing.

## Effect vocabulary

Import from `efflux`. Map operations to the most specific effect that is true:

| Operation in the code | Effect |
|---|---|
| `raise X`, or a call that propagates `X` | `Raises[X]` |
| `open(...)` / `Path.read_text` (read) | `ReadsFS` |
| `open(..., "w")` / `Path.write_text` | `WritesFS` |
| `requests` / `httpx` / `urllib` / `socket` | `Network` |
| `os.environ` / `os.getenv` | `ReadsEnv` |
| DB SELECT / fetch | `ReadsDB` |
| DB INSERT / UPDATE / DELETE / commit | `WritesDB` |
| `logging.*` / logging-style `print` | `Logs` |
| publishing events / messages | `Emits` |
| `random.*` / `secrets.*` | `Random` |
| `time.time` / `datetime.now` | `Clock` |
| `time.sleep` / blocking waits | `Blocks` (+ `Clock` for sleep) |
| mutating a module/global variable | `MutatesGlobal` |
| any outside-world interaction (umbrella) | `IO` |

`IO` is the umbrella over `Network`, `ReadsEnv`, `Filesystem`
(`ReadsFS`/`WritesFS`), and `Database` (`ReadsDB`/`WritesDB`). Declaring a parent
covers its children (declare `Database` and `ReadsDB`+`WritesDB` are covered).
Prefer the narrowest true effect; use an umbrella only when a function genuinely
spans many.

## Workflow

1. **Pick a scope** — a module or package. Annotate **bottom-up** (leaf functions
   first) so callers can rely on callees' declarations.
2. **For each function, determine its effects:** direct operations (table above);
   exceptions it can raise and does not catch → `Raises[Exc]`; plus the effects of
   the functions it calls (these propagate up the call graph).
3. **Rewrite the return annotation:** `def f(...) -> T:` becomes
   `def f(...) -> Effects[T, <effects>]:`. The real return type stays **first**;
   for `None` returns use `Effects[None, ...]`. Add
   `from efflux import Effects, <effect classes used>`.
4. **Contain effects you intend to swallow** instead of declaring them:
   - `try/except E:` discharges `Raises[E]`;
   - `with efflux.allow(WritesDB): ...`, or a `# efflux: allow WritesDB` comment on
     the call, discharges any effect for that call.
5. **Run the checker (the oracle):**
   ```bash
   efflux path/to/package        # or: uv run efflux path/to/package
   ```
   It prints, for each gap, that a function uses an effect it does not declare
   (only for functions that already carry an `Effects[...]`). Add each reported
   effect to that function's annotation and re-run until it prints
   `no effect violations found`.
6. **Type-check:** run mypy to confirm the plugin accepts the annotations and the
   code still type-checks.
7. **Third-party calls** efflux cannot see into are treated as pure. If one has
   effects, declare them so they propagate:
   ```toml
   [tool.efflux.external]
   "requests.api.get" = ["Network"]
   "time.time" = ["Clock"]
   ```

## Guidance

- **Gradual opt-in.** Only functions with an `Effects[...]` are checked. Annotate
  the boundaries that matter (public APIs, service/repository layers); don't
  decorate every trivial pure helper.
- `Effects[T]` with no effects means "declared pure" — distinct from unannotated.
- Keep declarations honest and minimal: the signature should tell the truth about
  what the function does.

## Done when

`efflux <path>` reports `no effect violations found` and mypy passes — every
annotated function's signature fully and accurately declares its effects.
