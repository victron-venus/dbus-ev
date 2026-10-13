"""The actual source archive must carry every installed runtime prerequisite."""

import json
import re
import tarfile
from pathlib import Path

from scripts.package_release import package_inputs, write_archive


def test_native_archive_contains_installer_and_tls_inputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / ".release-package.json").read_text())
    _, selected = package_inputs(root, config)
    archive = tmp_path / "candidate.tar.gz"
    write_archive(root, config["name"], selected, archive)
    runtime = (
        re.search(r'^RUNTIME_ITEMS="([^"]+)"', (root / "update.sh").read_text(), re.MULTILINE)
        .group(1)
        .split()
    )
    with tarfile.open(archive) as package:
        names = package.getnames()
        for item in runtime:
            prefix = f"{config['name']}/{item}"
            assert any(name == prefix or name.startswith(prefix + "/") for name in names), item
        for name in ("requirements-tls.txt", "requirements-mercedes.txt", "install-tls-deps.sh"):
            member = package.getmember(f"{config['name']}/{name}")
            assert package.extractfile(member).read() == (root / name).read_bytes()
        assert package.getmember(f"{config['name']}/install-tls-deps.sh").mode == 0o755
