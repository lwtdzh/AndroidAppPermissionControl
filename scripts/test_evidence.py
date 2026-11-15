#!/usr/bin/env python3
"""Preserve case provenance; cross-APK reuse requires pinned sources and integration."""
import hashlib
import json
import pathlib
import zipfile
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Only UI code can be excluded from a runtime comparison. All hooks, readers,
# schema, manifests, native sources and build inputs remain mandatory.
UI_FILES = {
    "app/src/main/java/io/github/lwtdzh/appstateshield/SettingsActivity.java",
    "app/src/main/java/io/github/lwtdzh/appstateshield/DeviceSettingsActivity.java",
}
CURRENT_ONLY = {"D00-capture", "D18-restored", "D18-installed-hashes", "L00-capture", "L01-prepare"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload(path):
    with zipfile.ZipFile(path) as archive:
        value = hashlib.sha256()
        for name in sorted(archive.namelist()):
            if name.startswith("META-INF/") and name.endswith((".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")):
                continue
            value.update(name.encode() + b"\0")
            value.update(hashlib.sha256(archive.read(name)).digest())
        return value.hexdigest()


def source_inputs():
    files = set()
    for folder in ["app/src", "verifier/src", "shared", "gradle"]:
        files.update(p for p in (ROOT / folder).rglob("*") if p.is_file())
    files.update(ROOT / p for p in ["app/build.gradle", "verifier/build.gradle", "build.gradle",
        "settings.gradle", "gradle.properties", "gradlew", "scripts/build-all.sh",
        "scripts/machine-test.py", "scripts/selinux-test.py", "scripts/test_device.py",
        "scripts/test_evidence.py", "scripts/requirement-ui-test.py", "scripts/location-ui-test.py"])
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}


def capture_build():
    """Called only after Gradle succeeds, before subsequent source edits."""
    products = {
        "AppStateShield": ROOT / "app/build/outputs/apk/release/app-release-unsigned.apk",
        "AppStateVerifier": ROOT / "verifier/build/outputs/apk/primary/release/verifier-primary-release-unsigned.apk",
    }
    for folder, product in [("sampleA", "Verifier-A"), ("sampleB", "Verifier-B")]:
        directory = ROOT / "verifier/build/outputs/apk" / folder / "debug"
        metadata = json.loads((directory / "output-metadata.json").read_text())
        products[product] = directory / metadata["elements"][0]["outputFile"]
    snapshot = {"files": source_inputs(), "apkPayloads": {k: payload(v) for k, v in products.items()}}
    path = ROOT / "verification/build-inputs.json"
    path.write_text(json.dumps(snapshot, indent=2) + "\n")


def case_inputs(device, artifacts):
    """Bind new observations to a build snapshot only when source and APK agree."""
    path = ROOT / "verification/build-inputs.json"
    if not path.exists():
        return {}
    snapshot = json.loads(path.read_text())
    if snapshot["files"] != source_inputs():
        return {}
    for product, expected in snapshot["apkPayloads"].items():
        name = next((n for n in artifacts if n.startswith(product + "-")), None)
        if name is None and product in {"Verifier-A", "Verifier-B"}:
            continue
        if not name or payload(ROOT / "verification" / name) != expected:
            return {}
    return {"buildInputsSHA256": sha(path), "apkPayloads": snapshot["apkPayloads"],
        "environment": {"fingerprint": device.shell("getprop", "ro.build.fingerprint"),
            "abi": device.shell("getprop", "ro.product.cpu.abi"),
            "vectorModuleSHA256": device.shell("sha256sum",
                "/data/adb/modules/zygisk_vector/module.prop").split()[0]}}


def capture_integration():
    path = ROOT / "verification/machine-0.4.0-results.json"
    report = json.loads(path.read_text())
    keys = ["D03-xiaomi-smoke", "D05-imei-live", "D06-fieldoff-masteroff"]
    rows = [report["cases"][key] for key in keys]
    if any(r.get("status") != "passed" or r.get("artifacts") != report["artifacts"] or
           not r.get("buildInputsSHA256") for r in rows):
        raise RuntimeError("Fresh enabled/update/disable integration evidence is missing")
    common = ("buildInputsSHA256", "environment", "apkPayloads")
    if any(r[k] != rows[0][k] for r in rows for k in common):
        raise RuntimeError("Integration build/environment changed")
    retained = ROOT / "verification" / ("integration-observations-" + sha(path)[:16] + ".json")
    if not retained.exists():
        retained.write_bytes(path.read_bytes())
    baseline_path = ROOT / "verification/selinux-0.4.0-results.json"
    baselines = json.loads(baseline_path.read_text())
    baseline = baselines["cases"]["D17-uninjected-permissive"]
    if (baseline.get("status") != "passed" or baseline.get("buildInputsSHA256") != rows[0]["buildInputsSHA256"] or
            any(baseline.get("artifacts", {}).get(n) != h for n,h in baselines["artifacts"].items()) or
            any(report["artifacts"].get(n) != h for n,h in baselines["artifacts"].items())):
        raise RuntimeError("Fresh real VPN/USB/SELinux baseline is required")
    retained_baseline = ROOT / "verification" / ("integration-baselines-" + sha(baseline_path)[:16] + ".json")
    if not retained_baseline.exists():
        retained_baseline.write_bytes(baseline_path.read_bytes())
    snapshot = {"artifacts": report["artifacts"], "enabledUpdatedDisabled": True,
                "report": str(retained.relative_to(ROOT)), "reportSHA256": sha(retained),
                "baselineReport": str(retained_baseline.relative_to(ROOT)),
                "baselineReportSHA256": sha(retained_baseline),
                "cases": keys, **{k: rows[0][k] for k in common}}
    (ROOT / "verification/reuse-integration.json").write_text(json.dumps(snapshot, indent=2) + "\n")


def local(path):
    value = (ROOT / path).resolve()
    if not value.is_relative_to(ROOT / "verification"):
        raise RuntimeError("Reuse evidence must be retained under verification/")
    return value


def accepted(report_path, key, current):
    """Return original row and attribution; never rewrite its APK hashes."""
    report = json.loads(report_path.read_text())
    row = report["cases"].get(key, {})
    if row.get("status") == "passed" and row.get("artifacts") == current:
        return row, "本次 APK 的实际验证"
    proof = report.get("reuse", {}).get(key)
    if key in CURRENT_ONLY or not proof:
        raise RuntimeError("Missing current/reviewed evidence: " + key)
    if proof["currentArtifacts"] != current or not proof.get("reason") or not proof.get("reviewedBy"):
        raise RuntimeError("Incomplete reuse review: " + key)
    original_path = local(proof["originalReport"])
    if sha(original_path) != proof["originalReportSHA256"]:
        raise RuntimeError("Original report changed: " + key)
    original = json.loads(original_path.read_text())["cases"][key]
    if original.get("status") != "passed" or original.get("artifacts") != proof["originalArtifacts"]:
        raise RuntimeError("Original passing case/artifacts differ: " + key)
    old_path, new_path = [local(proof[k]) for k in ["originalInputs", "currentInputs"]]
    if sha(old_path) != original.get("buildInputsSHA256") or sha(new_path) != proof["currentInputsSHA256"]:
        raise RuntimeError("Case lacks a build-time source snapshot: " + key)
    old, new = [json.loads(p.read_text()) for p in [old_path, new_path]]
    # Old evidence is linked to an actual build, not a later reconstruction.
    if original.get("apkPayloads") != old["apkPayloads"]:
        raise RuntimeError("Original case/build payload link is missing: " + key)
    if new["files"] != source_inputs():
        raise RuntimeError("Current worktree differs from reviewed build inputs")
    excluded = UI_FILES if proof["scope"] == "runtime-with-unchanged-settings-contract" else set()
    if proof["scope"] not in {"all-build-inputs", "runtime-with-unchanged-settings-contract"}:
        raise RuntimeError("Unsupported reuse scope")
    if excluded and not proof.get("settingsContractReview"):
        raise RuntimeError("UI changes need an explicit persistence-contract review")
    changed = {p for p in set(old["files"]) | set(new["files"])
               if old["files"].get(p) != new["files"].get(p)}
    if changed - excluded or sorted(changed) != sorted(proof["changedFiles"]):
        raise RuntimeError("Hooks/readers/schema/assertions changed: " + key)
    if excluded and not (key.startswith("M6-") or key.startswith("L13-native-")):
        raise RuntimeError("This case cannot exclude UI inputs: " + key)
    integration_path = local(proof["currentIntegration"])
    if sha(integration_path) != proof["currentIntegrationSHA256"]:
        raise RuntimeError("Current integration proof changed")
    integration = json.loads(integration_path.read_text())
    if (any(integration["artifacts"].get(n) != h for n,h in current.items()) or
            integration.get("enabledUpdatedDisabled") is not True or
            integration["environment"] != original.get("environment") or
            integration["apkPayloads"] != new["apkPayloads"]):
        raise RuntimeError("Current integration/environment does not support reuse: " + key)
    live_path = local(integration["report"])
    if sha(live_path) != integration["reportSHA256"]:
        raise RuntimeError("Current integration observations changed")
    live = json.loads(live_path.read_text())
    for case in ["D03-xiaomi-smoke", "D05-imei-live", "D06-fieldoff-masteroff"]:
        observed = live["cases"][case]
        # A regression report contains only the two release artifacts.
        if (observed.get("status") != "passed" or
            any(observed.get("artifacts", {}).get(n) != h for n,h in current.items()) or
            observed.get("environment") != integration["environment"] or
            observed.get("buildInputsSHA256") != proof["currentInputsSHA256"]):
            raise RuntimeError("Integration case is not a fresh observation: " + case)
    baseline_path = local(integration["baselineReport"])
    if sha(baseline_path) != integration["baselineReportSHA256"]:
        raise RuntimeError("Fresh real-baseline observations changed")
    baseline = json.loads(baseline_path.read_text())["cases"]["D17-uninjected-permissive"]
    if (baseline.get("status") != "passed" or baseline.get("buildInputsSHA256") != proof["currentInputsSHA256"] or
            any(baseline.get("artifacts", {}).get(n) != h for n,h in current.items()
                if n.startswith(("AppStateShield-", "AppStateVerifier-"))) or
            baseline.get("environment") != integration["environment"] or
            baseline["evidence"]["module"]["injected"] is not False or
            baseline["evidence"]["tunByName"] is not True or
            baseline["evidence"]["developer"] != 1 or baseline["evidence"]["debug"] != 1):
        raise RuntimeError("Current real VPN/USB/SELinux baseline is missing")
    for product, expected in new["apkPayloads"].items():
        name = next((n for n in current if n.startswith(product + "-")), None)
        if name is None:
            continue  # SELinux report binds only the two release APKs.
        if sha(ROOT / "verification" / name) != current[name] or payload(ROOT / "verification" / name) != expected:
            raise RuntimeError("Reviewed inputs do not match delivered APK: " + key)
    return original, "复用已有验证：" + proof["originalReport"] + "（" + proof["reason"] + "）"


if __name__ == "__main__":
    capture_integration() if "--integration" in sys.argv else capture_build()
