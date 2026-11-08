#!/usr/bin/env python3
"""Baseline/enabled/out-of-scope integration on a dedicated rooted Vector AVD."""
import argparse
import atexit
import json
import pathlib
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHIELD_PROJECT = ROOT.parent / "module-screenshot-shield"
MODULE = "io.github.lwtdzh.screenshotshield"
PROBE = "io.github.lwtdzh.screenshotprobe"
ACTIVITY = PROBE + "/.ProbeActivity"
DIRECTORY = "/sdcard/Pictures/ShieldProbe/"
CLI = "/data/adb/modules/zygisk_vector/cli"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--module-apk", type=pathlib.Path,
                        default=SHIELD_PROJECT / "app/build/outputs/apk/debug/app-debug.apk")
    args = parser.parse_args()
    if not args.serial.startswith("emulator-"):
        parser.error("This integration runner accepts emulator serials only.")
    prefix = ["adb", "-s", args.serial]
    binder_args = ""

    def adb(*parts, timeout=30):
        return subprocess.check_output(prefix + list(parts), text=True, timeout=timeout).strip()

    def shell(command):
        return adb("shell", command)

    def cli(*parts):
        return shell(CLI + " " + " ".join(parts))

    def latest():
        lines = adb("logcat", "-d", "-s", "ScreenshotProbe:I", "*:S").splitlines()
        records = [json.loads(line.split("RESULT ", 1)[1]) for line in lines if "RESULT " in line]
        return records[-1] if records else None

    def wait_result(condition, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = latest()
            if value and condition(value):
                return value
            time.sleep(0.2)
        raise AssertionError("Probe result timeout: " + json.dumps(latest(), ensure_ascii=False))

    def inspect(command="drain"):
        shell("am start -W --activity-single-top -n " + ACTIVITY + " --es command " + command)

    def run(label):
        shell("am force-stop " + PROBE)
        adb("logcat", "-c")
        shell("am start -W -n " + ACTIVITY + binder_args)
        baseline = wait_result(lambda value: "clipboard_normal_visible" in value or "startup_error" in value or "inspect_error" in value)
        assert "startup_error" not in baseline and "inspect_error" not in baseline, baseline
        # Real filesystem writes from another process, not synthetic FileObserver callbacks.
        shell("printf 'event' > " + DIRECTORY + "Screenshot_event.png")
        shell("printf 'event' > " + DIRECTORY + "ordinary_event.png")
        # Real provider notifications for known screenshot/ordinary rows.
        shell("content insert --uri content://media/external/images/media"
              " --bind _display_name:s:Screenshot_signal.png --bind relative_path:s:Pictures/ShieldProbe/"
              " --bind mime_type:s:image/png")
        shell("content insert --uri content://media/external/images/media"
              " --bind _display_name:s:ordinary_signal.png --bind relative_path:s:Pictures/ShieldProbe/"
              " --bind mime_type:s:image/png")
        shell("am broadcast -a shieldprobe.SCREENSHOT -p " + PROBE)
        shell("am broadcast -a shieldprobe.NORMAL -p " + PROBE)
        shell("am broadcast -a shieldprobe.MANIFEST_SCREENSHOT -n " + PROBE + "/.ManifestReceiver")
        shell("am broadcast -a shieldprobe.MANIFEST_NORMAL -n " + PROBE + "/.ManifestReceiver")
        inspect()
        final = wait_result(lambda value: "native_watch" in value and value["broadcast_normal_events"] > 0)
        for kind, filename in [("screenshot", "Screenshot_probe.png"), ("normal", "ordinary_probe.png")]:
            shell("am start -W --activity-single-top -n " + ACTIVITY
                  + " --es command pick_document --es doc_kind " + kind)
            deadline = time.monotonic() + 12
            chosen = False
            while time.monotonic() < deadline:
                shell("uiautomator dump --compressed /data/local/tmp/shield-document-test.xml")
                tree = ET.fromstring(shell("cat /data/local/tmp/shield-document-test.xml"))
                node = next((item for item in tree.iter("node") if item.get("text") == filename
                             or item.get("content-desc", "").startswith(filename + ",")), None)
                if node is not None:
                    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
                    shell("input tap " + str((x1 + x2) // 2) + " " + str((y1 + y2) // 2))
                    chosen = True
                    break
            assert chosen, "SAF picker did not expose fixture " + filename
            final = wait_result(lambda value: "document_" + kind + "_open" in value)
        shell("rm -f /data/local/tmp/shield-document-test.xml")
        return {"label": label, "initial": baseline, "after_events": final}

    health = cli("--json", "status")
    # Direct Binder tests reflect generated hidden AIDL transaction fields, on the
    # baseline as well as the injected app. Restore the VM test policy on exit.
    previous_policy = shell("settings get global hidden_api_policy")
    atexit.register(lambda: shell("settings delete global hidden_api_policy" if previous_policy == "null"
                                 else "settings put global hidden_api_policy " + previous_policy))
    shell("settings put global hidden_api_policy 1")
    for package, apk in [
        (MODULE, args.module_apk),
        (PROBE, ROOT / "app/build/outputs/apk/debug/app-debug.apk"),
    ]:
        adb("install", "-r", str(apk))
    shell("pm grant " + PROBE + " android.permission.READ_EXTERNAL_STORAGE")
    shell("pm grant " + PROBE + " android.permission.WRITE_EXTERNAL_STORAGE")
    shell("appops set " + PROBE + " MANAGE_EXTERNAL_STORAGE allow")
    shell("mkdir -p " + DIRECTORY + " /sdcard/Pictures/Screenshots/")
    selection = "\"relative_path='Pictures/ShieldProbe/'\""
    def reset():
        # An aborted SAF selection can leave its task with the probe's affinity.
        shell("am force-stop com.android.documentsui")
        shell("am force-stop " + PROBE)
        shell("content delete --uri content://media/external/images/media --where " + selection)
        shell("rm -f " + DIRECTORY + "*.png")
        for name in ["ordinary_probe.png", "Screenshot_probe.png"]:
            shell("content insert --uri content://media/external/images/media"
                  " --bind _display_name:s:" + name
                  + " --bind relative_path:s:Pictures/ShieldProbe/ --bind mime_type:s:image/png")
        # Write after provider cleanup/insertion. MediaStore deletes can also unlink the file.
        # adb captures here are PNG fixtures only, not official callback evidence.
        shell("screencap -p " + DIRECTORY + "ordinary_probe.png")
        shell("cp " + DIRECTORY + "ordinary_probe.png " + DIRECTORY + "Screenshot_probe.png")
        # SAF's recent-image view excludes unindexed/empty metadata fixtures.
        # Finish actual provider indexing before testing the permission-grant path.
        for filename in ["ordinary_probe.png", "Screenshot_probe.png"]:
            shell("content call --uri content://media --method scan_file --arg "
                  + DIRECTORY.replace("/sdcard/", "/storage/emulated/0/") + filename)
    reset()
    cli("modules", "disable", MODULE)
    baseline = run("module_disabled")
    assert baseline["initial"].get("raw_binder_registered") is True, baseline["initial"]
    binder_args = (" --ei raw_register " + str(baseline["initial"]["raw_register_code"])
                   + " --ei raw_unregister " + str(baseline["initial"]["raw_unregister_code"]))
    shell("settings delete global hidden_api_policy" if previous_policy == "null"
          else "settings put global hidden_api_policy " + previous_policy)
    reset()
    cli("modules", "enable", MODULE)
    cli("scope", "set", MODULE, PROBE + "/0")
    protected = run("module_enabled_scoped")
    reset()
    cli("scope", "rm", MODULE, PROBE + "/0")
    outside = run("module_enabled_outside_scope")
    cli("scope", "add", MODULE, PROBE + "/0")
    values = [baseline, protected, outside]
    destination = pathlib.Path(args.output)
    destination.write_text(json.dumps({"cases": values, "passed": False}, ensure_ascii=False, indent=2) + "\n")
    for case in values:
        hidden = case is protected
        initial, events = case["initial"], case["after_events"]
        assert initial["native"]["syscall_getpid_ok"] is True, (case["label"], initial["native"])
        assert initial["native"]["syscall_six_arguments_ok"] is True, (case["label"], initial["native"])
        if initial["native"]["clone_new_stack_supported"]:
            assert initial["native"]["clone_new_stack_ok"] is True, (case["label"], initial["native"])
        assert initial.get("raw_binder_registered") is True, (case["label"], initial)
        for key in ["java_screenshot_exists", "java_screenshot_open", "nio_screenshot_exists"]:
            assert initial[key] is not hidden, (case["label"], key, initial)
        for key in ["java_normal_exists", "java_normal_open", "nio_normal_exists"]:
            assert initial[key] is True, (case["label"], key)
        for key in ["open_screenshot", "syscall_open_screenshot", "stat_screenshot",
                    "access_screenshot", "readdir_screenshot", "fopen_screenshot", "openat_screenshot",
                    "syscall_getdents_screenshot", "syscall_stat_screenshot"]:
            assert initial["native"][key] is not hidden, (case["label"], key, initial["native"])
        for key in ["open_normal", "syscall_open_normal", "stat_normal", "access_normal", "readdir_normal",
                    "fopen_normal", "openat_normal"]:
            assert initial["native"][key] is True, (case["label"], key, initial["native"])
        for key in ["syscall_getdents_normal", "syscall_stat_normal"]:
            assert initial["native"][key] is True, (case["label"], key, initial["native"])
        for suffix in ["screenshot", "normal"]:
            assert initial["native"]["fixture_fd_" + suffix] is True, (case["label"], initial["native"])
            for key in ["fd_read", "fd_pread", "fd_readv", "fd_preadv", "fd_fstat", "fd_syscall_read", "fd_mmap",
                        "fd_dup_pread", "procfd_open", "procfd_realpath", "procroot_open", "symlink_open",
                        "libc_statx", "fd_syscall_statx", "procfd_syscall_readlink"]:
                assert initial["native"][key + "_" + suffix] is (not hidden or suffix == "normal"), (
                    case["label"], key, suffix, initial["native"])
        for key in ["media_legacy_count", "media_bundle_count", "media_client_count", "media_id_only_count"]:
            assert initial[key] == (1 if hidden else 2), (case["label"], key, initial)
        for key in ["file_screenshot_events", "broadcast_screenshot_events", "manifest_screenshot_events"]:
            assert events[key] == 0 if hidden else events[key] > 0, (case["label"], key, events)
        assert events["file_normal_events"] > 0, (case["label"], events)
        assert events["manifest_normal_events"] > 0, (case["label"], events)
        for key in ["notification_screenshot", "accessibility_screenshot"]:
            assert initial[key] == (0 if hidden else 1), (case["label"], key, initial)
        for key in ["notification_normal", "accessibility_normal", "accessibility_package_name_control"]:
            assert initial[key] == 1, (case["label"], key, initial)
        assert initial["clipboard_screenshot_visible"] is not hidden, (case["label"], initial)
        assert initial["clipboard_screenshot_description"] is not hidden, (case["label"], initial)
        assert initial["clipboard_screenshot_has"] is not hidden, (case["label"], initial)
        assert initial["clipboard_normal_visible"] is True, (case["label"], initial)
        for kind in ["screenshot", "normal"]:
            assert "document_" + kind + "_error" not in events, (case["label"], events)
            assert events["document_" + kind + "_count"] == (0 if hidden and kind == "screenshot" else 1), (case["label"], events)
            assert events["document_" + kind + "_columns"] == 1, (case["label"], events)
            assert events["document_" + kind + "_open"] is (not hidden or kind == "normal"), (case["label"], events)
        assert events["native_watch"]["normal_events"] > 0, (case["label"], events)
        assert events["native_watch"]["screenshot_events"] == 0 if hidden else events["native_watch"]["screenshot_events"] > 0
    result = {
        "environment": {"serial": args.serial, "vector": json.loads(health)},
        "cases": values,
        "official_callback": "Not tested by this runner; requires SystemUI screenshot with baseline receipt.",
        "passed": True,
    }
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("PASS: module disabled, enabled in scope, enabled outside scope")
    print(destination)


if __name__ == "__main__":
    main()
