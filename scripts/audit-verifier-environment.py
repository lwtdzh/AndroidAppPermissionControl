#!/usr/bin/env python3
"""Audit the two final 0.4.12 APKs against the signed 0.4.11 detector artifacts."""
import hashlib
import json
import os
import pathlib
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OLD = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/detector-matrix-20261115"
SDK = pathlib.Path("/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0")
ENV = dict(os.environ, JAVA_HOME="/opt/homebrew/opt/openjdk@17")
ABIS = {"arm64-v8a", "armeabi-v7a", "x86_64", "x86"}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def libraries(apk):
    return {n: digest(apk.read(n)) for n in apk.namelist() if n.startswith("lib/") and n.endswith(".so")}


def signer(path):
    text = subprocess.check_output([str(SDK / "apksigner"), "verify", "--print-certs", str(path)], env=ENV, text=True)
    return next(line for line in text.splitlines() if "certificate SHA-256 digest:" in line)


out = {}
certificates = []
for product, code in (("AppStateShield", 22), ("AppStateVerifier", 18)):
    path = ROOT / "verification" / (product + "-0.4.12.apk")
    prior = OLD / (product + "-0.4.11.apk")
    current = zipfile.ZipFile(path)
    old = zipfile.ZipFile(prior)
    libs, previous = libraries(current), libraries(old)
    assert {n.split("/")[1] for n in libs} == ABIS
    assert all(libs.get(name) == value for name, value in previous.items()), "Existing native libraries changed"
    certificate = signer(path)
    certificates.append(certificate)
    assert signer(prior) == certificate, "Signing identity changed"
    badging = subprocess.check_output([str(SDK / "aapt"), "dump", "badging", str(path)], text=True)
    package = next(line for line in badging.splitlines() if line.startswith("package:"))
    assert "versionName='0.4.12'" in package and ("versionCode='" + str(code) + "'") in package
    if product == "AppStateShield":
        assert libs == previous and "assets/native_init" not in current.namelist()
    else:
        assert all("lib/" + abi + "/libenvironmentprobe.so" in libs for abi in ABIS)
        assert not any("incrementalprobe" in n or "capabilityprobe" in n for n in current.namelist())
        dex = b"".join(current.read(n) for n in current.namelist() if n.endswith(".dex"))
        for fixture in (b"Landroid/telephony/VivoTelephonyManager;", b"Lcom/bun/miitmdid/core/MdidSdkHelper;"):
            assert fixture not in dex
        pins = json.loads(current.read("assets/attestation-trust-anchors.json"))
        assert len(pins["anchors"]) == 2 and pins["checkedAt"] == "2026-11-15"
    out[product] = {"sha256": digest(path.read_bytes()), "package": package, "nativeLibraries": libs,
        "signingIdentityPreserved": True, "existingNativePayloadsIdenticalTo0411": True,
        "debugFixturesExcluded": True}
assert certificates[0] == certificates[1]
(ROOT / "verification/verifier-environment-0.4.12-artifacts.json").write_text(json.dumps(out, indent=2) + "\n")
print("PASS final package/version/signature/four-ABI audit; existing native payloads unchanged")
