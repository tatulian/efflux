# efflux

[![CI](https://github.com/tatulian/efflux/actions/workflows/ci.yml/badge.svg)](https://github.com/tatulian/efflux/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

**efflux makes a function's real side effects part of its signature — and keeps them honest.**

```python
from efflux import Effects, Raises, WritesDB, Logs

def charge(user_id: int) -> Effects[Receipt, Raises[PaymentError], WritesDB, Logs]:
    ...
```

That return type says exactly what `charge` does to the outside world: it can raise
`PaymentError`, it writes to the database, it logs. Yet **to mypy and to your callers,
`charge` still returns `Receipt`** — the effects ride along as metadata, nothing about
your code or its types changes. A companion checker then propagates effects across your
call graph, so a function that *quietly* starts writing to the DB — or a domain layer
that sneaks in IO — gets caught.

See what your code does. Enforce what it's allowed to do.

---

## The problem

Python hides side effects. A signature like `def settle(order: Order) -> Receipt` tells
you the return type and nothing else:

- **What can it raise?** Python has no checked exceptions — you find out in production.
- **Does it touch the database? The network? The filesystem?** You have to read the body,
  and the bodies of everything it calls.
- **Did your architecture erode?** The "pure" domain function someone added a `requests`
  call to last quarter looks identical to the one that didn't.

Docstrings drift. Code review can't see three calls deep. The information you most want
about a function — its *blast radius* — is exactly what the type system throws away.

efflux puts it back, without making you rewrite anything.

## Quickstart

```bash
pip install efflux
```

Enable the mypy plugin (this is what makes `Effects[...]` type-check):

```toml
# pyproject.toml
[tool.mypy]
plugins = ["efflux.mypy_plugin"]
```

Annotate a boundary and let mypy and the checker keep it honest:

```python
from efflux import Effects, WritesDB

def save_user(u: User) -> Effects[None, WritesDB]:
    db.execute("insert into users ...")   # the declared WritesDB
```

Then propagate effects across your whole package:

```bash
efflux path/to/your/package
```

If some caller of `save_user` doesn't declare `WritesDB`, efflux tells you — pointing at
the exact call that introduced it.

## What you get

### Non-invasive by design

`Effects[T, *effects]` erases to `T`. Callers see the real return type; refactoring tools,
overload resolution, and `isinstance` all behave exactly as before. You can adopt efflux
one function at a time and rip it out just as easily — it's metadata on an `Annotated`
type, not a wrapper around your values.

### A practical effect vocabulary, with subsumption

Effects are just classes, arranged in a shallow hierarchy. **Declaring a parent covers its
children**, so you choose how precise to be:

```
IO                      — any interaction with the outside world
├── Network
├── ReadsEnv
├── Filesystem → ReadsFS, WritesFS
└── Database   → ReadsDB, WritesDB
Raises[E]               — parameterized by the exception class
Logs  Emits  Random  Clock  MutatesGlobal  Blocks
```

Declare `Database` and both `ReadsDB` and `WritesDB` are covered; declare `IO` and you've
covered the lot. `Raises[ConnectionError]` is covered by `Raises[OSError]`; bare `Raises`
covers anything.

### Your own effects

An effect is a class — subclass `Effect` anywhere, including in your own package.
Inheritance gives you subsumption for free:

```python
from efflux import Effect, WritesDB

class WritesKafka(Effect): ...          # a brand-new effect
class WritesPostgres(WritesDB): ...     # implies WritesDB
```

### Effects at runtime

```python
from efflux import effects_of

effects_of(charge)
# -> (Raises[PaymentError], WritesDB, Logs)  — in declaration order
```

### A checker that propagates across the call graph

`efflux <path>` infers each function's effects **bottom-up** — so you only annotate the
boundaries you care about — and reports any function that *uses* an effect it didn't
*declare*. It's **gradual**: only functions that carry an `Effects[...]` declaration are
enforced; everything else is inferred and propagated silently. Calls it can't see into are
treated as pure, and you can teach it about third-party functions:

```toml
[tool.efflux.external]
"requests.api.get" = ["Network"]
"time.time" = ["Clock"]
```

efflux already ships a built-in map for common stdlib and HTTP calls (`open`,
`os.getenv`, `logging.*`, `time.*`, `random.*`, `socket`, `requests`, `httpx`),
applied by default — your entries override it per callee, and `--no-builtins`
turns it off. Report every function's inferred effects instead of checking:

```bash
efflux --report path/to/your/package      # human-readable
efflux --report --json path/to/package    # machine-readable (also: efflux --json)
```

Run efflux as a pre-commit hook in your own repo:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/tatulian/efflux
  rev: v0.1.0
  hooks:
    - id: efflux
      args: ["yourpackage"]
```

Enforce architectural boundaries — forbid an effect across a glob of modules
(checks *inferred* effects, so it catches leaks even when undeclared):

```toml
[tool.efflux.boundaries]
"myapp.domain.*" = { forbid = ["IO"] }   # the domain layer must stay pure
```

Adopt on an existing codebase with a baseline — grandfather current violations
and fail only on new ones:

```bash
efflux mypkg --baseline efflux-baseline.json --update   # write the baseline once
efflux mypkg --baseline efflux-baseline.json            # then only new violations fail
```

Adopt fast — let efflux write the annotations for you (needs `pip install 'efflux[fix]'`):

```bash
efflux mypkg --fix            # complete existing Effects[...] declarations
efflux mypkg --fix --unsafe   # also wrap plain `-> T` return types (review the diff!)
```

### Narrowing: contain effects on purpose

A `try/except` discharges the matching `Raises`:

```python
def safe_parse(s: str) -> Effects[int]:   # declares no Raises
    try:
        return parse(s)                    # parse may Raises[ValueError]
    except ValueError:
        return 0
```

`efflux.allow(...)` (or a `# efflux: allow <Effect>` comment) discharges any effect you
intentionally contain:

```python
from efflux import allow

def warm_cache() -> Effects[int]:
    with allow(WritesDB):
        return _seed()                     # _seed writes to the DB on purpose
```

## A worked example

A billing service that reads and writes the DB, calls a payment gateway over the network,
can raise, and logs — all declared in one line:

```python
from efflux import Effects, Raises, ReadsDB, WritesDB, Network, Logs

class PaymentError(Exception): ...

def charge(user_id: int, cents: int) -> Effects[
    Receipt, Raises[PaymentError], ReadsDB, WritesDB, Network, Logs
]:
    account = load_account(user_id)         # ReadsDB
    if account.balance < cents:
        raise PaymentError("insufficient funds")
    receipt = gateway.capture(cents)        # Network
    save_receipt(receipt)                   # WritesDB
    log.info("charged user %s", user_id)    # Logs
    return receipt
```

Now enforce an **architectural boundary** — a domain rule that must stay pure:

```python
def price_basket(basket: Basket) -> Effects[Money]:   # declares: no effects
    return apply_discounts(basket.subtotal())
```

If someone later makes `apply_discounts` read feature flags from the database, efflux fails:

```text
pricing.py:12: error: function "pricing.price_basket" has undeclared effect
"ReadsDB" (introduced by call to "flags.is_enabled" at line 14)
```

The violation is caught at check time, with the exact call that broke the rule — not in a
postmortem.

## How it works

efflux is two independent layers that share one effect vocabulary:

- **Visibility** (`efflux/` + the mypy plugin) — `Effects[T, *effects]` is an `Annotated`
  type; the plugin makes it type-check as `T` and validates the effects. Pure runtime, zero
  cost to import.
- **The checker** (`efflux <path>`) — a separate static analyzer that drives mypy's own
  build, walks the call graph, and reports undeclared effects, with subsumption and
  discharge.

Use the first layer alone as *type-checked documentation*, or add the checker when you want
propagation enforced.

## Built for AI-assisted development

Effect annotations are **machine-readable contracts**, which pays off twice when AI coding
agents are in the loop:

- **Legibility without reading bodies.** An agent sees
  `-> Effects[Receipt, Raises[PaymentError], WritesDB]` and knows the blast radius — no need
  to trace the implementation or its callees.
- **A verification oracle.** After an agent edits code, `efflux <path>` deterministically
  flags any new, undeclared effect it introduced — instant feedback that a change didn't
  quietly start touching the DB or the network.
- **Navigation by effect.** "Everything that writes to the DB" or "what can this raise"
  become `grep` / `effects_of()` queries instead of archaeology.

efflux ships two [Claude Code](https://claude.com/claude-code) skills (in [`skills/`](skills/))
to make this hands-on:

- **efflux-annotate** — cover an existing codebase with `Effects[...]`, using the checker as
  the oracle.
- **efflux-navigate** — explore and audit a codebase by its declared effects.

## efflux vs. the alternatives

| | **efflux** | `returns` (dry-python) | Java-style checked exceptions | docstrings / plain mypy |
|---|:---:|:---:|:---:|:---:|
| Effects visible in the signature | ✅ | ✅ | errors only | informal / ❌ |
| Code & types stay unchanged (non-invasive) | ✅ | ❌ (wrap your values) | ❌ | ✅ / ✅ |
| Covers IO, DB, network… not just errors | ✅ | partial | ❌ | ❌ |
| Checked by tooling | ✅ mypy + checker | ✅ mypy plugin | ✅ compiler | ❌ |
| Propagates across the call graph | ✅ | via types | manual | ❌ |
| Gradual, opt-in adoption | ✅ | partial | ❌ all-or-nothing | n/a |

The short version: `returns` gives you typed effects but you wrap every value; checked
exceptions are all-or-nothing and only cover errors; docstrings aren't checked. efflux's bet
is **non-invasive metadata + a gradual checker**.

## Install

```bash
pip install efflux
```

> Not yet published to PyPI — until the first release, install from source:
> `uv pip install git+https://github.com/tatulian/efflux`

The mypy plugin is required for `Effects[...]` to type-check:

```ini
# mypy.ini
[mypy]
plugins = efflux.mypy_plugin
```

```toml
# or pyproject.toml
[tool.mypy]
plugins = ["efflux.mypy_plugin"]
```

## Effect reference

| Effect | Meaning |
|---|---|
| `IO` | umbrella for any outside-world interaction |
| `Network` | network access |
| `ReadsEnv` | reads environment variables |
| `Filesystem` / `ReadsFS` / `WritesFS` | filesystem access (read / write) |
| `Database` / `ReadsDB` / `WritesDB` | database access (read / write) |
| `Raises[E]` | can raise exception class `E` |
| `Logs` | emits log output |
| `Emits` | emits events / messages |
| `Random` | uses randomness |
| `Clock` | reads the clock |
| `MutatesGlobal` | mutates global / module state |
| `Blocks` | blocks the calling thread |

## FAQ

**Do I have to use the checker?** No. The annotations + mypy plugin work on their own as
checked documentation. The `efflux` checker is an optional second layer for call-graph
enforcement.

**What's the runtime cost?** Effectively none. `Effects[...]` is an `Annotated` type; at
runtime it's metadata, and `import efflux` does not import mypy.

**Is it all-or-nothing?** No — adoption is gradual. Only functions you annotate with
`Effects[...]` are enforced; the rest are inferred and propagated silently.

**Which versions?** Python ≥ 3.10. The checker drives mypy internals and is exercised
against mypy 2.x (`mypy>=2.1,<3`).

**Is it production-ready?** It's early (0.1, beta) but usable today: the visibility layer is
small and stable, and the checker has a thorough test suite. Pin your version and expect the
API to still move.

## License

MIT — see [LICENSE](LICENSE).
