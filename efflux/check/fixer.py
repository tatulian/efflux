from __future__ import annotations

from dataclasses import dataclass

from efflux.check.inference import check, infer
from efflux.check.model import EffectRef, FunctionModel


@dataclass(frozen=True)
class FunctionFix:
    """A planned edit: add `add` effects to `model`'s return annotation.
    `wrap=True` means the function has no `Effects[...]` yet (wrap a plain `-> T`);
    `wrap=False` means extend an existing `Effects[...]`."""

    model: FunctionModel
    add: list[EffectRef]
    wrap: bool


def _sort(effects: set[EffectRef]) -> list[EffectRef]:
    return sorted(effects, key=lambda e: (e.fullname, e.arg or ""))


def plan_fixes(
    functions: dict[str, FunctionModel],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    external: dict[str, frozenset[EffectRef]],
    *,
    aggressive: bool,
) -> dict[str, list[FunctionFix]]:
    """Group planned fixes by file. Safe: extend declared functions that miss
    effects (from ``check``). Aggressive: also wrap functions with no ``Effects[...]``
    that have inferred effects."""
    by_file: dict[str, list[FunctionFix]] = {}

    missing: dict[str, set[EffectRef]] = {}
    for d in check(functions, ancestors=ancestors, exc_ancestors=exc_ancestors, external=external):
        missing.setdefault(d.function.fullname, set()).add(d.effect)
    for fn, effects in missing.items():
        model = functions[fn]
        by_file.setdefault(model.file, []).append(FunctionFix(model, _sort(effects), wrap=False))

    if aggressive:
        inferred = infer(functions, external, ancestors, exc_ancestors)
        for fn, model in functions.items():
            if model.declared is None and inferred[fn]:
                by_file.setdefault(model.file, []).append(
                    FunctionFix(model, _sort(set(inferred[fn])), wrap=True)
                )
    return by_file


def _effect_import(effect: EffectRef) -> str:
    return effect.fullname.rsplit(".", 1)[-1]


def fix_file(source: str, fixes: list[FunctionFix]) -> tuple[str, list[str]]:
    """Apply `fixes` to `source`; return (new_source, skipped_fullnames).
    Requires libcst (``pip install 'efflux[fix]'``)."""
    try:
        import libcst as cst
        from libcst.codemod import CodemodContext
        from libcst.codemod.visitors import AddImportsVisitor
        from libcst.metadata import MetadataWrapper, PositionProvider
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("efflux --fix requires libcst: pip install 'efflux[fix]'") from exc

    by_line = {f.model.line: f for f in fixes}
    skipped: list[str] = []
    to_import: set[str] = set()

    class _Fixer(cst.CSTTransformer):
        METADATA_DEPENDENCIES = (PositionProvider,)

        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.BaseStatement:
            line = self.get_metadata(PositionProvider, original_node).start.line
            fix = by_line.get(line)
            if fix is None:
                return updated_node
            added = [
                cst.SubscriptElement(slice=cst.Index(value=cst.parse_expression(e.short)))
                for e in fix.add
            ]
            names = [_effect_import(e) for e in fix.add]
            if fix.wrap:
                if updated_node.returns is None:
                    skipped.append(fix.model.fullname)
                    return updated_node
                inner = cst.SubscriptElement(slice=cst.Index(value=updated_node.returns.annotation))
                wrapped = cst.Subscript(value=cst.Name("Effects"), slice=[inner, *added])
                to_import.update([*names, "Effects"])
                return updated_node.with_changes(returns=cst.Annotation(annotation=wrapped))
            ann = updated_node.returns.annotation if updated_node.returns is not None else None
            if not isinstance(ann, cst.Subscript):
                skipped.append(fix.model.fullname)
                return updated_node
            to_import.update(names)
            extended = ann.with_changes(slice=[*ann.slice, *added])
            return updated_node.with_changes(returns=cst.Annotation(annotation=extended))

    transformed = MetadataWrapper(cst.parse_module(source)).visit(_Fixer())
    if not to_import:
        return transformed.code, skipped

    context = CodemodContext()
    for name in sorted(to_import):
        AddImportsVisitor.add_needed_import(context, "efflux", name)
    final = AddImportsVisitor(context).transform_module(transformed)
    return final.code, skipped
