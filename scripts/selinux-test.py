#!/usr/bin/env python3
"""SELinux 0.3.0 validation on the dedicated AVD; private snapshots stay outside git."""
import argparse
import hashlib
import json
import os
import pathlib
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from test_evidence import case_inputs
from test_device import Device, METHODS, MODULE, PRIMARY

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = os.environ.get("APPSTATE_TEST_VERSION", "0.3.0")
ARTIFACTS = ROOT / "verification"
OUT = pathlib.Path(os.environ.get("APPSTATE_TEST_OUTPUT", ARTIFACTS))
STATE = pathlib.Path(os.environ.get("APPSTATE_TEST_STATE",
    pathlib.Path.home() / ("Library/Application Support/ScreenshotShield/selinux-" + VERSION)))
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
        self.path = OUT / ("selinux-" + VERSION + "-results.json")
        self.policy_boxes = {}
        self.policy_save = None
        self.policy_scrolls = 0
        self.enforcing_baseline = None
        self.only = set()
        self.started = time.monotonic()
        self.input_metadata = None
        self.report = json.loads(self.path.read_text()) if self.path.exists() else {"cases": {}}
        self.prior_artifacts = self.report.get("artifacts", {}).copy()
        self.report["artifacts"] = {name: hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()
                                   for name in ("AppStateShield-"+VERSION+".apk", "AppStateVerifier-"+VERSION+".apk")}

    def case(self, name, action):
        if not self.pending(name):
            return self.report["cases"].get(name, {}).get("evidence")
        print("START " + name, flush=True)
        started = time.monotonic()
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            evidence = action()
            if self.input_metadata is None:
                self.input_metadata = case_inputs(self.d, self.report["artifacts"])
            value = {"status": "passed", "evidence": evidence, "artifacts":self.report["artifacts"].copy(),
                     "startedAtUTC": stamp, "durationSeconds": round(time.monotonic() - started, 3),
                     **self.input_metadata}
        except Exception as error:
            value = {"status": "failed", "error": repr(error), "startedAtUTC": stamp,
                     "durationSeconds": round(time.monotonic()-started, 3)}
            if name in self.report["cases"]:
                self.report.setdefault("previousRuns", {}).setdefault(name, []).append(self.report["cases"][name])
            self.report["cases"][name] = value
            self.save()
            raise
        if name in self.report["cases"]:
            self.report.setdefault("previousRuns", {}).setdefault(name, []).append(self.report["cases"][name])
        self.report["cases"][name] = value
        self.save()
        print("PASS " + name, flush=True)
        return evidence

    def pending(self, name):
        if self.only and name not in self.only:
            return False
        row = self.report["cases"].get(name, {})
        if row.get("status") == "passed" and row.get("artifacts") == self.report["artifacts"]:
            marker = row.get("evidence", {}).get("module", {}) if isinstance(row.get("evidence"), dict) else {}
            if (name.startswith("M6-") and getattr(self, "resume_revision", None) is not None and
                    marker.get("deviceRevision") != self.resume_revision):
                return True
            print("KEEP verified " + name, flush=True)
            return False
        if time.monotonic() - self.started > 1200:
            raise RuntimeError("20-minute execution budget reached; preserve results and inspect durations")
        return True

    def validate_setup(self):
        """Resume requires installed bytes, original snapshot and live fixtures."""
        d = self.d
        check((STATE / "state.json").exists(), "Original regression snapshot is missing")
        installed = {}
        for pkg, name in [(MODULE, "AppStateShield-"+VERSION+".apk"),
                          (PRIMARY, "AppStateVerifier-"+VERSION+".apk"),
                          (B, "Verifier-A-"+VERSION+".apk"), (C, "Verifier-B-"+VERSION+".apk")]:
            path = d.shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
            installed[pkg] = d.shell("sha256sum", path).split()[0]
            check(installed[pkg] == hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest(),
                  "Installed artifact differs: " + pkg)
        check("tun0" in d.shell("ip", "link", "show"), "Resume VPN fixture is missing")
        for key in ("hidden_api_policy", "development_settings_enabled", "adb_enabled"):
            check(d.shell("settings", "get", "global", key) == "1", "Resume baseline differs: " + key)
        check(d.shell("cat", FIXTURE + "/ordinary_control.txt") == "0", "Resume ordinary fixture differs")
        check(d.shell("cat", FIXTURE + "/Screenshot_control.txt") == "0", "Resume screenshot fixture differs")
        baseline = self.report["cases"].get("D17-uninjected-enforcing", {})
        if baseline.get("artifacts") == self.report["artifacts"] and baseline.get("status") == "passed":
            self.enforcing_baseline = baseline["evidence"]
        self.report.setdefault("executions", []).append({
            "startedAtUTC": datetime.now(timezone.utc).isoformat(),
            "resume": True, "installedSha256": installed, "setupVerified": True})
        self.save()

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
        for pkg, name in [(MODULE, "AppStateShield-"+VERSION+".apk"), (PRIMARY, "AppStateVerifier-"+VERSION+".apk"),
                          (B, "Verifier-A-"+VERSION+".apk"), (C, "Verifier-B-"+VERSION+".apk")]:
            d.adb("install", "--no-incremental", "-r", str(ARTIFACTS / name))
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
        check(value["legacyVpnAvailable"] is True, "Supported legacy VPN information disappeared")
        check(value["legacyVpnConnected"] is (not (injected and "vpn" in enabled)),
              "Legacy VPN connection state differs")
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
        """Use fresh element bounds and edit only the switches that changed."""
        d = self.d
        if hasattr(self,"current_enabled") and pkg == PRIMARY:
            d.shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
            d.click("custom:" + pkg)
            for key in sorted(set(enabled) ^ self.current_enabled):
                node=d.find("method:"+key,scroll=True)
                if (node.get("checked")=="true") != (key in enabled):d.tap(node)
            d.click("save")
            d.find("add-app")
            tree = ET.fromstring(d.shell("cat", PREF))
            saved = json.loads(tree.find("string[@name='apps']").text)
            check(set(saved[pkg]) == set(METHODS) - set(enabled), "Saved switches differ from requested policy")
            self.current_enabled = set(enabled)
            return
        d.set_policy(pkg, enabled)

    def matrix(self):
        d = self.d
        if self.only and not any(name.startswith("M6-") for name in self.only):
            return
        layout = self.report["cases"].get("L14-matrix-editor-layout", {})
        if layout.get("status") != "passed" or layout.get("artifacts") != self.report["artifacts"]:
            # One real UI persistence check remains mandatory before bulk fixtures.
            d.set_policy(PRIMARY, set())
            self.case("L14-matrix-editor-layout", lambda: {"realUiSave": True,
                "savedDisabled": json.loads(ET.fromstring(d.shell("cat", PREF))
                    .find("string[@name='apps']").text)[PRIMARY]})
        remaining = []
        for i in range(64):
            mask = i ^ (i >> 1)
            bits = format(mask, "06b")
            enabled = {key for key, bit in zip(METHODS, bits) if bit == "1"}
            if self.pending("M6-" + bits):
                remaining.append((bits, enabled))
        print("Matrix: " + str(len(remaining)) + " remaining, bulk configuration; expected 3–8 minutes", flush=True)
        for bits, enabled in remaining:
            d.batch_policy(PRIMARY, enabled)
            self.case("M6-" + bits, lambda enabled=enabled: self.sample(enabled))
        self.policy_boxes = {}

    def tests(self, matrix=True):
        d = self.d
        self.validate_setup()
        baseline = self.report["cases"].get("L06-enforcing-baseline", {})
        if baseline.get("status") == "passed" and baseline.get("artifacts") == self.report["artifacts"]:
            self.enforcing_baseline = baseline["evidence"]
        modes = [
            ("L02-unscoped-permissive", "Permissive", False, set()),
            ("L03-all-off", "Permissive", True, set()),
            ("L04-selinux-only", "Permissive", True, {"selinux"}),
            ("L05-all-on", "Permissive", True, set(METHODS)),
            ("L06-enforcing-baseline", "Enforcing", False, set()),
            ("L06-enforcing-all-off", "Enforcing", True, set()),
            ("L07-enforcing-selinux-only", "Enforcing", True, {"selinux"}),
        ]
        for name, mode, injected, enabled in modes:
            if not self.pending(name):
                continue
            d.shell("setenforce", "1" if mode == "Enforcing" else "0")
            check(d.shell("getenforce") == mode, "Real mode baseline is missing")
            d.scope(MODULE, PRIMARY, injected)
            if injected:
                d.batch_policy(PRIMARY, enabled)
            self.case(name, lambda mode=mode, injected=injected, enabled=enabled:
                      self.sample(enabled, injected=injected, mode=mode))
        if matrix:
            d.shell("setenforce", "0")
            d.scope(MODULE, PRIMARY, True)
            self.matrix()
        for name, pkg, enabled in [("L08-independent-A", PRIMARY, set(METHODS)-{"selinux"}),
                                   ("L09-independent-B", B, {"selinux"})]:
            if self.pending(name):
                d.shell("setenforce", "0")
                d.scope(MODULE, pkg, True)
                d.batch_policy(pkg, enabled)
                self.case(name, lambda pkg=pkg, enabled=enabled: self.sample(enabled, pkg))
        if self.pending("L10-default-future-method"):
            d.shell("setenforce", "0")
            d.scope(MODULE, PRIMARY, True)
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
        groups = [({"selinux"}, "selinux-only"), ({"screenshot"}, "screenshot-only"),
                  (set(METHODS), "all-on")]
        groups = [(enabled, label) for enabled, label in groups if self.pending("L13-native-" + label)]
        if not groups:
            return
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
            for enabled, label in groups:
                d.batch_policy(PRIMARY, enabled)
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
        d.batch_policy(PRIMARY, set(METHODS))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["capture", "prepare", "smoke", "test", "native", "cleanup"])
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    run = Run()
    run.only = set(args.case)
    {"capture": run.capture, "prepare": run.prepare, "smoke": lambda: run.tests(False),
     "test": run.tests, "native": run.native, "cleanup": run.cleanup}[args.phase]()
