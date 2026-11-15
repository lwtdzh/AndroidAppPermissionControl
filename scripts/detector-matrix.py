#!/usr/bin/env python3
"""Third-party detector evidence on the dedicated, disposable emulator only."""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from test_device import Device, MODULE, METHODS, policy_fixture, profile_fixture

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/detector-matrix-20261115"
TARGETS = {
    "native": ("com.reveny.nativecheck", ".ui.activity.MainActivity"),
    "ruru": ("com.byxiaorun.detector", ".MainActivity"),
    "key": ("io.github.vvb2060.keyattestation", ".home.HomeActivity"),
}


class DetectorDevice(Device):
    def fixture(self, filename, pkg, change):
        if pkg not in {p for p, _ in TARGETS.values()} or filename not in {"policies", "device_profiles"}:
            raise ValueError("Only these three detector packages are authorized")
        if self.shell("id", "-u") != "0":
            raise RuntimeError("Requires root on the dedicated emulator")
        self.shell("am", "force-stop", MODULE)
        folder = "/data/user/0/" + MODULE + "/shared_prefs"
        path = folder + "/" + filename + ".xml"
        raw = self.shell("sh", "-c", "test ! -f " + path + " || cat " + path)
        tree = ET.fromstring(raw) if raw else ET.Element("map")
        change(tree)
        uid = re.search(r"^package:" + re.escape(MODULE) + r" uid:(\d+)$",
                        self.shell("pm", "list", "packages", "-U", MODULE), re.M).group(1)
        temp = path + ".detector-fixture"
        command = (f"mkdir -p {folder} && cat > {temp} && chown {uid}:{uid} {temp}"
                   f" && chmod 600 {temp} && restorecon {temp} && mv {temp} {path} && rm -f {path}.bak")
        subprocess.run(self.prefix + ["shell", command], input=ET.tostring(tree, encoding="utf-8"),
                       check=True, timeout=15, stdout=subprocess.DEVNULL)
        if ET.tostring(ET.fromstring(self.shell("cat", path))) != ET.tostring(tree):
            raise AssertionError("Fixture read-back differs")

    def configure(self, pkg, enabled, profile, scoped):
        self.shell("am", "force-stop", pkg)
        for module in self.cli("modules", "ls"):
            self.scope(module["PACKAGE"], pkg, scoped and module["PACKAGE"] == MODULE)
        self.fixture("policies", pkg, lambda tree: policy_fixture(tree, pkg, enabled))
        self.fixture("device_profiles", pkg, lambda tree: profile_fixture(tree, pkg, profile))
        # Real edits happen in this Activity. Clear the fixture-only stopped state
        # before a target without QUERY_ALL_PACKAGES resolves the provider.
        self.shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
        self.configuration = {"scope": scoped, "methods": sorted(enabled), "profile": profile}

    def page(self):
        self.shell("uiautomator", "dump", "--compressed", self.ui_path)
        raw = self.shell("cat", self.ui_path)
        nodes = list(ET.fromstring(raw).iter("node"))
        return raw, nodes

    def reset_key(self, dest):
        """Use the detector's own reset, deleting only its current UID's keys."""
        self.click("More options")
        raw, nodes = self.page()
        (dest / "reset-menu.xml").write_text(raw)
        self.tap(next(n for n in nodes if n.get("text") == "Reset"))
        raw, _ = self.page()
        (dest / "after-reset.xml").write_text(raw)

    def capture(self, case, name):
        pkg, activity = TARGETS[name]
        dest = STATE / "evidence" / case / name
        dest.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        stamp = datetime.now(timezone.utc).isoformat()
        self.shell("am", "force-stop", pkg)
        self.adb("logcat", "-c")
        launched = self.shell("am", "start", "-W", "-n", pkg + "/" + activity)
        if name == "key":
            self.reset_key(dest)
        pages, unique, statuses = [], [], {}
        previous = None
        unchanged = 0
        expanded = set()
        for index in range(10):
            raw, nodes = self.page()
            texts = [n.get("text") for n in nodes if n.get("text")]
            if not any(n.get("package") == pkg for n in nodes):
                (dest / f"page-{index}.xml").write_text(raw)
                self.screenshot(dest / f"page-{index}.png")
                break
            if "Disclaimer" in texts:
                self.tap(next(n for n in nodes if n.get("text") == "OK"))
                raw, nodes = self.page()
                texts = [n.get("text") for n in nodes if n.get("text")]
            if name == "ruru":
                for label in ("Abnormal Environment", "Setting Props"):
                    node = next((n for n in nodes if n.get("text") == label), None)
                    if node is not None and label not in expanded:
                        self.tap(node)
                        expanded.add(label)
                        raw, nodes = self.page()
                texts = [n.get("text") for n in nodes if n.get("text")]
                for row in ET.fromstring(raw).iter("node"):
                    label = None
                    for child in row:
                        if child.get("text"):
                            label = child.get("text")
                        status = child.get("content-desc")
                        if label and status in {"Not Found", "Suspicious", "Method unavailable", "Found"}:
                            statuses[label] = status
            (dest / f"page-{index}.xml").write_text(raw)
            self.screenshot(dest / f"page-{index}.png")
            pages.append(texts)
            for text in texts:
                if text not in unique:
                    unique.append(text)
            unchanged = unchanged + 1 if raw == previous else 0
            if unchanged >= 2:
                break
            previous = raw
            scroll = next((n for n in nodes if n.get("scrollable") == "true"), nodes[0])
            left, top, right, bottom = map(int, re.findall(r"\d+", scroll.get("bounds")))
            x = (left + right) // 2
            self.shell("input", "swipe", x, int(top + (bottom-top)*.78),
                       x, int(top + (bottom-top)*.22), 500)
        pid = self.shell("sh", "-c", "pidof " + shlex.quote(pkg) + " || true")
        logs = self.adb("logcat", "-d", "-v", "threadtime", "--pid=" + pid) if pid else ""
        if not pid:
            logs = self.adb("logcat", "-d", "-v", "threadtime")
            (dest / "exit-info.txt").write_text(self.shell("dumpsys", "activity", "exit-info", pkg))
        (dest / "logcat.txt").write_text(logs)
        result = {"package": pkg, "launch": launched, "pid": pid, "durationSeconds": round(time.monotonic()-start, 2),
                  "pages": pages, "texts": unique,
                  "statuses": statuses,
                  "startupFailure": not bool(pid),
                  "freshKeyReset": name == "key",
                  "injectionLog": [line for line in logs.splitlines()
                                   if "AppStateShield" in line or "DeviceProfile" in line],
                  "screenshots": [p.name for p in dest.glob("*.png")]}
        result["configuration"] = getattr(self, "configuration", None)
        result["startedAtUTC"] = stamp
        result["nativeReadyLog"] = [line for line in logs.splitlines() if "native ready" in line]
        policy = re.findall(r"Policy loaded=(true|false) enabled=\[([^]]*)\]", logs)
        configured = result["configuration"]
        result["policyConfirmed"] = bool(policy) and policy[-1][0] == "true"
        if configured and configured["scope"]:
            result["policyConfirmed"] = result["policyConfirmed"] and (
                sorted(filter(None, (x.strip() for x in policy[-1][1].split(",")))) ==
                configured["methods"])
        module_apk = self.shell("pm", "path", MODULE).splitlines()[0].removeprefix("package:")
        result["moduleSHA256"] = self.shell("sha256sum", module_apk).split()[0]
        (dest / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"case": case, "detector": name, "pid": pid, "texts": unique}, ensure_ascii=False), flush=True)
        if configured and configured["scope"] and not result["policyConfirmed"]:
            raise AssertionError("Detector did not load its intended policy: " + name)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case")
    parser.add_argument("--detector", choices=TARGETS, action="append")
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--scope", action="store_true")
    parser.add_argument("--methods", default="")
    parser.add_argument("--profile", type=pathlib.Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.case):
        raise ValueError("Invalid case label")
    d = DetectorDevice()
    enabled = set(filter(None, args.methods.split(",")))
    if not enabled <= set(METHODS):
        raise ValueError("Unknown protection method")
    profile = json.loads(args.profile.read_text()) if args.profile else {"schema": 1, "enabled": False}
    for name in args.detector or TARGETS:
        if args.configure:
            d.configure(TARGETS[name][0], enabled, profile, args.scope)
        d.capture(args.case, name)


if __name__ == "__main__":
    main()
