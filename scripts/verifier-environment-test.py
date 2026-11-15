#!/usr/bin/env python3
"""Targeted verifier checks on the dedicated AVD. Preserve/restore its complete stopped disk."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from test_device import ADB, Device, MODULE, PRIMARY, METHODS

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/verifier-environment-0.4.12"
AVD = STATE.parent / "emulator/ScreenshotShield_API36.avd"
REPORT = ROOT / "verification/verifier-environment-0.4.12-results.json"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest(folder):
    result = {}
    for path in sorted(folder.rglob("*")):
        key = str(path.relative_to(folder))
        if path.is_symlink():
            result[key] = {"link": str(path.readlink())}
        elif path.is_file():
            result[key] = {"sha256": sha(path), "bytes": path.stat().st_size, "mode": path.stat().st_mode & 0o777}
        elif path.is_dir():
            result[key] = {"directory": True}
    return result


def stopped():
    connected = subprocess.run([ADB, "-s", "emulator-5584", "get-state"], capture_output=True).returncode == 0
    processes = subprocess.check_output(["ps", "-axo", "command="], text=True)
    running = any("qemu-system" in line and ("-port 5584" in line or "-ports 5584," in line)
                  for line in processes.splitlines())
    return not connected and not running


def capture():
    assert stopped(), "Stop only the dedicated emulator before disk capture"
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    saved = STATE / "original-avd"
    assert not saved.exists(), "Never overwrite an original snapshot"
    subprocess.run(["cp", "-cRp", str(AVD), str(saved)], check=True)
    original = manifest(saved)
    assert original == manifest(AVD), "Captured disk differs"
    (STATE / "original.json").write_text(json.dumps({"files": original,
        "ramdiskSHA256": sha(STATE.parent / "emulator/ramdisk.img")}, indent=2) + "\n")
    print("PASS complete stopped AVD captured", flush=True)


def restore():
    if not stopped():
        device = Device()
        device.adb("emu", "kill")
        deadline = time.monotonic() + 30
        while not stopped() and time.monotonic() < deadline:
            time.sleep(.2)
    assert stopped(), "Emulator must exit before restoration"
    original = json.loads((STATE / "original.json").read_text())
    saved = STATE / "original-avd"
    assert manifest(saved) == original["files"], "Original snapshot changed"
    discard = STATE / "tested-avd"
    assert not discard.exists()
    AVD.rename(discard)
    subprocess.run(["cp", "-cRp", str(saved), str(AVD)], check=True)
    assert manifest(AVD) == original["files"], "Restored disk differs"
    assert sha(STATE.parent / "emulator/ramdisk.img") == original["ramdiskSHA256"]
    result = {"passed": True, "completeAVD": True, "exactFileTreeAndSHA256": True,
        "emulatorStopped": True, "serial": "emulator-5584", "atUTC": datetime.now(timezone.utc).isoformat()}
    (ROOT / "verification/verifier-environment-0.4.12-restoration.json").write_text(json.dumps(result, indent=2) + "\n")
    shutil.rmtree(discard)
    print("PASS full original AVD restored; every file hash matched", flush=True)


class EnvironmentDevice(Device):
    def scroll_controls(self, up):
        pane = next(n for n in self.nodes() if n.get("scrollable") == "true")
        left, top, right, bottom = map(int, re.findall(r"\d+", pane.get("bounds")))
        # Swipe along the pane margin: selectable TextViews otherwise consume the gesture.
        x = left + 8
        lower, upper = top + int((bottom-top)*.85), top + int((bottom-top)*.2)
        self.shell("input", "swipe", x, lower if up else upper, x, upper if up else lower, 300)
    def swipe_up(self):
        self.scroll_controls(True)
    def swipe_down(self):
        self.scroll_controls(False)


class Checks:
    def __init__(self):
        self.device = EnvironmentDevice()
        self.report = {"version": "0.4.12", "serial": "emulator-5584", "cases": {}, "artifacts": {},
                       "expectedCases": 8, "estimateMinutes": 4}
        self.latest = None
        self.origin = {}
        if REPORT.exists():
            previous = json.loads(REPORT.read_text())
            current = {name: sha(ROOT / "verification" / name) for name in
                       ("AppStateShield-0.4.12.apk", "AppStateVerifier-0.4.12.apk")}
            if previous.get("artifacts") == current:
                self.report = previous
                baseline = previous["cases"].get("E01-no-injection", {}).get("result")
                if baseline:
                    self.origin = self.fields(baseline)
                for row in previous["cases"].values():
                    self.latest = row.get("result", row.get("lastObservation", self.latest))

    def save(self):
        REPORT.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")

    def record(self, name, action):
        start = time.monotonic()
        row = {"atUTC": datetime.now(timezone.utc).isoformat(), "status": "running"}
        previous = self.report["cases"].get(name)
        if previous:
            row["earlierAttempts"] = previous.get("earlierAttempts", []) + [
                {key: value for key, value in previous.items() if key not in {"earlierAttempts", "result", "lastObservation"}}]
        self.report["cases"][name] = row
        try:
            row["result"] = action()
            row["status"] = "passed"
        except Exception as error:
            row.update(status="failed", error=str(error))
            if self.latest is not None:
                row["lastObservation"] = self.latest
            raise
        finally:
            row["seconds"] = round(time.monotonic() - start, 3)
            self.save()
            print(row["status"].upper(), name, row["seconds"], "seconds", flush=True)

    def snapshot(self, after=0):
        path = "/data/user/0/" + PRIMARY + "/files/environment-result.json"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            raw = subprocess.run(self.device.prefix + ["shell", "cat", path],
                                 text=True, capture_output=True, timeout=5)
            try:
                value = json.loads(raw.stdout)
            except json.JSONDecodeError:
                value = None
            if value and value.get("timestamp", 0) > after and "summary" in value:
                self.latest = value
                checks = {item["id"]: item for item in value["checks"]}
                assert value["version"] == "0.4.12" and checks["attestation.cleanup"]["value"] == "true"
                assert "attestation.challenge" in checks, "Attestation fields missing: " + json.dumps(checks.get("attestation.available"))
                assert checks["attestation.challenge"]["value"] == "true"
                return value
            if value is None:
                pass
            time.sleep(.1)
        raise AssertionError("Environment results did not complete")

    def launch(self, scoped, methods, profile):
        d = self.device
        d.shell("am", "force-stop", PRIMARY)
        for item in d.cli("modules", "ls"):
            d.scope(item["PACKAGE"], PRIMARY, scoped and item["PACKAGE"] == MODULE)
        d.batch_policy(PRIMARY, methods)
        d.batch_profile(PRIMARY, profile)
        d.shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
        before = int(time.time() * 1000) - 2000
        d.shell("rm", "-f", "/data/user/0/" + PRIMARY + "/files/environment-result.json")
        d.shell("am", "start", "-W", "-n", PRIMARY + "/.MainActivity")
        return self.snapshot(before)

    def setup(self):
        d = self.device
        assert d.shell("id", "-u") == "0"
        for pkg, filename in ((MODULE, "AppStateShield-0.4.12.apk"), (PRIMARY, "AppStateVerifier-0.4.12.apk")):
            local = ROOT / "verification" / filename
            remote = d.shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
            if d.shell("sha256sum", remote).split()[0] != sha(local):
                d.adb("install", "--no-incremental", "-r", str(local), timeout=60)
                remote = d.shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
            assert d.shell("sha256sum", remote).split()[0] == sha(local)
            self.report["artifacts"][filename] = sha(local)
        d.cli("modules", "enable", MODULE)
        self.report["environment"] = {"fingerprint": d.shell("getprop", "ro.build.fingerprint"),
            "abi": d.shell("getprop", "ro.product.cpu.abi"), "rootMode": d.shell("getenforce")}
        # Synthetic deterministic profile, not data read from a physical phone.
        self.profile = {"schema": 1, "enabled": True, "modelEnabled": True, "locationEnabled": False,
            "networkMode": "off", "preset": "xiaomi-14",
            "values": {"fingerprint": "Xiaomi/houji_global/houji:15/AQ3A.240627.003/OS2.0.201.0.VNCMIXM:user/release-keys",
                       "hide_module_apps": "true"}, "selected": ["fingerprint", "hide_module_apps"]}
        self.save()

    @staticmethod
    def fields(value):
        return {item["id"]: item for item in value["checks"]}

    def baseline(self):
        value = self.launch(False, [], {"enabled": False})
        assert not value["module"]["injected"]
        self.origin = self.fields(value)
        assert self.origin["rootFiles"]["status"] == "UNKNOWN", "Expected inaccessible root directories"
        assert self.origin["property.ro.build.tags"]["value"] == "test-keys"
        assert self.origin["attestation.security"]["value"] == "Software"
        assert self.origin["attestation.boot.locked"]["value"] == "false"
        assert self.origin["injection.maps"]["status"] == "PASS"
        return value

    def scoped_off(self):
        value = self.launch(True, [], {"enabled": False})
        assert value["module"]["injected"] and not value["module"]["enabled"]
        # The restored Magisk/Vector environment can use anonymous/memfd-backed mappings.
        # Compare the bounded known-path scan to real shell maps; do not require it to detect all injection.
        maps = self.device.shell("cat", "/proc/" + str(value["pid"]) + "/maps")
        known = [line for line in maps.splitlines() if any(marker in line for marker in
            ("/data/adb/", "libzygisk", "zygisk_vector", "libxposed", "liblsplant", "liblspd", "libsubstrate"))]
        assert (self.fields(value)["injection.maps"]["status"] == "WARN") == bool(known)
        value["shellKnownMappingLines"] = known
        value["knownPathScanIsNotCompleteInjectionDetection"] = True
        return value

    def protected(self):
        value = self.launch(True, METHODS, {"enabled": False})
        assert set(value["module"]["enabled"]) == set(METHODS)
        assert self.fields(value)["usb"]["value"] != self.origin["usb"]["value"]
        return value

    def model(self):
        value = self.launch(True, METHODS, self.profile)
        fields = self.fields(value)
        assert value["module"]["deviceEnabled"] and value["module"]["modelEnabled"], "Synthetic profile did not load"
        for key in ["property.ro.build.tags", "property.ro.vendor_dlkm.build.tags", "buildTags"]:
            assert fields[key]["value"] == "release-keys"
        assert fields["modules"]["value"] == "0"
        for key in ["attestation.security", "attestation.keyMint", "attestation.boot.locked", "attestation.boot.state"]:
            assert fields[key]["value"] == self.origin[key]["value"], "Model spoof changed signed attestation"
        return value

    def refresh(self):
        old = self.latest
        self.device.click("environment-refresh", scroll=True)
        value = self.snapshot(old["timestamp"])
        assert value["pid"] == old["pid"]
        summary = self.device.find("environment-summary", scroll=True)
        assert "Checking" not in summary.get("text", "")
        counter = self.device.find("session-screenshots", scroll=True)
        assert re.search(r"\b0\b", counter.get("text")), "Environment output affected screenshot count"
        self.device.click("environment-details", scroll=True)
        self.device.find("environment:rootFiles", scroll=True)
        self.device.screenshot(STATE / "environment-details.png")
        self.device.click("environment-details")
        return value

    def background(self):
        old = self.latest
        self.device.shell("input", "keyevent", "KEYCODE_HOME")
        # UI dump waits for idle; no blocking sleep is needed.
        self.device.nodes()
        current = self.snapshot()
        assert current["timestamp"] == old["timestamp"]
        self.device.shell("am", "start", "-W", "-n", PRIMARY + "/.MainActivity")
        value = self.snapshot(old["timestamp"])
        assert value["pid"] == old["pid"]
        return value

    def legacy(self):
        old = self.latest
        self.device.shell("am", "start", "-W", "-n", PRIMARY + "/io.github.lwtdzh.devicestateprobe.ProbeActivity",
                          "--es", "action", "environment")
        value = self.snapshot(old["timestamp"])
        assert value["pid"] == old["pid"]
        assert any(n.get("content-desc") == "environment-summary" for n in self.device.nodes())
        return value

    def disabled(self):
        value = self.launch(True, METHODS, {"enabled": False})
        fields = self.fields(value)
        assert fields["property.ro.build.tags"]["value"] == self.origin["property.ro.build.tags"]["value"]
        assert fields["modules"]["value"] == self.origin["modules"]["value"]
        self.device.screenshot(STATE / "environment-home.png")
        self.report["logcat"] = self.device.adb("logcat", "-d", "-s", "EnvironmentProbe:I", "*:S")
        assert "attestation.cleanup PASS true" in self.report["logcat"]
        return value

    def run(self):
        self.setup()
        for name, action in (("E01-no-injection", self.baseline), ("E02-scoped-off", self.scoped_off),
                             ("E03-methods-on", self.protected), ("E04-model-list-on", self.model),
                             ("E05-refresh-ui", self.refresh), ("E06-background-return", self.background),
                             ("E07-legacy-environment", self.legacy), ("E08-profile-disabled", self.disabled)):
            if self.report["cases"].get(name, {}).get("status") == "passed":
                print("RETAIN", name, "same signed APK", flush=True)
                continue
            self.record(name, action)
        print("PASS all 8 targeted verifier cases", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["capture", "run", "restore"])
    action = parser.parse_args().phase
    {"capture": capture, "run": lambda: Checks().run(), "restore": restore}[action]()
