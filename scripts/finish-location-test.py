#!/usr/bin/env python3
"""Unroot and stop the dedicated emulator only after selected cases and restoration."""
import json
import pathlib
import subprocess
from test_device import ADB, Device

ROOT=pathlib.Path(__file__).resolve().parents[1]
report_path=ROOT/"verification/location-ui-0.4.2-results.json"
report=json.loads(report_path.read_text())
cases=["L01-default-and-baseline","L02-region-UI-draft-save","L03-location-three-gates",
       "N01-present-SIM-coherence","N02-no-SIM-and-real-restoration","R01-category-refresh"]
assert all(report["cases"][name]["status"]=="passed" for name in cases)
restored=report["cases"]["D18-restored"]
assert restored["status"]=="passed" and restored["startedAtUTC"]>=max(
    report["cases"][name]["startedAtUTC"] for name in cases),"Restoration is not current"
assert all(report["restoration"].get(key) for key in [
    "originalAPKBytes","completeDataSnapshotRestored","modulesAndScopes","settings"])
device=Device()
device.adb("unroot")
device.adb("wait-for-device",timeout=15)
assert device.shell("id","-u")=="2000","ADB is still privileged"
report["restoration"]["adbUnrooted"]=True
shutdown=device.adb("emu","kill")
assert "OK" in shutdown,"Shutdown request was not accepted"
report["restoration"]["dedicatedEmulatorShutdownAccepted"]=True
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report["restoration"],ensure_ascii=False,indent=2))
