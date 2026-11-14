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
        ["fuzz", "-fuzz=^FuzzVehicleTelemetry$", "-exec=sh"],
        ["fuzz", "-fuzz=Fuzz.*"],
        ["fuzz", "-fuzz=^FuzzÄ$"],
        ["fuzz", "-fuzz=^FuzzVehicleTelemetry$", "-fuzztime=1٠s"],
        ["fuzz", "-fuzz=^FuzzVehicleTelemetry$", "-parallel=99"],
        ["fuzz", "-fuzz=^FuzzVehicleTelemetry$", "-fuzztime=0s"],
        ["fuzz", "-fuzz=^FuzzVehicleTelemetry$", "-timeout=301s"],
        ["fuzz-build", "-modfile=/tmp/other.mod"],
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


def test_fuzz_build_uses_instrumentation_without_execution(builder):
    command = builder["go_arguments"](["fuzz-build"])
    assert command == ["test", "-c", "-fuzz=Fuzz", f"-o={builder['os'].devnull}", "."]


def test_fuzz_limits_preserve_patched_module_wrapper(builder):
    assert builder["go_arguments"](
        [
            "fuzz",
            "-fuzz=^FuzzVehicleTelemetry$",
            "-fuzztime=60s",
            "-fuzzminimizetime=10s",
            "-parallel=2",
            "-timeout=120s",
        ]
    ) == [
        "test",
        "-run=^$",
        "-fuzz=^FuzzVehicleTelemetry$",
        "-fuzztime=60s",
        "-fuzzminimizetime=10s",
        "-parallel=2",
        "-timeout=120s",
        ".",
    ]


@pytest.mark.parametrize(
    "replacement",
    [
        "replace example.com/source => example.com/fork v1.0.1",
        "replace example.com/source => example.com/other v1.0.0",
        "",
        "replace example.com/source => example.com/fork v1.0.0\nreplace example.com/extra => example.com/other v1.0.0",
    ],
)
def test_replacement_drift_is_rejected_by_real_go_parser(builder, tmp_path, replacement):
    engine, source = tmp_path / "engine", tmp_path / "upstream"
    engine.mkdir()
    source.mkdir()
    prefix = "module example.com/fixture\ngo 1.20\n"
    (engine / "go.mod").write_text(prefix + replacement + "\n")
    (source / "go.mod").write_text(
        prefix + "replace example.com/source => example.com/fork v1.0.0\n"
    )
    with pytest.raises(SystemExit, match="replacements differ"):
        builder["validate_replacements"](engine, source)


def test_replacement_guard_accepts_equivalent_directive_order(builder, tmp_path):
    engine, source = tmp_path / "engine", tmp_path / "upstream"
    engine.mkdir()
    source.mkdir()
    first = "replace example.com/a => example.com/fork-a v1.0.0\n"
    second = "replace example.com/b => example.com/fork-b v2.0.0\n"
    prefix = "module example.com/fixture\ngo 1.20\n"
    (engine / "go.mod").write_text(prefix + first + second)
    (source / "go.mod").write_text(prefix + second + first)
    builder["validate_replacements"](engine, source)


def test_build_rejects_replacement_drift_before_staging_or_compilation(
    builder, tmp_path, monkeypatch
):
    source = tmp_path / "upstream"
    source.mkdir()
    (source / "go.mod").write_text("module example.com/fixture\ngo 1.20\n")
    real_output = builder["subprocess"].check_output

    def download(command, *args, **kwargs):
        if command[:3] == ["go", "mod", "download"]:
            return builder["json"].dumps({"Dir": str(source)}).encode()
        return real_output(command, *args, **kwargs)

    copy = MagicMock()
    monkeypatch.setattr(builder["subprocess"], "check_output", download)
    monkeypatch.setattr(builder["shutil"], "copytree", copy)
    monkeypatch.setattr(sys, "argv", ["build.py", "test"])
    with pytest.raises(SystemExit, match="replacements differ"):
        builder["main"]()
    copy.assert_not_called()
