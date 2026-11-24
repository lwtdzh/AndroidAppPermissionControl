#!/usr/bin/env python3
"""两个银行的模拟器启动对照；不登录，逐字恢复配置、作用域和原 APK。"""
import hashlib
import json
import pathlib
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
import test_device
import argparse
from test_device import Device, METHODS, MODULE

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/bank-codeview-20261119"
APK = ROOT / "verification/AppStateShield-bank-codeview.apk"
TARGETS = {
    "com.chinamworld.main": "com.ccb.start.StartActivity",
    "com.citiccard.mobilebank": None,
}
parser = argparse.ArgumentParser()
parser.add_argument("--package", choices=list(TARGETS))
parser.add_argument("--six-on-only", action="store_true")
args = parser.parse_args()
test_device.TEST_TARGETS.update(TARGETS)
ADB = "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"
if subprocess.check_output([ADB, "-s", "emulator-5584", "shell", "id", "-u"], text=True).strip() != "0":
    subprocess.run([ADB, "-s", "emulator-5584", "root"], check=True)
    subprocess.run([ADB, "-s", "emulator-5584", "wait-for-device"], check=True)
d = Device()
snap = STATE / ("startup-" + str(time.time_ns()))
d.shell("ls", "-d", "/data/local/tmp")
assert STATE.is_dir()
snap.mkdir(mode=0o700)
uiExists = d.shell("sh", "-c", "test -f " + shlex.quote(d.ui_path) + " && echo yes || echo no") == "yes"
uiBefore = subprocess.check_output(d.prefix + ["exec-out", "cat " + shlex.quote(d.ui_path)]) if uiExists else None
before = {}
for name in ("policies", "device_profiles"):
    path = f"/data/user/0/{MODULE}/shared_prefs/{name}.xml"
    data = subprocess.check_output(d.prefix + ["exec-out", "cat " + shlex.quote(path)])
    local = snap / (name + ".xml")
    local.write_bytes(data)
    local.chmod(0o600)
    before[name] = {"data": data, "local": local, "path": path,
                    "owner": d.shell("stat", "-c", "%u:%g", path),
                    "mode": d.shell("stat", "-c", "%a", path)}
profiles = ET.fromstring(before["device_profiles"]["data"])
for pkg in TARGETS:
    profile = profiles.find(f"string[@name='{pkg}']")
    assert profile is None or not json.loads(profile.text or "{}").get("enabled", False)
scopes = {m["PACKAGE"]: d.cli("scope", "ls", m["PACKAGE"]) for m in d.cli("modules", "ls")}
installed = d.shell("pm", "path", MODULE).splitlines()[0].removeprefix("package:")
d.adb("pull", installed, str(snap / "original-module.apk"))
rows = []
started = time.monotonic()
try:
    d.adb("install", "--no-incremental", "-r", str(APK))
    installed = d.shell("pm", "path", MODULE).splitlines()[0].removeprefix("package:")
    assert d.shell("sha256sum", installed).split()[0] == hashlib.sha256(APK.read_bytes()).hexdigest()
    for pkg, activity in TARGETS.items():
        if args.package and pkg != args.package:
            continue
        if activity is None:
            activity = d.shell("cmd", "package", "resolve-activity", "--brief",
                               "-a", "android.intent.action.MAIN",
                               "-c", "android.intent.category.LAUNCHER", pkg).splitlines()[-1]
            activity = activity.split("/", 1)[1]
        for enabled in ([METHODS] if args.six_on_only else ([], METHODS)):
            t = time.monotonic()
            label = pkg + ("-six-on" if enabled else "-six-off")
            d.shell("am", "force-stop", pkg)
            for module in scopes:
                d.scope(module, pkg, module == MODULE)
            d.batch_policy(pkg, enabled)
            cursor = d.shell("date", "+%m-%d %H:%M:%S.000")
            d.shell("am", "start", "-n", pkg + "/" + activity)
            pids = []
            for _ in range(3):
                time.sleep(3)
                pids.append(d.shell("sh", "-c", "pidof " + pkg + " || true"))
            logs = d.shell("logcat", "-d", "-T", cursor, "-v", "threadtime", "-s",
                           "AppStateShield", "ScreenshotShield", "SELinuxStateShield",
                           "DeveloperStateShield", "VpnStateShield", "VectorNative", "libc")
            (snap / (label + ".log")).write_text(logs)
            ui = [{"text": n.get("text"), "description": n.get("content-desc"),
                   "package": n.get("package")} for n in d.nodes()
                  if n.get("text") or n.get("content-desc")]
            (snap / (label + ".png")).write_bytes(subprocess.check_output(d.prefix + ["exec-out", "screencap -p"]))
            row = {"package": pkg, "enabled": list(enabled), "pids": pids, "ui": ui,
                   "seconds": round(time.monotonic()-t, 3), "log": str(snap / (label + ".log")),
                   "screenshot": str(snap / (label + ".png")),
                   "stable": bool(pids[0]) and pids[0] == pids[1] == pids[2],
                   "policyLoaded": "Policy loaded=true" in logs,
                   "nativeHooks": "native ready api=" in logs,
                   "codeViewReady": "native compatibility ready=1" in logs}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            row["passed"] = row["stable"] and row["policyLoaded"] and (
                not enabled or (row["nativeHooks"] and row["codeViewReady"]))
    assert all(row["passed"] for row in rows), "One or more bank startups failed"
finally:
    for pkg in TARGETS:
        d.shell("am", "force-stop", pkg)
    d.shell("am", "force-stop", MODULE)
    d.adb("install", "--no-incremental", "-r", str(snap / "original-module.apk"))
    restoredApk = d.shell("pm", "path", MODULE).splitlines()[0].removeprefix("package:")
    assert d.shell("sha256sum", restoredApk).split()[0] == hashlib.sha256(
        (snap / "original-module.apk").read_bytes()).hexdigest()
    for name, value in before.items():
        tmp = value["path"] + ".bank-codeview"
        d.adb("push", str(value["local"]), tmp)
        d.shell("sh", "-c", "chown " + value["owner"] + " " + shlex.quote(tmp)
                + " && chmod " + value["mode"] + " " + shlex.quote(tmp)
                + " && restorecon " + shlex.quote(tmp)
                + " && mv " + shlex.quote(tmp) + " " + shlex.quote(value["path"]))
        assert subprocess.check_output(d.prefix + ["exec-out", "cat " + shlex.quote(value["path"])]) == value["data"]
    for module, saved in scopes.items():
        for pkg in TARGETS:
            d.scope(module, pkg, any(r["APP_PACKAGE"] == pkg and r["USER_ID"] == 0 for r in saved))
        assert d.cli("scope", "ls", module) == saved
    if uiBefore is None:
        d.shell("rm", "-f", d.ui_path)
    else:
        (snap / "before-ui.xml").write_bytes(uiBefore)
        d.adb("push", str(snap / "before-ui.xml"), d.ui_path)
    report = {"cases": rows, "restored": True, "originalApkRestored": True,
              "apkSHA256": hashlib.sha256(APK.read_bytes()).hexdigest(),
              "seconds": round(time.monotonic()-started, 3), "serial": "emulator-5584"}
    data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (snap / "startup-results.json").write_text(data)
    (ROOT / "verification/bank-codeview-startup-20261119.json").write_text(data)
