from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallSite:
    """A call inside a function body. `callee` is the resolved callee fullname
    (or None if unresolved). `caught` is the set of exception fullnames caught by
    a surrounding try/except; `allowed` is the set of effect fullnames discharged
    by a surrounding efflux.allow(...) or `# efflux: allow` comment."""

    callee: str | None
    line: int
    caught: frozenset[str] = field(default_factory=frozenset)
    allowed: frozenset[str] = field(default_factory=frozenset)


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


@dataclass
class FunctionModel:
    """A function extracted from the program.

    `declared` is the set of declared effect fullnames (from `Effects[...]`),
    or None if the function has no effect declaration (then it is inferred and
    propagated but never itself reported)."""

    fullname: str
    file: str
    line: int
    declared: frozenset[EffectRef] | None
    calls: list[CallSite] = field(default_factory=list)


@dataclass(frozen=True)
class Diagnostic:
    """A single violation: `function` uses `effect` (via call site `call`)
    without declaring it."""

    function: FunctionModel
    effect: EffectRef
    call: CallSite

    def format(self) -> str:
        callee = self.call.callee or "<unresolved call>"
        return (
            f"{self.function.file}:{self.function.line}: error: "
            f'function "{self.function.fullname}" has undeclared effect '
            f'"{self.effect.short}" (introduced by call to "{callee}" '
            f"at line {self.call.line})"
        )


@dataclass(frozen=True)
class BoundaryViolation:
    """`function` matched a boundary glob that forbids `effect` (or an ancestor
    of it), introduced at call site `call`."""

    function: FunctionModel
    boundary: str
    effect: EffectRef
    call: CallSite

    def format(self) -> str:
        callee = self.call.callee or "<unresolved call>"
        return (
            f"{self.function.file}:{self.function.line}: error: "
            f'function "{self.function.fullname}" breaks boundary "{self.boundary}": '
            f'forbidden effect "{self.effect.short}" (introduced by call to "{callee}" '
            f"at line {self.call.line})"
        )
