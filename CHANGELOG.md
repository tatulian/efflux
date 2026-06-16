# Changelog

All notable changes to efflux are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0 the
public API may still move between minor versions.

## [Unreleased]

## [0.1.0] - 2026-06-06

First release.

### Added
- **Visibility layer.** `Effects[T, *effects]` declares a function's side effects in
  its return annotation and erases to `T` for callers — non-invasive metadata on an
  `Annotated` type. A shallow built-in effect hierarchy (`IO` → `Network` / `Process`
  / `Filesystem` / `Database` / …, plus `Raises[E]`, `Logs`, `Clock`, and more), with
  subsumption by subclassing. `effects_of()` reads the effects back at runtime.
- **mypy plugin** (`efflux.mypy_plugin`) that type-checks `Effects[...]` as `T` and
  validates that every declared effect is an `Effect` subclass.
- **Checker** (`efflux <path>`) that infers each function's effects bottom-up across
  the call graph and reports any function using an effect it did not declare, with
  effect subsumption and `try/except` / `efflux.allow(...)` discharge.
- Architectural **boundaries** (`[tool.efflux.boundaries]`), an **external map** for
  stdlib and popular third-party calls, **baselines** for gradual adoption, a
  `--fix` codemod, `--strict` raise modelling with an unused-declaration lint, and
  `--report` / `--report-unresolved` with call-graph coverage.
- A pre-commit hook, two Claude Code skills (`efflux-annotate`, `efflux-navigate`),
  and `py.typed`.
- Advisory `[unknown-effect]` warning when a name in `Effects[...]` does not resolve
  to an `Effect` subclass (a typo, a missing import, or a non-effect type); it never
  changes the exit code.
- Integration tests that verify the built-in external map against the real
  `requests`, `httpx`, and SQLAlchemy packages, guarding the shipped fullnames
  against version drift.

### Fixed
- The effect of a factory call in a `with` header (the idiomatic `with open(path)`,
  `with db.connect()`, `with NamedTemporaryFile()`) is no longer lost — the checker
  walked the body but not the header expression, so such functions inferred as pure
  while the coverage line still reported 100%.
- Dotted exception references in `Raises[...]` (e.g. `Raises[errors.MyError]`) now
  resolve to the exception instead of silently degrading to bare `Raises` (which
  covers any exception).
- `effects_of()` no longer raises `NameError` when the return type is only importable
  under `TYPE_CHECKING` together with `from __future__ import annotations`; it falls
  back to recovering the effects with placeholders for the unresolved names.
- `efflux --fix` now imports `Raises[E]` exception classes and user-defined effects
  from their own modules instead of hardcoding `from efflux import ...` (which left
  undefined names in the output). `--fix --strict` folds in `raise`-derived effects.
- Corrected built-in external-map fullnames for `httpx` (`httpx._api.*`) and
  SQLAlchemy (`sqlalchemy.engine.create` / `engine.base` / `orm.session`), which
  resolve to their definition sites, so those entries actually fire.

[Unreleased]: https://github.com/tatulian/efflux/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tatulian/efflux/releases/tag/v0.1.0
