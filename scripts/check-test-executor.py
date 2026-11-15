#!/usr/bin/env python3
"""Offline checks for preservation and cross-APK evidence admission, no device calls."""
import copy
import json
import pathlib
import tempfile
import unittest
import unittest.mock as mock
import xml.etree.ElementTree as ET
import zipfile
import test_evidence as evidence
from test_device import METHODS, PRIMARY, policy_fixture, profile_fixture


class Admission(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=evidence.ROOT / "verification")
        self.root = pathlib.Path(self.temporary.name)
        self.out = self.root / "verification"
        self.out.mkdir()
        self.ui = sorted(evidence.UI_FILES)[0]
        self.old_files = {"app/src/main/cpp/hook.cpp": "hook", self.ui: "old UI"}
        self.new_files = dict(self.old_files, **{self.ui: "new UI"})
        self.artifacts = {}
        payloads = {}
        for product in ["AppStateShield", "AppStateVerifier"]:
            path = self.out / (product + "-0.4.0.apk")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("classes.dex", b"synthetic-validator-fixture")
            self.artifacts[path.name] = evidence.sha(path)
            payloads[product] = evidence.payload(path)
        self.old = self.write("old-inputs.json", {"files": self.old_files, "apkPayloads": {"old": "payload"}})
        self.new = self.write("new-inputs.json", {"files": self.new_files, "apkPayloads": payloads})
        self.environment = {"fingerprint": "synthetic-platform", "abi": "arm64-v8a", "vector": "fixture"}
        self.original = {"status": "passed", "artifacts": {"old-apk": "old-sha"},
            "buildInputsSHA256": evidence.sha(self.old), "apkPayloads": {"old": "payload"},
            "environment": self.environment, "evidence": {"fixture": True}}
        self.original_report = self.write("original.json", {"cases": {"M6-000111": self.original}})
        current_row = {"status": "passed", "artifacts": self.artifacts,
            "buildInputsSHA256": evidence.sha(self.new), "environment": self.environment}
        observations = self.write("observations.json", {"cases": {
            k: current_row for k in ["D03-xiaomi-smoke", "D05-imei-live", "D06-fieldoff-masteroff"]}})
        baseline_row = dict(current_row, evidence={
            "module": {"injected": False}, "tunByName": True, "developer": 1, "debug": 1})
        baseline = self.write("baseline.json", {"cases": {"D17-uninjected-permissive": baseline_row}})
        self.integration_data = {"artifacts": self.artifacts, "environment": self.environment,
            "apkPayloads": payloads, "enabledUpdatedDisabled": True,
            "report": "verification/observations.json", "reportSHA256": evidence.sha(observations),
            "baselineReport": "verification/baseline.json", "baselineReportSHA256": evidence.sha(baseline)}
        self.integration = self.write("integration.json", self.integration_data)
        self.proof = {"currentArtifacts": self.artifacts, "originalArtifacts": self.original["artifacts"],
            "reason": "Only settings UI changed; persisted contract was reviewed", "reviewedBy": "offline-test",
            "scope": "runtime-with-unchanged-settings-contract", "settingsContractReview": "unchanged fixture schema",
            "changedFiles": [self.ui], "originalReport": "verification/original.json",
            "originalReportSHA256": evidence.sha(self.original_report),
            "originalInputs": "verification/old-inputs.json", "currentInputs": "verification/new-inputs.json",
            "currentInputsSHA256": evidence.sha(self.new),
            "currentIntegration": "verification/integration.json", "currentIntegrationSHA256": evidence.sha(self.integration)}
        self.patch_root = mock.patch.object(evidence, "ROOT", self.root)
        self.patch_sources = mock.patch.object(evidence, "source_inputs", lambda: self.new_files)
        self.patch_root.start()
        self.patch_sources.start()

    def tearDown(self):
        self.patch_sources.stop()
        self.patch_root.stop()
        self.temporary.cleanup()

    def write(self, name, data):
        path = self.out / name
        path.write_text(json.dumps(data))
        return path

    def admit(self):
        report = self.write("current.json", {"cases": {}, "reuse": {"M6-000111": self.proof}})
        return evidence.accepted(report, "M6-000111", self.artifacts)

    def test_reviewed_ui_reuse_preserves_original_provenance(self):
        before = self.original_report.read_bytes()
        row, label = self.admit()
        self.assertEqual(row, self.original)
        self.assertIn("复用已有验证", label)
        self.assertEqual(self.original_report.read_bytes(), before)
        self.assertNotEqual(row["artifacts"], self.artifacts)

    def test_hook_change_rejected(self):
        changed = copy.deepcopy(self.new_files)
        changed["app/src/main/cpp/hook.cpp"] = "changed hook"
        self.new_files.update(changed)
        data = json.loads(self.new.read_text())
        data["files"] = changed
        self.write(self.new.name, data)
        self.proof["currentInputsSHA256"] = evidence.sha(self.new)
        self.proof["changedFiles"].append("app/src/main/cpp/hook.cpp")
        with self.assertRaisesRegex(RuntimeError, "Hooks/readers/schema/assertions changed"):
            self.admit()

    def test_missing_build_time_binding_rejected(self):
        del self.original["buildInputsSHA256"]
        self.write(self.original_report.name, {"cases": {"M6-000111": self.original}})
        self.proof["originalReportSHA256"] = evidence.sha(self.original_report)
        with self.assertRaisesRegex(RuntimeError, "build-time source snapshot"):
            self.admit()

    def test_changed_environment_rejected(self):
        self.integration_data["environment"] = {"abi": "x86_64"}
        self.write(self.integration.name, self.integration_data)
        self.proof["currentIntegrationSHA256"] = evidence.sha(self.integration)
        with self.assertRaisesRegex(RuntimeError, "integration/environment"):
            self.admit()

    def test_changed_baseline_rejected(self):
        self.write("baseline.json", {"cases": {}})
        with self.assertRaisesRegex(RuntimeError, "real-baseline observations changed"):
            self.admit()


class Preservation(unittest.TestCase):
    def test_unknown_methods_and_other_apps_survive(self):
        tree = ET.fromstring("<map><string name='apps'>{}</string><int name='unknown' value='17'/></map>")
        apps = {PRIMARY: ["future_hidden", "vpn"], "other.app": ["debug"]}
        tree.find("string").text = json.dumps(apps)
        policy_fixture(tree, PRIMARY, {"vpn"})
        saved = json.loads(tree.find("string").text)
        self.assertEqual(saved["other.app"], apps["other.app"])
        self.assertEqual(set(saved[PRIMARY]), {"future_hidden"} | (set(METHODS) - {"vpn"}))
        self.assertEqual(tree.find("int").get("value"), "17")

    def test_values_unknown_keys_and_revision_survive(self):
        tree = ET.fromstring("<map><string name='other.app'>untouched</string></map>")
        profile = {"enabled": True, "revision": 1, "values": {"imei": "490154203237518"},
                   "selected": ["imei"], "unknown": "keep"}
        first = profile_fixture(tree, PRIMARY, profile)
        second = profile_fixture(tree, PRIMARY, dict(first, selected=[]))
        self.assertGreater(second["revision"], first["revision"])
        self.assertEqual(second["values"], profile["values"])
        self.assertEqual(second["unknown"], "keep")
        self.assertEqual(tree.find("string").text, "untouched")
        self.assertEqual(profile["revision"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
