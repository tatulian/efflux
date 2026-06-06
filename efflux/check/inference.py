from __future__ import annotations

import fnmatch

from efflux.check.model import (
    BoundaryViolation,
    CallSite,
    Diagnostic,
    EffectRef,
    FunctionModel,
)

RAISES_FULLNAME = "efflux.effects.Raises"


def _callee_effects(
    callee: str | None,
    functions: dict[str, FunctionModel],
    inferred: dict[str, frozenset[EffectRef]],
    external: dict[str, frozenset[EffectRef]],
) -> frozenset[EffectRef]:
    if callee is None:
        return frozenset()  # unresolved call -> boundary, assume pure
    model = functions.get(callee)
    if model is not None:
        # declared contract wins over body; else use current inferred estimate
        return model.declared if model.declared is not None else inferred[callee]
    return external.get(callee, frozenset())  # external -> map or pure


def infer(
    functions: dict[str, FunctionModel],
    external: dict[str, frozenset[EffectRef]],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
) -> dict[str, frozenset[EffectRef]]:
    """Bottom-up effect inference to a fixpoint, applying per-call discharge."""
    inferred: dict[str, frozenset[EffectRef]] = {fn: frozenset() for fn in functions}
    changed = True
    while changed:
        changed = False
        for fn, model in functions.items():
            acc: set[EffectRef] = set()
            for call in model.calls:
                for effect in _callee_effects(call.callee, functions, inferred, external):
                    if not _discharged(effect, call, ancestors, exc_ancestors):
                        acc.add(effect)
            new = frozenset(acc)
            if new != inferred[fn]:
                inferred[fn] = new
                changed = True
    return inferred


def _discharged(
    effect: EffectRef,
    call: CallSite,
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
) -> bool:
    """An effect is discharged at this call if allowed (its class or an ancestor
    is in call.allowed) or, for Raises[E'], if a caught exception catches E'."""
    if any(a in call.allowed for a in ancestors.get(effect.fullname, frozenset({effect.fullname}))):
        return True
    return (
        effect.fullname == RAISES_FULLNAME
        and effect.arg is not None
        and any(c in exc_ancestors.get(effect.arg, frozenset({effect.arg})) for c in call.caught)
    )


def _covered(
    used: EffectRef,
    declared: frozenset[EffectRef],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
) -> bool:
    for d in declared:
        if d.fullname == RAISES_FULLNAME and used.fullname == RAISES_FULLNAME:
            if d.arg is None:
                return True  # declared bare Raises covers any Raises[...]
            if used.arg is not None and d.arg in exc_ancestors.get(used.arg, frozenset({used.arg})):
                return True
        elif d.arg is None and used.arg is None:
            if d.fullname in ancestors.get(used.fullname, frozenset({used.fullname})):
                return True
    return False


def _source_call(
    model: FunctionModel,
    effect: EffectRef,
    functions: dict[str, FunctionModel],
    inferred: dict[str, frozenset[EffectRef]],
    external: dict[str, frozenset[EffectRef]],
) -> CallSite:
    """Pick the call site that introduced `effect` (for the diagnostic)."""
    for call in model.calls:
        if effect in _callee_effects(call.callee, functions, inferred, external):
            return call
    # Total fallback: never IndexError. A callee-less CallSite formats as
    # "<unresolved call>" (see Diagnostic.format).
    return model.calls[0] if model.calls else CallSite(callee=None, line=model.line)


def check(
    functions: dict[str, FunctionModel],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    external: dict[str, frozenset[EffectRef]],
) -> list[Diagnostic]:
    """Report effects used but not declared, for functions that declare effects."""
    inferred = infer(functions, external, ancestors, exc_ancestors)
    diagnostics: list[Diagnostic] = []
    for fn, model in functions.items():
        if model.declared is None:
            continue
        for effect in sorted(inferred[fn], key=lambda e: (e.fullname, e.arg or "")):
            if _covered(effect, model.declared, ancestors, exc_ancestors):
                continue
            call = _source_call(model, effect, functions, inferred, external)
            diagnostics.append(Diagnostic(function=model, effect=effect, call=call))
    return diagnostics


def _forbidden(
    effect: EffectRef, forbidden: frozenset[str], ancestors: dict[str, frozenset[str]]
) -> bool:
    """True if a forbidden fullname is the effect's class or one of its ancestors."""
    return bool(forbidden & ancestors.get(effect.fullname, frozenset({effect.fullname})))


def check_boundaries(
    functions: dict[str, FunctionModel],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    external: dict[str, frozenset[EffectRef]],
    boundaries: dict[str, frozenset[str]],
) -> list[BoundaryViolation]:
    """Report functions whose inferred effects break a [tool.efflux.boundaries] rule."""
    inferred = infer(functions, external, ancestors, exc_ancestors)
    violations: list[BoundaryViolation] = []
    for fn, model in functions.items():
        for pattern, forbidden in boundaries.items():
            if not fnmatch.fnmatchcase(fn, pattern):
                continue
            for effect in sorted(inferred[fn], key=lambda e: (e.fullname, e.arg or "")):
                if _forbidden(effect, forbidden, ancestors):
                    call = _source_call(model, effect, functions, inferred, external)
                    violations.append(
                        BoundaryViolation(
                            function=model, boundary=pattern, effect=effect, call=call
                        )
                    )
    return violations
