#!/usr/bin/env python3
"""Finalize an already-running test chain after its process exits, without polling."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import pathlib
import select
import subprocess
import sys
from test_evidence import accepted

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"


def check(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-pid", type=int)
    args = parser.parse_args()
    if args.after_pid is not None:
        check(args.after_pid > 1, "Invalid completion process")
        queue = select.kqueue()
        try:
            try:
                queue.control([select.kevent(args.after_pid, filter=select.KQ_FILTER_PROC,
                    flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT, fflags=select.KQ_NOTE_EXIT)], 0)
            except ProcessLookupError:
                pass  # An already-finished chain is still checked against all evidence below.
            else:
                print("Waiting for the existing test process to exit", flush=True)
                queue.control(None, 1)
        finally:
            queue.close()
    spec = importlib.util.spec_from_file_location("machine_test", ROOT / "scripts/machine-test.py")
    machine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(machine)
    run = machine.Run()
    report = run.report
    regression = json.loads((OUT / "selinux-0.4.0-results.json").read_text())
    for key in ["D16-D17-legacy-regression", "D16-actual-system-screenshot",
                "D08-native-callback-ownership", "D15-two-second-foreground"]:
        accepted(OUT / "machine-0.4.0-results.json", key, report["artifacts"])
    for i in range(64):
        accepted(OUT / "selinux-0.4.0-results.json", "M6-" + format(i, "06b"), regression["artifacts"])
    run.final_checks()
    d = run.d
    check(not d.shell("sh", "-c", "test ! -e /data/user/0/" + machine.B +
          "/files/fixture-clipboard.bin || echo present"), "Clipboard backup was not restored")
    run.open_editor()
    d.find("device-preset")
    d.screenshot(str(OUT / "machine-editor-0.4.0.png"))
    d.tap(run.find_edit("imei"))
    d.find("device-input:imei")
    d.screenshot(str(OUT / "machine-imei-editor-0.4.0.png"))
    d.click("取消", "text")
    run.read()
    d.find("machine-summary")
    d.screenshot(str(OUT / "machine-verifier-0.4.0.png"))
    run.rotate(1)
    run.read()
    d.find("machine-summary")
    d.screenshot(str(OUT / "machine-landscape-0.4.0.png"))
    run.rotate(0)
    original = json.loads((machine.STATE / "state.json").read_text())
    run.restore()
    installed = set(d.shell("pm", "list", "packages").splitlines())
    check({p for p in machine.PACKAGES if "package:" + p in installed} == set(original["packages"]),
          "Original package set was not restored")
    check(d.cli("modules", "ls") == original["modules"], "Original module list was not restored")
    check("tun0" not in d.shell("ip", "link", "show"), "VPN test service remains")
    check(not d.shell("sh", "-c", "test ! -e /sdcard/Pictures/SELinuxShieldProbe || echo present"),
          "Native regression fixture remains")
    check(not d.shell("sh", "-c", "test ! -e " + d.ui_path + " || echo present"), "UI fixture remains")
    print(d.adb("unroot"), flush=True)
    d.adb("wait-for-device")
    check(d.shell("id", "-u") != "0", "ADB is still root")
    shutdown = d.adb("emu", "kill")
    check("OK" in shutdown, "Dedicated emulator shutdown was not accepted")
    restored = {"settings": True, "scopes": True, "modules": True, "originalPackages": True,
                "mode": original["mode"], "vpnStopped": True, "fixturesRemoved": True,
                "clipboardBackupRestored": True, "adbUnrooted": True,
                "dedicatedEmulatorShutdownAccepted": True,
                "artifacts": report["artifacts"].copy(),
                "originalSnapshotSHA256": hashlib.sha256((machine.STATE / "state.json").read_bytes()).hexdigest(),
                "completedAtUTC": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    run.case("D18-restored", lambda: restored)
    (OUT / "machine-finalization-0.4.0.json").write_text(json.dumps(restored, indent=2) + "\n")
    subprocess.run([sys.executable, str(ROOT / "scripts/audit-machine.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/package-machine.py")], cwd=ROOT, check=True)
    print("PASS final evidence, restoration and delivery", flush=True)


if __name__ == "__main__":
    main()
