#!/usr/bin/env python3
"""Drive SystemUI through a screenshot key; require a saved image and baseline API receipt."""
import argparse
import atexit
import json
import pathlib
import subprocess
import time

MODULE = "io.github.lwtdzh.screenshotshield"
PROBE = "io.github.lwtdzh.screenshotprobe"
CLI = "/data/adb/modules/zygisk_vector/cli"

parser = argparse.ArgumentParser()
parser.add_argument("--serial", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--trigger", choices=["input-key", "console-chord"], default="input-key")
args = parser.parse_args()
if not args.serial.startswith("emulator-"):
    parser.error("Emulator serial required.")


def adb(*parts):
    return subprocess.check_output(["adb", "-s", args.serial, *parts], text=True, timeout=20).strip()


def shell(command):
    return adb("shell", command)


def latest():
    records = [json.loads(line.split("RESULT ", 1)[1])
               for line in adb("logcat", "-d", "-s", "ScreenshotProbe:I", "*:S").splitlines()
               if "RESULT " in line]
    return records[-1] if records else {}


def shots():
    # Read from unscoped shell; the module cannot falsify the system's saved image records.
    return shell("content query --uri content://media/external/images/media"
                 " --projection _id:_display_name --where \"relative_path='Pictures/Screenshots/'\"")


def run(enabled):
    shell(CLI + " scope set " + MODULE + " " + PROBE + "/0")
    # Vector's scope setter may enable a module; apply the requested enablement last.
    shell(CLI + " modules " + ("enable " if enabled else "disable ") + MODULE)
    shell("am force-stop " + PROBE)
    adb("logcat", "-c")
    shell("input keyevent WAKEUP; wm dismiss-keyguard")
    shell("am start -W -n " + PROBE + "/.ProbeActivity" + binder_args)
    before = shots()
    if args.trigger == "console-chord":
        adb("emu", "event", "send", "EV_KEY:KEY_VOLUMEDOWN:1", "EV_KEY:KEY_POWER:1", "EV_SYN:0:0")
        try:
            time.sleep(0.6)  # key-chord hold duration, not a retry delay
        finally:
            adb("emu", "event", "send", "EV_KEY:KEY_POWER:0", "EV_KEY:KEY_VOLUMEDOWN:0", "EV_SYN:0:0")
    else:
        # Inject a screenshot keyboard shortcut, not adb screencap or a synthetic API callback.
        # New virtio-input emulators may not route legacy console EV_KEY events.
        shell("input -d 0 keyevent SYSRQ")
    deadline = time.monotonic() + 10
    after = before
    while time.monotonic() < deadline:
        after = shots()
        if after != before:
            break
        time.sleep(0.2)
    saved = after != before
    deadline = time.monotonic() + 3
    value = latest()
    while not enabled and (value.get("screen_capture_callbacks", 0) == 0
                           or value.get("raw_screen_capture_callbacks", 0) == 0) and time.monotonic() < deadline:
        value = latest()
        time.sleep(0.1)
    logs = adb("logcat", "-d", "-s", "ScreenshotShield:I", "*:S")
    return {"enabled": enabled, "systemui_saved_screenshot": saved,
            "probe": value, "module_logs": logs}


previous_policy = shell("settings get global hidden_api_policy")
atexit.register(lambda: shell("settings delete global hidden_api_policy" if previous_policy == "null"
                             else "settings put global hidden_api_policy " + previous_policy))
shell("settings put global hidden_api_policy 1")
shell(CLI + " modules disable " + MODULE)
shell("am force-stop " + PROBE)
adb("logcat", "-c")
shell("am start -W -n " + PROBE + "/.ProbeActivity")
deadline = time.monotonic() + 10
discovery = latest()
while not discovery.get("raw_binder_registered") and time.monotonic() < deadline:
    discovery = latest()
    time.sleep(0.1)
assert discovery.get("raw_binder_registered"), discovery
binder_args = (" --ei raw_register " + str(discovery["raw_register_code"])
               + " --ei raw_unregister " + str(discovery["raw_unregister_code"]))
shell("settings delete global hidden_api_policy" if previous_policy == "null"
      else "settings put global hidden_api_policy " + previous_policy)
cases = [run(False), run(True)]
result = {"environment": "Android emulator screenshot keyboard shortcut, Android policy and SystemUI",
          "trigger": args.trigger,
          "cases": cases, "passed": False}
destination = pathlib.Path(args.output)
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
assert all(case["systemui_saved_screenshot"] for case in cases), "SystemUI did not save a screenshot."
assert "native ready" not in cases[0]["module_logs"], "Baseline was still injected."
assert cases[0]["probe"]["screen_capture_callbacks"] > 0, "Baseline did not receive official callback."
assert cases[1]["probe"]["screen_capture_callbacks"] == 0, "Official callback leaked with module enabled."
assert cases[0]["probe"]["raw_screen_capture_callbacks"] > 0, "Raw Binder baseline callback missing."
assert cases[1]["probe"]["raw_screen_capture_callbacks"] == 0, "Raw Binder callback leaked."
assert "native ready" in cases[1]["module_logs"], "Native layer failed to initialize."
result["passed"] = True
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print("PASS: SystemUI screenshots saved; official callback received before protection, blocked after.")
