"""Record the complete, exact three-wheel TLS dependency closure for offline use."""

import hashlib
import json
import os
import platform
import re
import sys
import zipfile
from email.parser import Parser
from pathlib import Path

EXPECTED = {"cffi": "2.1.1", "cryptography": "50.0.2", "pycparser": "3.11"}
IMAGES = {
    "build": "python:3.12.13-bookworm@sha256:3cd9086bdb30f7c9bc08a3fa621d9842e0d3f6f9291aeb4677e0547817c10b12",
    "verify": "python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2",
}


def read_trusted_hashes(lock: Path) -> dict[str, str]:
    """Accept only the exact reviewed dependency closure from the source checkout."""
    result = {}
    for line in lock.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([a-z0-9-]+)==(\S+) --hash=sha256:([a-f0-9]{64})", line)
        if not match:
            raise ValueError("Malformed trusted TLS wheel lock")
        name, version, digest = match.groups()
        if name in result or EXPECTED.get(name) != version:
            raise ValueError("Unexpected/duplicate trusted wheel lock entry")
        result[name] = digest
    if result.keys() != EXPECTED.keys():
        raise ValueError("Incomplete trusted TLS wheel lock")
    return result


def finalize(bundle: Path, trusted_lock: Path) -> None:
    """Verify produced wheel bytes against source-controlled pins, then record them."""
    trusted_hashes = read_trusted_hashes(trusted_lock)
    revision = os.environ.get("SOURCE_REVISION", "")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("SOURCE_REVISION must identify the reviewed Git commit")
    wheels = []
    names = set()
    for path in sorted((bundle / "wheels").glob("*.whl")):
        with zipfile.ZipFile(path) as archive:
            metadata = [
                name
                for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata) != 1:
                raise ValueError(f"Invalid wheel metadata: {path.name}")
            fields = Parser().parsestr(archive.read(metadata[0]).decode("utf-8"))
        name, version = fields["Name"], fields["Version"]
        if name in names or EXPECTED.get(name) != version:
            raise ValueError(f"Unexpected/duplicate wheel: {name} {version}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != trusted_hashes[name]:
            raise ValueError(f"Wheel differs from trusted source lock: {name}")
        names.add(name)
        wheels.append(
            {
                "name": name,
                "version": version,
                "file": path.name,
                "sha256": digest,
            }
        )
    if names != EXPECTED.keys():
        raise ValueError("Incomplete TLS dependency closure")
    (bundle / "requirements.txt").write_text(
        "".join(
            f"{w['name']}=={w['version']} --hash=sha256:{w['sha256']}\n" for w in wheels
        )
    )
    (bundle / "provenance.json").write_text(
        json.dumps(
            {
                "images": IMAGES,
                "python": sys.version,
                "machine": platform.machine(),
                "source_revision": revision,
                "libc": platform.libc_ver(),
                "wheels": wheels,
                "target": "CPython 3.12, Linux ARMv7 hard-float, glibc >= 2.36, libffi.so.8",
                "scope": "TLS dependency closure only; existing application dependencies remain required",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    # This image-local entrypoint writes only the fixed build artifact directory.
    finalize(Path("/bundle"), Path("/build/requirements-tls-armv7.txt"))
