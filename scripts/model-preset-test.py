#!/usr/bin/env python3
"""Preset UI, live Java/native reads and migration on emulator-5584 only."""
import hashlib
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
spec = importlib.util.spec_from_file_location("ui", ROOT / "scripts/requirement-ui-test.py")
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
ui.machine.STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/model-presets-0.4.3"
ui.machine.REPORT = OUT / "model-presets-0.4.3-results.json"
ui.machine.PACKAGES = (ui.MODULE, ui.PRIMARY)

MODEL = ["brand", "manufacturer", "model", "device", "product", "board",
         "hardware", "release", "incremental", "fingerprint"]

class Audit(ui.Audit):
    def revision_read(self, profile):
        # These cases verify model fields in the main process; phone-worker
        # completion is independent of the property adapter being exercised.
        latest = {}
        def ready():
            value = self.read()
            latest.update(value)
            return value if value["module"]["deviceRevision"] == profile["revision"] else None
        try:
            return self.wait(ready, "Main reader did not receive model revision", timeout=12)
        except Exception:
            (OUT/"model-revision-failure-0.4.3.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2)+"\n")
            raise

    def choose(self, title):
        self.d.click("device-preset")
        nodes = self.d.nodes()
        labels = [n.get("text", "") for n in nodes]
        assert title in labels and not any("X9s" in s for s in labels)
        assert "小米 14 · 国际版" in labels and "vivo X200 Pro mini" in labels
        assert not any("本机实测" in s for s in labels)
        self.d.click(title, "text")
        self.d.click("使用预设", "text")

    def assert_read(self, profile, sample):
        (OUT/("model-observed-"+profile["preset"]+"-0.4.3.json")).write_text(json.dumps(sample, ensure_ascii=False, indent=2)+"\n")
        assert sample["module"]["deviceEnabled"]
        assert sample["module"]["deviceRevision"] == profile["revision"]
        for key in MODEL:
            assert str(sample["reads"][key].get("value")) == profile["values"][key], (key, sample["reads"][key])
        v = profile["values"]
        expected = {"ro.product.model": v["model"], "ro.product.brand": v["brand"],
                    "ro.product.manufacturer": v["manufacturer"], "ro.build.fingerprint": v["fingerprint"],
                    "ro.product.device": v["device"], "ro.product.name": v["product"],
                    "ro.product.board": v["board"], "ro.hardware": v["hardware"]}
        if profile["preset"] == "vivo-x200-pro-mini":
            expected.update({"ro.product.vendor.device": "PD2415", "ro.product.odm.name": "PD2415",
                "ro.product.system_ext.manufacturer": "vivo", "ro.vendor.build.version.release": "15",
                "ro.vendor.build.fingerprint": "vivo/PD2415/PD2415:15/AP3A.240905.015.A2/compiler261012170621:user/release-keys"})
        else:
            expected.update({"ro.product.vendor.device": "mivendor", "ro.product.odm.name": "houji_global",
                "ro.product.system_ext.manufacturer": "QUALCOMM", "ro.vendor.build.version.release": "14",
                "ro.vendor.build.fingerprint": "Xiaomi/mivendor_sm8650_global/mivendor:14/UKQ1.240523.001/OS2.0.201.0.VNCMIXM:user/release-keys"})
        java = sample["reads"]["java_properties"]["value"]
        native = sample["reads"]["native"]["value"]
        for key, value in expected.items():
            assert java[key] == value, (key, java[key], value)
            assert len(native["properties"][key]) == 3
            paths = native["properties"][key]
            assert paths["get"] == value[:91] and paths["callback"] == value, (key, paths, value)
            # Bionic's deprecated read API returns a name capped at PROP_NAME_MAX.
            # Existing filters receive that truncated name for keys >= 32 bytes.
            if len(key) < 32:
                assert paths["read"] == value[:91], (key, paths, value)
            else:
                assert paths["read"] == self.baseline["reads"]["native"]["value"]["properties"][key]["read"]
        assert native["interfaceFreeControl"] and native["propertyCallbackLifetimeControl"]
        assert sample["reads"]["ordinary"]["value"]["file"] == "ordinary-device-control"
        return {"modelFields": len(MODEL), "properties": len(expected), "javaAndNativeCallbackFullValues": True,
                "legacyNativeValueLimit": [key for key, value in expected.items() if len(value) > 91],
                "legacyNativeReadVerifiedForShortKeys": True,
                "legacyNativeLongKeyLimit": [key for key in expected if len(key) >= 32]}

    def run_checks(self):
        d = self.d
        if not (ui.machine.STATE/"state.json").exists():
            self.capture()
        self.report["artifacts"] = {name: hashlib.sha256((OUT/name).read_bytes()).hexdigest()
            for name in ["AppStateShield-0.4.3.apk", "AppStateVerifier-0.4.3.apk"]}
        for name in self.report["artifacts"]:
            d.adb("install", "--no-incremental", "-r", str(OUT/name))
        for row in d.cli("modules", "ls"):
            d.scope(row["PACKAGE"], ui.PRIMARY, False)
        d.cli("modules", "enable", ui.MODULE); d.scope(ui.MODULE, ui.PRIMARY, True)
        d.shell("settings", "put", "global", "hidden_api_policy", "1")
        d.shell("cmd", "locale", "set-app-locales", ui.MODULE, "--locales", "zh-CN")
        d.batch_profile(ui.PRIMARY, {"schema": 1, "enabled": False, "preset": "custom", "values": {}, "selected": []})
        self.input_metadata = ui.case_inputs(d, self.report["artifacts"])
        assert self.input_metadata.get("buildInputsSHA256"), "Source/build binding missing"
        baseline = self.read(cold=True)
        self.baseline = baseline
        assert baseline["module"]["injected"] and not baseline["module"]["deviceEnabled"]

        def vivo():
            self.open_editor(); d.click("device-enabled")
            self.choose("vivo X200 Pro mini")
            d.find("device-group:model", scroll=True)
            assert not any(n.get("content-desc", "").startswith("device-edit:") for n in d.nodes())
            d.screenshot(str(OUT/"model-vivo-collapsed-0.4.3.png"))
            self.save()
            profile = self.profile(); assert profile["preset"] == "vivo-x200-pro-mini"
            sample = self.revision_read(profile)
            assert sample["pid"] == baseline["pid"]
            return {"profile": profile, "observed": sample, "samePid": sample["pid"], "groupsDefaultCollapsed": True,
                    **self.assert_read(profile, sample)}
        self.case("P01-vivo-preset-save-live-read", vivo)

        def xiaomi():
            self.open_editor(); self.choose("小米 14 · 国际版"); self.save()
            profile = self.profile(); sample = self.revision_read(profile)
            assert sample["pid"] == baseline["pid"]
            self.assert_read(profile, sample)
            self.open_editor()
            d.click("device-group:model", scroll=True)
            d.click("device-group-refresh:model", scroll=True)
            d.click("刷新", "text")
            self.save(); refreshed = self.profile()
            assert profile["values"] == refreshed["values"]
            assert set(profile["selected"]) == set(refreshed["selected"])
            after = self.revision_read(refreshed)
            assert after["pid"] == sample["pid"]
            return {"profile": refreshed, "observed": after, "samePid": after["pid"], "fixedRefresh": True,
                    **self.assert_read(refreshed, after)}
        self.case("P02-xiaomi-switch-refresh-live-read", xiaomi)

        def cancel():
            original = self.profile()
            self.open_editor(); self.choose("vivo X200 Pro mini")
            d.click("device-back"); d.click("丢弃", "text")
            assert self.profile() == original
            return {"changedPresetDraftDiscarded": True}
        self.case("P03-preset-draft-discard", cancel)
        # On a resumed same-APK run, prior UI cases remain passed. Restore their
        # saved fixture once so remaining cases can run after environment cleanup.
        kept = self.report["cases"]["P02-xiaomi-switch-refresh-live-read"]
        current = self.profile()
        expected_profile = kept["evidence"]["profile"]
        if not current.get("enabled") or current.get("values") != expected_profile["values"]:
            self.revision_read(d.batch_profile(ui.PRIMARY, expected_profile))

        def manual():
            original = self.profile()
            changed = json.loads(json.dumps(original))
            changed["values"]["device"] = "manual-device"
            changed = d.batch_profile(ui.PRIMARY, changed)
            sample = self.revision_read(changed)
            assert sample["pid"] == baseline["pid"]
            assert sample["reads"]["device"]["value"] == "manual-device"
            assert sample["reads"]["java_properties"]["value"]["ro.product.vendor.device"] == "manual-device"
            assert all(value == "manual-device" for value in sample["reads"]["native"]["value"]["properties"]["ro.product.vendor.device"].values())
            d.batch_profile(ui.PRIMARY, original)
            return {"customValueWinsInJavaAndNative": True, "samePid": sample["pid"]}
        self.case("P04-manual-device-override", manual)

        def migration():
            original = self.profile()
            legacy = json.loads(json.dumps(original))
            legacy["preset"] = "oppo-x9s"
            legacy["values"].update({"device": "privacy_x9s_123456", "product": "privacy_x9s_123456",
                "board": "privacy_board", "hardware": "privacy_platform", "incremental": "PRIVATE.12345678",
                "fingerprint": "OPPO/privacy_x9s_123456/privacy_x9s_123456:16/PRIVATE/PRIVATE.12345678:user/release-keys",
                "future_value": "KEEP"})
            d.batch_profile(ui.PRIMARY, legacy)
            self.open_editor(); self.save()
            migrated = self.profile()
            assert migrated["enabled"] and migrated["preset"] == "custom"
            for key in ["device", "product", "board", "hardware", "incremental", "fingerprint"]:
                assert key not in migrated["values"] and key not in migrated["selected"]
            assert migrated["values"]["imei"] == original["values"]["imei"]
            assert migrated["values"]["future_value"] == "KEEP"
            assert migrated["networkMode"] == original["networkMode"]
            d.batch_profile(ui.PRIMARY, original)
            return {"oldOppoBecomesCustom": True, "onlyKnownPlaceholdersRemoved": True, "idsAndUnknownValuesRetained": True}
        self.case("P05-oppo-retirement-save", migration)

        def disable():
            profile = d.batch_profile(ui.PRIMARY, dict(self.profile(), enabled=False))
            sample = self.revision_read(profile)
            assert sample["pid"] == baseline["pid"] and not sample["module"]["deviceEnabled"]
            for key in MODEL:
                assert sample["reads"][key] == baseline["reads"][key], key
            assert sample["reads"]["java_properties"]["value"] == baseline["reads"]["java_properties"]["value"]
            assert sample["reads"]["native"]["value"]["properties"] == baseline["reads"]["native"]["value"]["properties"]
            return {"originalBuildAndPropertiesRestored": True, "samePid": sample["pid"], "observed": sample}
        self.case("P06-disable-restores-original", disable)

if __name__ == "__main__":
    run = Audit()
    try:
        run.run_checks()
    finally:
        if (ui.machine.STATE/"state.json").exists():
            run.restore()
        run.d.adb("unroot"); run.d.adb("wait-for-device")
        assert run.d.shell("id", "-u") == "2000"
        run.report["restoration"]["adbdUnrooted"] = True
        run.d.adb("emu", "kill")
        run.report["restoration"]["emulatorShutdown"] = True
        ui.machine.REPORT.write_text(json.dumps(run.report, ensure_ascii=False, indent=2)+"\n")
