from __future__ import annotations

from collections.abc import Callable

from mypy.plugin import AnalyzeTypeContext, Plugin
from mypy.subtypes import is_subtype
from mypy.types import AnyType, Instance, Type, TypeOfAny

# mypy resolves the Effects form to its canonical definition-site fullname,
# regardless of how it was imported. efflux._core.Effects is that name.
EFFECTS_FULLNAMES = frozenset({"efflux._core.Effects"})

EFFECT_BASE_FULLNAME = "efflux._core.Effect"
RAISES_FULLNAME = "efflux.effects.Raises"


def _is_effect(typ: Type) -> bool:
    return isinstance(typ, Instance) and any(
        base.fullname == EFFECT_BASE_FULLNAME for base in typ.type.mro
    )


def _analyze_effects(ctx: AnalyzeTypeContext) -> Type:
    args = ctx.type.args
    if not args:
        ctx.api.fail(
            "Effects[...] requires a return type as its first argument",
            ctx.context,
        )
        return AnyType(TypeOfAny.from_error)
    # The whole Effects[ReturnType, *effects] form *is* ReturnType.
    return_type = ctx.api.analyze_type(args[0])
    for raw in args[1:]:
        analyzed = ctx.api.analyze_type(raw)
        if not _is_effect(analyzed):
            name = getattr(raw, "name", None) or str(raw)
            ctx.api.fail(
                f'"{name}" is not a valid effect (must subclass efflux.Effect)',
                ctx.context,
            )
        else:
            _check_raises_bound(ctx, analyzed)
    return return_type


def _check_raises_bound(ctx: AnalyzeTypeContext, analyzed: Type) -> None:
    # mypy does not enforce the Raises[E] TypeVar bound (E: BaseException) when
    # the type is resolved through our analyze hook, so we check it explicitly.
    if not isinstance(analyzed, Instance):
        return
    if not analyzed.type.has_base(RAISES_FULLNAME) or not analyzed.args:
        return
    if not is_subtype(analyzed.args[0], ctx.api.named_type("builtins.BaseException", [])):
        ctx.api.fail(
            f"{analyzed.type.name}[...] type argument must subclass BaseException",
            ctx.context,
        )


class EffluxPlugin(Plugin):
    def get_type_analyze_hook(self, fullname: str) -> Callable[[AnalyzeTypeContext], Type] | None:
        if fullname in EFFECTS_FULLNAMES:
            return _analyze_effects
        return None


def plugin(version: str) -> type[Plugin]:
    return EffluxPlugin
