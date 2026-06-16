# Contributing to efflux

Thanks for your interest in efflux. Bug reports, ideas, and pull requests are all
welcome.

## Development setup

efflux uses [uv](https://docs.astral.sh/uv/). With it installed:

```bash
git clone https://github.com/tatulian/efflux
cd efflux
uv sync            # create .venv and install efflux + dev tools
```

Install the git hooks (ruff lint + format, plus a few hygiene checks) so they run
on every commit:

```bash
uv run pre-commit install
```

## The checks

CI runs these on every push and pull request; run them locally before opening a PR
(or use the `Makefile` shortcuts — `make check` runs all of them):

```bash
uv run ruff check                 # lint
uv run ruff format --check        # formatting
uv run mypy efflux                # type-check (efflux dogfoods its own plugin)
uv run pytest -q                  # the full test suite
```

To run a single test file or test:

```bash
uv run pytest tests/check/test_inference.py -v
uv run pytest "tests/check/test_inference.py::test_check_raises_exception_subsumption" -v
```

You can also run the checker on efflux itself:

```bash
uv run efflux efflux
```

## Pull requests

- **Write a test first.** Every behaviour change — feature or bug fix — comes with a
  test that fails before the change and passes after. The suite is the contract.
- Keep changes focused; one logical change per PR is easiest to review.
- Match the surrounding style. The codebase favours small, well-documented functions
  and explains *why* in comments, not *what*.
- Make sure `make check` is green before pushing.

### Working on the checker

`efflux/check/engine.py` binds to semi-private mypy internals and is pinned to mypy
2.x (`mypy>=2.1,<3`). If you touch the AST walk, note that mypy ships compiled with
mypyc, so the walker reads a hand-maintained set of child attributes (`_CHILD_ATTRS`)
rather than subclassing mypy's visitors — add new node attributes there or calls
beneath them are missed (the parametrised `test_walker_captures_call_under_construct`
guards this). A mypy upgrade needs re-verification against `engine.py`.

## Reporting bugs

Open an issue with a minimal reproducer — the smallest snippet plus the `efflux`
command and the output you got versus what you expected. The
[bug report template](.github/ISSUE_TEMPLATE/bug_report.md) walks through it.

## License

By contributing you agree that your contributions are licensed under the project's
[MIT License](LICENSE).
