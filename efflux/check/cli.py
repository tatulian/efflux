from __future__ import annotations

import argparse
import json
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from mypy.errors import CompileError
from mypy.find_sources import InvalidSourceList

from efflux.check.baseline import filter_diagnostics, load_keys, write_baseline
from efflux.check.default_externals import DEFAULT_EXTERNAL_MAP
from efflux.check.engine import analyze
from efflux.check.external_map import load_boundaries, load_external_map
from efflux.check.inference import check, check_boundaries, check_unused, infer
from efflux.check.model import EffectRef, FunctionModel


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="efflux",
        description="Check and report side effects declared with Effects[...].",
    )
    parser.add_argument("paths", nargs="+", help="packages, modules, or files to analyze")
    parser.add_argument(
        "--report",
        action="store_true",
        help="print every function's inferred effects instead of checking",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--no-builtins",
        action="store_true",
        help="disable the built-in external effect map (stdlib/requests/httpx)",
    )
    parser.add_argument(
        "--baseline", metavar="FILE", help="suppress violations listed in this baseline file"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="(re)write the --baseline file from current violations and exit",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="rewrite source to add missing Effects[...] declarations",
    )
    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="with --fix, also wrap plain `-> T` annotations (more invasive)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="model explicit `raise` statements as effects and warn on unused declarations",
    )
    return parser


def _external_map(paths: list[str], use_builtins: bool) -> dict[str, frozenset[EffectRef]]:
    fullnames: dict[str, frozenset[str]] = {}
    if use_builtins:
        fullnames.update(DEFAULT_EXTERNAL_MAP)
    fullnames.update(load_external_map(paths))  # user config overrides built-ins
    return {
        callee: frozenset(EffectRef(name) for name in names) for callee, names in fullnames.items()
    }


def _run_report(
    functions: dict[str, FunctionModel],
    external: dict[str, frozenset[EffectRef]],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    *,
    as_json: bool,
    strict: bool,
) -> int:
    inferred = infer(functions, external, ancestors, exc_ancestors, include_raises=strict)
    rows = sorted(functions.values(), key=lambda m: (m.file, m.line))
    if as_json:
        payload = {
            "functions": [
                {
                    "function": m.fullname,
                    "file": m.file,
                    "line": m.line,
                    "effects": sorted(e.short for e in inferred[m.fullname]),
                }
                for m in rows
            ]
        }
        print(json.dumps(payload, indent=2))
    else:
        for m in rows:
            effects = sorted(e.short for e in inferred[m.fullname])
            print(f"{m.file}:{m.line}: {m.fullname} -> {', '.join(effects) or '(pure)'}")
    return 0


def _run_check(
    functions: dict[str, FunctionModel],
    external: dict[str, frozenset[EffectRef]],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    boundaries: dict[str, frozenset[str]],
    *,
    baseline: str | None,
    update: bool,
    as_json: bool,
    strict: bool,
) -> int:
    diagnostics = check(
        functions,
        ancestors=ancestors,
        exc_ancestors=exc_ancestors,
        external=external,
        include_raises=strict,
    )
    if update and baseline is not None:
        write_baseline(baseline, diagnostics)
        print(f"efflux: wrote {len(diagnostics)} baseline entries to {baseline}")
        return 0
    if baseline is not None:
        diagnostics = filter_diagnostics(diagnostics, load_keys(baseline))
    boundary_violations = check_boundaries(
        functions, ancestors, exc_ancestors, external, boundaries, include_raises=strict
    )
    unused = (
        check_unused(functions, ancestors, exc_ancestors, external, include_raises=True)
        if strict
        else []
    )
    diag_sorted = sorted(
        diagnostics, key=lambda d: (d.function.file, d.function.line, d.effect.short)
    )
    bound_sorted = sorted(
        boundary_violations,
        key=lambda b: (b.function.file, b.function.line, b.boundary, b.effect.short),
    )
    unused_sorted = sorted(unused, key=lambda u: (u.function.file, u.function.line, u.effect.short))
    ok = not diag_sorted and not bound_sorted  # advisory warnings never flip the exit code
    if as_json:
        payload: dict[str, object] = {
            "ok": ok,
            "violations": [
                {
                    "function": d.function.fullname,
                    "file": d.function.file,
                    "line": d.function.line,
                    "effect": d.effect.short,
                    "callee": getattr(d.call, "callee", None),
                    "call_line": d.call.line,
                }
                for d in diag_sorted
            ],
            "boundaries": [
                {
                    "function": b.function.fullname,
                    "file": b.function.file,
                    "line": b.function.line,
                    "boundary": b.boundary,
                    "effect": b.effect.short,
                    "callee": getattr(b.call, "callee", None),
                    "call_line": b.call.line,
                }
                for b in bound_sorted
            ],
        }
        if strict:
            payload["unused"] = [
                {
                    "function": u.function.fullname,
                    "file": u.function.file,
                    "line": u.function.line,
                    "effect": u.effect.short,
                }
                for u in unused_sorted
            ]
        print(json.dumps(payload, indent=2))
        return 0 if ok else 1
    if ok and not unused_sorted:
        print("no effect violations found")
        return 0
    for diag in diag_sorted:
        print(diag.format())
    for violation in bound_sorted:
        print(violation.format())
    for declaration in unused_sorted:
        print(declaration.format())
    return 0 if ok else 1


def _run_fix(
    functions: dict[str, FunctionModel],
    external: dict[str, frozenset[EffectRef]],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    *,
    aggressive: bool,
) -> int:
    from pathlib import Path

    from efflux.check.fixer import fix_file, plan_fixes

    by_file = plan_fixes(functions, ancestors, exc_ancestors, external, aggressive=aggressive)
    changed = 0
    skipped: list[str] = []
    for file, fixes in sorted(by_file.items()):
        source = Path(file).read_text()
        new_source, file_skipped = fix_file(source, fixes)
        skipped.extend(file_skipped)
        if new_source != source:
            Path(file).write_text(new_source)
            changed += 1
    print(f"efflux: fixed {changed} file(s)")
    for name in sorted(skipped):
        print(f"efflux: skipped {name} (no return annotation to wrap)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(sys.argv[1:] if argv is None else argv)

    try:
        external = _external_map(args.paths, use_builtins=not args.no_builtins)
        boundaries = load_boundaries(args.paths)
    except (tomllib.TOMLDecodeError, TypeError, OSError, ValueError) as exc:
        print(f"efflux: invalid efflux config: {exc}", file=sys.stderr)
        return 2

    try:
        functions, ancestors, exc_ancestors = analyze(args.paths, external=external)
    except CompileError as exc:
        print("efflux: could not analyze (mypy build failed):", file=sys.stderr)
        for message in exc.messages:
            print(f"  {message}", file=sys.stderr)
        return 2
    except InvalidSourceList as exc:
        print(f"efflux: {exc}", file=sys.stderr)
        return 2

    if args.fix:
        return _run_fix(functions, external, ancestors, exc_ancestors, aggressive=args.unsafe)

    if args.update and not args.baseline:
        print("efflux: --update requires --baseline FILE", file=sys.stderr)
        return 2

    if args.report:
        return _run_report(
            functions, external, ancestors, exc_ancestors, as_json=args.json, strict=args.strict
        )
    return _run_check(
        functions,
        external,
        ancestors,
        exc_ancestors,
        boundaries,
        baseline=args.baseline,
        update=args.update,
        as_json=args.json,
        strict=args.strict,
    )


if __name__ == "__main__":
    raise SystemExit(main())
