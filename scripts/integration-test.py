#!/usr/bin/env python3
"""Execute the persisted manual on the dedicated AVD, with real UI policy edits.

Run phases separately so failures can be fixed and rerun without losing evidence.
The cleanup phase restores the original pretest-state, not a rerun's transient state.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

from test_device import Device, MODULE, PRIMARY, METHODS

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = "0.3.0"
OUT = pathlib.Path(os.environ.get("APPSTATE_TEST_OUTPUT", ROOT / "verification" / VERSION))
B = PRIMARY + ".samplea"
C = PRIMARY + ".sampleb.screenshot"
MEDIA = "content://media/external/images/media"
DIRECTORY = "/sdcard/Pictures/ShieldProbe/"
SHOT_ACTIVITY = "io.github.lwtdzh.screenshotprobe.ProbeActivity"
STATE_ACTIVITY = "io.github.lwtdzh.devicestateprobe.ProbeActivity"
PREF = "/data/user/0/" + MODULE + "/shared_prefs/policies.xml"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Manual:
    def __init__(self):
        self.d = Device()
        self.only = set()
        self.visited = set()
        self.path = OUT / "integration-results.json"
        self.report = json.loads(self.path.read_text()) if self.path.exists() else {
            "environment": {"avd": "ScreenshotShield_API36", "serial": "emulator-5584",
                            "sdk": self.d.shell("getprop", "ro.build.version.sdk"),
                            "abi": self.d.shell("getprop", "ro.product.cpu.abi"),
                            "vector": self.d.cli("status")},
            "cases": {}}

    def case(self, name, action):
        self.visited.add(name)
        if self.only and name not in self.only:
            return
        print("START " + name, flush=True)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (OUT / f"AppStateShield-{VERSION}.apk", OUT / f"AppStateVerifier-{VERSION}.apk")
                     if p.exists()}
        previous = self.report["cases"].get(name)
        if previous:
            self.report.setdefault("previousRuns", {}).setdefault(name, []).append(previous)
        try:
            value = action()
            self.report["cases"][name] = {"status": "passed", "started": started,
                                         "artifacts": artifacts, "evidence": value}
        except Exception as error:
            self.report["cases"][name] = {"status": "failed", "started": started,
                                         "artifacts": artifacts, "error": repr(error)}
            if hasattr(error, "probe_evidence"):
                self.report["cases"][name]["evidence"] = error.probe_evidence
            elif name.startswith("X12-"):
                # Keep counters and state codes, never notification/clipboard payloads.
                try:
                    from collections import Counter
                    pid = self.d.shell("pidof", PRIMARY).split()[0]
                    log = self.d.adb("logcat", "-d", "--pid=" + pid, "-s", "ScreenshotDetector:I", "*:S")
                    self.report["cases"][name]["evidence"] = {
                        "sourceCounts": dict(Counter(re.findall(r"DETECTED source=(\w+)", log))),
                        "stateCounts": dict(Counter("/".join(pair) for pair in
                                                   re.findall(r"source=(\w+) code=(\w+)", log))),
                    }
                except Exception:
                    pass
            self.save()
            raise
        self.save()
        print("PASS " + name, flush=True)

    def save(self):
        self.report["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.report["artifacts"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (OUT / f"AppStateShield-{VERSION}.apk", OUT / f"AppStateVerifier-{VERSION}.apk")
            if p.exists()}
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")

    def policies(self):
        tree = ET.fromstring(self.d.shell("cat", PREF))
        node = tree.find("string[@name='apps']")
        return json.loads(node.text if node is not None else "{}")

    def remove(self, pkg):
        self.d.home_settings()
        self.d.click("custom:" + pkg, scroll=True)
        self.d.click("remove-custom", scroll=True)
        self.d.click("android:id/button1", "resource-id")
        self.d.find("add-app")
        check(pkg not in self.policies(), "Removed app still customized")

    def restore_services(self, values):
        listener = PRIMARY + "/io.github.lwtdzh.screenshotdetector.NotificationDetector"
        expected = set()
        for component in values["enabled_notification_listeners"].split(":"):
            if "/" in component:
                pkg, name = component.split("/", 1)
                expected.add(pkg + "/" + (pkg + name if name.startswith(".") else name))
        # NotificationManagerService keeps its own approved-listener state.
        # A raw Settings write alone can be undone on the next package change.
        self.d.shell("cmd", "notification",
                     "allow_listener" if listener in expected else "disallow_listener", listener)
        for key, value in values.items():
            self.d.shell("settings", "delete", "secure", key) if value == "null" else self.d.shell("settings", "put", "secure", key, value)
            check(self.d.shell("settings", "get", "secure", key) == value, "Service restore differs: " + key)

    def shots(self):
        rows = self.d.shell("content", "query", "--uri", MEDIA, "--projection", "_id:_display_name:relative_path")
        return {int(n) for n in re.findall(r"_id=(\d+)", rows)}

    def capture(self):
        """Read-only P03 snapshot before installing temporary flavors or editing scope."""
        d = self.d
        paths = (OUT / "pretest-state.json", OUT / "integration-preservation.json")
        check(not any(p.exists() for p in paths),
              "Existing snapshots must be kept until cleanup; archive them before a new test session")
        packages = set(re.findall(r"package:(\S+)", d.shell("pm", "list", "packages")))
        check(B not in packages and C not in packages, "Capture before installing temporary B/C targets")
        check(not re.search(r"^\d+: (?:tun|ppp|wg)\d+:", d.shell("ip", "link", "show"), re.M),
              "Existing VPN must not be replaced")
        modules = d.cli("modules", "ls")
        def settings(table, keys):
            return {key: d.shell("settings", "get", table, key) for key in keys}
        state = {"modules": modules, "scopes": {row["PACKAGE"]: d.cli("scope", "ls", row["PACKAGE"])
                 for row in modules},
                 "settings": settings("global", ("development_settings_enabled", "adb_enabled",
                                  "adb_wifi_enabled", "airplane_mode_on", "hidden_api_policy")),
                 "rotation": settings("system", ("accelerometer_rotation", "user_rotation")),
                 "services": settings("secure", ("enabled_accessibility_services",
                                  "enabled_notification_listeners", "accessibility_enabled"))}
        pref = d.shell("sh", "-c", "if test -f " + PREF + "; then cat " + PREF + "; else printf '<map/>'; fi")
        preserved = {"media": sorted(self.shots()), "font_scale": d.shell("settings", "get", "system", "font_scale"),
                     "app_locale": d.shell("cmd", "locale", "get-app-locales", MODULE) if MODULE in packages else "",
                     "verifier_locale": d.shell("cmd", "locale", "get-app-locales", PRIMARY) if PRIMARY in packages else "",
                     "permissions": {pkg: d.shell("dumpsys", "package", pkg) if pkg in packages else ""
                                     for pkg in (PRIMARY, B, C)},
                     "appops": {pkg: d.shell("cmd", "appops", "get", pkg) if pkg in packages else ""
                                for pkg in (PRIMARY, B, C)}, "pref": pref}
        for path, value in zip(paths, (state, preserved)):
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        self.report.setdefault("previousSessions", []).append(self.report["cases"])
        self.report["cases"] = {}
        self.case("P03-baseline", lambda: {"modulesSaved": len(modules), "mediaIdsSaved": len(preserved["media"]),
                                         "privateSnapshotsCreated": True})

    def prepare(self):
        baseline = OUT / "integration-preservation.json"
        if not baseline.exists():
            baseline.write_text(json.dumps({
                "media": sorted(self.shots()),
                "font_scale": self.d.shell("settings", "get", "system", "font_scale"),
                "app_locale": self.d.shell("cmd", "locale", "get-app-locales", MODULE),
                "permissions": {p: self.d.shell("dumpsys", "package", p) for p in (PRIMARY, B, C)},
                "appops": {p: self.d.shell("cmd", "appops", "get", p) for p in (PRIMARY, B, C)},
                "pref": self.d.shell("cat", PREF),
            }, indent=2))
        check(not re.search(r"^\d+: (?:tun|ppp|wg)\d+:", self.d.shell("ip", "link", "show"), re.M),
              "Existing VPN: do not replace")
        for pkg in (PRIMARY, B, C):
            for perm in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_IMAGES"):
                self.d.shell("pm", "grant", pkg, "android.permission." + perm)
            self.d.shell("appops", "set", pkg, "MANAGE_EXTERNAL_STORAGE", "allow")
        self.d.shell("settings", "put", "global", "development_settings_enabled", "1")
        for row in json.loads((OUT / "pretest-state.json").read_text())["modules"]:
            for pkg in (PRIMARY, B, C):
                self.d.scope(row["PACKAGE"], pkg, False)
        self.d.scope(MODULE, C, False)
        self.d.cli("modules", "enable", MODULE)
        self.d.scope(MODULE, PRIMARY, True)
        self.d.scope(MODULE, B, True)
        self.d.shell("mkdir", "-p", DIRECTORY, "/sdcard/Pictures/Screenshots/")
        self.fixtures()
        self.d.shell("am", "force-stop", C)
        self.d.shell("am", "start", "-W", "--activity-clear-top", "-n", C + "/" + STATE_ACTIVITY, "--es", "action", "vpn-start")
        nodes = self.d.nodes()
        consent = next((n for n in nodes if n.get("resource-id") == "android:id/button1"), None)
        if consent is not None:
            self.d.tap(consent)
        deadline = time.monotonic() + 10
        while "tun0" not in self.d.shell("ip", "link", "show") and time.monotonic() < deadline:
            time.sleep(.2)
        check("tun0" in self.d.shell("ip", "link", "show"), "No real VPN fixture")
        self.case("P03-P07/V01/D01", lambda: {
            "realTun": True, "adb": self.d.shell("settings", "get", "global", "adb_enabled"),
            "developer": self.d.shell("settings", "get", "global", "development_settings_enabled"),
            "adbd": self.d.shell("getprop", "init.svc.adbd"),
            "hiddenApiPolicyUnchanged": self.d.shell("settings", "get", "global", "hidden_api_policy")})

    def packaging(self):
        def run():
            apk = OUT / f"AppStateShield-{VERSION}.apk"
            with zipfile.ZipFile(apk) as archive:
                libraries = sorted(n for n in archive.namelist() if n.startswith("lib/"))
                expected = {f"lib/{abi}/lib{library}.so"
                            for abi in ("arm64-v8a", "armeabi-v7a", "x86", "x86_64")
                            for library in ("shield", "vpnstate", "developerstate", "selinuxstate")}
                check(set(libraries) == expected, "Four-ABI module libraries differ")
                check(archive.read("assets/xposed_init").decode().strip() ==
                      "io.github.lwtdzh.appstateshield.IntegratedEntry", "Module entry differs")
            installed = {}
            for pkg, filename in ((MODULE, f"AppStateShield-{VERSION}.apk"),
                                  (PRIMARY, f"AppStateVerifier-{VERSION}.apk")):
                path = self.d.shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
                actual = self.d.shell("sha256sum", path).split()[0]
                expected_hash = hashlib.sha256((OUT / filename).read_bytes()).hexdigest()
                check(actual == expected_hash, "Installed APK does not match delivery: " + pkg)
                installed[pkg] = actual
            launcher = self.d.shell("cmd", "package", "query-activities", "--brief",
                "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", MODULE)
            check("SettingsActivity" not in launcher, "Main module has a launcher")
            entry = self.d.shell("cmd", "package", "query-activities", "--brief",
                "-a", "android.intent.action.MAIN", "-c", "de.robv.android.xposed.category.MODULE_SETTINGS", "-p", MODULE)
            check("SettingsActivity" in entry, "Vector settings entry not registered")
            return {"libraries": libraries, "installedSha256": installed,
                    "noLauncher": True, "vectorSettingsIntent": entry,
                    "avd": self.d.adb("emu", "avd", "name"), "serial": "emulator-5584",
                    "vectorStatus": self.d.cli("status")}
        self.case("P01-P02/P04", run)
        def final_upgrade():
            before = self.policies()
            for name in (f"AppStateShield-{VERSION}.apk", f"AppStateVerifier-{VERSION}.apk"):
                self.d.adb("install", "--no-incremental", "-r", str(OUT / name))
            check(self.policies() == before, "Final signed upgrade changed customizations")
            return {"finalSignedUpgrade": True, "customizationsPreserved": True}
        self.case("I06-final-upgrade", final_upgrade)

    def fixtures(self):
        # Only touch IDs/files added by this test. Existing unrelated images remain.
        existing = self.d.shell("content", "query", "--uri", MEDIA, "--projection", "_id:_display_name",
                                "--where", "relative_path='Pictures/ShieldProbe/'")
        preserved = set(json.loads((OUT / "integration-preservation.json").read_text())["media"])
        for ident in map(int, re.findall(r"_id=(\d+)", existing)):
            check(ident not in preserved, "Preexisting ShieldProbe fixture would be overwritten")
            self.d.shell("content", "delete", "--uri", MEDIA + "/" + str(ident))
        for name in ("ordinary_probe.png", "Screenshot_probe.png",
                     "ordinary_event.png", "Screenshot_event.png"):
            self.d.shell("rm", "-f", DIRECTORY + name)
        self.d.shell("screencap", "-p", DIRECTORY + "ordinary_probe.png")
        self.d.shell("cp", DIRECTORY + "ordinary_probe.png", DIRECTORY + "Screenshot_probe.png")
        for name in ("ordinary_probe.png", "Screenshot_probe.png"):
            self.d.shell("content", "call", "--uri", "content://media", "--method", "scan_file",
                         "--arg", DIRECTORY.replace("/sdcard/", "/storage/emulated/0/") + name)

    def state_assert(self, value, enabled, injected=True, loaded=True):
        marker = value["module"]
        check(marker["injected"] == injected, "Injection differs")
        if injected:
            check(marker["policyLoaded"] == loaded and set(marker["enabled"]) == set(enabled), "Policy differs")
            check(marker["futureMethodEnabled"], "Future method default lost")
        for key, method, raw in (("development_settings_enabled", "developer", 1),
                                 ("adb_enabled", "debug", 1), ("adb_wifi_enabled", "debug", 0)):
            expected = 0 if method in enabled and injected else raw
            for suffix in ("global", "float", "long", "call", "clientCall"):
                check(str(value[key + "." + suffix]) in (str(expected), str(float(expected))),
                      key + "." + suffix + " differs: " + str(value[key + "." + suffix]))
            for suffix in ("query", "valueOnly", "bundleQuery"):
                cursor = value[key + "." + suffix]
                check(isinstance(cursor, dict) and cursor["value"] == str(expected), key + "." + suffix + " failed")
                for kind in ("int", "long", "float"):
                    check(cursor[kind] == expected, key + " numeric cursor read failed")
                check(cursor["columns"] == (["name", "value"] if suffix == "query" else ["value"]),
                      "Projection was changed")
            raw_other = {
                "development_settings_enabled": {"secure": "1", "system": None},
                "adb_enabled": {"secure": "1", "system": "1"},
                "adb_wifi_enabled": {"secure": None, "system": None},
            }
            for table in ("secure", "system"):
                expected_other = "0" if method in enabled and injected else raw_other[key][table]
                check(value.get(key + "." + table) == expected_other, key + "." + table + " differs")
        for phase in value["lifecycle"].values():
            check(phase["injected"] == injected, "Early lifecycle not injected")
            check(phase["developer"] == (0 if injected and "developer" in enabled else 1), "Early developer differs")
            check(phase["debug"] == (0 if injected and "debug" in enabled else 1), "Early debug differs")
        # Enforcing can deny this UID access to enforce: the original Java API
        # then returns false and libselinux returns -1. Compare the actual APIs;
        # the dedicated SELinux suite separately checks un-injected baselines.
        expected_selinux = (injected and "selinux" in enabled) or (
            value["selinux"]["native"]["security_getenforce"] == "1")
        check(value["selinux"]["javaEnforced"] is expected_selinux, "SELinux Java/native results differ")
        vpn = injected and "vpn" in enabled
        check(value["vpnNetworks"] == (0 if vpn else 1), "VPN enumeration differs")
        for key in ("activeVpn", "parcelVpn", "callbackVpn", "legacyVpn", "tunByName", "linkTextTunnel"):
            check(value[key] is (not vpn), key + " differs: " + str(value[key]))
        check(value["activeNotVpn"] is vpn, "NOT_VPN capability differs")
        check(("tun0" in value["interfaces"]) is (not vpn), "Java tunnel list differs")
        check(("tun0" in value["native"]["interfaces"]) is (not vpn), "Native tunnel list differs")
        check(value["native"]["listLifetimeOk"] and value["native"]["getpidOk"], "Native lifetime/control failed")
        check("wlan0" in value["interfaces"] and value["networks"] and value["wifiTransport"], "Ordinary network missing")
        proxy = injected and "proxy" in enabled
        for key in ("hostVisible", "portVisible", "bulkHostVisible"):
            check(value["proxyFixture"][key] is (not proxy), "Proxy metadata differs")
        check(value["proxyFixture"]["response"] == 204 and value["proxyFixture"]["actualHttpProxyUsed"], "Real proxy broken")
        check(value["internet"] == 204, "Ordinary HTTPS failed")
        debug = injected and "debug" in enabled
        check(value["init.svc.adbd.java"] == ("stopped" if debug else "running"), "Java adbd differs")
        for suffix in ("get", "read", "callback"):
            check(value["native"]["init.svc.adbd." + suffix] == ("stopped" if debug else "running"), "Native adbd differs")
            for key in ("sys.usb.config", "sys.usb.state"):
                check(("adb" in value["native"][key + "." + suffix]) is (not debug), "Native USB differs")
            check(value["native"]["ro.build.version.sdk." + suffix] == "36", "Ordinary property changed")
        for key in ("sys.usb.config", "sys.usb.state"):
            check(("adb" in value[key + ".java"]) is (not debug), "Java USB differs")
        for source in (value["service.adb.tcp.port.java"], value["native"]["service.adb.tcp.port.get"]):
            check(source == ("-1" if debug else ""), "Debug port property differs")
        check(value["ro.build.version.sdk.java"] == "36", "Ordinary Java property changed")
        check(value["activeInfoConnected"], "Legacy ordinary network state lost")
        check(value["proxyFixture"]["ordinaryProperty"], "Ordinary proxy-independent property lost")
        check(value["airplane_mode_on.global"] == 0, "Ordinary setting changed")
        if loaded:
            for operation in ("foreignRead", "write", "otherPackage", "insert", "update", "delete", "query"):
                check(value[operation + "Denied"] is True, "Policy isolation failed: " + operation)

    def shot_assert(self, value, hidden):
        check("startup_error" not in value and "inspect_error" not in value, "Probe error: " + str(value))
        check(value.get("raw_binder_registered") is True, "Raw Binder not registered: " + str(value.get("raw_binder_error")))
        native = value["native"]
        for kind in ("screenshot", "normal"):
            expected = not hidden or kind == "normal"
            for key in ("java_" + kind + "_exists", "java_" + kind + "_open", "nio_" + kind + "_exists"):
                check(value[key] is expected, key + " differs")
            for key in ("open", "syscall_open", "stat", "access", "readdir", "fopen", "openat",
                        "syscall_getdents", "syscall_stat"):
                check(native[key + "_" + kind] is expected, key + "_" + kind + " differs")
            check(native["fixture_fd_" + kind], "No independent FD fixture")
            for key in ("fd_read", "fd_pread", "fd_readv", "fd_preadv", "fd_fstat", "fd_syscall_read",
                        "fd_mmap", "fd_dup_pread", "procfd_open", "procfd_realpath", "procroot_open",
                        "symlink_open", "libc_statx", "fd_syscall_statx", "procfd_syscall_readlink"):
                check(native[key + "_" + kind] is expected, key + "_" + kind + " differs")
        for key in ("syscall_getpid_ok", "syscall_six_arguments_ok"):
            check(native[key], key + " failed")
        if native["clone_new_stack_supported"]:
            check(native["clone_new_stack_ok"], "clone control failed")
        for key in ("media_legacy_count", "media_bundle_count", "media_client_count", "media_id_only_count"):
            check(value[key] == (1 if hidden else 2), key + " differs: " + str(value[key]))
        for key in ("notification_screenshot", "accessibility_screenshot"):
            check(value[key] == (0 if hidden else 1), key + " differs")
        for key in ("notification_normal", "accessibility_normal", "accessibility_package_name_control"):
            check(value[key] == 1, key + " differs")
        for key in ("clipboard_screenshot_visible", "clipboard_screenshot_description", "clipboard_screenshot_has"):
            check(value[key] is (not hidden), key + " differs")
        check(value["clipboard_normal_visible"], "Ordinary clipboard hidden")

    def sample(self, pkg, enabled, injected=True, shot=True):
        value = self.d.start_probe(pkg)
        try:
            self.state_assert(value, enabled, injected)
        except AssertionError as error:
            error.probe_evidence = {"state": value}
            raise
        result = {"state": value}
        if shot:
            result["screenshot"] = self.d.start_probe(pkg, "shot")
            try:
                self.shot_assert(result["screenshot"], injected and "screenshot" in enabled)
            except AssertionError as error:
                error.probe_evidence = result
                raise
        return result

    def ui(self):
        d = self.d
        d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", "en")
        d.shell("settings", "put", "system", "accelerometer_rotation", "0")
        d.shell("settings", "put", "system", "user_rotation", "0")
        if not self.only:
            for pkg in list(self.policies()):
                self.remove(pkg)
        def opening():
            d.home_settings()
            nodes = d.nodes()
            check(not self.policies(), "First settings list not empty")
            check(any("All methods enabled" in n.get("text", "") for n in nodes), "Default explanation missing")
            check(not any("Planned" in n.get("text", "") for n in nodes), "Stale pending status")
            return {"empty": True, "defaultAll": True, "methodCount": len(METHODS)}
        self.case("U01", opening)
        def search():
            for query in ("App State", "screenshotdetector", "SCREENSHOTDETECTOR", "unmatched-application-123"):
                d.home_settings(); d.click("add-app"); d.click("app-search")
                d.shell("input", "text", query.replace(" ", "%s")); d.back()
                matches = [n.get("content-desc") for n in d.nodes() if n.get("content-desc", "").startswith("pick:")]
                check((bool(matches)) == (not query.startswith("unmatched")), "Search differs: " + query)
                check("pick:" + MODULE not in matches, "Module appears in picker")
            d.click("app-search")
            d.shell("input", "keyevent", "KEYCODE_MOVE_END")
            d.shell("input", "keyevent", *(["KEYCODE_DEL"] * len(query)))
            d.back()
            check(any(n.get("content-desc", "").startswith("pick:") for n in d.nodes()), "Clear search did not reset")
            d.home_settings(); d.click("add-app"); d.click("app-search")
            d.shell("input", "text", "com.android.settings"); d.back()
            check(not any(n.get("content-desc") == "pick:com.android.settings" for n in d.nodes()), "System filter off failed")
            d.click("show-system"); d.find("pick:com.android.settings")
            return {"namePackageCaseAndNoMatch": True, "clear": True, "selfExcluded": True, "systemFilter": True}
        self.case("U02-U04", search)
        def drafts():
            d.home_settings(); d.picker(PRIMARY)
            check(d.find("method:vpn").get("checked") == "true", "New switch default false")
            d.click("cancel"); check(PRIMARY not in self.policies(), "Cancel saved app")
            d.home_settings(); d.picker(PRIMARY); d.click("method:vpn"); d.back()
            d.click("android:id/button2", "resource-id")
            check(d.find("method:vpn").get("checked") == "false", "Keep editing lost draft")
            d.click("cancel"); d.click("android:id/button1", "resource-id")
            d.find("add-app")
            check(PRIMARY not in self.policies(), "Discard saved app")
            d.home_settings(); d.picker(PRIMARY)
            check(d.find("method:vpn").get("checked") == "true", "Discard left draft behind")
            d.click("save")
            check(self.policies()[PRIMARY] == [], "Default customization not empty")
            d.home_settings(); d.picker(PRIMARY); d.click("save"); d.back()
            check(len(self.policies()) == 1, "Duplicate app")
            return {"cancel": True, "keepDraft": True, "discard": True, "savedAllEnabled": True, "singleEntry": True}
        self.case("U05-U09/U23", drafts)
        def edits():
            for enabled in ({"screenshot", "proxy", "debug", "selinux"}, {"vpn", "proxy", "debug", "selinux"}):
                d.set_policy(PRIMARY, enabled)
                check(set(self.policies()[PRIMARY]) == set(METHODS) - enabled, "Saved switches wrong")
                d.home_settings(); d.picker(PRIMARY)
                check(d.find("method:developer", scroll=True).get("checked") == "false", "Reopen differs")
            d.click("enable-all", scroll=True); d.click("save")
            check(self.policies()[PRIMARY] == [], "Enable-all failed")
            d.home_settings(); d.picker(PRIMARY); d.click("disable-all", scroll=True); d.click("save")
            check(set(self.policies()[PRIMARY]) == set(METHODS), "Disable-all failed")
            return {"replaceSavedValue": True, "enableAll": True, "disableAll": True}
        self.case("U10-U13", edits)
        def rotation():
            d.home_settings(); d.picker(PRIMARY); d.click("method:vpn")
            d.shell("settings", "put", "system", "accelerometer_rotation", "0")
            for rotation in (1, 0):
                d.shell("settings", "put", "system", "user_rotation", str(rotation))
                d.find("save")
                check(d.find("method:vpn", scroll=True).get("checked") == "true", "Rotated draft differs")
            d.shell("input", "keyevent", "HOME"); d.shell("am", "kill", MODULE)
            d.shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
            check(d.find("method:vpn").get("checked") == "true", "Background task recreation lost draft")
            d.home_settings(); d.picker(PRIMARY)
            check(d.find("method:vpn").get("checked") == "false", "Force-stop kept unsaved draft")
            d.click("cancel"); d.click("add-app")
            d.search("com.android.settings"); d.click("show-system")
            for rotation in (1, 0):
                d.shell("settings", "put", "system", "user_rotation", str(rotation))
                check(d.find("app-search").get("text") == "com.android.settings", "Rotated search lost")
                check(d.find("show-system").get("checked") == "true", "Rotated filter lost")
                d.find("pick:com.android.settings", scroll=True)
            return {"draftRotation": True, "processRecreation": True, "forceStopDiscard": True, "pickerRotation": True}
        self.case("U14-U16", rotation)
        def remove():
            d.home_settings(); d.picker(PRIMARY); d.click("method:vpn")
            d.click("remove-custom", scroll=True); d.click("android:id/button2", "resource-id")
            check(d.find("method:vpn", scroll=True).get("checked") == "true", "Cancelled removal lost draft")
            self.remove(PRIMARY)
            for pkg, enabled in ((PRIMARY, {"vpn"}), (B, {"debug"}), (C, {"proxy"})):
                d.set_policy(pkg, enabled)
            check(len(self.policies()) == 3, "Three app configurations missing")
            d.adb("uninstall", B)
            d.home_settings(); d.click("custom:" + B, scroll=True)
            check(any("uninstalled" in n.get("text", "") for n in d.nodes()), "Uninstalled app label missing")
            d.click("remove-custom", scroll=True); d.click("android:id/button1", "resource-id")
            d.find("add-app")
            check(B not in self.policies(), "Uninstalled customization not removed")
            d.adb("install", "--no-incremental", "-r", str(OUT / "Verifier-A.apk"))
            for perm in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_IMAGES"):
                d.shell("pm", "grant", B, "android.permission." + perm)
            d.shell("appops", "set", B, "MANAGE_EXTERNAL_STORAGE", "allow")
            return {"cancelRestore": True, "removeRestore": True, "multiApp": True, "uninstalledRemoval": True}
        self.case("U17-U20", remove)
        def layout():
            d.shell("settings", "put", "system", "font_scale", "1.5")
            for rotation in (1, 0):
                d.shell("settings", "put", "system", "user_rotation", str(rotation))
                d.home_settings(); d.picker(C); d.find("method:debug", scroll=True)
                node = d.find("save")
                x, y = d.center(node)
                check(x > 0 and y > 0, "Save button is outside screen")
                d.screenshot(OUT / ("settings-font-" + str(rotation) + ".png"))
                d.click("save")
            d.shell("settings", "put", "system", "font_scale", "1.0")
            return {"fontScale": 1.5, "landscapePortrait": True, "longPackage": C}
        self.case("U21", layout)
        def locales():
            before = self.policies(); results = {}
            for locale, title in (("en", "AppStateShield"), ("zh-Hans", "应用状态屏蔽"),
                                  ("zh-HK", "應用狀態屏蔽"), ("zh-MO", "應用狀態屏蔽"),
                                  ("zh-TW", "應用狀態屏蔽"), ("ja", "アプリ状態シールド")):
                d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", locale)
                d.home_settings()
                check(any(n.get("text") == title for n in d.nodes()), "Wrong localized title: " + locale)
                d.picker(PRIMARY); d.find("method:debug", scroll=True); d.find("save")
                check(self.policies() == before, "Locale change modified settings")
                results[locale] = True
            d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", "en")
            return results
        self.case("U22", locales)

    def write_pref(self, xml):
        self.d.shell("am", "force-stop", MODULE)
        path = OUT / "pref-fixture.xml"
        remote = "/data/local/tmp/appstate-pref-fixture.xml"
        try:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
                stream.write(xml)
            path.chmod(0o600)
            self.d.adb("push", str(path), remote)
            self.d.shell("chmod", "600", remote)
            self.d.shell("cp", remote, PREF)
        finally:
            path.unlink(missing_ok=True)
            self.d.shell("rm", "-f", remote)

    def localization(self):
        d = self.d
        catalog = json.loads((ROOT / "app/src/main/assets/settings-text.json").read_text())
        names = {"screenshot": ("截图状态", "Screenshot"), "vpn": ("VPN 状态", "VPN"),
                 "proxy": ("网络代理", "Network proxy"), "developer": ("开发者选项", "Developer options"),
                 "debug": ("USB / 无线调试", "USB / wireless debugging")}
        before = self.policies()
        def run():
            evidence = {}
            for locale in ("en", "zh-Hans", "zh-HK", "zh-MO", "zh-TW", "ja"):
                d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", locale)
                d.home_settings(); d.picker(PRIMARY)
                key = catalog["aliases"].get(locale, locale)
                translated = catalog["locales"].get(key, {})
                def text(pair):
                    return translated.get(pair[0], pair[0] if key == "zh" else pair[1])
                check(d.find("save").get("text") == text(("保存", "Save")), "Save translation differs")
                check(d.find("cancel").get("text") == text(("取消", "Cancel")), "Cancel translation differs")
                checked = {}
                for _ in range(6):
                    for node in d.nodes():
                        desc = node.get("content-desc", "")
                        if not desc.startswith("method:"): continue
                        method = desc.split(":", 1)[1]
                        check(node.get("text") == text(names[method]), "Method translation differs: " + locale + "/" + method)
                        checked[method] = node.get("text")
                    if len(checked) == len(METHODS): break
                    d.swipe_up()
                check(set(checked) == set(METHODS), "Not all localized switches were visible")
                check(self.policies() == before, "Language change altered a saved policy")
                evidence[locale] = checked
            return {"localizedLabels": evidence, "savedPoliciesUnchanged": True}
        try:
            self.case("U22-labels", run)
        finally:
            d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", "en")

    def entries(self):
        d = self.d
        d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", "en")
        def vector():
            d.shell("am", "force-stop", MODULE)
            d.shell("am", "force-stop", "org.matrix.vector.manager")
            d.shell("am", "start", "-W", "-n", "org.matrix.vector.manager/.ui.MainActivity")
            for _ in range(3):
                d.click("Modules", "text")
                try:
                    d.find("Search modules", "text")
                    break
                except AssertionError:
                    pass  # Startup can redraw Vector's navigation after the first tap.
            d.find("Search modules", "text")
            d.click("AppStateShield", "text")
            d.click("Open companion app")
            d.find("add-app")
            texts = [n.get("text", "") for n in d.nodes()]
            check("AppStateShield" in texts and VERSION + " · Vector" in texts, "Wrong module settings/version")
            check("All methods enabled by default" in texts, "Default explanation missing")
            d.screenshot(OUT / "vector-settings-entry.png")
            d.shell("input", "keyevent", "HOME")
            width, height = d.dimensions()
            d.shell("input", "swipe", width // 2, int(height * .82), width // 2, int(height * .25), 400)
            labels = [n.get("text") for n in d.nodes()]
            check("App State Verifier" in labels, "Verifier icon missing from the actual launcher drawer")
            check("AppStateShield" not in labels, "Main module icon appeared in launcher drawer")
            d.screenshot(OUT / "launcher-no-module-icon.png")
            return {"actualVectorModuleOpened": True, "companionActionOpenedSettings": True,
                    "settingsVersion": VERSION, "launcherVerifierPresent": True, "launcherModuleAbsent": True}
        self.case("P05", vector)
        def developer():
            d.shell("am", "force-stop", "com.android.settings")
            d.shell("am", "start", "-W", "-a", "android.settings.APPLICATION_DEVELOPMENT_SETTINGS")
            check(d.find("android:id/switch_widget", "resource-id").get("checked") == "true",
                  "Real developer options master switch is not enabled")
            d.find("USB debugging", "text", scroll=True)
            tree = ET.fromstring(d.shell("cat", d.ui_path))
            row = next(p for p in tree.iter("node") if any(c.get("text") == "USB debugging" for c in list(p)))
            check(any(c.get("resource-id", "").endswith("/switchWidget") and c.get("checked") == "true"
                      for c in row.iter("node")), "Real USB debugging switch is not enabled")
            shell_values = {"developer": d.shell("settings", "get", "global", "development_settings_enabled"),
                            "usb": d.shell("settings", "get", "global", "adb_enabled"),
                            "adbd": d.shell("getprop", "init.svc.adbd")}
            check(shell_values == {"developer": "1", "usb": "1", "adbd": "running"}, "Real shell baseline differs")
            d.screenshot(OUT / "system-usb-enabled.png")
            return {"actualSystemSettingsOpened": True, "masterChecked": True, "usbChecked": True,
                    "alreadyEnabledSwitchesPreserved": True, "shell": shell_values}
        self.case("D01-system-ui", developer)
        def typography():
            font = d.shell("settings", "get", "system", "font_scale")
            try:
                d.shell("settings", "put", "system", "font_scale", "1.5")
                for rotation in (1, 0):
                    d.shell("settings", "put", "system", "user_rotation", str(rotation))
                    d.home_settings(); d.picker(C)
                    d.screenshot(OUT / ("settings-title-" + str(rotation) + ".png"))
                return {"topOfEditorCaptured": True, "fontScale": 1.5, "portraitAndLandscape": True,
                        "longPackage": C}
            finally:
                d.shell("settings", "delete", "system", "font_scale") if font == "null" else d.shell("settings", "put", "system", "font_scale", font)
                d.shell("settings", "put", "system", "user_rotation", "0")
        self.case("U21-top-layout", typography)

    def navigation(self):
        d = self.d
        self.case("P07-clipboard-backup", self.preserve_clipboard)
        d.shell("cmd", "locale", "set-app-locales", MODULE, "--locales", "en")
        d.shell("settings", "put", "system", "accelerometer_rotation", "0")
        d.shell("settings", "put", "system", "user_rotation", "0")
        def recents():
            d.set_policy(PRIMARY, set(METHODS))
            d.home_settings(); d.picker(PRIMARY); d.click("method:vpn")
            before = d.shell("pidof", MODULE)
            d.shell("input", "keyevent", "HOME")
            deadline = time.monotonic() + 10
            stopped = False
            while time.monotonic() < deadline:
                blocks = re.split(r"\* Hist\s+#", d.shell("dumpsys", "activity", "activities"))
                stopped = any(MODULE + "/.SettingsActivity" in block and
                              "packageName=" + MODULE in block and "state=STOPPED" in block and
                              "mHaveState=true" in block for block in blocks)
                if stopped: break
                time.sleep(.1)
            check(stopped, "Android did not finish saving the background activity")
            d.shell("am", "kill", MODULE)
            d.kill_reader(MODULE)  # A retained provider reference may keep am kill from ending this process.
            names = [row.split()[-1] for row in d.shell("ps", "-A", "-o", "NAME").splitlines()[1:]]
            check(MODULE not in names, "Background settings process was not killed")
            d.shell("input", "keyevent", "APP_SWITCH")
            candidates = [n for n in d.nodes()
                          if n.get("resource-id", "").endswith(("/snapshot", "/thumbnail"))
                          and n.get("content-desc") == "AppStateShield"]
            def visible_area(node):
                left, top, right, bottom = map(int, re.findall(r"\d+", node.get("bounds")))
                return (right - left) * (bottom - top)
            task = max(candidates, key=visible_area, default=None)
            check(task is not None, "No real recent-task thumbnail")
            d.tap(task)
            d.find("save")
            check(d.shell("pidof", MODULE) != before, "Recent task did not recreate process")
            check(d.find("method:vpn", scroll=True).get("checked") == "false", "Recent-task draft lost")
            d.home_settings(); d.picker(PRIMARY)
            check(d.find("method:vpn").get("checked") == "true", "Force-stop kept draft")
            return {"recentTaskClicked": True, "taskLabel": "AppStateShield",
                    "taskBounds": task.get("bounds"), "processRecreated": True,
                    "androidSavedStateBeforeKill": True,
                    "draftRestored": True, "forceStopUsesSaved": True}
        self.case("U16-recents", recents)
        def gesture():
            overlay = "com.android.internal.systemui.navbar.gestural"
            was_enabled = "[x] " + overlay in d.shell("cmd", "overlay", "list")
            d.shell("cmd", "overlay", "enable", "--user", "0", overlay)
            try:
                d.home_settings(); d.picker(PRIMARY); d.click("method:vpn")
                check(d.shell("settings", "get", "secure", "navigation_mode") == "2", "Gesture navigation not active")
                width, height = d.dimensions()
                d.shell("input", "swipe", 2, height // 2, width // 3, height // 2, 400)
                d.find("android:id/button2", "resource-id")
                d.click("android:id/button2", "resource-id")
                check(d.find("method:vpn").get("checked") == "false", "Gesture back lost draft")
                d.click("cancel"); d.click("android:id/button1", "resource-id")
                check(self.policies()[PRIMARY] == [], "Gesture cancel altered saved settings")
                d.screenshot(OUT / "settings-gesture.png")
                return {"actualEdgeGesture": True, "unsavedConfirmation": True, "keepAndDiscard": True}
            finally:
                if not was_enabled: d.shell("cmd", "overlay", "disable", "--user", "0", overlay)
        self.case("U21-gesture", gesture)
        def repeated():
            for _ in range(3):
                d.home_settings(); d.picker(PRIMARY)
                x, y = d.center(d.find("save"))
                d.shell("input", "tap", x, y); d.shell("input", "tap", x, y)
                d.find("add-app"); d.back()
            check(self.policies()[PRIMARY] == [], "Repeat-save changed policy")
            check(list(self.policies()).count(PRIMARY) == 1, "Repeat-save duplicated app")
            return {"threeRepeatedSelections": True, "doubleTapSave": True, "singleEntry": True}
        self.case("U23-repeat", repeated)
        def reinstalled_default():
            check(B not in self.policies(), "Reinstalled app inherited removed customization")
            d.scope(MODULE, B, False)  # Rebind Vector's cached scope to the post-install UID.
            d.scope(MODULE, B, True)
            return {"scopeReboundAfterReinstall": True, "target": self.sample(B, set(METHODS))}
        self.case("U20-reinstalled-default", reinstalled_default)

    def exceptional(self):
        d = self.d
        self.fixtures()
        before = d.shell("cat", PREF)
        try:
            def corrupt():
                self.write_pref('<map><string name="apps">broken-json</string></map>')
                d.home_settings()
                check(not any(n.get("content-desc", "").startswith("custom:") for n in d.nodes()),
                      "Corrupt JSON did not render the default page")
                return {"invalidJsonFixture": True, "settingsUsesDefaults": True,
                        "target": self.sample(PRIMARY, set(METHODS))}
            self.case("I03", corrupt)
            def unknown():
                tree = ET.fromstring(before)
                node = tree.find("string[@name='apps']")
                policies = json.loads(node.text)
                policies[PRIMARY] = ["unknown-disabled"]
                node.text = json.dumps(policies)
                self.write_pref(ET.tostring(tree, encoding="unicode"))
                value = self.sample(PRIMARY, set(METHODS))
                d.set_policy(PRIMARY, set(METHODS) - {"vpn"})
                check("unknown-disabled" in self.policies()[PRIMARY], "Unknown ID lost by UI save")
                check(set(self.policies()[PRIMARY]) == {"unknown-disabled", "vpn"}, "Known switch edit differs")
                return {"initial": value, "disabled": self.policies()[PRIMARY]}
            self.case("I04", unknown)
        finally:
            self.write_pref(before)
        def unavailable():
            d.set_policy(PRIMARY, set())
            d.shell("am", "force-stop", MODULE)
            restarted = self.sample(PRIMARY, set())
            d.shell("pm", "disable", MODULE + "/.PolicyProvider")
            try:
                value = d.start_probe(PRIMARY)
                self.state_assert(value, set(METHODS), loaded=False)
                shot = d.start_probe(PRIMARY, "shot"); self.shot_assert(shot, True)
                return {"forceStoppedProviderRestarted": restarted, "state": value, "screenshot": shot}
            finally:
                d.shell("pm", "enable", MODULE + "/.PolicyProvider")
        self.case("I05", unavailable)
        def native():
            results = {}
            for enabled in (set(), {"developer"}, {"debug"}, {"vpn"}, {"proxy"}, {"screenshot"}, {"selinux"}, set(METHODS)):
                d.set_policy(PRIMARY, enabled)
                value = d.start_probe(PRIMARY)
                self.state_assert(value, enabled)
                actual = {name[3:-3] for name in value["native"]["protectionLibraries"]}
                expected = {lib for method, lib in (("screenshot", "shield"), ("vpn", "vpnstate"),
                            ("debug", "developerstate"), ("selinux", "selinuxstate")) if method in enabled}
                check(actual == expected, "Unselected native library loaded: " + str(actual))
                results[",".join(sorted(enabled))] = sorted(actual)
            policies = self.policies()
            d.adb("install", "--no-incremental", "-r", str(OUT / f"AppStateShield-{VERSION}.apk"))
            d.adb("install", "--no-incremental", "-r", str(OUT / f"AppStateVerifier-{VERSION}.apk"))
            check(self.policies() == policies, "Upgrade lost policies")
            value = self.sample(PRIMARY, set(METHODS))
            return {"libraries": results, "upgradePolicyPreserved": True, "final": value}
        self.case("I01-I02/I06", native)
        def selinux_evidence():
            path = ROOT / "verification" / f"selinux-{VERSION}-results.json"
            evidence = json.loads(path.read_text())
            for name in ("L02-unscoped-permissive", "L03-all-off", "L04-selinux-only", "L05-all-on",
                         "L06-enforcing-baseline", "L06-enforcing-all-off", "L07-enforcing-selinux-only"):
                check(evidence["cases"].get(name, {}).get("status") == "passed", "SELinux evidence missing: " + name)
            for name, digest in evidence["artifacts"].items():
                check(hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest,
                      "SELinux evidence belongs to another APK: " + name)
            return {"realSELinux": d.shell("getenforce"), "permissiveEvidence": str(path.relative_to(ROOT)),
                    "testedArtifactsMatch": True}
        self.case("I07", selinux_evidence)

    def fixture(self, pkg, command, uri=None):
        path = "/data/user/0/" + pkg + "/files/services-result.json"
        self.d.shell("rm", "-f", path)
        args = ["am", "start", "-W", "--activity-clear-top", "-n", pkg + "/io.github.lwtdzh.screenshotdetector.FixtureActivity",
                "--es", "command", command]
        if uri:
            args += ["--es", "uri", uri]
        self.d.shell(*args)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = subprocess.run(self.d.prefix + ["shell", "cat", path],
                                    capture_output=True, text=True, timeout=10)
            try:
                if result.returncode == 0:
                    return json.loads(result.stdout)
            except json.JSONDecodeError:
                pass
            if time.monotonic() < deadline:
                time.sleep(.2)
        raise TimeoutError("Fixture did not finish")

    def preserve_clipboard(self):
        d = self.d
        path = "/data/user/0/" + C + "/files/fixture-clipboard.bin"
        exists = d.shell("sh", "-c", "if test -f " + path + "; then echo yes; else echo no; fi") == "yes"
        if exists:
            return {"existingPrivateBackupRetained": True}
        scoped = any(row["APP_PACKAGE"] == C and row["USER_ID"] == 0 for row in d.cli("scope", "ls", MODULE))
        d.scope(MODULE, C, False)
        try:
            d.kill_reader(C)
            self.fixture(C, "clipboard-save")
            check(d.shell("sh", "-c", "if test -f " + path + "; then echo yes; else echo no; fi") == "yes",
                  "Clipboard backup was not created")
            return {"privateBackupCreated": True, "unhookedSender": True}
        finally:
            d.scope(MODULE, C, scoped)

    def detector(self):
        d = self.d
        preservation = OUT / "integration-preservation.json"
        original = json.loads(preservation.read_text())
        if "verifier_locale" not in original:
            original["verifier_locale"] = d.shell("cmd", "locale", "get-app-locales", PRIMARY)
            preservation.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n")
        d.shell("cmd", "locale", "set-app-locales", PRIMARY, "--locales", "en")
        component = PRIMARY + "/.AccessibilityDetector"
        listener = PRIMARY + "/.NotificationDetector"
        sources = {"official", "binder", "media_observer", "media_poll", "media_legacy", "media_client",
                   "file_observer", "file_poll", "native_inotify", "native_files", "native_syscall",
                   "accessibility_event", "accessibility_nodes"}
        d.scope(MODULE, C, False)
        d.kill_reader(C)
        d.shell("pm", "grant", C, "android.permission.POST_NOTIFICATIONS")
        d.shell("appops", "set", "--uid", C, "POST_NOTIFICATION", "allow")
        d.shell("appops", "set", C, "POST_NOTIFICATION", "allow")
        self.preserve_clipboard()
        def logs(pid):
            return d.adb("logcat", "-d", "--pid=" + pid, "-s", "ScreenshotDetector:I", "AndroidRuntime:E", "*:S")
        def counts(pid):
            from collections import Counter
            return dict(Counter(re.findall(r"DETECTED source=(\w+)", logs(pid))))
        def wait(predicate, message, seconds=25):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                value = predicate()
                if value: return value
                time.sleep(.2)
            raise AssertionError(message)
        def open_main(pid=None):
            from collections import Counter
            def ready_counts(current):
                return Counter(re.findall(r"source=(\w+) code=state_ready", logs(current)))
            if not pid:
                existing = d.shell("sh", "-c", "pidof " + PRIMARY + " || true").split()
                pid = existing[0] if existing else None
            before = ready_counts(pid) if pid else {}
            d.shell("am", "start", "-W", "--activity-clear-top", "-n", PRIMARY + "/.MainActivity")
            current = d.shell("pidof", PRIMARY).split()[0]
            if current != pid:
                before = {}
            wait(lambda: all(ready_counts(current)[source] > before.get(source, 0) for source in sources),
                 "Current detector generation not ready")
            return current
        d.shell("cmd", "notification", "allow_listener", listener)
        old = json.loads((OUT / "pretest-state.json").read_text())["services"]["enabled_accessibility_services"]
        services = component if old in ("", "null") else old + ":" + component
        d.shell("settings", "put", "secure", "enabled_accessibility_services", services)
        d.shell("settings", "put", "secure", "accessibility_enabled", "1")
        try:
            for hidden, stage in ((False, "disabled"), (True, "enabled"), (False, "disabled-restored")):
                def run():
                    d.set_policy(PRIMARY, {"screenshot"} if hidden else set())
                    d.kill_reader(PRIMARY)
                    pid = open_main()
                    d.click("clear_log")
                    before = counts(pid)
                    def newly_observed():
                        return {source: number - before.get(source, 0)
                                for source, number in counts(pid).items() if number > before.get(source, 0)}
                    initial_delivery = self.fixture(PRIMARY, "snapshot")
                    self.fixture(C, "notification-normal")
                    self.fixture(C, "notification-shot")
                    pid = open_main(pid)
                    delivered = self.fixture(PRIMARY, "snapshot")
                    normal_delta = delivered["notificationOrdinary"] - initial_delivery["notificationOrdinary"]
                    shot_delta = delivered["notificationScreenshot"] - initial_delivery["notificationScreenshot"]
                    check(normal_delta > 0, "New real ordinary notification not delivered")
                    check(shot_delta == 0 if hidden else shot_delta > 0,
                          "Real named screenshot notification differs")
                    pid = open_main(pid)
                    d.find("source-filter")
                    before = counts(pid)
                    before_shots = self.shots()
                    focus = [line for line in d.shell("dumpsys", "window").splitlines()
                             if "mCurrentFocus=" in line]
                    check(any(PRIMARY in line and "MainActivity" in line for line in focus),
                          "Screenshot log page was not foreground")
                    d.shell("input", "-d", "0", "keyevent", "SYSRQ")
                    wait(lambda: self.shots() != before_shots, "No SystemUI screenshot")
                    if not hidden:
                        wait(lambda: sources <= set(newly_observed()), "Some real sources did not observe screenshot")
                    else:
                        # Poll cycles must run after SystemUI's thumbnail overlay has disappeared.
                        wait(lambda: "com.android.systemui.screenshot" not in d.shell("dumpsys", "window", "windows"),
                             "Screenshot overlay did not finish", 15)
                    observed = newly_observed()
                    if hidden: check(not observed, "Real screenshot leaked: " + str(observed))
                    else: check(sources <= set(observed), "Missing screenshot sources")
                    current = self.fixture(PRIMARY, "snapshot")
                    check(current["notificationConnected"] and current["accessibilityConnected"], "Services not really connected")
                    check(current["notificationOrdinary"] > 0 and current["accessibilityOrdinary"] > 0, "Ordinary service events lost")
                    check(current["accessibilityScreenshot"] == 0 if hidden else current["accessibilityScreenshot"] > 0,
                          "Real accessibility event differs")
                    # SystemUI may omit a posted notification; record that separately from actual accessibility delivery.
                    rows = d.shell("content", "query", "--uri", MEDIA, "--projection", "_id",
                                   "--where", "_display_name='Screenshot_probe.png' AND relative_path='Pictures/ShieldProbe/'")
                    ident = re.search(r"_id=(\d+)", rows).group(1)
                    self.fixture(C, "clipboard-shot", MEDIA + "/" + ident)
                    shot_clip = self.fixture(PRIMARY, "snapshot")
                    check(shot_clip["clipboardVisible"] is (not hidden), "Real clipboard read differs")
                    self.fixture(C, "clipboard-normal")
                    normal_clip = self.fixture(PRIMARY, "snapshot")
                    check(normal_clip["clipboardVisible"] and normal_clip["clipboardHas"], "Ordinary clipboard lost")
                    check("FATAL EXCEPTION" not in logs(pid), "Detector crashed")
                    return {"systemSaved": True, "signals": observed, "services": current,
                            "namedNotifications": delivered,
                            "namedNotificationDelta": {"ordinary": normal_delta, "screenshot": shot_delta},
                            "systemUiNotificationDelta": current["notificationScreenshot"] - delivered["notificationScreenshot"],
                            "shotClipboardVisible": shot_clip["clipboardVisible"],
                            "normalClipboardVisible": normal_clip["clipboardVisible"]}
                self.case("X12-" + stage, run)
            def routes():
                pid = open_main()
                d.click("source-filter")
                # Choose official callback from the actual Spinner, then rotate.
                node = next(n for n in d.nodes() if n.get("text") in ("官方回调", "System callback"))
                d.tap(node)
                def official_selected():
                    spinner = next((n for n in d.nodes() if n.get("content-desc") == "source-filter"), None)
                    return spinner is not None and any(n.get("text") in ("官方回调", "System callback")
                                                       for n in spinner.iter("node"))
                wait(official_selected, "Official source selection did not settle", 8)
                for rotation in (1, 0):
                    d.shell("settings", "put", "system", "user_rotation", str(rotation))
                    wait(official_selected, "Source lost on rotation", 8)
                catalog = {n.get("name"): n.text for n in ET.parse(
                    ROOT / "verifier/src/main/res/values-en/strings.xml").getroot().findall("string")}
                keys = ["official", "binder", "media_observer", "media_poll", "media_legacy", "media_client",
                        "file_observer", "file_poll", "native_inotify", "native_files", "native_syscall",
                        "broadcast_dynamic", "broadcast_manifest", "clipboard", "notification_event",
                        "notification_list", "accessibility_event", "accessibility_nodes"]
                selected = []
                for key in ["all_sources"] + ["source_" + k for k in keys]:
                    d.click("source-filter")
                    d.click(catalog[key], "text", scroll=True)
                    selected.append(key)
                    d.click("restart", scroll=True)
                d.click("source-filter")
                d.click(catalog["all_sources"], "text", scroll=True)
                d.click("clear_log")
                d.shell("input", "keyevent", "HOME")
                pid = open_main(pid)
                d.click("restart", scroll=True)
                d.click("check_document", scroll=True)
                node = wait(lambda: next((n for n in d.nodes() if n.get("text") == "ordinary_probe.png"
                            or n.get("content-desc", "").startswith("ordinary_probe.png,")), None), "Picker unavailable")
                d.tap(node)
                wait(lambda: "READ_CHECK route=check_stream accessible=true" in logs(pid), "Log-page URI read missing")
                d.click("grant_notifications", scroll=True); d.back()
                d.click("grant_accessibility", scroll=True); d.back()
                check("FATAL EXCEPTION" not in logs(pid), "Log page navigation crashed")
                return {"rotationKeepsSource": True, "filterAndRestart": selected, "clear": True,
                        "backgroundResume": True, "systemPickerGrant": True, "permissionReturn": True}
            self.case("X13", routes)
        finally:
            self.fixture(C, "cancel-notification")
            self.fixture(C, "clipboard-restore")
            self.preserve_clipboard()  # Keep an unmodified original backup for the reboot probes.
            baseline_services = json.loads((OUT / "pretest-state.json").read_text())["services"]
            self.restore_services(baseline_services)

    def reboot(self):
        d = self.d
        expected = {PRIMARY: {"screenshot", "proxy", "debug"}, B: {"vpn", "developer"}, C: set(METHODS)}
        for pkg in (PRIMARY, B):
            d.set_policy(pkg, expected[pkg])
        if C in self.policies(): self.remove(C)
        for pkg in (PRIMARY, B, C):
            d.scope(MODULE, pkg, True)
        saved = self.policies()
        d.adb("reboot")
        d.adb("wait-for-device", timeout=60)
        deadline = time.monotonic() + 60
        while d.shell("getprop", "sys.boot_completed") != "1" and time.monotonic() < deadline:
            time.sleep(.5)
        check(d.shell("getprop", "sys.boot_completed") == "1", "Reboot timed out")
        d.adb("root"); d.adb("wait-for-device", timeout=30)
        d.shell("input", "keyevent", "WAKEUP"); d.shell("wm", "dismiss-keyguard")
        def wait_wifi():
            deadline = time.monotonic() + 60
            while True:
                links = d.shell("ip", "-brief", "link", "show")
                up = bool(re.search(r"^wlan0\s+UP\b", links, re.MULTILINE))
                connectivity = d.shell("dumpsys", "connectivity")
                validated = any(line.strip().startswith("NetworkAgentInfo{")
                                and "Transports: WIFI Capabilities:" in line
                                and re.search(r"\bVALIDATED\b", line)
                                for line in connectivity.splitlines())
                if up and validated:
                    return {"interfaceUp": True, "validatedSystemNetwork": True}
                check(time.monotonic() < deadline, "Wi-Fi not ready after reboot")
                time.sleep(.5)
        network_ready = wait_wifi()
        d.shell("am", "start", "-W", "--activity-clear-top", "-n", C + "/" + STATE_ACTIVITY, "--es", "action", "vpn-start")
        deadline = time.monotonic() + 15
        while "tun0" not in d.shell("ip", "link", "show") and time.monotonic() < deadline:
            time.sleep(.2)
        check("tun0" in d.shell("ip", "link", "show"), "VPN not recreated after reboot")
        wait_wifi()
        def run():
            check(self.policies() == saved, "Reboot lost settings")
            process = json.loads(d.shell("cat", "/data/user/0/" + C + "/files/vpn-result.json"))
            check(process["injected"] and process["policyLoaded"] and set(process["enabled"]) == set(METHODS),
                  "Independent :vpn process does not use its package defaults")
            results = {pkg: self.sample(pkg, enabled) for pkg, enabled in expected.items()}
            return {"policiesPreserved": True, "systemWifiReady": network_ready,
                    "vpnProcess": process, "targets": results}
        self.case("S10-S11", run)

    def networks(self):
        d = self.d
        self.fixtures()
        def lifetime():
            d.set_policy(PRIMARY, {"vpn"})
            return [self.sample(PRIMARY, {"vpn"}, shot=False) for _ in range(10)]
        self.case("V02-V07/V04-ten-cold-starts/D02-D07", lifetime)
        def restart():
            d.shell("am", "start", "-W", "--activity-clear-top", "-n", C + "/" + STATE_ACTIVITY, "--es", "action", "vpn-stop")
            deadline = time.monotonic() + 10
            while "tun0" in d.shell("ip", "link", "show") and time.monotonic() < deadline:
                time.sleep(.2)
            check("tun0" not in d.shell("ip", "link", "show"), "Stopping fixture did not release TUN")
            d.set_policy(PRIMARY, set())
            no_vpn = d.start_probe(PRIMARY)
            check(no_vpn["vpnNetworks"] == 0 and no_vpn["activeVpn"] is False and no_vpn["internet"] == 204,
                  "No-VPN baseline failed")
            d.shell("am", "start", "-W", "--activity-clear-top", "-n", C + "/" + STATE_ACTIVITY, "--es", "action", "vpn-start")
            deadline = time.monotonic() + 10
            while "tun0" not in d.shell("ip", "link", "show") and time.monotonic() < deadline:
                time.sleep(.2)
            restored = self.sample(PRIMARY, set())
            d.set_policy(PRIMARY, {"vpn"})
            hidden = self.sample(PRIMARY, {"vpn"})
            return {"stopped": no_vpn, "restarted": restored, "protected": hidden}
        self.case("V08", restart)
        def wireless():
            original = d.shell("settings", "get", "global", "adb_wifi_enabled")
            try:
                d.shell("settings", "put", "global", "adb_wifi_enabled", "1")
                d.set_policy(PRIMARY, set())
                value = d.start_probe(PRIMARY)
                actual = d.shell("settings", "get", "global", "adb_wifi_enabled")
                maintained = actual == "1" and value["adb_wifi_enabled.global"] == 1
                protected = None
                if maintained:
                    d.set_policy(PRIMARY, {"debug"})
                    protected = d.start_probe(PRIMARY)
                    for suffix in ("global", "float", "long", "call", "clientCall"):
                        check(str(protected["adb_wifi_enabled." + suffix]) in ("0", "0.0"),
                              "Enabled wireless debugging was not hidden: " + suffix)
                    for suffix in ("query", "valueOnly", "bundleQuery"):
                        check(protected["adb_wifi_enabled." + suffix]["value"] == "0",
                              "Wireless debugging cursor was not hidden")
                    check(d.shell("settings", "get", "global", "adb_wifi_enabled") == "1",
                          "Blocking changed the real wireless debugging switch")
                return {"enabledBaselineMaintained": maintained, "shellValue": actual,
                        "appValue": value["adb_wifi_enabled.global"],
                        "protected": protected,
                        "interpretation": "开启状态已建立" if maintained else "未验证开启状态；模拟器自动恢复为零"}
            finally:
                d.shell("settings", "delete", "global", "adb_wifi_enabled") if original == "null" else d.shell("settings", "put", "global", "adb_wifi_enabled", original)
        self.case("D08", wireless)
        if (not self.only or "D08" in self.only) and not self.report["cases"]["D08"]["evidence"]["enabledBaselineMaintained"]:
            self.report["cases"]["D08"]["status"] = "platform-limited"
            self.save()

    def cleanup(self):
        d = self.d
        baseline = json.loads((OUT / "pretest-state.json").read_text())
        preserved = json.loads((OUT / "integration-preservation.json").read_text())
        def run():
            d.scope(MODULE, C, False)
            d.kill_reader(C)
            self.fixture(C, "cancel-notification")
            self.fixture(C, "clipboard-restore")
            d.shell("am", "start", "-W", "--activity-clear-top", "-n", C + "/" + STATE_ACTIVITY, "--es", "action", "vpn-stop")
            d.shell("am", "force-stop", C)
            check("tun0" not in d.shell("ip", "link", "show"), "Fixture TUN still present")
            for key, value in baseline["settings"].items():
                d.shell("settings", "delete", "global", key) if value == "null" else d.shell("settings", "put", "global", key, value)
            for key, value in baseline["rotation"].items():
                d.shell("settings", "put", "system", key, value)
            self.restore_services(baseline["services"])
            for row in baseline["modules"]:
                pkg = row["PACKAGE"]
                expected = {(r["APP_PACKAGE"], r["USER_ID"]) for r in baseline["scopes"][pkg]}
                current = {(r["APP_PACKAGE"], r["USER_ID"]) for r in d.cli("scope", "ls", pkg)}
                for target, user in current - expected:
                    d.cli("scope", "rm", pkg, target + "/" + str(user))
                for target, user in expected - current:
                    d.cli("scope", "add", pkg, target + "/" + str(user))
                d.cli("modules", "enable" if row["STATUS"] == "enabled" else "disable", pkg)
                check({(r["APP_PACKAGE"], r["USER_ID"]) for r in d.cli("scope", "ls", pkg)} == expected, "Scope restore failed")
                saved_status = next(r["STATUS"] for r in d.cli("modules", "ls") if r["PACKAGE"] == pkg)
                check(saved_status == row["STATUS"], "Module enabled state restore failed")
            self.write_pref(preserved["pref"])
            original_node = ET.fromstring(preserved["pref"]).find("string[@name='apps']")
            original_policies = json.loads(original_node.text if original_node is not None else "{}")
            check(self.policies() == original_policies, "Original customizations were not restored")
            if not any(row["PACKAGE"] == MODULE for row in baseline["modules"]):
                for pkg in (PRIMARY, B, C): d.scope(MODULE, pkg, False)
                d.cli("modules", "disable", MODULE)
            ordinary = d.start_probe(PRIMARY)
            check(ordinary["internet"] == 204 and ordinary["vpnNetworks"] == 0,
                  "Ordinary internet failed after stopping the test VPN")
            original_ids = set(preserved["media"])
            added = self.shots() - original_ids
            for ident in added: d.shell("content", "delete", "--uri", MEDIA + "/" + str(ident))
            check(original_ids <= self.shots(), "Original images missing")
            for name in ("ordinary_probe.png", "Screenshot_probe.png", "ordinary_event.png", "Screenshot_event.png"):
                d.shell("rm", "-f", DIRECTORY + name)
            for temp in (d.ui_path, "/data/local/tmp/appstate-pref-fixture.xml"):
                d.shell("rm", "-f", temp)
            font = preserved["font_scale"]
            d.shell("settings", "delete", "system", "font_scale") if font == "null" else d.shell("settings", "put", "system", "font_scale", font)
            for pkg, value in ((MODULE, preserved["app_locale"]),
                               (PRIMARY, preserved.get("verifier_locale", ""))):
                locales = re.search(r"\[(.*?)\]", value)
                selected = locales.group(1).replace(" ", "") if locales else ""
                args = ("--locales", selected) if selected else ()
                d.shell("cmd", "locale", "set-app-locales", pkg, *args)
            for perm in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_IMAGES"):
                if not re.search(r"android.permission." + perm + r": granted=true", preserved["permissions"][PRIMARY]):
                    d.shell("pm", "revoke", PRIMARY, "android.permission." + perm)
            mode = re.search(r"MANAGE_EXTERNAL_STORAGE: (\w+)", preserved["appops"][PRIMARY])
            d.shell("appops", "set", PRIMARY, "MANAGE_EXTERNAL_STORAGE", mode.group(1) if mode else "default")
            d.shell("am", "force-stop", PRIMARY)  # Releases temporary system-picker URI grants and live listeners.
            d.adb("uninstall", B); d.adb("uninstall", C)
            check(d.shell("settings", "get", "global", "hidden_api_policy") == baseline["settings"]["hidden_api_policy"], "Hidden API setting changed")
            settings_restored = {key: d.shell("settings", "get", "global", key) for key in baseline["settings"]}
            check(settings_restored == baseline["settings"], "Global settings restore differs")
            services_restored = {key: d.shell("settings", "get", "secure", key) for key in baseline["services"]}
            check(services_restored == baseline["services"], "Service state changed during cleanup")
            return {"settingsScopesServicesRestored": True, "originalImagesPreserved": True,
                    "newImagesDeleted": len(added), "samplesUninstalled": True, "fixtureVpnStopped": True,
                    "originalCustomizationsRestored": True,
                    "clipboardBackupRestored": True,
                    "ordinaryInternet": ordinary["internet"],
                    "settings": settings_restored, "services": services_restored}
        self.case("R01-R04", run)
        def capture_script():
            global OUT
            original_out = OUT
            original_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               (OUT / "pretest-state.json", OUT / "integration-preservation.json")}
            with tempfile.TemporaryDirectory(prefix=".capture-validation-", dir=OUT) as folder:
                try:
                    OUT = pathlib.Path(folder)
                    fresh = Manual()
                    fresh.capture()
                    paths = (OUT / "pretest-state.json", OUT / "integration-preservation.json")
                    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
                    check(all(p.stat().st_mode & 0o777 == 0o600 for p in paths), "Snapshot permissions differ")
                    try:
                        fresh.capture()
                        raise AssertionError("Capture overwrote existing snapshots")
                    except AssertionError as error:
                        check("Existing snapshots" in str(error), "Unexpected capture rejection")
                    check(hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                          "Rejected capture changed a snapshot")
                finally:
                    OUT = original_out
            check(original_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  (OUT / "pretest-state.json", OUT / "integration-preservation.json")}, "Original backups changed")
            return {"freshReadOnlyCapture": True, "mode600": True, "overwriteRejected": True,
                    "originalSnapshotsUnchanged": True, "temporaryCaptureDeleted": True}
        self.case("P03-capture-script", capture_script)

    def shutdown(self):
        def devices():
            output = subprocess.check_output([self.d.prefix[0], "devices"], text=True)
            return {row.split()[0]: row.split()[1] for row in output.splitlines()[1:] if len(row.split()) >= 2}
        def run():
            before = devices()
            check("emulator-5584" in before, "Dedicated AVD is not connected")
            response = self.d.adb("emu", "kill")
            deadline = time.monotonic() + 20
            after = devices()
            while "emulator-5584" in after and time.monotonic() < deadline:
                time.sleep(.2)
                after = devices()
            check("emulator-5584" not in after, "Dedicated AVD did not close")
            check({k: v for k, v in before.items() if k != "emulator-5584"} == after,
                  "Other connected device states changed")
            return {"quitAccepted": "OK" in response, "dedicatedAvdDisconnected": True,
                    "otherDeviceStatesUnchanged": True}
        self.case("R05", run)

    def matrix(self, first, last):
        self.fixtures()
        self.case("P07-clipboard-backup", self.preserve_clipboard)
        for number in range(first, last + 1):
            bits = format(number, "06b")
            enabled = {key for key, bit in zip(METHODS, bits) if bit == "1"}
            def run():
                self.d.set_policy(PRIMARY, enabled)
                return self.sample(PRIMARY, enabled)
            self.case("M" + bits, run)

    def deep(self):
        for enabled, stage in ((False, "disabled"), (True, "enabled"), (False, "disabled-restored")):
            def run():
                self.fixtures()
                self.d.set_policy(PRIMARY, {"screenshot"} if enabled else set())
                value = self.d.start_probe(PRIMARY, "shot")
                self.shot_assert(value, enabled)
                for name in ("Screenshot_event.png", "ordinary_event.png"):
                    self.d.shell("touch", DIRECTORY + name)
                media_before = self.d.read_shot(PRIMARY)["media_callbacks"]
                self.d.shell("content", "insert", "--uri", MEDIA, "--bind", "_display_name:s:Screenshot_signal.png",
                             "--bind", "relative_path:s:Pictures/ShieldProbe/", "--bind", "mime_type:s:image/png")
                deadline = time.monotonic() + (1 if enabled else 5)
                while time.monotonic() < deadline:
                    observed = self.d.read_shot(PRIMARY)["media_callbacks"]
                    if not enabled and observed > media_before: break
                    time.sleep(.1)
                media_after_shot = self.d.read_shot(PRIMARY)["media_callbacks"]
                self.d.shell("content", "insert", "--uri", MEDIA, "--bind", "_display_name:s:ordinary_signal.png",
                             "--bind", "relative_path:s:Pictures/ShieldProbe/", "--bind", "mime_type:s:image/png")
                deadline = time.monotonic() + 5
                while self.d.read_shot(PRIMARY)["media_callbacks"] <= media_after_shot and time.monotonic() < deadline:
                    time.sleep(.1)
                for action in ("SCREENSHOT", "NORMAL"):
                    self.d.shell("am", "broadcast", "-a", "shieldprobe." + action, "-p", PRIMARY)
                    self.d.shell("am", "broadcast", "-a", "shieldprobe.MANIFEST_" + action,
                                 "-n", PRIMARY + "/io.github.lwtdzh.screenshotprobe.ManifestReceiver")
                self.d.shell("am", "start", "-W", "--activity-single-top", "-n",
                             PRIMARY + "/" + SHOT_ACTIVITY, "--es", "command", "drain")
                value = self.d.read_shot(PRIMARY)
                # am broadcast returning does not mean onReceive has run.
                # Refresh the diagnostic snapshot until all expected positive
                # controls arrive; the native drain result remains intact.
                positive = [prefix + kind + "_events"
                            for prefix in ("file_", "broadcast_", "manifest_")
                            for kind in ("screenshot", "normal")
                            if not (enabled and kind == "screenshot")]
                deadline = time.monotonic() + 5
                while any(value[key] <= 0 for key in positive) and time.monotonic() < deadline:
                    self.d.shell("am", "start", "-W", "--activity-single-top", "-n",
                                 PRIMARY + "/" + SHOT_ACTIVITY, "--es", "command", "inspect")
                    value = self.d.read_shot(PRIMARY)
                check(value["media_callbacks"] > media_after_shot, "Ordinary provider notification was lost")
                check(media_after_shot == media_before if enabled else media_after_shot > media_before,
                      "Screenshot provider notification differs")
                for kind in ("screenshot", "normal"):
                    hidden = enabled and kind == "screenshot"
                    for prefix in ("file_", "broadcast_", "manifest_"):
                        count = value[prefix + kind + "_events"]
                        check(count == 0 if hidden else count > 0, prefix + kind + " events differ")
                    count = value["native_watch"][kind + "_events"]
                    check(count == 0 if hidden else count > 0, "inotify differs")
                for kind, filename in (("screenshot", "Screenshot_probe.png"), ("normal", "ordinary_probe.png")):
                    self.d.shell("am", "start", "-W", "--activity-single-top", "-n", PRIMARY + "/" + SHOT_ACTIVITY,
                                 "--es", "command", "pick_document", "--es", "doc_kind", kind)
                    chosen = False
                    for attempt in range(12):
                        node = next((n for n in self.d.nodes() if n.get("text") == filename
                                     or n.get("content-desc", "").startswith(filename + ",")), None)
                        if node is not None:
                            self.d.tap(node)
                            chosen = True
                            break
                    check(chosen, "System picker did not expose " + filename)
                    deadline = time.monotonic() + 10
                    value = self.d.read_shot(PRIMARY)
                    while "document_" + kind + "_open" not in value and time.monotonic() < deadline:
                        time.sleep(.1)
                        value = self.d.read_shot(PRIMARY)
                    check("document_" + kind + "_open" in value, "System picker callback did not finish")
                    hidden = enabled and kind == "screenshot"
                    check(value["document_" + kind + "_count"] == (0 if hidden else 1), "Document cursor differs")
                    check(value["document_" + kind + "_columns"] == 1, "Document projection changed")
                    check(value["document_" + kind + "_open"] is (not hidden), "Authorized document read differs")
                before = self.shots()
                self.d.shell("input", "-d", "0", "keyevent", "SYSRQ")
                deadline = time.monotonic() + 12
                while self.shots() == before and time.monotonic() < deadline:
                    time.sleep(.2)
                check(self.shots() != before, "SystemUI did not save screenshot")
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    value = self.d.read_shot(PRIMARY)
                    if not enabled and (value["screen_capture_callbacks"] > 0 and value["raw_screen_capture_callbacks"] > 0):
                        break
                    time.sleep(.2)
                for key in ("screen_capture_callbacks", "raw_screen_capture_callbacks"):
                    check(value[key] == 0 if enabled else value[key] > 0, key + " differs")
                return {"screenshotEnabled": enabled, "systemSaved": True, "probe": value,
                        "mediaBefore": media_before, "mediaAfterScreenshot": media_after_shot}
            self.case("X02-X11-" + stage, run)

    def media(self):
        for hidden, stage in ((False, "disabled"), (True, "enabled"), (False, "disabled-restored")):
            def run():
                self.fixtures()
                self.d.set_policy(PRIMARY, {"screenshot"} if hidden else set())
                self.d.start_probe(PRIMARY, "shot")
                evidence = []
                def observe(kind, operation, action):
                    before = self.d.read_shot(PRIMARY)["media_callbacks"]
                    result = action()
                    deadline = time.monotonic() + (1.5 if hidden and kind == "screenshot" else 5)
                    after = before
                    while time.monotonic() < deadline:
                        after = self.d.read_shot(PRIMARY)["media_callbacks"]
                        if not (hidden and kind == "screenshot") and after > before:
                            break
                        time.sleep(.1)
                    evidence.append({"kind": kind, "operation": operation, "before": before, "after": after,
                                     "providerResult": result})
                    try:
                        check(after == before if hidden and kind == "screenshot" else after > before,
                              kind + " MediaStore " + operation + " notification differs")
                    except AssertionError as error:
                        error.probe_evidence = {"screenshotEnabled": hidden, "realProviderMutations": evidence}
                        raise
                for kind, name in (("screenshot", "Screenshot_mutation.png"), ("ordinary", "ordinary_mutation.png")):
                    def insert():
                        self.d.shell("cp", DIRECTORY + "ordinary_probe.png", DIRECTORY + name)
                        return self.d.shell("content", "call", "--uri", "content://media", "--method", "scan_file",
                            "--arg", DIRECTORY.replace("/sdcard/", "/storage/emulated/0/") + name)
                    observe(kind, "insert", insert)
                    row = self.d.shell("content", "query", "--uri", MEDIA, "--projection", "_id",
                                       "--where", "_display_name='" + name + "' AND relative_path='Pictures/ShieldProbe/'")
                    ident = re.search(r"_id=(\d+)", row)
                    check(ident is not None, "Inserted mutation row missing")
                    item = MEDIA + "/" + ident.group(1)
                    observe(kind, "update", lambda: self.d.shell("content", "update", "--uri", item,
                            "--bind", "_display_name:s:" + name.replace(".png", "_updated.png")))
                    observe(kind, "delete", lambda: self.d.shell("content", "delete", "--uri", item))
                return {"screenshotEnabled": hidden, "realProviderMutations": evidence}
            self.case("X07-media-" + stage, run)

    def scope_cases(self):
        self.fixtures()
        def disabled():
            self.d.cli("modules", "disable", MODULE)
            try: return self.sample(PRIMARY, set(), False)
            finally: self.d.cli("modules", "enable", MODULE)
        self.case("S01", disabled)
        def outside():
            self.d.scope(MODULE, PRIMARY, False)
            try: return self.sample(PRIMARY, set(), False)
            finally: self.d.scope(MODULE, PRIMARY, True)
        self.case("S02/S07-S08", outside)
        def customization_outside():
            self.d.scope(MODULE, PRIMARY, False)
            self.d.set_policy(PRIMARY, {"vpn", "developer"})
            saved = self.policies()[PRIMARY]
            outside_value = self.sample(PRIMARY, set(), False)
            self.d.scope(MODULE, PRIMARY, True)
            scoped_value = self.sample(PRIMARY, {"vpn", "developer"})
            self.d.scope(MODULE, PRIMARY, False)
            removed_value = self.sample(PRIMARY, set(), False)
            check(self.policies()[PRIMARY] == saved, "Removing scope changed customization")
            self.d.scope(MODULE, PRIMARY, True)
            return {"outside": outside_value, "addedScope": scoped_value, "removedScope": removed_value,
                    "customizationPreserved": True}
        self.case("S07-S08", customization_outside)
        self.d.set_policy(PRIMARY, set(METHODS))
        self.remove(PRIMARY)
        self.case("S03", lambda: self.sample(PRIMARY, set(METHODS)))
        self.d.set_policy(PRIMARY, set(METHODS))
        self.case("S04", lambda: self.sample(PRIMARY, set(METHODS)))
        self.d.set_policy(PRIMARY, set())
        self.case("S05", lambda: self.sample(PRIMARY, set()))
        def timing():
            old = self.d.start_probe(PRIMARY)
            self.d.set_policy(PRIMARY, set(METHODS))
            live = self.d.start_probe(PRIMARY, cold=False)
            check(live["module"]["enabled"] == old["module"]["enabled"], "Changed live process")
            fresh = self.d.start_probe(PRIMARY)
            self.state_assert(fresh, set(METHODS))
            return {"old": old["module"], "live": live["module"], "fresh": fresh["module"]}
        self.case("S06/S09", timing)
        self.d.set_policy(PRIMARY, {"screenshot", "proxy", "debug"})
        self.d.set_policy(B, {"vpn", "developer"})
        self.d.scope(MODULE, C, True)
        if C in self.policies(): self.remove(C)
        self.case("M33/S10", lambda: {p: self.sample(p, e) for p, e in (
            (PRIMARY, {"screenshot", "proxy", "debug"}), (B, {"vpn", "developer"}), (C, set(METHODS)))})
        self.d.set_policy(PRIMARY, {"vpn", "developer"})
        self.case("M34", lambda: {p: self.sample(p, e) for p, e in (
            (PRIMARY, {"vpn", "developer"}), (B, {"vpn", "developer"}), (C, set(METHODS)))})
        self.remove(PRIMARY)
        self.case("M35", lambda: {p: self.sample(p, e) for p, e in (
            (PRIMARY, set(METHODS)), (B, {"vpn", "developer"}), (C, set(METHODS)))})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["capture", "prepare", "packaging", "entries", "navigation", "localization", "matrix", "deep", "media", "scope", "ui", "exceptional", "detector", "reboot", "networks", "cleanup", "shutdown"])
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--last", type=int, default=63)
    parser.add_argument("--case", action="append", default=[], help="Run only named cases; retain prerequisite state")
    args = parser.parse_args()
    manual = Manual()
    manual.only = set(args.case)
    if args.phase == "matrix": manual.matrix(args.first, args.last)
    else: getattr(manual, args.phase if args.phase != "scope" else "scope_cases")()
    check(manual.only <= manual.visited, "Case names do not belong to this phase: " + str(manual.only - manual.visited))


if __name__ == "__main__":
    main()
