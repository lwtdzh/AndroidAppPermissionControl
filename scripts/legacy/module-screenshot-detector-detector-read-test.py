"""Genuine SAF selection checks in the standalone detector on emulator-5584.

Run module-screenshot-probe/scripts/emulator-test.py first to create indexed PNG fixtures.
"""
import json
import pathlib
import re
import runpy
import xml.etree.ElementTree as ET

test = runpy.run_path(str(pathlib.Path(__file__).with_name("detector-test.py")))
shell, cli, wait, logs = (test[name] for name in ("shell", "cli", "wait_for", "logs"))
P, M = test["P"], test["M"]
work = pathlib.Path("/tmp/screenshot-detector-work")


def select(filename):
    test["click"]("选择图片检查读取")
    def find():
        shell("uiautomator", "dump", "--compressed", "/data/local/tmp/detector-read.xml")
        root = ET.fromstring(shell("cat", "/data/local/tmp/detector-read.xml"))
        return [n for n in root.iter("node") if n.get("text") == filename
                or n.get("content-desc", "").startswith(filename + ",")]
    node = wait(find)[0]
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
    # Tap below the small preview button in a grid card.
    shell("input", "tap", str((x1 + x2) // 2), str(y1 + (y2 - y1) * 2 // 3))


if __name__ == "__main__":
    old = json.loads(cli("--json", "scope", "ls", M))["data"]
    was_scoped = any(item["APP_PACKAGE"] == P for item in old)
    shell("cmd", "locale", "set-app-locales", P, "--locales", "zh-Hans")
    results = []
    try:
        for protected in (False, True):
            for kind, filename in (("screenshot", "Screenshot_probe.png"), ("normal", "ordinary_probe.png")):
                cli("scope", "add" if protected else "rm", M, P + "/0")
                shell("am", "force-stop", P)
                shell("am", "start", "-W", "-n", P + "/.MainActivity")
                pid = shell("pidof", P).split()[0]
                wait(lambda: "source=media_client code=state_ready" in logs(pid))
                select(filename)
                current = wait(lambda: logs(pid) if "READ_CHECK route=check_thumbnail" in logs(pid) else None)
                checks = dict(re.findall(r"READ_CHECK route=(\w+) accessible=(true|false)", current))
                assert len(checks) == 16, checks
                assert "FATAL EXCEPTION" not in current
                expected = not (protected and kind == "screenshot")
                for route, value in checks.items():
                    if route == "check_native_open":
                        # This ROM denies reopening the granted provider fd via /proc even
                        # without hooks. Its false result is not proof of module protection.
                        continue
                    assert (value == "true") == expected, (protected, kind, route, checks)
                assert not test["detections"](current), "Selecting an old image is not a new screenshot."
                results.append({"protected": protected, "fixture": kind, "genuine_picker_grant": True,
                                "checks": {k: v == "true" for k, v in checks.items()}})
                print({"protected": protected, "fixture": kind, "checks": checks}, flush=True)
    finally:
        cli("scope", "add" if was_scoped else "rm", M, P + "/0")
        shell("am", "force-stop", P)
        shell("cmd", "locale", "set-app-locales", P)
        shell("rm", "-f", "/data/local/tmp/detector-read.xml")
    (work / "detector-read.json").write_text(json.dumps(
        {"passed": True, "cases": results}, ensure_ascii=False, indent=2) + "\n")
