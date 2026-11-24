#!/usr/bin/env python3
"""Dedicated-emulator helpers; UI persistence and bulk runtime fixtures are separate."""
import json
import pathlib
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

ADB = "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"
MODULE = "io.github.lwtdzh.appstateshield"
PRIMARY = "io.github.lwtdzh.screenshotdetector"
METHODS = ["screenshot", "vpn", "proxy", "developer", "debug", "selinux"]
CLI = "/data/adb/modules/zygisk_vector/cli"
TEST_TARGETS = {PRIMARY, PRIMARY + ".samplea", PRIMARY + ".sampleb.screenshot"}


def policy_fixture(tree, pkg, enabled):
    """Preserve unknown method IDs and every unrelated preference/package."""
    node = tree.find("string[@name='apps']")
    if node is None:
        node = ET.SubElement(tree, "string", name="apps")
    apps = json.loads(node.text or "{}")
    disabled = set(apps.get(pkg, [])) - set(METHODS)
    apps[pkg] = sorted(disabled | (set(METHODS) - set(enabled)))
    node.text = json.dumps(apps, ensure_ascii=False, separators=(",", ":"))


def profile_fixture(tree, pkg, profile):
    node = tree.find("string[@name='" + pkg + "']")
    previous = json.loads(node.text or "{}") if node is not None else {}
    value = json.loads(json.dumps(profile))
    value["revision"] = max(int(time.time() * 1000), previous.get("revision", 0) + 1)
    if node is None:
        node = ET.SubElement(tree, "string", name=pkg)
    node.text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


class Device:
    def __init__(self, serial="emulator-5584"):
        if serial != "emulator-5584":
            raise ValueError("Only emulator-5584 is accepted")
        self.prefix = [ADB, "-s", serial]
        if "ScreenshotShield_API36" not in self.adb("emu", "avd", "name"):
            raise ValueError("Wrong AVD")
        if self.shell("getprop", "ro.boot.qemu") != "1":
            raise ValueError("Expected an emulator")
        self.ui_path = "/data/local/tmp/appstate-manual-ui.xml"

    def adb(self, *args, timeout=40):
        return subprocess.check_output(self.prefix + list(args), text=True, timeout=timeout).strip()

    def shell(self, *args):
        # MediaStore resolves the caller's package: UID 0 has none; shell owns com.android.shell.
        if args and args[0] == "content":
            result = subprocess.run(self.prefix + ["shell",
                shlex.join(["su", "2000", "-c", shlex.join(str(x) for x in args)])],
                capture_output=True, text=True, timeout=40)
            output = result.stdout + result.stderr
            if result.returncode or "Error while accessing provider" in output or "Exception" in output:
                raise RuntimeError("MediaStore command failed: " + output)
            return result.stdout.strip()
        return self.adb("shell", shlex.join(str(x) for x in args))

    def cli(self, *args):
        value = json.loads(self.shell(CLI, "--json", *args))
        if not value.get("success"):
            raise RuntimeError("Vector failed: " + " ".join(args))
        return value.get("data")

    def scope(self, module, pkg, enabled):
        exists = any(row["APP_PACKAGE"] == pkg and row["USER_ID"] == 0
                     for row in self.cli("scope", "ls", module))
        if enabled != exists:
            self.cli("scope", "add" if enabled else "rm", module, pkg + "/0")

    def nodes(self):
        self.shell("uiautomator", "dump", "--compressed", self.ui_path)
        return list(ET.fromstring(self.shell("cat", self.ui_path)).iter("node"))

    def center(self, node):
        left, top, right, bottom = map(int, re.findall(r"\d+", node.get("bounds", "")))
        return (left + right) // 2, (top + bottom) // 2

    def tap(self, node):
        self.shell("input", "tap", *self.center(node))

    def find(self, value, attribute="content-desc", scroll=False):
        for attempt in range(9 if scroll else 3):
            node = next((n for n in self.nodes() if n.get(attribute) == value), None)
            if node is not None:
                return node
            if scroll:
                if attempt < 3:
                    self.swipe_up()
                else:
                    self.swipe_down()
        raise AssertionError("Missing UI control: " + value)

    def click(self, value, attribute="content-desc", scroll=False):
        self.tap(self.find(value, attribute, scroll))
        if value == "save" and attribute == "content-desc":
            self.find("add-app")  # Wait for the committed editor to return home before reading disk.

    def swipe_up(self):
        width, height = self.dimensions()
        self.shell("input", "swipe", width // 2, int(height * .72), width // 2, int(height * .28), 250)

    def swipe_down(self):
        width, height = self.dimensions()
        self.shell("input", "swipe", width // 2, int(height * .28), width // 2, int(height * .72), 250)

    def back(self):
        self.shell("input", "keyevent", "BACK")

    def dimensions(self):
        bounds = list(map(int, re.findall(r"\d+", self.nodes()[0].get("bounds"))))
        return bounds[2], bounds[3]

    def search(self, value):
        node = self.find("app-search")
        current = node.get("text", "")
        self.tap(node)
        self.shell("input", "keyevent", "KEYCODE_MOVE_END")
        if current:
            self.shell("input", "keyevent", *(["KEYCODE_DEL"] * len(current)))
        if value:
            self.shell("input", "text", value.replace(" ", "%s"))
        self.back()

    def home_settings(self):
        self.shell("am", "force-stop", MODULE)
        self.shell("am", "start", "-W", "-n", MODULE + "/.SettingsActivity")
        self.find("add-app")

    def picker(self, pkg):
        self.click("add-app")
        self.search(pkg)
        self.click("pick:" + pkg)
        self.find("save")

    def set_policy(self, pkg, enabled):
        self.home_settings()
        self.picker(pkg)
        wanted = {key: key in enabled for key in METHODS}
        visited = set()
        for attempt in range(10):
            for node in self.nodes():
                desc = node.get("content-desc", "")
                if not desc.startswith("method:"):
                    continue
                key = desc.split(":", 1)[1]
                if key in visited:
                    continue
                if (node.get("checked") == "true") != wanted[key]:
                    self.tap(node)
                visited.add(key)
            if visited == set(METHODS):
                break
            self.swipe_up()
        if visited != set(METHODS):
            raise AssertionError("Cannot edit every method")
        self.click("save")
        self.find("add-app")

    def batch_preference(self, filename, pkg, change):
        """Root-only atomic fixture on the dedicated AVD; never stop a target reader."""
        if pkg not in TEST_TARGETS or filename not in {"policies", "device_profiles"}:
            raise ValueError("Only synthetic targets and known preference files are accepted")
        if self.shell("id", "-u") != "0":
            raise RuntimeError("Bulk fixtures require root on the dedicated emulator")
        self.shell("am", "force-stop", MODULE)  # Discard the provider's cached SharedPreferences.
        folder = "/data/user/0/" + MODULE + "/shared_prefs"
        path = folder + "/" + filename + ".xml"
        raw = self.shell("sh", "-c", "test ! -f " + path + " || cat " + path)
        tree = ET.fromstring(raw) if raw else ET.Element("map")
        result = change(tree)
        uid = re.search(r"^package:" + re.escape(MODULE) + r" uid:(\d+)$",
                        self.shell("pm", "list", "packages", "--user", "0", "-U", MODULE), re.M).group(1)
        mode = self.shell("stat", "-c", "%a", path) if raw else "600"
        temporary = path + ".appstate-fixture"
        command = ("mkdir -p " + folder + " && cat > " + temporary +
                   " && chown " + uid + ":" + uid + " " + temporary +
                   " && chmod " + mode + " " + temporary + " && restorecon " + temporary +
                   " && mv " + temporary + " " + path + " && rm -f " + path + ".bak")
        subprocess.run(self.prefix + ["shell", command], input=ET.tostring(tree, encoding="utf-8"),
                       check=True, timeout=15, stdout=subprocess.DEVNULL)
        # Check all elements, including unknown keys and other apps, after saving.
        saved = ET.fromstring(self.shell("cat", path))
        if ET.tostring(saved) != ET.tostring(tree):
            raise AssertionError("Bulk preference read-back differs")
        # A live target may restart the provider during the atomic write and
        # cache the previous XML. Invalidate that process after the read-back.
        self.shell("am", "force-stop", MODULE)
        return result

    def batch_policy(self, pkg, enabled):
        if not set(enabled) <= set(METHODS):
            raise ValueError("Unknown enabled method")
        self.batch_preference("policies", pkg, lambda tree: policy_fixture(tree, pkg, enabled))

    def batch_profile(self, pkg, profile):
        return self.batch_preference("device_profiles", pkg,
                                     lambda tree: profile_fixture(tree, pkg, profile))

    def kill_reader(self, pkg):
        for line in self.shell("ps", "-A", "-o", "PID,NAME").splitlines()[1:]:
            fields = line.split()
            if len(fields) == 2 and fields[1] == pkg:
                self.shell("kill", "-9", fields[0])

    def start_probe(self, pkg, kind="state", cold=True):
        if cold:
            self.kill_reader(pkg)
        filename = "screenshot-result.json" if kind == "shot" else "result.json"
        path = "/data/user/0/" + pkg + "/files/" + filename
        self.shell("rm", "-f", path)
        activity = ("io.github.lwtdzh.screenshotprobe.ProbeActivity" if kind == "shot"
                    else "io.github.lwtdzh.devicestateprobe.ProbeActivity")
        # A restored task may have a fixture above its root probe. Request the
        # probe itself instead of merely bringing that task's old top forward.
        action = ["--es", "action", "selinux"] if kind == "selinux" else []
        self.shell("am", "start", "-W", "--activity-clear-top", "-n", pkg + "/" + activity, *action)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            result = subprocess.run(self.prefix + ["shell", "cat", path], text=True, capture_output=True, timeout=10)
            if result.returncode == 0:
                try:
                    value = json.loads(result.stdout)
                    if kind == "state" and "proxyFixture" in value:
                        return value
                    if kind == "selinux" and "bootProperty" in value:
                        return value
                    if kind == "shot" and ("clipboard_normal_visible" in value or "startup_error" in value or "inspect_error" in value):
                        return value
                except json.JSONDecodeError:
                    pass
            time.sleep(.2)
        raise TimeoutError("No complete probe result")

    def read_shot(self, pkg):
        path = "/data/user/0/" + pkg + "/files/screenshot-result.json"
        deadline = time.monotonic() + 5
        while True:
            try:
                return json.loads(self.shell("cat", path))
            except json.JSONDecodeError:
                # Live callbacks may be rewriting this diagnostic snapshot.
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)

    def screenshot(self, destination):
        with pathlib.Path(destination).open("wb") as out:
            subprocess.run(self.prefix + ["exec-out", "screencap", "-p"], stdout=out, check=True, timeout=10)
