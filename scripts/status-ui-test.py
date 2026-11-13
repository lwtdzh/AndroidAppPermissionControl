#!/usr/bin/env python3
"""0.3.1 UI checks on emulator-5584. Capture first; restore even after a failed run."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import time
from test_device import Device, MODULE, PRIMARY, METHODS

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/status-ui-0.3.1"
C = PRIMARY + ".sampleb.screenshot"
REPORT = OUT / "status-ui-0.3.1-results.json"


def check(value, message):
    if not value:
        raise AssertionError(message)


class Run:
    def __init__(self):
        self.d = Device()
        self.report = json.loads(REPORT.read_text()) if REPORT.exists() else {"cases": {}}

    def case(self, name, action):
        print("START " + name, flush=True)
        if name in self.report["cases"]:
            self.report.setdefault("previousRuns", {}).setdefault(name, []).append(self.report["cases"][name])
        try:
            self.report["cases"][name] = {"status": "passed", "evidence": action()}
        except Exception as error:
            self.report["cases"][name] = {"status": "failed", "error": repr(error)}
            raise
        finally:
            REPORT.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")
        print("PASS " + name, flush=True)

    def wait(self, read, message, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = read()
            if value:
                return value
        raise AssertionError(message)

    def capture(self):
        d = self.d
        check(not (STATE / "state.json").exists(), "Original snapshot already exists")
        check("tun0" not in d.shell("ip", "link", "show"), "Do not replace an existing VPN")
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        original = {"mode": d.shell("getenforce"), "modules": d.cli("modules", "ls"),
                    "packages": {}, "prefs": {}, "settings": {}, "launcher": "default", "locales": {}}
        original["screenshots"] = self.shots()
        original["scopes"] = {m["PACKAGE"]: d.cli("scope", "ls", m["PACKAGE"]) for m in original["modules"]}
        for namespace, keys in {"global": ["hidden_api_policy", "development_settings_enabled", "adb_wifi_enabled", "http_proxy"],
                                "system": ["accelerometer_rotation", "user_rotation", "font_scale"]}.items():
            original["settings"][namespace] = {key: d.shell("settings", "get", namespace, key) for key in keys}
        package_dump = d.shell("dumpsys", "package", MODULE)
        if re.search(r"enabledComponents:\s+io.github.lwtdzh.appstateshield.Launcher", package_dump):
            original["launcher"] = "enable"
        elif re.search(r"disabledComponents:\s+io.github.lwtdzh.appstateshield.Launcher", package_dump):
            original["launcher"] = "disable"
        for pkg in (MODULE, PRIMARY, C):
            if "package:" + pkg not in d.shell("pm", "list", "packages").splitlines():
                continue
            remote = d.shell("pm", "path", pkg).removeprefix("package:").splitlines()[0]
            local = STATE / (pkg + ".apk")
            d.adb("pull", remote, str(local)); local.chmod(0o600)
            original["packages"][pkg] = str(local)
            original["locales"][pkg] = d.shell("cmd", "locale", "get-app-locales", pkg).split("[", 1)[1].split("]", 1)[0]
            folder = "/data/user/0/" + pkg + "/shared_prefs"
            if d.shell("sh", "-c", "test ! -d " + folder + " || echo present") == "present":
                remote_tar = "/data/local/tmp/status-ui-prefs.tar"
                d.shell("tar", "-cf", remote_tar, "-C", "/data/user/0/" + pkg, "shared_prefs")
                local_tar = STATE / (pkg + ".tar")
                d.adb("pull", remote_tar, str(local_tar)); local_tar.chmod(0o600)
                d.shell("rm", "-f", remote_tar)
                original["prefs"][pkg] = str(local_tar)
        with os.fdopen(os.open(STATE / "state.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as output:
            json.dump(original, output)
        self.case("I00-capture", lambda: {"serial": "emulator-5584", "sdk": d.shell("getprop", "ro.build.version.sdk"),
                                        "abi": d.shell("getprop", "ro.product.cpu.abi"), "originalMode": original["mode"]})

    def launcher(self):
        result = self.d.shell("cmd", "package", "query-activities", "--brief",
                              "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", MODULE)
        return MODULE + "/.Launcher" in result

    def shots(self):
        rows = self.d.shell("content", "query", "--uri", "content://media/external/images/media",
                            "--projection", "_id", "--where", "_display_name LIKE 'Screenshot%'")
        return sorted(re.findall(r"_id=(\d+)", rows))

    def open_main(self, cold=False):
        d = self.d
        if cold:
            d.shell("am", "force-stop", PRIMARY)
        # Start a genuine launcher task, including MAIN/LAUNCHER on its root intent.
        # Otherwise a later launcher tap creates a second activity above the
        # shell's component-only root rather than resuming the observed page.
        d.shell("am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                "-f", "0x10208000" if cold else "0x10200000", "-n", PRIMARY + "/.MainActivity")
        def ready():
            values = self.summary()
            return values if len(values) == 6 and all("读取中" not in v for v in values.values()) else None
        return self.wait(ready, "Summary did not finish reading")

    def summary(self):
        return {n.get("content-desc").split(":", 1)[1]: n.get("text")
                for n in self.d.nodes() if n.get("content-desc", "").startswith("summary:")}

    def count(self):
        node = next((n for n in self.d.nodes() if n.get("content-desc") == "session-screenshots"), None)
        return int(re.search(r"\d+", node.get("text")).group()) if node is not None else -1

    def run(self):
        d = self.d
        check((STATE / "state.json").exists(), "Capture before installing")
        # A clean AVD first installs the published version to exercise an actual upgrade.
        original = json.loads((STATE / "state.json").read_text())
        installed = set(d.shell("pm", "list", "packages").splitlines())
        if MODULE not in original["packages"] and "package:" + MODULE not in installed:
            d.adb("install", "--no-incremental", "-r", str(OUT / "AppStateShield-0.3.0.apk"))
        if PRIMARY not in original["packages"] and "package:" + PRIMARY not in installed:
            d.adb("install", "--no-incremental", "-r", str(OUT / "AppStateVerifier-0.3.0.apk"))
        if C not in original["packages"] and "package:" + C not in installed:
            d.adb("install", "--no-incremental", "-r", str(OUT / "Verifier-B-0.3.0.apk"))
        for pkg, name in ((MODULE, "AppStateShield-0.3.1.apk"), (PRIMARY, "AppStateVerifier-0.3.1.apk")):
            d.adb("install", "--no-incremental", "-r", str(OUT / name))
            d.shell("cmd", "locale", "set-app-locales", pkg, "--locales", "zh-Hans")
        self.report["artifacts"] = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
                                    for name in ("AppStateShield-0.3.1.apk", "AppStateVerifier-0.3.1.apk")}
        for module in d.cli("modules", "ls"):
            for pkg in (PRIMARY, C):
                d.scope(module["PACKAGE"], pkg, False)
        d.cli("modules", "enable", MODULE)
        d.shell("settings", "put", "global", "hidden_api_policy", "1")
        d.shell("settings", "put", "global", "development_settings_enabled", "1")
        d.shell("settings", "put", "global", "adb_wifi_enabled", "0")
        d.shell("settings", "put", "global", "http_proxy", ":0")
        d.shell("input", "keyevent", "WAKEUP"); d.shell("wm", "dismiss-keyguard")
        self.case("I01-default-off-upgrade", self.icon_default)
        self.case("I02-enable-open-upgrade", self.icon_enable)
        self.case("I03-disable-vector-entry", self.icon_disable)
        self.case("I04-profile-isolation", self.icon_profile)
        self.case("V01-observed-baseline", self.baseline)
        self.case("V02-live-proxy", self.proxy)
        self.case("V03-live-vpn", self.vpn)
        self.case("V04-shielded-readings", self.shielded)
        self.case("V05-real-screenshot-session", self.screenshots)
        self.case("V06-rotation-background-clear", self.lifecycle)
        self.case("V07-fresh-session", self.fresh)
        self.case("V08-font-size", self.font)
        self.case("V11-locales", self.locales)

    def icon_default(self):
        self.d.home_settings()
        check(self.d.find("show-launcher").get("checked") == "false" and not self.launcher(), "Icon default differs")
        return {"defaultOff": True, "upgradedFrom": "0.3.0"}

    def icon_enable(self):
        d = self.d
        d.click("show-launcher")
        check(self.launcher(), "No launcher activity after enabling")
        d.shell("am", "force-stop", MODULE)
        d.shell("am", "start", "-W", "-n", MODULE + "/.Launcher")
        check(d.find("show-launcher").get("checked") == "true", "Launcher did not open settings")
        d.adb("install", "--no-incremental", "-r", str(OUT / "AppStateShield-0.3.1.apk"))
        d.home_settings()
        check(self.launcher() and d.find("show-launcher").get("checked") == "true", "Upgrade lost icon setting")
        d.screenshot(OUT / "settings-icon-0.3.1.png")
        return {"launcherOpensSettings": True, "survivesColdStartAndUpgrade": True}

    def icon_disable(self):
        d = self.d
        d.click("show-launcher")
        check(not self.launcher(), "Launcher still resolves")
        d.home_settings()
        check(d.find("show-launcher").get("checked") == "false", "Vector settings entry failed")
        d.adb("install", "--no-incremental", "-r", str(OUT / "AppStateShield-0.3.1.apk"))
        check(not self.launcher(), "Upgrade changed disabled icon")
        return {"hidden": True, "vectorSettingsOpen": True, "upgradeKeepsOff": True}

    def icon_profile(self):
        d = self.d
        old_users = d.shell("pm", "list", "users")
        created = d.shell("pm", "create-user", "AppStateIconTest031")
        match = re.search(r"Success: created user id (\d+)", created)
        check(match is not None, "Could not create a separate test user")
        user = match.group(1)
        def visible():
            # The fresh test user is locked; include both direct-boot categories.
            return ".Launcher" in d.shell("cmd", "package", "query-activities", "--brief", "--query-flags", "786432", "--user", user,
                "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", MODULE)
        try:
            d.shell("pm", "install-existing", "--user", user, MODULE)
            check(not visible(), "Fresh user's launcher should default off")
            d.shell("pm", "enable", "--user", user, MODULE + "/.Launcher")
            check(visible() and not self.launcher(), "Per-user launcher state leaked")
            d.shell("pm", "disable", "--user", user, MODULE + "/.Launcher")
            check(not visible() and not self.launcher(), "Per-user disable differs")
        finally:
            d.shell("pm", "remove-user", user)
            self.wait(lambda: d.shell("pm", "list", "users") == old_users, "Test user was not removed")
        return {"freshUserDefaultOff": True, "perUserIsolation": True, "testUserRemoved": True}

    def baseline(self):
        values = self.open_main(True)
        check("已开启" in values["developer"] and "已开启" in values["usb"], "True developer/USB baseline missing")
        check("未开启" in values["vpn"] and "未配置" in values["proxy"], "Network baseline differs")
        check(self.count() == 0, "Fresh session count is not zero")
        if self.d.shell("getenforce") == "Enforcing":
            check("宽容模式" not in values["selinux"], "Failed SELinux read was labeled Permissive")
        return {"readings": values, "realSELinux": self.d.shell("getenforce")}

    def proxy(self):
        d = self.d
        d.shell("settings", "put", "global", "http_proxy", "127.0.0.1:9")
        values = self.wait(lambda: (v if "已配置" in v.get("proxy", "") else None) if (v := self.summary()) else None,
                           "Live proxy was not refreshed")
        d.shell("settings", "put", "global", "http_proxy", ":0")
        self.wait(lambda: "未配置" in self.summary().get("proxy", ""), "Proxy removal was not refreshed")
        return {"configuredThenRemovedWithoutRestart": True, "configuredReading": values["proxy"]}

    def vpn(self):
        d = self.d
        d.shell("am", "start", "-W", "-n", C + "/io.github.lwtdzh.devicestateprobe.ProbeActivity",
                "--es", "action", "vpn-start")
        consent = next((n for n in d.nodes() if n.get("resource-id") == "android:id/button1"), None)
        if consent is not None:
            d.tap(consent)
        self.wait(lambda: "tun0" in d.shell("ip", "link", "show"), "No real VPN baseline")
        values = self.open_main()
        self.wait(lambda: "已开启" in self.summary().get("vpn", ""), "VPN reading missing")
        d.shell("am", "force-stop", C)
        self.wait(lambda: "未开启" in self.summary().get("vpn", ""), "VPN removal not refreshed")
        return {"realVpnCreatedAndStopped": True, "readings": values}

    def shielded(self):
        d = self.d
        d.scope(MODULE, PRIMARY, True)
        d.set_policy(PRIMARY, set(METHODS))
        values = self.open_main(True)
        for key in ("vpn", "developer", "usb", "wireless"):
            check("未开启" in values[key], "Shielded reading differs: " + key)
        check(any("读数可能经过屏蔽" in n.get("text", "") for n in d.nodes()), "Filtered-reading explanation missing")
        check(d.shell("settings", "get", "global", "development_settings_enabled") == "1", "Real setting changed")
        return {"readings": values, "realDeveloper": "1", "realSELinux": d.shell("getenforce")}

    def screenshots(self):
        d = self.d
        d.set_policy(PRIMARY, set())
        self.open_main(True)
        d.find("source-filter")
        self.wait(lambda: any("入口就绪" in n.get("text", "") for n in d.nodes()), "No screenshot listener")
        for wanted in (1, 2):
            d.shell("input", "-d", "0", "keyevent", "SYSRQ")
            self.wait(lambda: self.count() == wanted, "Real screenshot count differs")
            self.wait(lambda: "com.android.systemui.screenshot" not in d.shell("dumpsys", "window", "windows"),
                      "Screenshot overlay did not close")
        pid = d.shell("pidof", PRIMARY).split()[0]
        logs = d.adb("logcat", "-d", "--pid=" + pid, "-s", "ScreenshotDetector:I", "*:S")
        signals = len(re.findall(r"DETECTED source=(?:official|binder)", logs))
        check(signals >= 4, "Independent official/Binder callbacks missing")
        d.screenshot(OUT / "verifier-summary-0.3.1.png")
        return {"realSystemUICaptures": 2, "summaryCount": self.count(), "officialAndBinderSignalsAtLeast": signals}

    def lifecycle(self):
        d = self.d
        before = self.count()
        for attempt in range(12):
            nodes = d.nodes()
            button = next((n for n in nodes if n.get("content-desc") == "restart"), None)
            if button is not None:
                d.tap(button); break
            scroll = next(n for n in nodes if n.get("class") == "android.widget.ScrollView")
            left, top, right, bottom = map(int, re.findall(r"\d+", scroll.get("bounds")))
            start, end = top + (bottom - top) * 2 // 3, top + (bottom - top) // 3
            if attempt >= 6:
                start, end = end, start
            d.shell("input", "swipe", right - 5, start, right - 5, end, 600)
        else:
            raise AssertionError("Restart control is not reachable in the diagnostic scroll")
        check(self.count() == before, "Restart reset session")
        d.click("clear_log")
        check(self.count() == before, "Clearing logs reset session")
        d.shell("input", "keyevent", "HOME")
        # Use the launcher's actual flags. CLEAR_TOP recreates a standard activity
        # and would intentionally start a new page rather than resume its task.
        d.shell("am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                "-f", "0x10200000", "-n", PRIMARY + "/.MainActivity")
        self.wait(lambda: self.count() == before, "Background task did not preserve the session")
        d.shell("settings", "put", "system", "accelerometer_rotation", "0")
        for rotation in ("1", "0"):
            d.shell("settings", "put", "system", "user_rotation", rotation)
            def rotated():
                width, height = d.dimensions()
                return (width > height) == (rotation == "1")
            self.wait(rotated, "Requested screen rotation did not occur")
            self.wait(lambda: self.count() == before, "Rotation reset session")
        return {"preservedCount": before, "restart": True, "clearLog": True, "background": True, "rotation": True}

    def fresh(self):
        self.open_main(True)
        check(self.count() == 0, "Cold reopen did not start a fresh session")
        self.d.back()
        self.open_main()
        check(self.count() == 0, "New task did not start a fresh session")
        return {"coldStartZero": True, "newPageZero": True}

    def font(self):
        self.d.shell("settings", "put", "system", "font_scale", "1.3")
        self.open_main(True)
        self.d.find("summary:selinux")
        self.d.find("source-filter")
        self.d.screenshot(OUT / "verifier-font-0.3.1.png")
        return {"fontScale": 1.3, "summaryAndDiagnosticsVisible": True}

    def locales(self):
        d = self.d
        values = {}
        try:
            for locale, label, icon in (("zh-Hans", "本次打开", "显示应用图标"),
                                        ("zh-Hant", "本次開啟", "顯示應用圖示"),
                                        ("en", "This session", "Show app icon"),
                                        ("ja", "今回の起動", "アプリアイコンを表示")):
                d.shell("cmd", "locale", "set-app-locales", PRIMARY, "--locales", locale)
                d.shell("am", "force-stop", PRIMARY)
                d.shell("am", "start", "-W", "-n", PRIMARY + "/.MainActivity")
                self.wait(lambda: any(label in n.get("text", "") for n in d.nodes()), "Summary locale differs")
                d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", locale)
                d.home_settings()
                check(d.find("show-launcher").get("text") == icon, "Icon locale differs")
                values[locale] = {"summary": True, "icon": True}
        finally:
            for pkg in (MODULE, PRIMARY):
                d.shell("cmd", "locale", "set-app-locales", pkg, "--locales", "zh-Hans")
        return values

    def restore(self):
        d = self.d
        original = json.loads((STATE / "state.json").read_text())
        d.shell("am", "force-stop", C)
        check("tun0" not in d.shell("ip", "link", "show"), "Temporary VPN still active")
        if "screenshots" in original:
            for row in set(self.shots()) - set(original["screenshots"]):
                d.shell("content", "delete", "--uri", "content://media/external/images/media/" + row)
            check(self.shots() == original["screenshots"], "Temporary screenshots remain")
        for pkg, local in original["packages"].items():
            d.shell("am", "force-stop", pkg)
            d.adb("install", "--no-incremental", "-r", "-d", local)
            d.shell("am", "force-stop", pkg)
            remote = d.shell("pm", "path", pkg).removeprefix("package:").splitlines()[0]
            check(d.shell("sha256sum", remote).split()[0] == hashlib.sha256(pathlib.Path(local).read_bytes()).hexdigest(),
                  "Original APK differs")
            folder = "/data/user/0/" + pkg
            if pkg in original["prefs"]:
                temporary = "/data/local/tmp/status-ui-restore.tar"
                d.adb("push", original["prefs"][pkg], temporary)
                d.shell("tar", "-xf", temporary, "-C", folder)
                uid = re.search(r"userId=(\d+)", d.shell("dumpsys", "package", pkg)).group(1)
                d.shell("chown", "-R", uid + ":" + uid, folder + "/shared_prefs")
                d.shell("restorecon", "-R", folder + "/shared_prefs")
                d.shell("rm", "-f", temporary)
            else:
                d.shell("rm", "-rf", folder + "/shared_prefs")
            d.shell("cmd", "locale", "set-app-locales", pkg, "--locales", original.get("locales", {}).get(pkg, ""))
        for pkg in (MODULE, PRIMARY, C):
            if pkg not in original["packages"]:
                d.adb("uninstall", pkg)
                check("package:" + pkg not in d.shell("pm", "list", "packages").splitlines(), "Temporary APK remains")
        d.shell("pm", original["launcher"], MODULE + "/.Launcher") if MODULE in original["packages"] and original["launcher"] != "default" else None
        # 0.3.0 has no alias; remove the test-only enabled/disabled component override.
        if MODULE in original["packages"] and original["launcher"] == "default":
            d.shell("pm", "default-state", MODULE + "/.Launcher")
        for module in original["modules"]:
            d.cli("modules", "enable" if module["STATUS"] == "enabled" else "disable", module["PACKAGE"])
            prior = {(s["APP_PACKAGE"], s["USER_ID"]) for s in original["scopes"][module["PACKAGE"]]}
            for pkg in (PRIMARY, C):
                d.scope(module["PACKAGE"], pkg, (pkg, 0) in prior)
            check(d.cli("scope", "ls", module["PACKAGE"]) == original["scopes"][module["PACKAGE"]], "Original scope differs")
        for namespace, values in original["settings"].items():
            for key, value in values.items():
                d.shell("settings", "delete", namespace, key) if value == "null" else d.shell("settings", "put", namespace, key, value)
                check(d.shell("settings", "get", namespace, key) == value, "Original setting differs")
        check(d.shell("getenforce") == original["mode"], "SELinux mode changed")
        check(d.cli("modules", "ls") == original["modules"], "Original module list or state differs")
        self.case("I99-restored", lambda: {"originalApks": True, "scopes": True, "settings": True,
                                         "prefs": True, "SELinuxUnchanged": True, "vpnStopped": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["capture", "run", "restore"])
    parser.add_argument("--case", help="Run one existing method after its prerequisites are prepared")
    args = parser.parse_args()
    run = Run()
    if args.case:
        check(args.phase == "run", "--case is only for prepared runs")
        run.case(args.case.split(":", 1)[0], getattr(run, args.case.split(":", 1)[1]))
    else:
        getattr(run, args.phase)()
