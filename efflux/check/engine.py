from __future__ import annotations

import importlib
import os
from collections.abc import Iterator

from mypy import build
from mypy.find_sources import create_source_list
from mypy.nodes import (
    CallExpr,
    ClassDef,
    Decorator,
    Expression,
    FuncDef,
    MemberExpr,
    MypyFile,
    Node,
    OverloadedFuncDef,
    RefExpr,
    Statement,
    TryStmt,
    TupleExpr,
    TypeInfo,
    WithStmt,
)
from mypy.options import Options
from mypy.types import Instance, Type, UnboundType

from efflux.check.model import CallSite, EffectRef, FunctionModel


def _make_options() -> Options:
    options = Options()
    options.preserve_asts = True  # keep ASTs after analysis (else freed)
    options.export_types = (
        True  # populate result.types for method-call resolution via receiver type
    )
    options.incremental = False  # fresh run, no cache interference
    options.check_untyped_defs = True  # analyze bodies of unannotated functions too
    options.follow_imports = "normal"
    options.plugins = ["efflux.mypy_plugin"]  # so Effects[...] type-checks cleanly
    return options


def _build(
    paths: list[str],
) -> tuple[dict[str, MypyFile], dict[Expression, Type]]:
    """Build the given paths; return ({module_id: MypyFile} for the input files,
    the expression->type map)."""
    options = _make_options()
    sources = create_source_list(paths, options)
    targets = {os.path.realpath(s.path) for s in sources if s.path}
    result = build.build(sources, options)
    trees = {
        mod: tree
        for mod, tree in result.files.items()
        if tree.path and os.path.realpath(tree.path) in targets
    }
    return trees, result.types


def _build_trees(paths: list[str]) -> dict[str, MypyFile]:
    """Backward-compatible: just the trees (used by tests and _declared_effects)."""
    return _build(paths)[0]


def _iter_funcdefs(trees: dict[str, MypyFile]) -> Iterator[tuple[str, FuncDef]]:
    """Yield (file_path, FuncDef) for every function/method in the trees."""
    for tree in trees.values():
        yield from _walk_funcdefs(tree.path, tree.defs)


def _walk_funcdefs(file: str, stmts: list[Statement]) -> Iterator[tuple[str, FuncDef]]:
    # Walks methods, @overload implementations, and nested (closure) functions.
    for stmt in stmts:
        func: FuncDef | None = None
        if isinstance(stmt, FuncDef):
            func = stmt
        elif isinstance(stmt, Decorator):
            func = stmt.func
        elif isinstance(stmt, OverloadedFuncDef):
            impl = stmt.impl
            if isinstance(impl, Decorator):
                impl = impl.func
            if isinstance(impl, FuncDef):
                func = impl
        elif isinstance(stmt, ClassDef):
            yield from _walk_funcdefs(file, stmt.defs.body)
            continue
        if func is not None:
            yield file, func
            yield from _walk_funcdefs(file, func.body.body)  # nested defs (closures)


EFFECT_BASE_FULLNAME = "efflux._core.Effect"
RAISES_FULLNAME = "efflux.effects.Raises"
ALLOW_FULLNAME = "efflux.allow.allow"


def _resolve_effect_name(unbound: UnboundType, module: MypyFile) -> str | None:
    """Resolve an effect annotation node to its class fullname, walking dotted
    references (e.g. ``efflux.WritesDB`` or ``fx.WritesDB``) through nested
    symbol tables. Returns None if it is not a resolvable Effect subclass."""
    cur: object = module
    for part in unbound.name.split("."):
        names = getattr(cur, "names", None)
        if names is None:
            return None
        sym = names.get(part)
        if sym is None or sym.node is None:
            return None
        cur = sym.node  # MypyFile for a submodule, TypeInfo for the class
    if isinstance(cur, TypeInfo) and cur.has_base(EFFECT_BASE_FULLNAME):
        return cur.fullname
    return None


def _resolve_exception(unbound: UnboundType, module: MypyFile) -> tuple[str, frozenset[str]] | None:
    """Resolve an exception annotation to (fullname, ancestor fullnames). Builtins
    via runtime MRO; user exceptions via mypy TypeInfo.mro. None if unresolvable."""
    import builtins as _bi

    name = unbound.name.rsplit(".", 1)[-1]
    obj = getattr(_bi, name, None)
    if isinstance(obj, type) and issubclass(obj, BaseException):
        anc = frozenset(
            f"builtins.{c.__qualname__}" for c in obj.__mro__ if issubclass(c, BaseException)
        )
        return f"builtins.{obj.__qualname__}", anc
    sym = module.names.get(name)
    node = getattr(sym, "node", None) if sym is not None else None
    if isinstance(node, TypeInfo) and node.has_base("builtins.BaseException"):
        anc = frozenset(b.fullname for b in node.mro if b.fullname != "builtins.object")
        return node.fullname, anc
    return None


def _declared_effects(
    func: FuncDef, module: MypyFile, exc_ancestors: dict[str, frozenset[str]]
) -> frozenset[EffectRef] | None:
    """Return declared effects as EffectRefs (Raises[E] carries the exception
    fullname), or None if the function has no Effects[...] return annotation.
    Populates `exc_ancestors` for any Raises exception types encountered."""
    unanalyzed = func.unanalyzed_type
    ret = getattr(unanalyzed, "ret_type", None)
    if not isinstance(ret, UnboundType) or ret.name.split(".")[-1] != "Effects":
        return None
    effects: set[EffectRef] = set()
    for arg in ret.args[1:]:
        if not isinstance(arg, UnboundType):
            continue
        fullname = _resolve_effect_name(arg, module)
        if fullname is None:
            continue
        exc: str | None = None
        if fullname == RAISES_FULLNAME and arg.args and isinstance(arg.args[0], UnboundType):
            resolved = _resolve_exception(arg.args[0], module)
            if resolved is not None:
                exc, anc = resolved
                exc_ancestors[exc] = anc
        effects.add(EffectRef(fullname, exc))
    return frozenset(effects)


# mypy 2.1.0 ships fully compiled with mypyc, so its AST visitors
# (TraverserVisitor / NodeVisitor) are compiled *traits*: an interpreted Python
# class cannot subclass them, and node.accept() rejects a duck-typed visitor
# ("interpreted classes cannot inherit from compiled traits"). The nodes also
# use mypyc slots, so they expose neither __dict__ nor populated __slots__ for
# generic reflection. We therefore walk the AST explicitly, reading the known,
# stable child attributes of each statement/expression node via getattr.
#
# _CHILD_ATTRS lists every attribute that may hold a child Node or a
# (possibly nested) list/tuple of child Nodes. It is a superset across node
# types; getattr-with-default makes absent attributes harmless. This mirrors the
# child set that TraverserVisitor itself descends into.
_CHILD_ATTRS: tuple[str, ...] = (
    # statements
    "body",
    "else_body",
    "finally_body",
    "handlers",
    "types",
    "vars",
    "lvalues",
    "rvalue",
    "index",
    "target",
    "msg",
    "expr",
    "subject",
    "guards",
    "bodies",
    "from_expr",  # MatchStmt + raise...from
    # expressions
    "callee",
    "args",
    "left",
    "right",
    "operands",
    "left_expr",
    "cond",
    "if_expr",
    "else_expr",
    "base",
    "begin_index",
    "end_index",
    "stride",
    "items",
    "keys",
    "key",
    "value",
    "values",
    "operand",
    "analyzed",
    "sequences",
    "condlists",
    "indices",
    "generator",
)


def _iter_children(node: Node) -> Iterator[Node]:
    """Yield the immediate child AST nodes of ``node`` (statements and
    expressions), flattening lists/tuples (including nested lists such as a
    comprehension's ``condlists``). Non-node attributes and ``None`` slots are
    skipped."""
    for attr in _CHILD_ATTRS:
        val = getattr(node, attr, None)
        if isinstance(val, Node):
            yield val
        elif isinstance(val, (list, tuple)):
            for item in val:
                if isinstance(item, Node):
                    yield item
                elif isinstance(item, (list, tuple)):  # e.g. condlists
                    for sub in item:
                        if isinstance(sub, Node):
                            yield sub


def _resolve_member_callee(member: MemberExpr, types: dict[Expression, Type]) -> str | None:
    """Resolve a method call `recv.name(...)` to the method's fullname using the
    receiver's type. Returns None if the receiver type or method can't be found."""
    recv_type = types.get(member.expr)
    if recv_type is None and isinstance(member.expr, RefExpr) and member.expr.node is not None:
        recv_type = getattr(member.expr.node, "type", None)
    if not isinstance(recv_type, Instance):
        return None
    sym = recv_type.type.get(member.name)
    if sym is None:
        return None
    node = sym.node
    if isinstance(node, Decorator):
        node = node.func
    if isinstance(node, FuncDef):
        return node.fullname
    return None


def _callee_fullname(callee: Expression, types: dict[Expression, Type]) -> str | None:
    """Resolve a call's callee to a fullname. Plain references (`f`, `mod.func`)
    carry a fullname; method calls (`recv.method`) are resolved via the type map."""
    if isinstance(callee, RefExpr) and callee.fullname:
        return callee.fullname
    if isinstance(callee, MemberExpr):
        return _resolve_member_callee(callee, types)
    return None


def _caught_excs(stmt: TryStmt) -> frozenset[str]:
    """Exception fullnames caught by a try statement's except clauses. A bare
    `except:` catches BaseException (everything)."""
    caught: set[str] = set()
    for type_expr in stmt.types:
        if type_expr is None:
            caught.add("builtins.BaseException")
        elif isinstance(type_expr, TupleExpr):
            for item in type_expr.items:
                if isinstance(item, RefExpr) and item.fullname:
                    caught.add(item.fullname)
        elif isinstance(type_expr, RefExpr) and type_expr.fullname:
            caught.add(type_expr.fullname)
    return frozenset(caught)


def _allow_effects(stmt: WithStmt) -> frozenset[str]:
    """Effect fullnames discharged by a `with efflux.allow(...)` context manager
    (empty if this `with` is not an efflux.allow call)."""
    allowed: set[str] = set()
    for expr in stmt.expr:
        if (
            isinstance(expr, CallExpr)
            and isinstance(expr.callee, RefExpr)
            and expr.callee.fullname == ALLOW_FULLNAME
        ):
            for arg in expr.args:
                if isinstance(arg, RefExpr) and arg.fullname:
                    allowed.add(arg.fullname)
    return frozenset(allowed)


def _comment_allows(path: str, module: MypyFile) -> dict[int, frozenset[str]]:
    """Scan source for `# efflux: allow <Name> [...]` *comments* (not string
    literals); map line -> the discharged effect fullnames (resolved against the
    module symbol table)."""
    import re
    import tokenize

    out: dict[int, frozenset[str]] = {}
    pattern = re.compile(r"#\s*efflux:\s*allow\s+(.+)$")
    try:
        with open(path, "rb") as handle:
            tokens = list(tokenize.tokenize(handle.readline))
    except (OSError, tokenize.TokenError, SyntaxError):
        return out
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        match = pattern.match(tok.string)
        if not match:
            continue
        names = match.group(1).replace(",", " ").split()
        fullnames: set[str] = set()
        for name in names:
            sym = module.names.get(name.split(".")[-1])
            node = getattr(sym, "node", None) if sym is not None else None
            if isinstance(node, TypeInfo) and node.has_base(EFFECT_BASE_FULLNAME):
                fullnames.add(node.fullname)
        if fullnames:
            out[tok.start[0]] = frozenset(fullnames)
    return out


def _collect_calls(
    func: FuncDef,
    types: dict[Expression, Type],
    comment_allows: dict[int, frozenset[str]],
) -> list[CallSite]:
    """Collect call sites within a function body, region-aware. Does NOT descend
    into nested functions/lambdas (pruned)."""
    calls: list[CallSite] = []
    _walk_calls(func.body, types, frozenset(), frozenset(), calls, comment_allows)
    calls.sort(key=lambda c: c.line)
    return calls


def _walk_calls(
    node: Node,
    types: dict[Expression, Type],
    caught: frozenset[str],
    allowed: frozenset[str],
    calls: list[CallSite],
    comment_allows: dict[int, frozenset[str]],
) -> None:
    if isinstance(node, FuncDef):
        return  # nested function is its own model; lambdas are walked inline
    if isinstance(node, CallExpr):
        line_allowed = allowed | comment_allows.get(node.line, frozenset())
        calls.append(
            CallSite(_callee_fullname(node.callee, types), node.line, caught, line_allowed)
        )
        for child in _iter_children(node):
            _walk_calls(child, types, caught, allowed, calls, comment_allows)
        return
    if isinstance(node, TryStmt):
        body_caught = caught | _caught_excs(node)
        _walk_calls(node.body, types, body_caught, allowed, calls, comment_allows)
        if node.else_body is not None:
            # the `else` clause is NOT covered by this try's except handlers
            _walk_calls(node.else_body, types, caught, allowed, calls, comment_allows)
        for handler in node.handlers:  # handler bodies run AFTER the exception
            _walk_calls(handler, types, caught, allowed, calls, comment_allows)
        if node.finally_body is not None:
            _walk_calls(node.finally_body, types, caught, allowed, calls, comment_allows)
        return
    if isinstance(node, WithStmt):
        _walk_calls(node.body, types, caught, allowed | _allow_effects(node), calls, comment_allows)
        return
    for child in _iter_children(node):
        _walk_calls(child, types, caught, allowed, calls, comment_allows)


def _ancestors_map(effect_fullnames: set[str]) -> dict[str, frozenset[str]]:
    """For each effect, its own fullname plus the fullnames of its Effect
    superclasses (via runtime MRO), so a declared parent effect covers its
    children. User effects in non-importable temp modules fall back to
    self-only."""
    from efflux._core import Effect

    out: dict[str, frozenset[str]] = {}
    for fullname in effect_fullnames:
        mod, _, cls = fullname.rpartition(".")
        try:
            klass = getattr(importlib.import_module(mod), cls)
        except (ImportError, AttributeError, ValueError):
            out[fullname] = frozenset({fullname})
            continue
        anc = {
            f"{c.__module__}.{c.__qualname__}"
            for c in klass.__mro__
            if issubclass(c, Effect) and c is not Effect
        }
        out[fullname] = frozenset(anc | {fullname})
    return out


def analyze(
    paths: list[str],
    external: dict[str, frozenset[EffectRef]] | None = None,
) -> tuple[
    dict[str, FunctionModel],
    dict[str, frozenset[str]],
    dict[str, frozenset[str]],
]:
    """Build the project and produce (functions, tag-ancestors, exc-ancestors)."""
    trees, types = _build(paths)
    module_of = {tree.path: tree for tree in trees.values()}
    functions: dict[str, FunctionModel] = {}
    all_effects: set[str] = set()
    exc_ancestors: dict[str, frozenset[str]] = {}
    for file, func in _iter_funcdefs(trees):
        module = module_of[file]
        declared = _declared_effects(func, module, exc_ancestors)
        if declared:
            all_effects |= {ref.fullname for ref in declared}
        functions[func.fullname] = FunctionModel(
            fullname=func.fullname,
            file=file,
            line=func.line,
            declared=declared,
            calls=_collect_calls(func, types, _comment_allows(module.path, module)),
        )
    for effects in (external or {}).values():
        all_effects |= {ref.fullname for ref in effects}
    return functions, _ancestors_map(all_effects), exc_ancestors
