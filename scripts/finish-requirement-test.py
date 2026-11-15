#!/usr/bin/env python3
"""Finish only the completed 0.4.1 UI tests; does not deploy to any physical device."""
import json
import pathlib
from test_device import Device,MODULE,PRIMARY
root=pathlib.Path(__file__).resolve().parents[1]
path=root/"verification/requirement-ui-0.4.1-results.json"
report=json.loads(path.read_text())
required=["U01-install-default","U02-home-timer-and-pause","U03-detail-directory-search",
          "U04-editor-preset-and-cancel","U05-row-random-selects","U06-enable-manual-update-disable",
          "U07-legacy-entry-switch","U08-visible-active-IMEI"]
for key in required:
    assert report["cases"][key]["status"]=="passed"
    assert report["cases"][key]["artifacts"]==report["artifacts"]
assert report["restoration"]["modulesAndScopes"]
d=Device()
original=json.loads((pathlib.Path.home()/
    "Library/Application Support/ScreenshotShield/requirement-ui-0.4.1/state.json").read_text())
assert d.cli("modules","ls")==original["modules"]
installed=set(d.shell("pm","list","packages").splitlines())
assert {pkg for pkg in [MODULE,PRIMARY] if "package:"+pkg in installed}==set(original["packages"])
d.adb("unroot");d.adb("wait-for-device")
assert d.shell("id","-u")!="0"
assert "OK" in d.adb("emu","kill")
report["restoration"].update(adbUnrooted=True,dedicatedEmulatorShutdownAccepted=True)
path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print("PASS 8 targeted checks; original environment restored and emulator shutdown accepted")
