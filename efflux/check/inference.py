from __future__ import annotations

import fnmatch

from efflux.check.model import (
    BoundaryViolation,
    CallSite,
    Diagnostic,
    EffectRef,
    FunctionModel,
    RaiseSite,
    UnresolvedCall,
    UnusedDeclaration,
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
    include_raises: bool = False,
) -> dict[str, frozenset[EffectRef]]:
    """Bottom-up effect inference to a fixpoint, applying per-call discharge.
    With ``include_raises``, explicit ``raise`` statements (``model.raises``)
    contribute Raises[E] too, subject to the same region-scoped discharge."""
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
            if include_raises:
                for site in model.raises:
                    if not _discharged(site.effect, site, ancestors, exc_ancestors):
                        acc.add(site.effect)
            new = frozenset(acc)
            if new != inferred[fn]:
                inferred[fn] = new
                changed = True
    return inferred


def _discharged(
    effect: EffectRef,
    call: CallSite | RaiseSite,
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
) -> bool:
    """An effect is discharged at this site if allowed (its class or an ancestor
    is in site.allowed) or, for Raises[E'], if a caught exception catches E'."""
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
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
) -> CallSite | RaiseSite:
    """Pick the *undischarged* call or raise site that introduced `effect` (for the
    diagnostic). Skipping discharged sites matters when, e.g., a call is caught by a
    try/except but a re-raise in the handler re-introduces the same effect."""
    for call in model.calls:
        if effect in _callee_effects(
            call.callee, functions, inferred, external
        ) and not _discharged(effect, call, ancestors, exc_ancestors):
            return call
    for site in model.raises:  # raise-introduced (only when include_raises put it in inferred)
        if site.effect == effect and not _discharged(site.effect, site, ancestors, exc_ancestors):
            return site
    # Total fallback: never IndexError. A callee-less CallSite formats as
    # "<unresolved call>" (see Diagnostic.format).
    return model.calls[0] if model.calls else CallSite(callee=None, line=model.line)


def check(
    functions: dict[str, FunctionModel],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    external: dict[str, frozenset[EffectRef]],
    include_raises: bool = False,
) -> list[Diagnostic]:
    """Report effects used but not declared, for functions that declare effects."""
    inferred = infer(functions, external, ancestors, exc_ancestors, include_raises=include_raises)
    diagnostics: list[Diagnostic] = []
    for fn, model in functions.items():
        if model.declared is None:
            continue
        for effect in sorted(inferred[fn], key=lambda e: (e.fullname, e.arg or "")):
            if _covered(effect, model.declared, ancestors, exc_ancestors):
                continue
            call = _source_call(
                model, effect, functions, inferred, external, ancestors, exc_ancestors
            )
            diagnostics.append(Diagnostic(function=model, effect=effect, call=call))
    return diagnostics


def check_unused(
    functions: dict[str, FunctionModel],
    ancestors: dict[str, frozenset[str]],
    exc_ancestors: dict[str, frozenset[str]],
    external: dict[str, frozenset[EffectRef]],
    include_raises: bool = False,
) -> list[UnusedDeclaration]:
    """Report declared effects that cover none of a function's inferred effects
    (declared-but-unused). Advisory; only functions that declare effects qualify."""
    inferred = infer(functions, external, ancestors, exc_ancestors, include_raises=include_raises)
    unused: list[UnusedDeclaration] = []
    for fn, model in functions.items():
        if model.declared is None:
            continue
        used = inferred[fn]
        for declared in sorted(model.declared, key=lambda e: (e.fullname, e.arg or "")):
            if not any(
                _covered(effect, frozenset({declared}), ancestors, exc_ancestors) for effect in used
            ):
                unused.append(UnusedDeclaration(function=model, effect=declared))
    return unused


def _is_unresolved(call: CallSite, functions: dict[str, FunctionModel]) -> bool:
    """A blind-spot call: the callee couldn't be resolved at all, or it's a bare
    (unqualified) name that isn't a known in-project function — i.e. a callback or a
    local holding a callable. Qualified callees (`m.g`, `requests.get`) count as
    resolved even when their effects are unknown, to avoid flooding the report."""
    if call.callee is None:
        return True
    return "." not in call.callee and call.callee not in functions


def unresolved_calls(functions: dict[str, FunctionModel]) -> list[UnresolvedCall]:
    """Every call whose callee could not be resolved (its effects are assumed pure) —
    the blind spot surfaced by --report-unresolved."""
    return [
        UnresolvedCall(function=model, call=call)
        for model in functions.values()
        for call in model.calls
        if _is_unresolved(call, functions)
    ]


def call_coverage(functions: dict[str, FunctionModel]) -> tuple[int, int]:
    """(resolved, total) call sites — how much of the call graph efflux can see."""
    total = resolved = 0
    for model in functions.values():
        for call in model.calls:
            total += 1
            if not _is_unresolved(call, functions):
                resolved += 1
    return resolved, total


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
    include_raises: bool = False,
) -> list[BoundaryViolation]:
    """Report functions whose inferred effects break a [tool.efflux.boundaries] rule."""
    inferred = infer(functions, external, ancestors, exc_ancestors, include_raises=include_raises)
    violations: list[BoundaryViolation] = []
    for fn, model in functions.items():
        for pattern, forbidden in boundaries.items():
            if not fnmatch.fnmatchcase(fn, pattern):
                continue
            for effect in sorted(inferred[fn], key=lambda e: (e.fullname, e.arg or "")):
                if _forbidden(effect, forbidden, ancestors):
                    call = _source_call(
                        model, effect, functions, inferred, external, ancestors, exc_ancestors
                    )
                    violations.append(
                        BoundaryViolation(
                            function=model, boundary=pattern, effect=effect, call=call
                        )
                    )
    return violations
