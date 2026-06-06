from pathlib import Path

import yaml  # provided by pre-commit (a hard dependency) in the dev env


def test_pre_commit_hooks_file_defines_efflux_hook():
    hooks = yaml.safe_load(Path(".pre-commit-hooks.yaml").read_text())
    assert isinstance(hooks, list)
    hook = next(h for h in hooks if h["id"] == "efflux")
    assert hook["entry"] == "efflux"
    assert hook["language"] == "python"
    assert hook["pass_filenames"] is False
