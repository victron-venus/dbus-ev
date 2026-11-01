"""Consumer regressions for rejected detached OCI evidence before publication.

Preserved from the independent CodeRabbit review; this file is not generated.
"""

# Imports follow the vendored script path; each test owns its temporary checkout.
# pylint: disable=wrong-import-position,missing-class-docstring,missing-function-docstring

import argparse
import base64
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import merge_oci_archives as oci
import release_provenance
import release_versioned
import stage_release_assets
import version_plan
import version_receipt


# Explicit paths and evidence describe the shared build fixture.
# pylint: disable-next=too-many-instance-attributes
class BuildInputsFixture(unittest.TestCase):
    def setUp(self):
        # This synthetic fixture intentionally has no detached OCI contract.
        self.enterContext(patch.object(release_provenance, "REQUIRED_PAIRS", ()))
        # unittest owns cleanup across setup, the test body and assertion failures.
        # pylint: disable-next=consider-using-with
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.metadata = self.root / "metadata"
        self.metadata.mkdir()
        self.source = self.metadata / "package.json"
        self.source.write_text(
            '{"version":"1.2.3","dependencies":{"example":"1.0.0"}}',
            encoding="utf-8",
        )
        self.policy = {
            "repository": "example/project",
            "mode": "release",
            "version_file": "metadata/package.json",
            "versioning": {
                "schema": 1,
                "promotion": "final-build",
                "files": [
                    {
                        "path": "metadata/package.json",
                        "format": "json",
                        "field": "version",
                        "value": "full",
                    }
                ],
            },
        }
        self.plan = version_plan.create_plan("1.2.3", "rc", 1, "a" * 40, self.policy, 51)
        self.files = version_plan.sync_versions(self.root, self.policy, self.plan)
        self.evidence = {
            "source_sha": self.plan["source_sha"],
            "plan_sha256": version_plan.plan_digest(self.plan),
            "effective_inputs_sha256": version_plan.effective_inputs_digest(self.files),
            "files": self.files,
        }
        self.plan_path = self.root / ".release-plan.json"
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.inputs_path = self.root / ".release-inputs.json"
        self.write_evidence()
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / "package.bin").write_bytes(b"package with the full RC identity")
        self.output = self.assets / "release-inputs-linux.json"
        toolchain = patch.object(
            version_receipt, "capture_toolchain", return_value={"python": "3.12.0"}
        )
        toolchain.start()
        self.addCleanup(toolchain.stop)

    def write_evidence(self):
        self.inputs_path.write_text(json.dumps(self.evidence), encoding="utf-8")

    def create(self):
        return version_receipt.create_receipt(
            self.plan_path, self.inputs_path, self.assets, self.output
        )


class DetachedProvenanceTests(BuildInputsFixture):
    """Use real detached OCI evidence at the staging and publication boundaries."""

    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": self.policy["repository"],
            "GITHUB_RUN_ID": "99",
            "GITHUB_RUN_ATTEMPT": "1",
        }))
        self.pair = {
            "image": "image.oci.tar",
            "sidecar": "image.provenance.json",
            "platforms": list(oci.PLATFORMS),
        }
        self.enterContext(patch.object(release_provenance, "REQUIRED_PAIRS", (self.pair,)))
        self.enterContext(patch.dict(os.environ, {"RELEASE_VERSION_PLAN": str(self.plan_path)}))
        self.policy["sign_releases"] = True
        self.policy["detached_provenance"] = [self.pair]
        self.policy["versioning"]["artifacts"] = [
            {
                "path": self.pair["image"],
                "format": "oci",
                "value": "full",
                "field": ["config", "Labels", "org.opencontainers.image.version"],
            }
        ]
        self.plan = version_plan.create_plan("1.2.3", "rc", 1, "a" * 40, self.policy, 51)
        self.files = version_plan.sync_versions(self.root, self.policy, self.plan)
        self.evidence.update(
            plan_sha256=version_plan.plan_digest(self.plan),
            effective_inputs_sha256=version_plan.effective_inputs_digest(self.files),
            files=self.files,
        )
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.write_evidence()
        (self.root / ".release-policy.json").write_text(json.dumps(self.policy), encoding="utf-8")
        self.image = self.assets / self.pair["image"]
        self.sidecar = self.assets / self.pair["sidecar"]
        inputs = {platform: self.native_archive(platform) for platform in oci.PLATFORMS}
        release_provenance.detach(inputs, self.image, self.sidecar, self.policy, self.plan)

    def native_archive(self, platform):
        entries = {"oci-layout": oci.canonical({"imageLayoutVersion": "1.0.0"})}

        def blob(value, media):
            raw = oci.canonical(value)
            digest = version_receipt.sha256(raw)
            entries[oci.BLOB_PREFIX + digest] = raw
            return {"mediaType": media, "digest": "sha256:" + digest, "size": len(raw)}

        system, architecture = platform.split("/")
        config = blob(
            {
                "os": system,
                "architecture": architecture,
                "config": {
                    "Labels": {
                        "org.opencontainers.image.version": self.plan["version"],
                        "org.opencontainers.image.revision": self.plan["source_sha"],
                    }
                },
                "rootfs": {"type": "layers", "diff_ids": []},
            },
            oci.CONFIG,
        )
        image = blob(
            {"schemaVersion": 2, "mediaType": oci.MANIFEST, "config": config, "layers": []},
            oci.MANIFEST,
        )
        statement = blob(
            {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [{"name": "image", "digest": {"sha256": image["digest"][7:]}}],
                "predicateType": "https://slsa.dev/provenance/v1",
                "predicate": {},
            },
            oci.IN_TOTO,
        )
        attestation = blob(
            {
                "schemaVersion": 2,
                "mediaType": oci.MANIFEST,
                "artifactType": oci.ATTESTATION,
                "subject": dict(image),
                "config": blob({}, oci.EMPTY_CONFIG),
                "layers": [statement],
            },
            oci.MANIFEST,
        )
        image["platform"] = {"os": system, "architecture": architecture}
        attestation["platform"] = {"os": "unknown", "architecture": "unknown"}
        attestation["annotations"] = {oci.REFERENCE_TYPE: "attestation-manifest"}
        entries["index.json"] = oci.canonical(
            {
                "schemaVersion": 2,
                "mediaType": oci.INDEX,
                "manifests": [image, attestation],
            }
        )
        path = self.root / f"native-{architecture}.oci.tar"
        with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as archive:
            for name, raw in sorted(entries.items()):
                entry = tarfile.TarInfo(name)
                entry.size = len(raw)
                archive.addfile(entry, io.BytesIO(raw))
        return path

    def inventory(self):
        return [
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": version_receipt.sha256(path.read_bytes()),
            }
            for path in sorted(self.assets.iterdir())
        ]

    def assert_staging_rejected(self, message):
        before = {path.name: path.read_bytes() for path in self.assets.iterdir()}
        with (
            patch.object(
                stage_release_assets.subprocess,
                "check_output",
                return_value=self.plan["source_sha"],
            ),
            patch.object(stage_release_assets.subprocess, "run") as receipt_writer,
            patch.object(stage_release_assets, "inspect_staged_artifacts") as metadata,
            self.assertRaisesRegex(ValueError, message),
        ):
            stage_release_assets.stage(self.root, "native", ["assets/*"])
        receipt_writer.assert_not_called()
        metadata.assert_not_called()
        self.assertFalse((self.root / "release-assets").exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.assets.iterdir()})

    def assert_publication_rejected(self, message, authenticated=None):
        gh = Mock(repo=self.policy["repository"])
        evidence = self.root / "published-evidence.json"
        stage_assets = release_versioned.rc.stage_assets

        def stage(source, destination):
            actual = stage_assets(source, destination)
            return actual if authenticated is None else authenticated

        # Mock remote qualification only; staging, receipts and provenance stay real.
        with (
            patch.object(release_versioned, "PLAN", self.plan_path),
            patch.object(release_versioned, "StateGitHub", return_value=gh),
            patch.object(
                release_versioned,
                "context",
                return_value=(
                    {},
                    {"id": 99, "run_attempt": 1, "head_sha": self.plan["source_sha"]},
                    {"data": self.policy},
                ),
            ),
            patch.object(release_versioned, "verify_reservation"),
            patch.object(release_versioned.rc, "ensure_absent"),
            patch.object(release_versioned.rc, "superseded_candidate", return_value=None),
            patch.object(release_versioned.rc, "stage_assets", side_effect=stage),
            patch.object(release_versioned.rc, "verify_required_signatures") as signatures,
            patch.object(release_versioned, "begin_publication") as begin,
            patch.object(release_versioned.rc, "_publish_prepared") as publish,
            patch.object(release_versioned.rc, "EVIDENCE", evidence),
            self.assertRaisesRegex(ValueError, message),
        ):
            release_versioned.publish_versioned(
                argparse.Namespace(repo=self.policy["repository"], assets=str(self.assets))
            )
        signatures.assert_not_called()
        begin.assert_not_called()
        publish.assert_not_called()
        self.assertEqual(gh.mock_calls, [])
        self.assertFalse(evidence.exists())

    def test_valid_pair_has_a_publisher_accepted_receipt(self):
        receipt = self.create()
        verified = version_receipt.verify_receipts(
            self.assets, self.plan, self.inventory(), self.policy,
            version_receipt.producer_identity(
                self.policy["repository"], 99, 1, self.plan["source_sha"]
            ),
        )
        self.assertEqual(verified[0]["inputs"], receipt)
        self.assertEqual(release_provenance.REQUIRED_PAIRS, (self.pair,))

    def test_modified_sidecar_bytes_fail_before_publication(self):
        self.create()
        authenticated = self.inventory()
        original = self.sidecar.read_bytes()
        self.sidecar.write_bytes(original + b" ")
        self.assertEqual(json.loads(original), json.loads(self.sidecar.read_bytes()))
        self.assert_publication_rejected(
            "sidecar differs from authenticated inventory", authenticated
        )

    def test_noncanonical_base64_fails_before_receipt_or_publication(self):
        data = json.loads(self.sidecar.read_bytes())
        digest, encoded = next(
            (key, value) for key, value in data["blobs"].items() if value.endswith("=")
        )
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        offset = -3 if encoded.endswith("==") else -2
        index = len(encoded) + offset
        changed = (
            encoded[:index] + alphabet[alphabet.index(encoded[index]) + 1] + encoded[index + 1 :]
        )
        self.assertEqual(
            base64.b64decode(encoded, validate=True), base64.b64decode(changed, validate=True)
        )
        data["blobs"][digest] = changed
        self.sidecar.write_bytes(oci.canonical(data))
        self.assert_staging_rejected("Noncanonical or oversized provenance blob")
        self.create()
        self.assert_publication_rejected("Noncanonical or oversized provenance blob")

    def test_unreferenced_metadata_fails_before_receipt_or_publication(self):
        data = json.loads(self.sidecar.read_bytes())
        raw = b'{"unreferenced":true}'
        data["blobs"][version_receipt.sha256(raw)] = base64.b64encode(raw).decode()
        self.sidecar.write_bytes(oci.canonical(data))
        self.assert_staging_rejected("Unreferenced provenance metadata blob")
        self.create()
        self.assert_publication_rejected("Unreferenced provenance metadata blob")

    def test_changed_index_sha256_fails_before_receipt_or_publication(self):
        data = json.loads(self.sidecar.read_bytes())
        data["image"]["index_sha256"] = "0" * 64
        self.sidecar.write_bytes(oci.canonical(data))
        self.assert_staging_rejected("Detached provenance image binding mismatch")
        self.create()
        self.assert_publication_rejected("Detached provenance image binding mismatch")

    def test_staged_half_pair_fails_before_receipt_or_publication(self):
        for missing in (self.image, self.sidecar):
            with self.subTest(missing=missing.name):
                raw = missing.read_bytes()
                missing.unlink()
                try:
                    self.assert_staging_rejected("partial provenance pair")
                    self.create()
                    self.assert_publication_rejected(
                        "Authenticated inventory lacks provenance pair"
                    )
                finally:
                    missing.write_bytes(raw)
                    self.output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
