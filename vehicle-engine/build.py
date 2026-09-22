#!/usr/bin/env python3
"""Build/test the pinned providers with mandatory patches in an isolated copy."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ALL_PACKAGES = "./..."


def build_arguments(args):
    command = ["build"]
    if args.trimpath:
        command.append("-trimpath")
    if args.ldflags:
        command.append("-ldflags=-s -w")
    if args.output is not None:
        command.append(f"-o={args.output.resolve()}")
    return command


def test_arguments(args, parser):
    command = ["test"]
    if args.race:
        command.append("-race")
    if args.count is not None:
        if args.count < 1:
            parser.error("-count must be positive")
        command.append(f"-count={args.count}")
    return command


def go_arguments(argv=None):
    """Accept only build/test options that cannot replace the patched module."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("-trimpath", action="store_true")
    build.add_argument("-ldflags", choices=("-s -w",))
    build.add_argument("--output", type=Path)
    build.add_argument("package", nargs="?", choices=(".",), default=".")
    test = commands.add_parser("test")
    test.add_argument("-race", action="store_true")
    test.add_argument("-count", type=int)
    test.add_argument("package", nargs="?", choices=(".", ALL_PACKAGES), default=ALL_PACKAGES)
    vet = commands.add_parser("vet")
    vet.add_argument("package", nargs="?", choices=(".", ALL_PACKAGES), default=ALL_PACKAGES)
    args = parser.parse_args(argv)
    if args.command == "build":
        command = build_arguments(args)
    elif args.command == "test":
        command = test_arguments(args, parser)
    else:
        command = ["vet"]
    command.append("." if args.package == "." else ALL_PACKAGES)
    return command


def main():
    # Validate before downloading modules or invoking any process.
    command = go_arguments()
    root = Path(__file__).resolve().parent
    os.chdir(root)
    module = json.loads(
        subprocess.check_output(["go", "mod", "download", "-json", "github.com/evcc-io/evcc"])
    )
    source = Path(module["Dir"])
    inputs = json.loads((root / "patches/inputs.json").read_text())
    with tempfile.TemporaryDirectory(prefix="dbus-ev-engine-") as temporary:
        stage = Path(temporary) / "upstream"
        shutil.copytree(source, stage)
        stage.chmod(0o700)
        for item in inputs:
            name, expected = item["path"], item["sha256"]
            original, target = source / name, stage / name
            if hashlib.sha256(original.read_bytes()).hexdigest() != expected:
                raise SystemExit(f"Pinned upstream source changed: {name}")
            target.parent.chmod(0o700)
            target.chmod(0o600)
        subprocess.run(
            ["git", "apply", str(root / "patches/conservative.patch")], cwd=stage, check=True
        )
        modfile = Path(temporary) / "engine.mod"
        modfile.write_text(
            (root / "go.mod").read_text() + f"\nreplace github.com/evcc-io/evcc => {stage}\n"
        )
        shutil.copyfile(root / "go.sum", modfile.with_suffix(".sum"))
        # S8705: only allowlisted options reach Go. The output filename is a
        # literal -o=value; callers cannot inject -modfile/-overlay/-toolexec/-exec.
        subprocess.run(  # NOSONAR - validated build options, no arbitrary Go flags
            ["go", command[0], "-mod=readonly", f"-modfile={modfile}", *command[1:]],
            shell=False,
            check=True,
        )


if __name__ == "__main__":
    main()
