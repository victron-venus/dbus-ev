"""The engine build CLI cannot override mandatory patches or invoke Go hooks."""

import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(name="builder")
def load_builder():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "vehicle-engine/build.py"))


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["run", "evil.go"],
        ["build", "-modfile=/tmp/other.mod"],
        ["build", "-mod=mod"],
        ["build", "-overlay=/tmp/overlay.json"],
        ["build", "-toolexec=sh"],
        ["build", "-ldflags=-extld=sh"],
        ["build", "/tmp/unreviewed-package"],
        ["test", "-exec=sh"],
        ["test", "-args", "unreviewed-test-argument"],
        ["test", "-count=0"],
        ["test", "-count=1; touch injected"],
        ["vet", "-vettool=/tmp/tool"],
    ],
)
def test_invalid_build_arguments_fail_before_any_process(builder, monkeypatch, arguments):
    monkeypatch.setattr(sys, "argv", ["build.py", *arguments])
    download, run = MagicMock(), MagicMock()
    monkeypatch.setattr(builder["subprocess"], "check_output", download)
    monkeypatch.setattr(builder["subprocess"], "run", run)
    with pytest.raises(SystemExit) as error:
        builder["main"]()
    assert error.value.code == 2
    download.assert_not_called()
    run.assert_not_called()


def test_supported_build_commands_and_literal_output(builder, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    parse = builder["go_arguments"]
    output = "-exec=sh ; $(touch injected)"
    assert parse(["build", "-trimpath", "-ldflags=-s -w", f"--output={output}", "."]) == [
        "build",
        "-trimpath",
        "-ldflags=-s -w",
        f"-o={tmp_path / output}",
        ".",
    ]
    assert parse(["test", "-race", "-count=1", "./..."]) == ["test", "-race", "-count=1", "./..."]
    assert parse(["vet", "./..."]) == ["vet", "./..."]
    assert not (tmp_path / "injected").exists()
