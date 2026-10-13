"""An untrusted bundle cannot replace the source-controlled installation hashes."""

import hashlib
import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path


def test_rewritten_bundle_hashes_do_not_authorize_installation(tmp_path):
    """Exercise real offline pip, redirecting only the install target to a fixture."""
    root = Path(__file__).resolve().parents[1]
    bundle = tmp_path / "untrusted-bundle"
    wheels = bundle / "wheels"
    wheels.mkdir(parents=True)
    requirements = []
    for name, version in {"cffi": "2.1.1", "cryptography": "50.0.2", "pycparser": "3.11"}.items():
        wheel = wheels / f"{name}-{version}-py3-none-any.whl"
        dist = f"{name}-{version}.dist-info"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(f"{name}/__init__.py", f"__version__ = {version!r}\n")
            archive.writestr(
                f"{dist}/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            )
            archive.writestr(
                f"{dist}/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            archive.writestr(f"{dist}/RECORD", "")
        requirements.append(
            f"{name}=={version} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}\n"
        )
    (bundle / "requirements.txt").write_text("".join(requirements))

    # ensurepip uses the interpreter's bundled wheels, without network access.
    environment = tmp_path / "pip-environment"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    control = subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            "--require-hashes",
            "--only-binary=:all:",
            "--find-links",
            str(wheels),
            "--target",
            str(tmp_path / "control-install"),
            "-r",
            str(bundle / "requirements.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert control.returncode == 0, control.stdout + control.stderr

    # Preserve the real installer command, replacing only its absolute device target.
    destination = tmp_path / "guarded-install"
    shim = tmp_path / "shim"
    shim.mkdir()
    executable = shim / "python3"
    executable.write_text(
        f"#!{sys.executable}\nimport os, sys\n"
        f"args = [{str(python)!r}, *sys.argv[1:]]\n"
        f"args = [{str(destination)!r} if x == '/data/setupOptions/dbus-ev/python' "
        "else x for x in args]\n"
        f"os.execv({str(python)!r}, args)\n"
    )
    executable.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(root / "install-tls-deps.sh"), str(bundle)],
        env={**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "DO NOT MATCH THE HASHES" in result.stderr, result.stdout + result.stderr
    assert not destination.exists() or not list(destination.iterdir())
