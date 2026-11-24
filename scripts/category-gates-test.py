#!/usr/bin/env python3
"""0.4.13 category controls: real UI persistence, then bounded same-PID API fixtures."""
import argparse
import copy
import importlib.util
import json
import pathlib
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from test_device import ADB, Device, MODULE, PRIMARY

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/category-gates-0.4.13"
REPORT = ROOT / "verification/category-gates-0.4.13-results.json"
spec = importlib.util.spec_from_file_location("preserve", ROOT / "scripts/verifier-environment-test.py")
preserve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preserve)
preserve.STATE = STATE
sha = preserve.sha
GROUPS = ("ids", "network", "model", "location", "environment")
FLAGS = ("idsEnabled", "modelEnabled", "locationEnabled", "environmentEnabled", "networkMode")


def restore():
    if not preserve.stopped():
        Device().adb("emu", "kill")
        deadline = time.monotonic() + 30
        while not preserve.stopped() and time.monotonic() < deadline:
            time.sleep(.2)
    assert preserve.stopped(), "Dedicated AVD must be stopped"
    original = json.loads((STATE / "original.json").read_text())
    assert preserve.manifest(STATE / "original-avd") == original["files"]
    discard = STATE / "tested-avd"
    assert not discard.exists()
    preserve.AVD.rename(discard)
    subprocess.run(["cp", "-cRp", str(STATE / "original-avd"), str(preserve.AVD)], check=True)
    assert preserve.manifest(preserve.AVD) == original["files"]
    assert sha(STATE.parent / "emulator/ramdisk.img") == original["ramdiskSHA256"]
    (ROOT / "verification/category-gates-0.4.13-restoration.json").write_text(json.dumps({
        "passed": True, "completeAVD": True, "exactFileTreeAndSHA256": True,
        "ramdiskUnchanged": True, "emulatorStopped": True, "serial": "emulator-5584",
        "atUTC": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
    shutil.rmtree(discard)
    print("PASS complete original AVD restored", flush=True)


class Checks:
    def __init__(self):
        self.d = preserve.EnvironmentDevice()
        self.latest = None
        self.hashes = {name: sha(ROOT / "verification" / name) for name in
                       ("AppStateShield-0.4.13.apk", "AppStateVerifier-0.4.13.apk")}
        self.report = {"version": "0.4.13", "serial": "emulator-5584",
                       "expectedCases": 13, "estimateMinutes": 5, "cases": {}, "artifacts": self.hashes}
        if REPORT.exists():
            old = json.loads(REPORT.read_text())
            assert old["artifacts"] == self.hashes, "Keep old evidence separate after an APK change"
            self.report = old
        self.base = self.report.get("baseline")
        self.fixture = self.report.get("fixture")

    def save(self):
        REPORT.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n")

    def case(self, name, action):
        if self.report["cases"].get(name, {}).get("status") == "passed":
            print("RETAIN", name, "same signed APK", flush=True)
            return
        row = {"status": "running", "atUTC": datetime.now(timezone.utc).isoformat()}
        old = self.report["cases"].get(name)
        if old:
            row["earlierAttempts"] = old.get("earlierAttempts", []) + [
                {k: v for k, v in old.items() if k != "earlierAttempts"}]
        self.report["cases"][name] = row
        self.save()
        start = time.monotonic()
        try:
            row["result"] = action()
            row["status"] = "passed"
        except Exception as error:
            row.update(status="failed", error=repr(error), lastObservation=self.latest)
            raise
        finally:
            row["seconds"] = round(time.monotonic() - start, 3)
            self.save()
            print(row["status"].upper(), name, row["seconds"], "seconds", flush=True)

    def setup(self):
        d = self.d
        assert d.shell("id", "-u") == "0"
        d.shell("input", "keyevent", "KEYCODE_HOME")
        d.nodes()  # Let Activity stop callbacks quiesce cyclic provider reads before fixtures.
        for pkg, name in ((MODULE, "AppStateShield-0.4.13.apk"), (PRIMARY, "AppStateVerifier-0.4.13.apk")):
            installed = subprocess.run(d.prefix + ["shell", "pm", "path", pkg],
                                       text=True, capture_output=True, timeout=10)
            remote = installed.stdout.strip().splitlines()[0].removeprefix("package:") if installed.stdout.strip() else None
            if not remote or d.shell("sha256sum", remote).split()[0] != self.hashes[name]:
                d.adb("install", "--no-incremental", "-r", str(ROOT / "verification" / name), timeout=60)
                remote = d.shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
            assert d.shell("sha256sum", remote).split()[0] == self.hashes[name]
        d.cli("modules", "enable", MODULE)
        for module in d.cli("modules", "ls"):
            d.scope(module["PACKAGE"], PRIMARY, module["PACKAGE"] == MODULE)
        d.batch_policy(PRIMARY, [])
        for permission in ("READ_PHONE_STATE", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "BLUETOOTH_CONNECT"):
            d.shell("pm", "grant", PRIMARY, "android.permission." + permission)
        for pkg in (MODULE, PRIMARY):
            d.shell("cmd", "locale", "set-app-locales", pkg, "--locales", "zh-CN")
        d.shell("settings", "put", "global", "hidden_api_policy", "1")
        self.report["environment"] = {"fingerprint": d.shell("getprop", "ro.build.fingerprint"),
            "abi": d.shell("getprop", "ro.product.cpu.abi"), "sdk": d.shell("getprop", "ro.build.version.sdk")}
        self.save()

    def profile(self):
        raw = self.d.shell("cat", "/data/user/0/" + MODULE + "/shared_prefs/device_profiles.xml")
        return json.loads(ET.fromstring(raw).find("string[@name='" + PRIMARY + "']").text)

    def editor(self):
        self.d.home_settings()
        self.d.picker(PRIMARY)
        self.d.click("device-config", scroll=True)
        self.d.find("device-enabled")

    def commit(self):
        self.d.click("device-save")
        self.d.find("device-config", scroll=True)
        return self.profile()

    def group(self, group):
        key = "device-network-mode:off" if group == "network" else "device-" + group + "-enabled"
        title = self.d.find("device-group:" + group, scroll=True)
        if title.get("text", "").endswith("⌄"):
            self.d.tap(title)
        return self.d.find(key, scroll=True)

    def collapsed(self, group):
        title = self.d.find("device-group:" + group, scroll=True)
        if title.get("text", "").endswith("⌃"):
            self.d.tap(title)

    def defaults(self):
        self.d.batch_profile(PRIMARY, {"schema": 1, "enabled": False, "values": {}, "selected": []})
        self.editor()
        assert self.d.find("device-enabled").get("checked") == "false"
        self.d.click("device-enabled")
        headers = {}
        expected_counts = {
            "ids": "9/10",
            "network": "15/15",
            "model": "13/13",
            "location": "3/3",
            "environment": "6/6",
        }
        for group in GROUPS:
            node = self.d.find("device-group:" + group, scroll=True)
            text = node.get("text", "")
            assert "已关闭" in text, node.attrib
            assert expected_counts[group] in text, (group, text)
            headers[group] = text
        self.d.screenshot(STATE / "default-off.png")
        self.group("ids")
        assert self.d.find("device-field-enabled:android_id", scroll=True).get("enabled") == "false"
        p = self.commit()
        assert p["enabled"] and all(not p[k] for k in FLAGS[:-1]) and p["networkMode"] == "off"
        assert len(p["selected"]) == 46 and "drm_id" not in p["selected"]
        assert set(p["selected"]) == set(p["values"]) - {"drm_id"}
        self.report["preparedProfile"] = p
        return {"headers": headers, "saved": p, "offDisablesChildControl": True,
                "defaultFieldSelection": expected_counts}

    def ui_gates(self):
        self.editor()
        for group, field in (("ids", "android_id"), ("model", "brand"),
                             ("location", "latitude"), ("environment", "hide_sensors")):
            self.group(group)
            self.d.click("device-" + group + "-enabled", scroll=True)
            assert "已开启" in self.d.find("device-group:" + group, scroll=True).get("text", "")
            node = self.d.find("device-field-enabled:" + field, scroll=True)
            assert node.get("enabled") == "true"
            if node.get("checked") == "true":
                self.d.tap(node)
                assert self.d.find("device-field-enabled:" + field, scroll=True).get("checked") == "false"
            self.collapsed(group)
        self.d.shell("settings", "put", "system", "accelerometer_rotation", "0")
        self.d.shell("settings", "put", "system", "user_rotation", "1")
        assert self.d.find("device-enabled").get("checked") == "true"
        self.d.shell("settings", "put", "system", "user_rotation", "0")
        p = self.commit()
        assert all(p[k] for k in FLAGS[:-1])
        assert "android_id" not in p["selected"] and "brand" not in p["selected"]
        self.editor()
        self.group("ids")
        self.d.click("device-ids-enabled", scroll=True)
        self.d.click("device-back")
        self.d.click("丢弃", "text")
        assert self.profile() == p
        return {"savedFlags": {k: p[k] for k in FLAGS}, "rotationPreservedDraft": True,
                "discardKeptProfile": True, "independentFields": True}

    def ui_network_refresh(self):
        before = self.profile()
        self.editor()
        self.group("network")
        states = []
        for mode, label in (("simulate", "模拟 SIM 卡"), ("no_sim", "模拟无 SIM 卡"), ("off", "已关闭")):
            self.d.click("device-network-mode:" + mode, scroll=True)
            assert label in self.d.find("device-group:network", scroll=True).get("text", "")
            states.append(label)
        self.d.click("device-group-refresh:network", scroll=True)
        self.d.click("刷新", "text")
        self.collapsed("network")
        self.group("ids")
        self.d.click("device-group-refresh:ids", scroll=True)
        self.d.click("刷新", "text")
        self.collapsed("ids")
        self.group("model")
        self.d.click("device-preset", scroll=True)
        self.d.click("vivo X200 Pro mini", "text")
        self.d.click("填写参数", "text")
        p = self.commit()
        assert {k: p[k] for k in FLAGS} == {k: before[k] for k in FLAGS}
        assert p["values"]["android_id"] != before["values"]["android_id"]
        assert p["preset"] == "vivo-x200-pro-mini"
        self.editor()
        for group in ("ids", "model", "location", "environment"):
            self.group(group)
            self.d.click("device-" + group + "-enabled", scroll=True)
            self.collapsed(group)
        p = self.commit()
        assert all(not p[k] for k in FLAGS[:-1])
        return {"networkHeaderStates": states, "refreshPreservedCategoryFlags": True,
                "presetPreservedCategoryFlags": True, "savedAllOff": True}

    def snapshot(self, profile=None, cold=False):
        d = self.d
        if profile is not None:
            d.shell("input", "keyevent", "KEYCODE_HOME")
            d.nodes()
            profile = d.batch_profile(PRIMARY, profile)
        if cold:
            d.shell("am", "force-stop", PRIMARY)
        path = "/data/user/0/" + PRIMARY + "/files/machine-result.json"
        # A restored AVD clock can lag the host. Compare device samples to each other.
        previous = subprocess.run(d.prefix + ["shell", "cat", path], capture_output=True, text=True, timeout=5)
        try:
            after = json.loads(previous.stdout).get("timestamp", 0)
        except ValueError:
            after = 0
        d.shell("am", "start", "-W", "--activity-clear-top", "-n",
                PRIMARY + "/io.github.lwtdzh.screenshotdetector.DeviceActivity")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            raw = subprocess.run(d.prefix + ["shell", "cat", path], capture_output=True, text=True, timeout=5)
            try:
                value = json.loads(raw.stdout)
            except ValueError:
                value = {}
            if value.get("timestamp", 0) > after and "ordinary" in value.get("reads", {}) and (not profile or
                    value["module"].get("deviceRevision") == profile["revision"]):
                self.latest = value
                if self.report.get("runtimePid") and not cold:
                    assert value["pid"] == self.report["runtimePid"], "Target process restarted"
                return value
            time.sleep(.1)
        raise AssertionError("No fresh complete runtime snapshot: " + str(self.latest))

    @staticmethod
    def field(value, key):
        row = value["reads"][key]
        assert "error" not in row, (key, row)
        return row["value"]

    @staticmethod
    def comparable(value, key):
        return {k: v for k, v in value["reads"][key].items() if k in {"value", "error"}}

    def baseline(self):
        p = copy.deepcopy(self.report["preparedProfile"])
        p["values"].update(android_id="1234567890abcdef", brand="CategoryBrand", model="CategoryModel",
                           hide_sensors="true", hide_module_apps="true", timezone="Asia/Tokyo", total_ram="12")
        p["selected"] = list(p["values"])
        self.fixture = p
        self.report["fixture"] = p
        value = self.snapshot(p, cold=True)
        assert value["module"]["injected"] and value["module"]["deviceEnabled"]
        assert not value["module"]["idsEnabled"] and not value["module"]["environmentEnabled"]
        assert self.field(value, "android_id") != p["values"]["android_id"]
        assert self.field(value, "hide_sensors") > 0
        self.report["nativeMACBaselineAvailable"] = any(
            name.startswith(("wlan", "eth")) for name in self.field(value, "native")["interfaces"])
        assert "wlan0" in self.field(value, "java_macs"), "No Java Wi-Fi interface baseline"
        self.base = value
        self.report["baseline"] = value
        self.report["runtimePid"] = value["pid"]
        return value

    def on_profile(self):
        p = copy.deepcopy(self.fixture)
        for key in FLAGS[:-1]:
            p[key] = True
        p["networkMode"] = "simulate"
        return p

    def enabled(self):
        p = self.on_profile()
        value = self.snapshot(p)
        for key in ("android_id", "brand", "model", "timezone"):
            assert self.field(value, key) == p["values"][key], (key, value["reads"][key])
        assert self.field(value, "hide_sensors") == 0
        assert self.field(value, "hide_module_apps") == 0
        assert self.field(value, "total_ram") == 12 * 1024 ** 3
        assert self.field(value, "latitude") == float(p["values"]["latitude"])
        assert self.field(value, "wifi_mac").lower() == p["values"]["wifi_mac"].lower()
        assert set(self.field(value, "native")["properties"]["ro.product.model"].values()) == {"CategoryModel"}
        native = self.field(value, "native")
        assert native["interfaceFreeControl"]
        for name in self.field(self.base, "native")["interfaces"]:
            if name.startswith(("wlan", "eth")):
                assert native["interfaces"][name].lower() == p["values"]["wifi_mac"].lower()
        assert self.field(value, "java_macs")["wlan0"].lower() == p["values"]["wifi_mac"].lower()
        assert self.field(value, "sim_state") == 5
        assert self.field(value, "subscription_count") == 1
        self.d.screenshot(STATE / "categories-enabled-read.png")
        return value

    def fields_off(self):
        p = self.on_profile()
        p["selected"] = []
        value = self.snapshot(p)
        for key in ("android_id", "brand", "model", "latitude", "wifi_mac", "timezone",
                    "hide_sensors", "hide_module_apps", "total_ram"):
            assert self.comparable(value, key) == self.comparable(self.base, key), (key, value["reads"][key])
        assert self.field(value, "sim_state") == 5
        cells = self.field(value, "cells")
        assert cells == self.field(value, "async_cells") and len(cells) == 1
        cell = cells[0]
        assert cell["cid"] == cell["parcelCid"] == 2147483647
        assert cell["signal"] == cell["parcelSignal"] == 2147483647
        assert not cell.get("mcc") and not cell.get("mnc")
        sub = self.field(value, "subscriptions")[0]
        assert not sub["iccid"] and not sub["parcelIccid"]
        assert not sub.get("mcc") and not sub.get("parcelMcc")
        assert self.field(value, "native")["interfaces"] == self.field(self.base, "native")["interfaces"]
        return value

    def updated(self):
        p = self.on_profile()
        p["values"].update(android_id="fedcba0987654321", model="CategoryUpdated")
        value = self.snapshot(p)
        assert self.field(value, "android_id") == "fedcba0987654321"
        assert self.field(value, "model") == "CategoryUpdated"
        assert set(self.field(value, "native")["properties"]["ro.product.model"].values()) == {"CategoryUpdated"}
        return value

    def category_off(self):
        value = self.snapshot(self.fixture)
        for key in ("android_id", "brand", "model", "latitude", "wifi_mac", "timezone",
                    "hide_sensors", "hide_module_apps", "total_ram", "sim_state", "subscription_count"):
            assert self.comparable(value, key) == self.comparable(self.base, key), (key, value["reads"][key])
        assert self.field(value, "native")["interfaces"] == self.field(self.base, "native")["interfaces"]
        return value

    def network(self, partial=False):
        p = self.on_profile()
        if partial:
            p["selected"] = ["wifi_mac", "cid", "signal"]
        value = self.snapshot(p)
        cells = self.field(value, "cells")
        assert cells == self.field(value, "async_cells") and len(cells) == 1
        cell = cells[0]
        assert cell["cid"] == cell["parcelCid"] == int(p["values"]["cid"])
        assert cell["signal"] == cell["parcelSignal"] == int(p["values"]["signal"])
        if partial:
            assert cell["tac"] == cell["pci"] == 2147483647
            assert not cell.get("mcc") and not cell.get("mnc")
        else:
            assert cell["mcc"] == p["values"]["mcc"] and cell["mnc"] == p["values"]["mnc"]
            assert self.field(value, "imsi") == p["values"]["imsi"]
        return value

    def no_sim(self):
        p = self.on_profile()
        p["networkMode"] = "no_sim"
        value = self.snapshot(p)
        assert self.field(value, "sim_state") == 1
        assert self.field(value, "subscription_count") == 0
        assert self.field(value, "cells") == self.field(value, "async_cells") == []
        assert not self.field(value, "imsi")
        assert self.field(value, "imei") == p["values"]["imei"]
        assert self.field(value, "wifi_mac").lower() == p["values"]["wifi_mac"].lower()
        self.d.screenshot(STATE / "no-sim-read.png")
        return value

    def master_off(self):
        p = self.on_profile()
        p["enabled"] = False
        value = self.snapshot(p)
        for key in ("android_id", "brand", "model", "latitude", "wifi_mac", "timezone",
                    "hide_sensors", "hide_module_apps", "total_ram", "sim_state", "subscription_count"):
            assert self.comparable(value, key) == self.comparable(self.base, key), (key, value["reads"][key])
        assert self.field(value, "native")["properties"]["ro.product.model"] == self.field(self.base, "native")["properties"]["ro.product.model"]
        assert self.field(value, "native")["interfaces"] == self.field(self.base, "native")["interfaces"]
        return value

    def legacy(self):
        p = self.on_profile()
        for key in ("idsEnabled", "environmentEnabled", "networkMode"):
            p.pop(key)
        value = self.snapshot(p)
        for key in ("android_id", "hide_sensors", "sim_state", "wifi_mac"):
            assert self.comparable(value, key) == self.comparable(self.base, key), (key, value["reads"][key])
        assert self.field(value, "model") == p["values"]["model"]
        assert value["module"]["modelEnabled"] and value["module"]["locationEnabled"]
        return value

    def run(self, phase):
        self.setup()
        if phase == "runtime" and self.report.get("runtimePid"):
            live = subprocess.run(self.d.prefix + ["shell", "pidof", PRIMARY],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
            if str(self.report["runtimePid"]) not in live.split():
                self.report.setdefault("runtimeSessions", []).append({
                    "reason": "Re-establish dependent integration after fixture stopped the provider and Android killed its reader",
                    "pid": self.report["runtimePid"],
                    "cases": {key: copy.deepcopy(self.report["cases"][key]) for key in
                              ("C04-real-category-off-baseline", "C05-all-categories-enabled")}})
                for key in ("C04-real-category-off-baseline", "C05-all-categories-enabled"):
                    self.report["cases"][key]["status"] = "rerun-required"
                self.save()
        cases = [("C01-default-headers-ui-save", self.defaults), ("C02-field-gates-rotation-discard", self.ui_gates),
                 ("C03-three-states-refresh-preset", self.ui_network_refresh)] if phase == "ui" else [
            ("C04-real-category-off-baseline", self.baseline), ("C05-all-categories-enabled", self.enabled),
            ("C06-fields-off-virtual-defaults", self.fields_off), ("C07-same-pid-values-update", self.updated),
            ("C08-category-off-restoration", self.category_off), ("C09-network-full-sync-async-parcel", self.network),
            ("C10-network-partial-fields", lambda: self.network(True)), ("C11-no-sim", self.no_sim),
            ("C12-master-off-restoration", self.master_off), ("C13-legacy-missing-flags", self.legacy)]
        for name, action in cases:
            self.case(name, action)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("capture", "ui", "runtime", "restore"))
    phase = parser.parse_args().phase
    if phase == "capture":
        preserve.capture()
    elif phase == "restore":
        restore()
    else:
        Checks().run(phase)
