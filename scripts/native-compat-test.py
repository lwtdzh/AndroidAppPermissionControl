#!/usr/bin/env python3
"""专用模拟器：加载正式 APK 原生库，复现本地 ART 符号校验及原生入口兼容性。"""
import hashlib
import json
import pathlib
import subprocess
import time
import zipfile
from test_device import Device

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/bank-codeview-20261119"
NDK = pathlib.Path("/opt/homebrew/share/android-commandlinetools/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin")
STATE.mkdir(mode=0o700, exist_ok=True)
d = Device()
compiler = str(NDK / "aarch64-linux-android28-clang++")
commands = [
    (["shared/test/CompatVectorFixture.cpp"], "libcompatvector.so", ["-shared", "-fPIC"]),
    (["shared/test/CompatArtFixture.cpp"], "libart.so", ["-shared", "-fPIC"]),
    (["shared/test/NativeCompatTest.cpp"], "native-compat-test", ["-ldl"]),
    (["shared/test/EntryHookTest.cpp"], "entry-hook-test", ["-ldl"]),
]
for sources, name, flags in commands:
    subprocess.run([compiler, "-std=c++17", "-static-libstdc++", "-O0", "-g", *[str(ROOT / s) for s in sources],
                    *flags, "-o", str(STATE / name)], check=True)
apk = ROOT / "app/build/outputs/apk/release/app-release-unsigned.apk"
with zipfile.ZipFile(apk) as archive:
    library = archive.read("lib/arm64-v8a/libnativecompat.so")
(STATE / "libnativecompat.so").write_bytes(library)
remote = "/data/local/tmp/appstate-nativecompat-" + str(time.time_ns())
d.shell("ls", "-d", "/data/local/tmp")
d.shell("mkdir", remote)
rows = []
names = [c[1] for c in commands] + ["libnativecompat.so"]
try:
    for name in names:
        d.adb("push", str(STATE / name), remote + "/" + name)
        d.shell("chmod", "700", remote + "/" + name)
    for name in ("native-compat-test", "entry-hook-test"):
        started = time.monotonic()
        result = subprocess.run(d.prefix + ["shell", "LD_LIBRARY_PATH=" + remote + " " + remote + "/" + name + " " + remote],
                                capture_output=True, text=True, timeout=30)
        (STATE / (name + ".log")).write_text(result.stdout + result.stderr)
        print(result.stdout + result.stderr, flush=True)
        rows.append({"name": name, "exitCode": result.returncode,
                     "seconds": round(time.monotonic() - started, 3)})
        if result.returncode:
            raise RuntimeError(name + " failed")
finally:
    for name in names:
        d.shell("rm", "-f", remote + "/" + name)
    d.shell("rmdir", remote)
    report = {"cases": rows, "serial": "emulator-5584",
              "abi": d.shell("getprop", "ro.product.cpu.abi"), "restored": True,
              "nativecompatSHA256": hashlib.sha256(library).hexdigest(),
              "unsignedApkSHA256": hashlib.sha256(apk.read_bytes()).hexdigest(),
              "fixture": "local ART symbol + Vector-shaped redirect, not OEM ART runtime"}
    (ROOT / "verification/native-compat-20261119-results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
