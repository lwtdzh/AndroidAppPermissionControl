#!/usr/bin/env python3
"""SELinux 0.3.0 validation on the dedicated AVD; private snapshots stay outside git."""
import argparse
import hashlib
import json
import os
import pathlib
import time
import xml.etree.ElementTree as ET
from test_device import Device, METHODS, MODULE, PRIMARY

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/selinux-0.3.0"
PREF = "/data/user/0/" + MODULE + "/shared_prefs/policies.xml"
B = PRIMARY + ".samplea"
C = PRIMARY + ".sampleb.screenshot"
TARGETS = [PRIMARY, B, C]
FIXTURE = "/sdcard/Pictures/SELinuxShieldProbe"


def check(ok, message):
    if not ok:
        raise AssertionError(message)


class Run:
    def __init__(self):
        self.d = Device()
        self.path = OUT / "selinux-0.3.0-results.json"
        self.policy_boxes = {}
        self.policy_save = None
        self.enforcing_baseline = None
        self.report = json.loads(self.path.read_text()) if self.path.exists() else {"cases": {}}
        self.report["artifacts"] = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
                                   for name in ("AppStateShield-0.3.0.apk", "AppStateVerifier-0.3.0.apk")}

    def case(self, name, action):
        print("START " + name, flush=True)
        try:
            evidence = action()
            value = {"status": "passed", "evidence": evidence}
        except Exception as error:
            value = {"status": "failed", "error": repr(error)}
            self.report["cases"][name] = value
            self.save()
            raise
        if name in self.report["cases"]:
            self.report.setdefault("previousRuns", {}).setdefault(name, []).append(self.report["cases"][name])
        self.report["cases"][name] = value
        self.save()
        print("PASS " + name, flush=True)

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")

    def capture(self):
        d = self.d
        check(not (STATE / "state.json").exists(), "Existing original snapshot must not be overwritten")
        check("tun0" not in d.shell("ip", "link", "show"), "An existing VPN must not be replaced")
        check(d.shell("sh", "-c", "test ! -e " + FIXTURE + " && echo absent") == "absent", "Fixture path exists")
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        modules = d.cli("modules", "ls")
        settings = {key: d.shell("settings", "get", "global", key)
                    for key in ("hidden_api_policy", "development_settings_enabled", "adb_enabled")}
        original = {"mode": d.shell("getenforce"), "settings": settings, "modules": modules,
                    "fontScale": d.shell("settings", "get", "system", "font_scale"),
                    "scopes": {m["PACKAGE"]: d.cli("scope", "ls", m["PACKAGE"]) for m in modules},
                    "packages": {}, "storageGranted": "android.permission.READ_EXTERNAL_STORAGE: granted=true" in
                    d.shell("dumpsys", "package", PRIMARY), "pref": d.shell("sh", "-c",
                        "test ! -f " + PREF + " || cat " + PREF)}
        installed = set(d.shell("pm", "list", "packages").splitlines())
        for pkg in [MODULE] + TARGETS:
            if "package:" + pkg not in installed:
                continue
            remote = d.shell("pm", "path", pkg)
            if remote:
                destination = STATE / (pkg + ".apk")
                d.adb("pull", remote.splitlines()[0].removeprefix("package:"), str(destination))
                destination.chmod(0o600)
                original["packages"][pkg] = str(destination)
        with os.fdopen(os.open(STATE / "state.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as out:
            json.dump(original, out)
        self.case("L00-capture", lambda: {"originalMode": original["mode"], "originalSaved": True,
                                        "serial": "emulator-5584", "sdk": d.shell("getprop", "ro.build.version.sdk"),
                                        "abi": d.shell("getprop", "ro.product.cpu.abi")})

    def prepare(self):
        d = self.d
        check((STATE / "state.json").exists(), "Capture the original state before installation")
        for pkg, name in [(MODULE, "AppStateShield-0.3.0.apk"), (PRIMARY, "AppStateVerifier-0.3.0.apk"),
                          (B, "Verifier-A-0.3.0.apk"), (C, "Verifier-B-0.3.0.apk")]:
            d.adb("install", "--no-incremental", "-r", str(OUT / name))
        for m in d.cli("modules", "ls"):
            for pkg in TARGETS:
                d.scope(m["PACKAGE"], pkg, False)
        d.cli("modules", "enable", MODULE)
        d.scope(MODULE, PRIMARY, True)
        d.scope(MODULE, B, True)
        d.shell("settings", "put", "global", "hidden_api_policy", "1")
        d.shell("settings", "put", "global", "development_settings_enabled", "1")
        check(d.shell("settings", "get", "global", "adb_enabled") == "1", "No real USB debugging baseline")
        d.shell("mkdir", "-p", FIXTURE)
        for name in ("ordinary_control.txt", "Screenshot_control.txt"):
            d.shell("sh", "-c", "printf 0 > " + FIXTURE + "/" + name)
        for pkg in TARGETS:
            for permission in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"):
                d.shell("pm", "grant", pkg, "android.permission." + permission)
        d.shell("am", "force-stop", C)
        d.shell("am", "start", "-W", "-n", C + "/io.github.lwtdzh.devicestateprobe.ProbeActivity",
                "--es", "action", "vpn-start")
        consent = next((n for n in d.nodes() if n.get("resource-id") == "android:id/button1"), None)
        if consent is not None:
            d.tap(consent)
        deadline = time.monotonic() + 10
        while "tun0" not in d.shell("ip", "link", "show") and time.monotonic() < deadline:
            time.sleep(.2)
        check("tun0" in d.shell("ip", "link", "show"), "No real VPN baseline")
        self.case("L01-prepare", lambda: {"realVpn": True, "realUsbDebug": True, "fixture": "constructed file",
                                        "installedSha256": {
                                            pkg: d.shell("sha256sum", d.shell("pm", "path", pkg).splitlines()[0]
                                                         .removeprefix("package:")).split()[0]
                                            for pkg in (MODULE, PRIMARY)}})

    def sample(self, enabled, pkg=PRIMARY, injected=True, mode="Permissive"):
        d = self.d
        value = d.start_probe(pkg, "selinux")
        self.report["lastProbe"] = value
        self.save()
        check(d.shell("getenforce") == mode, "Module changed the real SELinux mode")
        marker = value["module"]
        check(marker["injected"] is injected, "Injection differs")
        if injected:
            check(marker["policyLoaded"] and set(marker["enabled"]) == set(enabled), "Policy differs")
            check(marker["futureMethodEnabled"], "Future methods should remain enabled")
        protected = injected and "selinux" in enabled
        expected = "1" if protected or mode == "Enforcing" else "0"
        if mode == "Enforcing" and not injected and self.enforcing_baseline is None:
            self.enforcing_baseline = value
        baseline = self.enforcing_baseline if mode == "Enforcing" else None
        for key in ("javaEnforced",):
            expected_java = protected or (baseline[key] if baseline else expected == "1")
            check(value[key] is expected_java, key + " differs")
        check(value["javaEnabled"] is True, "SELinux is enabled on this Android device")
        if d.shell("getprop", "ro.boot.selinux") == "":
            check(value["bootProperty"] == "" and value["bootPropertyDefault"] == "absent-control",
                  "A missing property or its caller default was changed")
        for key in ("fileInputStream", "randomAccessFile", "nio", "channel"):
            raw = baseline[key] if baseline else None
            wanted = raw if isinstance(raw, str) and raw.startswith("ERROR:") else expected
            check(value[key] == wanted, key + " differs: " + str(value[key]))
        for key in ("read", "pread", "pread64", "readv", "dup", "fread", "freadPartial", "fgets", "security_getenforce"):
            raw = baseline["native"].get(key) if baseline else None
            inaccessible = raw is None or (isinstance(raw, str) and raw.startswith("ERROR"))
            wanted = raw if baseline and inaccessible and key != "security_getenforce" else expected
            if key == "security_getenforce" and baseline:
                wanted = "1" if protected else raw
            check(value["native"].get(key) == wanted, key + " differs: " + str(value["native"].get(key)))
        for key, expected_control in (("eof", "0"), ("freadPartialItems", "0"), ("badFd", "EBADF"),
                                      ("ordinaryRead", "0"), ("is_selinux_enabled", "1"), ("contextAvailable", "true")):
            if baseline and key in ("eof", "freadPartialItems"):
                expected_control = baseline["native"].get(key)
            check(value["native"].get(key) == expected_control, "Ordinary control differs: " + key)
        check(value["native"]["directSyscall"] == (baseline["native"]["directSyscall"] if baseline else "0"),
              "The direct-syscall limitation must stay visible")
        for stage in ("attachBaseContext", "providerOnCreate", "applicationOnCreate"):
            wanted = protected or (baseline["lifecycle"][stage]["selinux"] if baseline else expected == "1")
            check(value["lifecycle"][stage]["selinux"] is wanted, "Early SELinux differs")
        for key, method in (("developer", "developer"), ("debug", "debug")):
            check(value[key] == (0 if injected and method in enabled else 1), key + " independence differs")
        check(value["adbd"] == ("stopped" if injected and "debug" in enabled else "running"), "Debug property differs")
        check(value["tunByName"] is (not (injected and "vpn" in enabled)), "VPN independence differs")
        check(("tun0" in value["nativeState"]["interfaces"]) is (not (injected and "vpn" in enabled)),
              "Native VPN independence differs")
        for key in ("hostVisible", "portVisible", "bulkHostVisible"):
            check(value["proxyFixture"][key] is (not (injected and "proxy" in enabled)), "Proxy independence differs")
        check(value["proxyFixture"]["response"] == 204 and value["proxyFixture"]["actualHttpProxyUsed"],
              "Ordinary proxy traffic failed")
        check(value["ordinaryFixture"] is True, "Ordinary shared file changed")
        check(value["screenshotFixture"] is (not (injected and "screenshot" in enabled)), "Screenshot independence differs")
        libraries = {lib for method, lib in (("screenshot", "libshield.so"), ("vpn", "libvpnstate.so"),
                     ("debug", "libdeveloperstate.so"), ("selinux", "libselinuxstate.so"))
                     if injected and method in enabled}
        check(set(value["nativeState"]["protectionLibraries"]) == libraries, "Unselected native library loaded")
        for suffix in ("get", "read", "callback"):
            check(value["nativeState"]["init.svc.adbd." + suffix] ==
                  ("stopped" if injected and "debug" in enabled else "running"), "Native debug property changed")
        return value

    def policy(self, pkg, enabled):
        """Use the real editor, caching measured coordinates only while its layout is unchanged."""
        d = self.d
        if self.policy_boxes and self.policy_save and pkg == PRIMARY:
            d.shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
            d.click("custom:" + pkg)
            # Measured bounds are reused within this same test session, not across
            # rotation/font/locale changes; the saved policy is checked after every edit.
            current = self.current_enabled
            for key in set(enabled) ^ current:
                x, y = self.policy_boxes[key]
                d.shell("input", "tap", x, y)
            d.shell("input", "tap", *self.policy_save)
            d.find("add-app")
            tree = ET.fromstring(d.shell("cat", PREF))
            saved = json.loads(tree.find("string[@name='apps']").text)
            check(set(saved[pkg]) == set(METHODS) - set(enabled), "UI coordinates no longer match saved switches")
            self.current_enabled = set(enabled)
            return
        d.set_policy(pkg, enabled)

    def matrix(self):
        d = self.d
        # Keep each iteration to measured UI actions. With the reduced test-only
        # font scale all six native controls fit; restore the original in cleanup.
        d.shell("settings", "put", "system", "font_scale", "0.85")
        d.set_policy(PRIMARY, set())
        d.home_settings()
        d.click("custom:" + PRIMARY)
        nodes = d.nodes()
        boxes = {n.get("content-desc").split(":")[1]: d.center(n) for n in nodes
                 if n.get("content-desc", "").startswith("method:")}
        check(set(boxes) == set(METHODS), "Six controls must fit before caching measured coordinates")
        self.policy_boxes = boxes
        self.policy_save = d.center(next(n for n in nodes if n.get("content-desc") == "save"))
        d.click("save")
        self.current_enabled = set()
        # Gray order changes one control at a time but every bit pattern is recorded.
        for i in range(64):
            mask = i ^ (i >> 1)
            bits = format(mask, "06b")
            enabled = {key for key, bit in zip(METHODS, bits) if bit == "1"}
            self.policy(PRIMARY, enabled)
            self.case("M6-" + bits, lambda enabled=enabled: self.sample(enabled))
        self.policy_boxes = {}

    def tests(self, matrix=True):
        d = self.d
        d.shell("setenforce", "0")
        check(d.shell("getenforce") == "Permissive", "A real permissive baseline is required")
        d.scope(MODULE, PRIMARY, False)
        self.case("L02-unscoped-permissive", lambda: self.sample(set(), injected=False))
        d.scope(MODULE, PRIMARY, True)
        for enabled, name in [(set(), "L03-all-off"), ({"selinux"}, "L04-selinux-only"), (set(METHODS), "L05-all-on")]:
            d.set_policy(PRIMARY, enabled)
            self.case(name, lambda enabled=enabled: self.sample(enabled))
        # Changing mode while the test runs never changes anything on physical devices.
        d.shell("setenforce", "1")
        d.scope(MODULE, PRIMARY, False)
        self.case("L06-enforcing-baseline", lambda: self.sample(set(), injected=False, mode="Enforcing"))
        d.scope(MODULE, PRIMARY, True)
        d.set_policy(PRIMARY, set())
        self.case("L06-enforcing-all-off", lambda: self.sample(set(), mode="Enforcing"))
        d.set_policy(PRIMARY, {"selinux"})
        self.case("L07-enforcing-selinux-only", lambda: self.sample({"selinux"}, mode="Enforcing"))
        d.shell("setenforce", "0")
        if matrix:
            self.matrix()
        d.set_policy(PRIMARY, set(METHODS) - {"selinux"})
        d.set_policy(B, {"selinux"})
        self.case("L08-independent-A", lambda: self.sample(set(METHODS) - {"selinux"}))
        self.case("L09-independent-B", lambda: self.sample({"selinux"}, B))
        d.home_settings()
        d.click("custom:" + PRIMARY, scroll=True)
        d.click("remove-custom", scroll=True)
        d.click("android:id/button1", "resource-id")
        d.find("add-app")
        self.case("L10-default-future-method", lambda: self.sample(set(METHODS)))
        def full_state():
            value = d.start_probe(PRIMARY)
            check(value["internet"] == 204, "Ordinary HTTPS failed")
            check(value["native"]["listLifetimeOk"] and value["native"]["getpidOk"], "Native lifetime failed")
            for key in ("foreignReadDenied", "otherPackageDenied", "writeDenied", "insertDenied", "updateDenied", "deleteDenied", "queryDenied"):
                check(value[key] is True, "Policy isolation failed: " + key)
            return value
        self.case("L11-https-policy-isolation", full_state)
        if matrix:
            self.case("L12-ten-cold-starts", lambda: [self.sample(set(METHODS)) for _ in range(10)])

    def cleanup(self):
        d = self.d
        original = json.loads((STATE / "state.json").read_text())
        # Restore enforcement before package changes and private-file restoration.
        d.shell("setenforce", "1" if original["mode"] == "Enforcing" else "0")
        d.shell("am", "force-stop", C)
        check("tun0" not in d.shell("ip", "link", "show"), "Temporary VPN still running")
        d.shell("rm", "-rf", FIXTURE)
        for pkg in [MODULE] + TARGETS:
            d.shell("am", "force-stop", pkg)
            if pkg in original["packages"]:
                d.adb("install", "--no-incremental", "-r", "-d", original["packages"][pkg])
                installed = d.shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
                check(d.shell("sha256sum", installed).split()[0] ==
                      hashlib.sha256(pathlib.Path(original["packages"][pkg]).read_bytes()).hexdigest(),
                      "Original APK hash differs: " + pkg)
            else:
                d.adb("uninstall", pkg)
        for m in original["modules"]:
            d.cli("modules", "enable" if m["STATUS"] == "enabled" else "disable", m["PACKAGE"])
            prior = {(s["APP_PACKAGE"], s["USER_ID"]) for s in original["scopes"][m["PACKAGE"]]}
            for pkg in TARGETS:
                d.scope(m["PACKAGE"], pkg, (pkg, 0) in prior)
        if original["pref"]:
            local = STATE / "policies.xml"
            local.write_text(original["pref"]); local.chmod(0o600)
            uid = next(m["UID"] for m in original["modules"] if m["PACKAGE"] == MODULE)
            d.adb("push", str(local), "/data/local/tmp/selinux-policy.xml")
            d.shell("cp", "/data/local/tmp/selinux-policy.xml", PREF)
            d.shell("chown", str(uid) + ":" + str(uid), PREF)
            d.shell("chmod", "660", PREF)
            d.shell("restorecon", PREF)
            d.shell("rm", "-f", "/data/local/tmp/selinux-policy.xml")
            check(d.shell("cat", PREF) == original["pref"], "Original policies differ")
        else:
            d.shell("rm", "-f", PREF)
        for key, value in original["settings"].items():
            d.shell("settings", "delete", "global", key) if value == "null" else d.shell("settings", "put", "global", key, value)
            check(d.shell("settings", "get", "global", key) == value, "Original setting differs: " + key)
        scale = original.get("fontScale", "1.0")
        d.shell("settings", "delete", "system", "font_scale") if scale == "null" else d.shell("settings", "put", "system", "font_scale", scale)
        check(d.shell("settings", "get", "system", "font_scale") == scale, "Original font scale differs")
        if not original.get("storageGranted", False):
            for permission in ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"):
                d.shell("pm", "revoke", PRIMARY, "android.permission." + permission)
                check("android.permission." + permission + ": granted=true" not in d.shell("dumpsys", "package", PRIMARY),
                      "Temporary permission remains granted: " + permission)
        check(d.shell("getenforce") == original["mode"], "Original mode differs")
        statuses = {m["PACKAGE"]: m["STATUS"] for m in d.cli("modules", "ls")}
        for m in original["modules"]:
            check(statuses[m["PACKAGE"]] == m["STATUS"], "Module enable state restore differs")
            check(d.cli("scope", "ls", m["PACKAGE"]) == original["scopes"][m["PACKAGE"]], "Scope restore differs")
        self.case("L99-restored", lambda: {"selinux": original["mode"], "settings": True, "scopes": True,
                                         "policies": True, "originalApks": True, "fontScale": scale,
                                         "temporaryStorageGrantsRemoved": not original.get("storageGranted", False),
                                         "moduleStates": True, "vpnStopped": True, "fixturesRemoved": True})

    def native(self):
        """Regression for the shared read wrappers, using the retained native probe."""
        d = self.d
        directory = "/sdcard/Pictures/ShieldProbe"
        names = ["ordinary_probe.png", "Screenshot_probe.png"]
        existed = d.shell("sh", "-c", "test ! -d " + directory + " || echo exists") == "exists"
        for name in names:
            check(d.shell("sh", "-c", "test ! -e " + directory + "/" + name + " && echo absent") == "absent",
                  "Preexisting screenshot fixture must not be overwritten")
        def clipboard(command):
            d.shell("rm", "-f", "/data/user/0/" + C + "/files/services-result.json")
            d.shell("am", "start", "-W", "--activity-clear-top", "-n",
                    C + "/io.github.lwtdzh.screenshotdetector.FixtureActivity", "--es", "command", command)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                value = d.shell("sh", "-c", "test ! -f /data/user/0/" + C +
                                "/files/services-result.json || cat /data/user/0/" + C + "/files/services-result.json")
                if value:
                    check(isinstance(json.loads(value).get("clipboardHas"), bool), "Clipboard fixture failed")
                    return
                time.sleep(.1)
            raise TimeoutError("Clipboard fixture did not complete")
        clipboard("clipboard-save")
        d.shell("mkdir", "-p", directory)
        try:
            d.shell("screencap", "-p", directory + "/" + names[0])
            d.shell("cp", directory + "/" + names[0], directory + "/" + names[1])
            for enabled, label in [({"selinux"}, "selinux-only"), ({"screenshot"}, "screenshot-only"),
                                   (set(METHODS), "all-on")]:
                d.set_policy(PRIMARY, enabled)
                def run(enabled=enabled):
                    value = d.start_probe(PRIMARY, "shot")
                    check("startup_error" not in value and "inspect_error" not in value, "Screenshot probe error")
                    native = value["native"]
                    for kind in ("normal", "screenshot"):
                        visible = kind == "normal" or "screenshot" not in enabled
                        for key in ("open", "syscall_open", "stat", "access", "fopen", "fd_read", "fd_pread",
                                    "fd_readv", "fd_preadv", "fd_syscall_read", "fd_mmap", "fd_dup_pread",
                                    "procfd_open", "symlink_open"):
                            check(native[key + "_" + kind] is visible, key + "_" + kind + " differs")
                        check(native["fixture_fd_" + kind], "No genuine existing FD fixture")
                    for key in ("syscall_getpid_ok", "syscall_six_arguments_ok", "clone_new_stack_ok"):
                        check(native[key] is True, "Native ordinary control failed: " + key)
                    return {"native": native, "constructedScreenshotFile": True,
                            "realSystemUiScreenshotEvent": False}
                self.case("L13-native-" + label, run)
        finally:
            d.shell("am", "force-stop", PRIMARY)
            clipboard("clipboard-restore")
            for name in names:
                d.shell("rm", "-f", directory + "/" + name)
            if not existed:
                d.shell("rmdir", directory)
        d.set_policy(PRIMARY, set(METHODS))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["capture", "prepare", "smoke", "test", "native", "cleanup"])
    args = parser.parse_args()
    run = Run()
    {"capture": run.capture, "prepare": run.prepare, "smoke": lambda: run.tests(False),
     "test": run.tests, "native": run.native, "cleanup": run.cleanup}[args.phase]()
