"""Real screenshots and visible multi-route logger checks on the dedicated AVD."""
import collections
import json
import pathlib
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET

P = "io.github.lwtdzh.screenshotdetector"
M = "io.github.lwtdzh.screenshotshield"
CLI = "/data/adb/modules/zygisk_vector/cli"
ADB = ["adb", "-s", "emulator-5584"]
WORK = pathlib.Path("/tmp/screenshot-detector-work")
COMPONENT = P + "/.AccessibilityDetector"
NOTIFICATION = P + "/.NotificationDetector"
SOURCES = {
    "official", "binder", "media_observer", "media_poll", "media_legacy", "media_client",
    "file_observer", "file_poll", "native_inotify", "native_files", "native_syscall",
    "accessibility_event", "accessibility_nodes",
}


def adb(*args):
    return subprocess.check_output(ADB + list(args), text=True, timeout=25).strip()


def shell(*args):
    return adb("shell", shlex.join(args))


def cli(*args):
    return shell(CLI, *args)


def wait_for(condition, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("Timed out waiting for detector state")


def logs(pid):
    return adb("logcat", "-d", "--pid=" + pid, "-s",
               "ScreenshotDetector:I", "ScreenshotShield:I", "AndroidRuntime:E", "*:S")


def view():
    shell("uiautomator", "dump", "--compressed", "/data/local/tmp/detector-check.xml")
    root = ET.fromstring(shell("cat", "/data/local/tmp/detector-check.xml"))
    return [n for n in root.iter("node") if n.get("package") == P]


def click(label):
    node = wait_for(lambda: [n for n in view() if n.get("text") == label])[0]
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    shell("input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))


def photos():
    return shell("content", "query", "--uri", "content://media/external/images/media",
                 "--projection", "_id", "--where", "relative_path='Pictures/Screenshots/'")


def detections(log):
    return collections.Counter(re.findall(r"DETECTED source=(\w+)", log))


def launch(protected):
    cli("scope", "add" if protected else "rm", M, P + "/0")
    shell("am", "force-stop", P)
    # Force stop disables enabled accessibility services; reconnect AFTER stopping.
    shell("settings", "put", "secure", "enabled_accessibility_services", COMPONENT)
    shell("settings", "put", "secure", "accessibility_enabled", "1")
    shell("input", "keyevent", "WAKEUP")
    shell("wm", "dismiss-keyguard")
    shell("am", "start", "-W", "-n", P + "/.MainActivity")
    pid = shell("pidof", P).split()[0]
    wait_for(lambda: all(f"source={s} code=state_ready" in logs(pid) for s in SOURCES))
    click("清空日志")
    return pid


def restore_setting(key, value):
    if value == "null":
        shell("settings", "delete", "secure", key)
    else:
        shell("settings", "put", "secure", key, value)


if __name__ == "__main__":
    assert "emulator-5584" in adb("devices")
    assert shell("settings", "get", "global", "hidden_api_policy") == "null"
    assert "versionName=0.1.4" in shell("dumpsys", "package", M)
    assert "versionName=0.1.1" in shell("dumpsys", "package", P)
    # This test requires granted photo/all-file/notification permissions on the dedicated AVD.
    original_scope = json.loads(cli("--json", "scope", "ls", M))["data"]
    originally_scoped = any(n["APP_PACKAGE"] == P for n in original_scope)
    old_services = shell("settings", "get", "secure", "enabled_accessibility_services")
    old_enabled = shell("settings", "get", "secure", "accessibility_enabled")
    shell("cmd", "locale", "set-app-locales", P, "--locales", "zh-Hans")
    WORK.mkdir(exist_ok=True)
    results = []
    try:
        for protected in (False, True):
            pid = launch(protected)
            baseline_log = logs(pid)
            assert not detections(baseline_log), "Existing items must not be counted as new screenshots."
            before = photos()
            shell("input", "-d", "0", "keyevent", "SYSRQ")
            wait_for(lambda: photos() != before)
            if not protected:
                wait_for(lambda: SOURCES <= set(detections(logs(pid))))
            texts = wait_for(lambda: [n.get("text", "") for n in view()])
            current = logs(pid)
            signals = detections(current)
            assert "FATAL EXCEPTION" not in current
            if protected:
                assert not signals, current
                assert "0 条截图信号" in texts, texts
            else:
                assert SOURCES <= set(signals), signals
                assert f"{sum(signals.values())} 条截图信号" in texts, texts
            results.append({
                "protected": protected, "systemui_saved_screenshot": True,
                "detector_version": "0.1.1", "module_version": "0.1.4",
                "hidden_api_policy": shell("settings", "get", "global", "hidden_api_policy"),
                "signal_counts": dict(signals),
            })
            (WORK / ("protected.log" if protected else "unprotected.log")).write_text(current)
            print(results[-1], flush=True)
        # A real delivered broadcast, explicitly a fixture rather than a ROM screenshot action.
        for protected in (False, True):
            pid = launch(protected)
            shell("am", "broadcast", "-a", P + ".SCREENSHOT_TEST", "-p", P)
            shell("am", "broadcast", "-a", P + ".SCREENSHOT_TEST", "-n", P + "/.BroadcastDetector")
            texts = wait_for(lambda: [n.get("text", "") for n in view()])
            signals = detections(logs(pid))
            if protected:
                assert not signals, signals
            else:
                assert {"broadcast_dynamic", "broadcast_manifest"} <= set(signals), signals
            results.append({"protected": protected, "fixture": "delivered_broadcast",
                            "signal_counts": dict(signals), "real_rom_action": False})
            print(results[-1], flush=True)
    finally:
        cli("scope", "add" if originally_scoped else "rm", M, P + "/0")
        shell("am", "force-stop", P)
        restore_setting("enabled_accessibility_services", old_services)
        restore_setting("accessibility_enabled", old_enabled)
        shell("cmd", "locale", "set-app-locales", P)
        shell("rm", "-f", "/data/local/tmp/detector-check.xml")
    (WORK / "detector-expanded.json").write_text(json.dumps(
        {"passed": True, "cases": results}, ensure_ascii=False, indent=2) + "\n")
