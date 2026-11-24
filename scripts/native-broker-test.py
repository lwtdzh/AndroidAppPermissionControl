#!/usr/bin/env python3
"""Dedicated emulator: actual seccomp broker IO and process-ownership contracts."""
import hashlib
import argparse
import json
import pathlib
import subprocess
import time
from test_device import Device

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--report", type=pathlib.Path,
                    default=ROOT / "verification/native-broker-20261119-results.json")
args = parser.parse_args()
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/xianyu-network-20261119"
NDK = pathlib.Path("/opt/homebrew/share/android-commandlinetools/ndk/29.0.14206865/toolchains/llvm/prebuilt/darwin-x86_64/bin")
assert STATE.is_dir(), "Use the retained diagnostic state directory"
d = Device()
binary = STATE / "native-broker-test"
source = ROOT / "shared/test/NativeBrokerTest.cpp"
subprocess.run([str(NDK / "aarch64-linux-android28-clang++"), "-std=c++17", "-O2",
                "-static-libstdc++", str(source), "-o", str(binary)], check=True)
remote = "/data/local/tmp/appstate-broker-" + str(time.time_ns())
d.shell("ls", "-d", "/data/local/tmp")
d.adb("push", str(binary), remote)
d.shell("chmod", "700", remote)
started = time.monotonic()
try:
    run = subprocess.run(d.prefix + ["shell", remote], capture_output=True, text=True, timeout=30)
    print(run.stdout + run.stderr, flush=True)
    assert run.returncode == 0, "Broker runtime contracts failed"
finally:
    # Stop only our own executable if a timeout left it running.
    for line in d.shell("ps", "-A", "-o", "PID,NAME").splitlines()[1:]:
        words = line.split()
        if len(words) == 2 and words[1] == pathlib.PurePosixPath(remote).name:
            d.shell("kill", "-TERM", words[0])
    d.shell("rm", "-f", remote)
report = {"passed": True, "seconds": round(time.monotonic()-started, 3),
          "serial": "emulator-5584", "abi": d.shell("getprop", "ro.product.cpu.abi"),
          "contracts": ["raw-copy-valid-and-EFAULT", "readv", "preadv", "worker-ownership",
                        "fork-child-real-bytes", "dup-offset-and-EOF", "EBADF",
                        "ordinary-pipe", "reused-FD-selected",
                        "broker-backtrace-signal-isolation",
                        "caller-backtrace-signal-preserved", "disable-real-bytes"],
          "fixture": "standalone seccomp broker using production header, not OEM runtime",
          "sourceSHA256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in [source, ROOT/"app/src/main/cpp/device-syscall-view.h",
                                     ROOT/"app/src/main/cpp/device-raw-io.h"]},
          "temporaryExecutableRemoved": True}
args.report.write_text(
    json.dumps(report, indent=2) + "\n")
