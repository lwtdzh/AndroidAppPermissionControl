#!/usr/bin/env python3
"""Install signed 0.3.1 APKs on the vivo selected by APPSTATE_VIVO_SERIAL; preserve policy."""
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERIAL = os.environ.get("APPSTATE_VIVO_SERIAL", "")
MODULE = "io.github.lwtdzh.appstateshield"
PRIMARY = "io.github.lwtdzh.screenshotdetector"
CLI = "/data/adb/modules/zygisk_vector/cli"
ADB = "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"


def adb(*args):
    return subprocess.check_output([ADB, "-s", SERIAL, *args], text=True, timeout=60).strip()


def shell(*args):
    return adb("shell", shlex.join(str(value) for value in args))


def root(*args):
    return shell("su", "-c", shlex.join(str(value) for value in args))


def framework():
    modules = json.loads(root(CLI, "--json", "modules", "ls"))["data"]
    return {"modules": modules,
            "scopes": {m["PACKAGE"]: json.loads(root(CLI, "--json", "scope", "ls", m["PACKAGE"]))["data"]
                       for m in modules}}


def policy():
    return root("cat", "/data/user/0/" + MODULE + "/shared_prefs/policies.xml")


def check(ok, message):
    if not ok:
        raise AssertionError(message)


def main():
    check(bool(SERIAL), "Set APPSTATE_VIVO_SERIAL to the explicitly authorized phone's ADB serial")
    check(shell("getprop", "ro.product.model") == "V2419A", "Unexpected device model")
    state_dir = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/vivo-status-ui-0.3.1"
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    before = {"framework": framework(), "policy": policy(), "mode": root("getenforce")}
    snapshot = state_dir / ("before-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    with os.fdopen(os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as output:
        json.dump(before, output)
    report = {"model": "vivo V2419A", "sdk": shell("getprop", "ro.build.version.sdk"), "packages": {}}
    for pkg, name in ((MODULE, "AppStateShield-0.3.1.apk"), (PRIMARY, "AppStateVerifier-0.3.1.apk")):
        local = ROOT / "verification" / name
        expected = hashlib.sha256(local.read_bytes()).hexdigest()
        current_path = shell("pm", "path", pkg).removeprefix("package:").splitlines()[0]
        already_installed = shell("sha256sum", current_path).split()[0] == expected
        via_root = False
        if not already_installed:
            # vivo's USB installer gate can time out. Use the already-authorized
            # rooted package manager, without changing USB/security settings.
            temporary = "/data/local/tmp/" + name
            adb("push", str(local), temporary)
            try:
                check(root("sha256sum", temporary).split()[0] == expected, "Transferred APK differs")
                check("Success" in root("pm", "install", "-r", temporary), "Root package installation failed")
                via_root = True
            finally:
                root("rm", "-f", temporary)
        remote = shell("pm", "path", pkg).removeprefix("package:").splitlines()[0]
        actual = shell("sha256sum", remote).split()[0]
        check(expected == actual, "Installed hash differs")
        dump = shell("dumpsys", "package", pkg)
        version = re.search(r"versionName=([^\s]+)", dump).group(1)
        check(version == "0.3.1", "Installed version differs")
        report["packages"][pkg] = {"version": version, "sha256": actual, "installed": True, "rootInstaller": via_root}
        shell("am", "force-stop", pkg)
    check(framework() == before["framework"], "Vector scopes or module state changed")
    check(policy() == before["policy"], "Saved policies changed")
    check(root("getenforce") == before["mode"], "Real SELinux mode changed")
    # Include the snapshot from before the first attempt, even if USB confirmation
    # interrupted that attempt after upgrading only one of the APKs.
    current_framework, current_policy, current_mode = framework(), policy(), root("getenforce")
    for prior in state_dir.glob("before-*.json"):
        original = json.loads(prior.read_text())
        check(original["framework"] == current_framework and original["policy"] == current_policy
              and original["mode"] == current_mode, "Original configuration differs after an earlier attempt")
    # Check only this application's controls; never retain other app UI or logs.
    ui = "/data/local/tmp/appstate-vivo-ui.xml"
    shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
    shell("uiautomator", "dump", "--compressed", ui)
    nodes = list(ET.fromstring(shell("cat", ui)).iter("node"))
    toggle = next(n for n in nodes if n.get("content-desc") == "show-launcher")
    report["iconOff"] = toggle.get("checked") == "false"
    check(report["iconOff"], "Expected default-off icon")
    shell("am", "start", "-W", "-n", PRIMARY + "/.MainActivity")
    deadline = time.monotonic() + 20
    while True:
        shell("uiautomator", "dump", "--compressed", ui)
        nodes = list(ET.fromstring(shell("cat", ui)).iter("node"))
        original_app = next((n for n in nodes if n.get("resource-id") == "com.vivo.doubleinstance:id/main"), None)
        if original_app is not None:
            left, top, right, bottom = map(int, re.findall(r"\d+", original_app.get("bounds")))
            shell("input", "tap", (left + right) // 2, (top + bottom) // 2)
            report["openedOriginalApp"] = True
            continue
        values = {n.get("content-desc").split(":", 1)[1]: n.get("text")
                  for n in nodes if n.get("content-desc", "").startswith("summary:")}
        if len(values) == 6 and all("读取中" not in value and "Reading" not in value for value in values.values()):
            break
        check(time.monotonic() < deadline, "Phone summary did not appear")
    report["summary"] = values
    report["sessionCounterVisible"] = any(n.get("content-desc") == "session-screenshots" for n in nodes)
    report["preserved"] = {"policy": True, "frameworkScopesAndState": True, "realSELinuxMode": True}
    shell("rm", "-f", ui)
    (ROOT / "verification/vivo-status-ui-0.3.1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("PASS both 0.3.1 APKs installed; hashes, policy, Vector scopes and SELinux verified")


if __name__ == "__main__":
    main()
