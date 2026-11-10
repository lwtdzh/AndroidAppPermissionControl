#!/usr/bin/env python3
"""Observe scoped cold starts without ptrace, per-hook changes, or private app logs."""
import argparse
import json
import pathlib
import re
import shlex
import subprocess
import time

MODULE = "io.github.lwtdzh.screenshotshield"
CLI = "/data/adb/modules/zygisk_vector/cli"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--activity", required=True, help="package/activity")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--scroll", action="store_true", help="Scroll up and down during each observation.")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if not args.serial.startswith("emulator-") or args.seconds < 1 or args.attempts < 1:
        parser.error("Use an emulator, positive duration and attempt count.")
    package = args.activity.split("/", 1)[0]

    def adb(*parts):
        return subprocess.check_output(["adb", "-s", args.serial, *parts], text=True, timeout=20).strip()

    def shell(*parts):
        return adb("shell", shlex.join(parts))

    def cli(*parts):
        value = json.loads(shell(CLI, "--json", *parts))
        if not value.get("success"):
            raise RuntimeError("Vector command failed: " + " ".join(parts))
        return value

    scope = cli("scope", "ls", MODULE)["data"]
    originally_scoped = any(item["APP_PACKAGE"] == package and item["USER_ID"] == 0 for item in scope)
    modules = cli("modules", "ls")["data"]
    enabled = next(item["STATUS"] == "enabled" for item in modules if item["PACKAGE"] == MODULE)
    cases = []
    size = re.findall(r"(\d+)x(\d+)", shell("wm", "size"))[-1]
    width, height = map(int, size)
    result = {"package": package, "seconds_per_start": args.seconds, "cases": cases, "passed": False}
    try:
        cli("scope", "add", MODULE, package + "/0")
        cli("modules", "enable", MODULE)
        for attempt in range(args.attempts):
            shell("am", "force-stop", package)
            started = shell("date", "+%m-%d %H:%M:%S.000")
            shell("am", "start", "-W", "-n", args.activity)
            begin = time.monotonic()
            samples = []
            zygotes = set(shell("pidof", "zygote64", "zygote").split())
            processes = [line.split() for line in shell("ps", "-A", "-o", "PID,PPID,NAME").splitlines()[1:]]
            initial_pid = next((fields[0] for fields in processes
                                if len(fields) == 3 and fields[1] in zygotes and fields[2] == package), "")
            maps_ok = False
            gestures = 0
            while time.monotonic() - begin < args.seconds:
                process = subprocess.run(["adb", "-s", args.serial, "shell", "pidof", package],
                                         capture_output=True, text=True, timeout=20)
                pid = process.stdout.strip() if process.returncode == 0 else ""
                # A raw clone briefly has the same command name as its parent.
                # Track the zygote child, rather than comparing the full pidof list.
                samples.append({"seconds": round(time.monotonic() - begin, 2),
                                "same_process_alive": bool(initial_pid) and initial_pid in pid.split()})
                if not samples[-1]["same_process_alive"]:
                    break
                if args.scroll and gestures < 2 and time.monotonic() - begin >= args.seconds * (gestures + 1) / 3:
                    start, end = (0.7, 0.3) if gestures == 0 else (0.3, 0.7)
                    shell("input", "swipe", str(width // 2), str(int(height * start)),
                          str(width // 2), str(int(height * end)), "350")
                    gestures += 1
                time.sleep(1)  # sample process liveness, no debugger or memory edits
            if samples[-1]["same_process_alive"]:
                maps = shell("cat", "/proc/" + initial_pid + "/maps")
                maps_ok = not any("r--s 00000000" in line and
                                  line.endswith(("/bin/linker64", "/bin/linker"))
                                  for line in maps.splitlines())
            foreground = any(package in line and "ResumedActivity" in line
                             for line in shell("dumpsys", "activity", "activities").splitlines())
            logs = adb("logcat", "-d", "-T", started, "-s", "ScreenshotShield:I", "*:S")
            # Record only module status, never application logs or account data.
            native_lines = [line.split("ScreenshotShield:", 1)[-1].strip()
                            for line in logs.splitlines()
                            if "native ready api=" in line or "linker analysis file view" in line]
            case = {"attempt": attempt + 1, "samples": samples, "foreground": foreground,
                    "scroll_gestures": gestures,
                    "linker_file_view_absent": maps_ok, "module_status": native_lines,
                    "passed": all(item["same_process_alive"] for item in samples) and foreground
                              and maps_ok and any("native ready api=" in line for line in native_lines)}
            cases.append(case)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            print("Cold start " + str(attempt + 1) + ": " + ("PASS" if case["passed"] else "FAIL"), flush=True)
            if not case["passed"]:
                raise AssertionError("Scoped application cold start failed.")
        result["passed"] = True
    finally:
        shell("am", "force-stop", package)
        # Remove only the temporary entry; retain companion apps and other users.
        if not originally_scoped:
            cli("scope", "rm", MODULE, package + "/0")
        cli("modules", "enable" if enabled else "disable", MODULE)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
