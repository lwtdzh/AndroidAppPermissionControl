#!/usr/bin/env python3
"""Package pinned detector observations, final APKs and restoration evidence."""
import csv
import hashlib
import json
import pathlib
import re
import shutil
import zipfile
from test_evidence import payload, source_inputs

PROJECT = pathlib.Path(__file__).resolve().parents[1]
PRIVATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/detector-matrix-20261115"
OUTPUT = pathlib.Path.home() / "Downloads/AppStateShield-0.4.11-detector-tests"
FINAL = PRIVATE / "AppStateShield-0.4.11.apk"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def copy(source, relative):
    target = OUTPUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def main():
    build = json.loads((PROJECT / "verification/build-inputs.json").read_text())
    assert build["files"] == source_inputs(), "Sources changed after the pinned build"
    assert payload(FINAL) == build["apkPayloads"]["AppStateShield"]
    assert payload(PRIVATE / "AppStateVerifier-0.4.11.apk") == build["apkPayloads"]["AppStateVerifier"]
    audit = json.loads((PROJECT / "verification/machine-build-checks-0.4.11.json").read_text())
    for name in ("AppStateShield-0.4.11.apk", "AppStateVerifier-0.4.11.apk"):
        assert audit[name]["sha256"] == sha(PRIVATE / name)
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
    methods = json.loads((PRIVATE / "final-methods.json").read_text())
    expected = {"Enforcing-uninjected", "Permissive-uninjected",
                "Policy-UID-and-write-isolation"} | {"M6-" + format(x, "06b") for x in range(64)}
    assert expected <= methods["cases"].keys()
    assert all(methods["cases"][name]["status"] == "passed" for name in expected)
    assert methods["installed"]["io.github.lwtdzh.appstateshield"] == sha(FINAL)
    integration = json.loads((PRIVATE / "module-list-integration.json").read_text())
    assert integration["passed"] and integration["coldLoadedFinalAPK"]
    assert integration["installed"] == {
        pkg: methods["installed"][pkg] for pkg in integration["installed"]}
    assert json.loads((PRIVATE / "restoration.json").read_text())["passed"]
    for name in ("native", "ruru", "key"):
        value = json.loads((PRIVATE / "evidence/N05-final-best" / name / "result.json").read_text())
        assert not value["startupFailure"] and value["policyConfirmed"]
        assert value["moduleSHA256"] == sha(FINAL)
        if name == "ruru":
            assert value["statuses"]["Xposed Modules"] == "Not Found"
            assert value["statuses"]["Setting Props"] == "Not Found"
            assert value["statuses"]["vpn not connected"] == "Not Found"
    assert not OUTPUT.exists(), "Do not overwrite an existing deliverable"
    OUTPUT.mkdir()
    copy(FINAL, FINAL.name)
    verifier = PRIVATE / "AppStateVerifier-0.4.11.apk"
    assert methods["installed"]["io.github.lwtdzh.screenshotdetector"] == sha(verifier)
    copy(verifier, verifier.name)
    copy(PRIVATE / "AppStateShield-0.4.11-matrix.apk", "provenance/AppStateShield-0.4.11-matrix.apk")
    copy(PRIVATE / "matrix-build-inputs.json", "provenance/matrix-build-inputs.json")
    copy(PRIVATE / "AppStateShield-0.4.11-before-dlkm.apk",
         "provenance/AppStateShield-0.4.11-before-dlkm.apk")
    copy(PRIVATE / "build-inputs-before-dlkm.json", "provenance/build-inputs-before-dlkm.json")
    for name in ("AppStateShield-0.4.11-before-vpn.apk",
                 "AppStateVerifier-0.4.11-before-vpn.apk", "build-inputs-before-vpn.json",
                 "final-methods-before-vpn.json", "final-methods-preparation-before-dlkm.json"):
        copy(PRIVATE / name, "provenance/" + name)
    copy(PROJECT / "verification/build-inputs.json", "provenance/final-build-inputs.json")
    copy(PROJECT / "verification/DETECTOR-0.4.11-REPORT.md", "verification/DETECTOR-0.4.11-REPORT.md")
    copy(PROJECT / "verification/machine-build-checks-0.4.11.json",
         "verification/machine-build-checks-0.4.11.json")
    for name in ("DETECTOR-LIMITATIONS-0.4.11.md", "TEST-MANUAL.md",
                 "ARCHITECTURE.md", "TEST-EXECUTION-POLICY.md"):
        copy(PROJECT / "docs" / name, "docs/" + name)
    rows = []
    controls = {"setup-empty-module", "setup-attach-only", "setup-attach-callback",
                "stock-control", "stock-clean", "D02-no-native-registry",
                "D03-no-native-libraries", "D05-key-provider-running"}
    for folder in sorted((PRIVATE / "evidence").iterdir()):
        selected = bool(re.match(r"^[HJKLN]\d", folder.name)) and folder.name != "N00-incomplete-capture"
        incomplete = folder.name == "N00-incomplete-capture"
        if not (selected or incomplete or folder.name in controls or folder.name.startswith("D04-registry-")):
            continue
        for file in folder.rglob("*"):
            if file.is_file():
                copy(file, "evidence/" + str(file.relative_to(PRIVATE / "evidence")))
        for path in sorted(folder.glob("*/result.json")):
            value = json.loads(path.read_text())
            configuration = value.get("configuration") or {}
            profile = configuration.get("profile") or {}
            logs = "\n".join(value.get("injectionLog", []))
            # Older samples keep their original JSON. Derived checks live here only.
            match = re.findall(r"Policy loaded=(true|false) enabled=\[([^]]*)\]", logs)
            loaded = bool(match and match[-1][0] == "true")
            native = [line for line in value.get("texts", [])
                      if re.search(r"detected|Found Injection|abnormal|Experimental Detections:|Custom ROM Detections:",
                                   line, re.I)]
            root_of_trust = [line for line in value.get("texts", []) if "verifiedBootKey:" in line]
            rows.append({
                "case": folder.name, "detector": path.parent.name,
                "evidenceRole": "matrix" if selected else "diagnostic-control",
                "scope": configuration.get("scope"),
                "methods": ",".join(configuration.get("methods", [])),
                "profileEnabled": profile.get("enabled", False),
                "modelEnabled": profile.get("modelEnabled", False),
                "profileSelected": ",".join(profile.get("selected", [])),
                "startupFailure": value.get("startupFailure", not bool(value.get("pid"))),
                "policyLoadedDerived": loaded, "nativeReady": value.get("nativeReadyLog", []),
                "nativeFindings": native, "ruruStatuses": value.get("statuses", {}),
                "keyRootOfTrust": root_of_trust,
                "keyWarnings": [text for text in value.get("texts", []) if text in {
                    "Unknown root certificate", "Bootloader is unlocked",
                    "This device does not support hardware-level key attestation.",
                    "Unable to attest device IDs", "Unable to attest"}],
                "keySecurity": [text for text in value.get("texts", []) if "Security level:" in text],
                "freshKeyReset": value.get("freshKeyReset"),
                "moduleSHA256": value.get("moduleSHA256"),
                "startedAtUTC": value.get("startedAtUTC"),
                "durationSeconds": value.get("durationSeconds"),
                "evidence": "evidence/" + str(path.relative_to(PRIVATE / "evidence")),
            })
    assert sum(row["case"].startswith("H") for row in rows) == 48
    assert sum(row["case"] == "K01-final-best-default-detectors" for row in rows) == 3
    assert sum(row["case"] == "L04-final-best-default" for row in rows) == 3
    assert sum(row["case"] == "N05-final-best" for row in rows) == 3
    assert sum(row["case"] == "N06-final-best-expanded" for row in rows) == 1
    (OUTPUT / "matrix.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    with (OUTPUT / "matrix.csv").open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list))
                             else value for key, value in row.items()})
    sources = [json.loads(p.read_text()) for p in sorted((PRIVATE / "assets").glob("*.source.json"))]
    (OUTPUT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "moduleSHA256": sha(FINAL),
        "verifierSHA256": sha(verifier),
        "mainMatrix": {"configurations": 16, "detectors": 3, "observations": 48},
        "finalSixMethodCases": len(expected),
        "thirdPartyObservationsByPhase": {
            phase: sum(row["case"].startswith(phase) and row["evidenceRole"] == "matrix" for row in rows)
            for phase in ("H", "J", "K", "L", "N")},
        "allSixMethodCasesPassed": True,
        "originalEmulatorRestored": True,
        "runtime": {"android": 16, "api": 36, "abi": "arm64-v8a", "physicalPhoneUsed": False},
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    for name in ("final-methods.json", "module-list-integration.json", "restoration.json",
                 "module-list-ui-saved.json", "module-list-ui-edit.xml", "module-list-ui-edit.png",
                 "native-expanded-settings.xml", "native-expanded-settings.png",
                 "key-device-props-option.xml", "key-device-props-option.png",
                 "key-device-props-capability.json", "native-custom-rom-details.xml",
                 "native-custom-rom-details.png", "module-list-integration-before-dlkm.json",
                 "native-injection-details.json", "native-injection-details.xml",
                 "native-injection-details.png", "module-list-integration-before-vpn.json",
                 "native-injection-mapped-libraries.json"):
        if (PRIVATE / name).exists():
            copy(PRIVATE / name, name)
    for file in (PROJECT / "verification").glob("detector-*.log"):
        if any(word in file.name for word in ("final-", "expanded-", "module-restoration", "field-unit",
                                              "root-environment", "root-features")):
            copy(file, "verification/" + file.name)
    copy(PROJECT / "verification/build-0.4.11-module-list.log",
         "verification/build-0.4.11-module-list.log")
    copy(PROJECT / "verification/build-0.4.11-dlkm.log", "verification/build-0.4.11-dlkm.log")
    copy(PROJECT / "verification/build-0.4.11-vpn-info.log", "verification/build-0.4.11-vpn-info.log")
    for file in (PROJECT / "verification").glob("final-*-0.4.11*.log"):
        copy(file, "verification/" + file.name)
    copy(PRIVATE / "ruru-mainactivity.smali", "controls/ruru-mainactivity.smali")
    copy(PRIVATE / "native-source/sources/com/reveny/nativecheck/app/Native.java",
         "controls/native-detector-Native.java")
    for file in (PRIVATE / "empty-control").glob("*.java"):
        copy(file, "controls/" + file.name)
    for name in ("AndroidManifest.xml", "module-variants.py"):
        copy(PRIVATE / "empty-control" / name, "controls/" + name)
    for name in ("verify-module-list.py", "verify-module-restoration.py",
                 "verify-expanded-detectors.py", "verify-final-methods.py",
                 "verify-dlkm-detectors.py", "verify-final-module-list.py",
                 "verify-injection-details.py", "restore-original-avd.py",
                 "verify-vpn-detectors.py", "verify-final-package-lists.py"):
        copy(PRIVATE / name, "executors/" + name)
    for name in ("test_device.py", "detector-matrix.py", "selinux-test.py", "test_evidence.py",
                 "audit-machine.py", "package-detector-report.py"):
        copy(PROJECT / "scripts" / name, "source/scripts/" + name)
    for name in ("ModuleListHooks.java", "NativeLibraries.java", "PolicyVisibility.java",
                 "PolicyVisibilityReceiver.java", "PolicyProvider.java", "DeviceRuntime.java",
                 "DeviceStore.java", "PolicyStore.java", "DeviceHooks.java", "AttestationHooks.java"):
        copy(PROJECT / "app/src/main/java/io/github/lwtdzh/appstateshield" / name,
             "source/app/src/main/java/io/github/lwtdzh/appstateshield/" + name)
    copy(PROJECT / "verifier/src/main/java/io/github/lwtdzh/screenshotdetector/ModuleListProbe.java",
         "source/verifier/src/main/java/io/github/lwtdzh/screenshotdetector/ModuleListProbe.java")
    for relative in (
        "app/src/main/java/io/github/lwtdzh/vpnstateshield/VpnModule.java",
        "verifier/src/main/java/io/github/lwtdzh/devicestateprobe/SelinuxProbe.java",
        "shared/java/io/github/lwtdzh/deviceprofile/DeviceField.java",
        "shared/java/io/github/lwtdzh/deviceprofile/AttestationPrivacy.java",
        "app/src/vectorApiStub/java/org/matrix/vector/nativebridge/NativeAPI.java",
    ):
        copy(PROJECT / relative, "source/" + relative)
    (OUTPUT / "README.md").write_text(
        "# AppStateShield 0.4.11 环境检测交付包\n\n"
        "先读 [实测报告](verification/DETECTOR-0.4.11-REPORT.md)，"
        "再读 [尚未解决的逐项原因](docs/DETECTOR-LIMITATIONS-0.4.11.md)。\n\n"
        "根目录两个 APK 为最终签名产物。provenance 下 matrix APK 对应 H，before-dlkm APK 对应 J/K，"
        "before-vpn APK 对应 L，最终 APK 对应 N；分别记录哈希，不能互换结果。matrix.csv / matrix.json 对应原始 evidence 中的"
        "截图、XML、配置和日志。diagnostic-control 行包含故障及隔离试验，不是最终通过记录。\n\n"
        "final-methods.json 是最终 APK 的 64 组合、两种真实 SELinux 基线和 UID/写入隔离检查；"
        "module-list-integration.json 是最终 APK 冷启动后的五项查询/同 PID 恢复；"
        "UI 操作复用来源固定在 L，相关设置/存储/过滤源码哈希均相同。"
        "provenance/final-methods-before-vpn.json 是被新 VPN 修复中断的旧运行，未作为最终通过记录。"
        "restoration.json 记录完整 AVD 恢复。\n\n"
        "本次只验证专用模拟器的 ARM64 / Android 16，没有进行真机测试。执行器源码供审查，"
        "运行依赖专用测试环境；source 是与本次修复有关的部分文件，不是独立可构建的项目。\n",
        encoding="utf-8")
    hashes = {str(p.relative_to(OUTPUT)): sha(p) for p in sorted(OUTPUT.rglob("*")) if p.is_file()}
    (OUTPUT / "SHA256SUMS.txt").write_text("".join(h + "  " + p + "\n" for p, h in hashes.items()))
    zip_path = OUTPUT.with_name(OUTPUT.name + ".zip")
    assert not zip_path.exists()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for p in sorted(OUTPUT.rglob("*")):
            if p.is_file():
                archive.write(p, str(p.relative_to(OUTPUT.parent)))
    assert all(sha(OUTPUT / p) == h for p, h in hashes.items())
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
    print(json.dumps({"directory": str(OUTPUT), "archive": str(zip_path),
                      "archiveSHA256": sha(zip_path), "files": len(hashes) + 1,
                      "matrixRows": len(rows)}, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
