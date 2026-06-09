from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallSite:
    """A call inside a function body. `callee` is the resolved callee fullname
    (or None if unresolved). `caught` is the set of exception fullnames caught by
    a surrounding try/except; `allowed` is the set of effect fullnames discharged
    by a surrounding efflux.allow(...) or `# efflux: allow` comment. `unresolved_hint`
    is the call's member/name (e.g. ``do_io``) when the callee couldn't be resolved,
    for the --report-unresolved listing."""

    callee: str | None
    line: int
    caught: frozenset[str] = field(default_factory=frozenset)
    allowed: frozenset[str] = field(default_factory=frozenset)
    unresolved_hint: str | None = None


@dataclass(frozen=True)
class EffectRef:
    """A declared/used effect. `fullname` is the effect class fullname; `arg` is
    the exception fullname for Raises[E] (None for plain/tag effects)."""

    fullname: str
    arg: str | None = None

    @property
    def short(self) -> str:
        name = self.fullname.rsplit(".", 1)[-1]
        if self.arg is None:
            return name
        return f"{name}[{self.arg.rsplit('.', 1)[-1]}]"


@dataclass(frozen=True)
class RaiseSite:
    """An explicit `raise` in a function body. `effect` is the `Raises[E]` it
    introduces; `caught`/`allowed` mirror CallSite for region-scoped discharge
    (a raise inside a try whose except catches it, or under `efflux.allow`)."""

    effect: EffectRef
    line: int
    caught: frozenset[str] = field(default_factory=frozenset)
    allowed: frozenset[str] = field(default_factory=frozenset)


@dataclass
class FunctionModel:
    """A function extracted from the program.

    `declared` is the set of declared effect fullnames (from `Effects[...]`),
    or None if the function has no effect declaration (then it is inferred and
    propagated but never itself reported). `raises` holds explicit `raise`
    statements (only consulted in --strict / `include_raises` mode)."""

    fullname: str
    file: str
    line: int
    declared: frozenset[EffectRef] | None
    calls: list[CallSite] = field(default_factory=list)
    raises: list[RaiseSite] = field(default_factory=list)
    name: str = ""  # module-stripped display name (e.g. "Repo.save"); set by the engine

    @property
    def display_name(self) -> str:
        """Short name for messages — no module prefix (the file is already shown)."""
        return self.name or self.fullname.rsplit(".", 1)[-1]


def _source_suffix(call: CallSite | RaiseSite) -> str:
    """`(from "<callee>")` for a resolved call; empty for a raise or unresolved call
    (the diagnostic's line already points at the raise / the call)."""
    if isinstance(call, CallSite) and call.callee:
        return f' (from "{call.callee}")'
    return ""


@dataclass(frozen=True)
class Diagnostic:
    """A single violation: `function` uses `effect` (via a call or a raise)
    without declaring it. Reported at the introducing call/raise line."""

    function: FunctionModel
    effect: EffectRef
    call: CallSite | RaiseSite

    def format(self) -> str:
        return (
            f"{self.function.file}:{self.call.line}: error: "
            f'"{self.function.display_name}" has undeclared effect "{self.effect.short}"'
            f"{_source_suffix(self.call)}  [undeclared-effect]"
        )


@dataclass(frozen=True)
class BoundaryViolation:
    """`function` matched a boundary glob that forbids `effect` (or an ancestor
    of it), introduced at call site `call`."""

    function: FunctionModel
    boundary: str
    effect: EffectRef
    call: CallSite | RaiseSite

    def format(self) -> str:
        return (
            f"{self.function.file}:{self.call.line}: error: "
            f'"{self.function.display_name}" breaks boundary "{self.boundary}": '
            f'forbidden effect "{self.effect.short}"{_source_suffix(self.call)}  [boundary]'
        )


@dataclass(frozen=True)
class UnusedDeclaration:
    """`function` declares `effect` in its `Effects[...]` but no call introduces it
    (it covers none of the function's inferred effects). Advisory only; reported at
    the declaration (the function's def line)."""

    function: FunctionModel
    effect: EffectRef

    def format(self) -> str:
        return (
            f"{self.function.file}:{self.function.line}: warning: "
            f'"{self.function.display_name}" declares unused effect "{self.effect.short}"'
            f"  [unused-effect]"
        )


@dataclass(frozen=True)
class UnresolvedCall:
    """A call whose callee efflux could not resolve (dynamic dispatch, a call on
    `Any`, a callback parameter, ...). Its effects are assumed pure — a blind spot
    surfaced by --report-unresolved. Informational (`note`), never an error."""

    function: FunctionModel
    call: CallSite

    def format(self) -> str:
        hint = self.call.unresolved_hint or self.call.callee  # member name, or the bare callee
        what = f" to `{hint}()`" if hint else ""
        return (
            f"{self.function.file}:{self.call.line}: note: "
            f'unresolved call{what} in "{self.function.display_name}" '
            f"— effects assumed pure  [unresolved-call]"
        )
