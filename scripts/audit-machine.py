#!/usr/bin/env python3
"""Inspect the actual release APKs without reading private signing material."""
import hashlib
import argparse
import json
import os
import pathlib
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
SDK = pathlib.Path(os.environ.get("ANDROID_HOME", "/opt/homebrew/share/android-commandlinetools"))
ABIS = {"arm64-v8a", "armeabi-v7a", "x86", "x86_64"}
EXPORTS = {
    "libshield.so": ["appstateshield_set_selinux_read_filter","appstateshield_overlay_own_code"],
    "libvpnstate.so": ["appstateshield_set_device_interface_filter"],
    "libdeveloperstate.so": ["appstateshield_set_selinux_property_filter",
                             "appstateshield_set_device_property_filter",
                             "appstateshield_set_device_property_handles"],
    "libselinuxstate.so": ["appstateshield_set_device_property_filter",
                          "appstateshield_set_device_property_handles"],
    "libdevicestate.so": ["Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeUpdate",
                         "Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeObjectsReady",
                         "Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeDiagnostics"],
}


def certificate(path):
    environment = dict(os.environ, JAVA_HOME="/opt/homebrew/opt/openjdk@17")
    output = subprocess.check_output(
        [str(SDK / "build-tools/36.0.0/apksigner"), "verify", "--print-certs", str(path)],
        env=environment, text=True)
    values = re.findall(r"certificate SHA-256 digest: ([0-9a-f]+)", output)
    if not values:
        raise RuntimeError("No verified APK certificate: " + path.name)
    return values


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",default="0.4.0")
    parser.add_argument("--apk-dir", type=pathlib.Path, default=OUT)
    args=parser.parse_args()
    version=args.version
    if not re.fullmatch(r"\d+\.\d+\.\d+",version):raise ValueError("Invalid version")
    nm = SDK / "ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin/llvm-nm"
    report = {}
    fixtures = []
    for path in (ROOT / "verifier/src/debug/java").rglob("*.java"):
        fixtures.append(str(path.relative_to(ROOT / "verifier/src/debug/java"))[:-5].encode())
    fixtures.append(b"io/github/lwtdzh/screenshotdetector/VivoFixtureProvider")
    for product in ["AppStateShield", "AppStateVerifier"]:
        path = args.apk_dir / (product + "-"+version+".apk")
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(dir=OUT) as temporary:
            names = archive.namelist()
            if any(name.endswith(("/libincrementalprobe.so","/libcapabilityprobe.so")) for name in names):
                raise RuntimeError("Release contains a debug native fixture")
            abis = {name.split("/")[1] for name in names if name.startswith("lib/") and name.endswith(".so")}
            if abis != ABIS:
                raise RuntimeError("Incomplete ABI set: " + product)
            dex = b"".join(archive.read(name) for name in names if re.fullmatch(r"classes\d*\.dex", name))
            if not dex or any(fixture in dex for fixture in fixtures):
                raise RuntimeError("Release contains a debug fixture or no dex: " + product)
            checks = 0
            if product == "AppStateShield":
                if tuple(map(int, version.split("."))) >= (0, 4, 11):
                    if "assets/native_init" in names:
                        raise RuntimeError("Release still registers native libraries eagerly")
                    for name in names:
                        if re.fullmatch(r"classes\d*\.dex", name):
                            local_dex = pathlib.Path(temporary) / name
                            local_dex.write_bytes(archive.read(name))
                            definitions = subprocess.check_output(
                                [str(SDK / "build-tools/36.0.0/dexdump"), str(local_dex)], text=True)
                            if re.search(r"Class descriptor\s*:\s*'Lorg/matrix/vector/nativebridge/NativeAPI;'", definitions):
                                raise RuntimeError("Release contains the compileOnly NativeAPI stub")
                elif archive.read("assets/native_init").decode().splitlines() != list(EXPORTS):
                    raise RuntimeError("Unexpected native loader list")
                for abi in sorted(abis):
                    for library, extra in EXPORTS.items():
                        local = pathlib.Path(temporary) / library
                        local.write_bytes(archive.read("lib/" + abi + "/" + library))
                        output = subprocess.check_output(
                            [str(nm), "--dynamic", "--defined-only", str(local)], text=True)
                        symbols = {line.split()[-1] for line in output.splitlines() if line.split()}
                        required=extra if version=="0.4.7" else [
                            s for s in extra if s not in {"appstateshield_overlay_own_code",
                                "Java_io_github_lwtdzh_appstateshield_DeviceRuntime_nativeDiagnostics"}]
                        if library=="libdevicestate.so" and symbols & {"device_raw6","device_raw_return"}:
                            raise RuntimeError("Raw broker helper was exported")
                        for symbol in ["native_init", "JNI_OnLoad"] + required:
                            if symbol not in symbols:
                                raise RuntimeError("Missing native export: " + abi + "/" + library + "/" + symbol)
                            checks += 1
        old = OUT / (product + "-0.3.1.apk")
        if certificate(path) != certificate(old):
            raise RuntimeError("Signing identity changed: " + product)
        report[path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "fourABIs": sorted(abis), "OEMDebugClassesExcluded": True,
            "nativeExportChecks": checks, "signingIdentityPreserved": True,
        }
    for name in ["app/build/reports/lint-results-release.xml",
                 "verifier/build/reports/lint-results-primaryRelease.xml"]:
        issues = ET.parse(ROOT / name).getroot().findall("issue")
        errors = sum(issue.get("severity") in {"Error", "Fatal"} for issue in issues)
        report[name] = {"errors": errors, "warnings": sum(issue.get("severity") == "Warning" for issue in issues)}
        if errors:
            raise RuntimeError("Release lint errors: " + name)
    if version=="0.4.0":report["unit"] = (OUT / "device-field-unit-0.4.0.log").read_text().strip()
    (OUT / ("machine-build-checks-"+version+".json")).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
