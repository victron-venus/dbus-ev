#!/usr/bin/env python3
"""Build/test the pinned providers with mandatory patches in an isolated copy."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
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
        command = sys.argv[1:]
        if not command or command[0] not in ("test", "build", "vet"):
            raise SystemExit("Usage: python3 build.py build|test|vet [Go arguments]")
        subprocess.run(
            ["go", command[0], "-mod=readonly", f"-modfile={modfile}", *command[1:]], check=True
        )


if __name__ == "__main__":
    main()
