---
name: efflux-navigate
description: Use when exploring or auditing a codebase by its side effects — find functions by effect (DB writes, network, raises X), read a function's effect surface, or enforce effect boundaries, using efflux annotations and effects_of().
---

# Navigating code by its effects

efflux declares side effects in return types
(`-> Effects[Receipt, Raises[PaymentError], WritesDB, Logs]`). Use those
declarations to navigate and audit a codebase: answer "what does this do?" and
"what does X?" in terms of effects instead of reading every body.

## Three lenses

1. **Static (grep) — who declares what.** Search the annotations:
   ```bash
   grep -rn "Effects\[" path/      # every annotated function
   grep -rn "WritesDB" path/       # DB writers (also see subsumption below)
   grep -rn "Raises\[" path/       # functions that declare raising
   ```
2. **Runtime — a function's exact effects.** `effects_of` returns the declared
   effects tuple, in declaration order:
   ```python
   from efflux import effects_of
   from mypkg.billing import charge

   effects_of(charge)   # -> (Raises[PaymentError], WritesDB, Logs)
   ```
3. **Inference — where effects are used but undeclared.** `efflux <path>` reports
   used-but-not-declared gaps and drives effect propagation across calls; use it
   to find under-declared boundaries.

## Respect subsumption when matching

Effects form a hierarchy, so a query must include the umbrellas:
- a "DB writer" is anything declaring `WritesDB`, **or** `Database`, **or** `IO`;
- "does network" → `Network` or `IO`;
- "can raise `ValueError`" → `Raises[ValueError]`, a superclass such as
  `Raises[Exception]`, or bare `Raises`.

Search for the effect *and its ancestors* — don't assume only the narrowest tag
appears.

## Common queries

- **"What can this function do?"** → `effects_of(fn)`, or read its `Effects[...]`.
- **"Find everything that writes the DB / hits the network / raises X."** → grep
  the effect plus its umbrellas; confirm with `effects_of`.
- **"What is the effect surface of this module?"** → list its annotated functions
  and their effects.
- **"Which functions are pure?"** → those declared `Effects[T]` with no effects
  (no IO/Raises in the declaration).
- **"Enforce a boundary"** (e.g. the domain layer must not touch IO) → grep the
  layer for `IO`/`Network`/`Database`/`WritesDB`/…; anything declaring them breaks
  the boundary. Run `efflux <path>` to also catch effects that *leak* in through
  calls without a declaration.

## Tips

- Pair with the `efflux-annotate` skill — navigation is far more useful once the
  boundaries are annotated.
- For a precise, runtime-accurate answer prefer `effects_of()`; for a fast survey
  prefer grep; to find *missing* declarations run `efflux <path>`.
