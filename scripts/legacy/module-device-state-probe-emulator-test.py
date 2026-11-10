#!/usr/bin/env python3
"""Compare genuine enabled system state with each scoped module; restore settings and scopes."""
import argparse
import json
import pathlib
import re
import shlex
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
SDK = pathlib.Path("/opt/homebrew/share/android-commandlinetools")
ADB = str(SDK / "platform-tools/adb")
CLI = "/data/adb/modules/zygisk_vector/cli"
PKG = "io.github.lwtdzh.devicestateprobe"
VPN = "io.github.lwtdzh.vpnstateshield"
DEV = "io.github.lwtdzh.developerstateshield"
KEYS = ["development_settings_enabled", "adb_enabled", "adb_wifi_enabled"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default="emulator-5584")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.serial != "emulator-5584":
        parser.error("Use only the dedicated emulator-5584.")

    def adb(*parts):
        return subprocess.check_output([ADB, "-s", args.serial, *parts], text=True, timeout=40).strip()

    def shell(*parts):
        return adb("shell", shlex.join(parts))

    def cli(*parts):
        value = json.loads(shell(CLI, "--json", *parts))
        if not value.get("success"):
            raise RuntimeError("Vector command failed: " + " ".join(parts))
        return value["data"] if "data" in value else None

    if shell("getprop", "ro.boot.qemu") != "1":
        raise RuntimeError("Expected an emulator.")
    if "ScreenshotShield_API36" not in adb("emu", "avd", "name"):
        raise RuntimeError("Unexpected AVD.")
    original_settings = {key: shell("settings", "get", "global", key) for key in KEYS}
    original_airplane = shell("settings", "get", "global", "airplane_mode_on")
    scopes = {module: cli("scope", "ls", module) for module in [VPN, DEV]}
    modules = cli("modules", "ls")
    enabled = {module: next(row["STATUS"] == "enabled" for row in modules if row["PACKAGE"] == module)
               for module in [VPN, DEV]}
    original_appop = shell("appops", "get", PKG, "ACTIVATE_VPN")
    # This fixture must not displace a user's pre-existing VPN.
    if re.search(r"\btun\d+\b", shell("ip", "link")):
        raise RuntimeError("A VPN is already present; leave it untouched.")
    result = {"serial": args.serial, "platform": shell("getprop", "ro.build.version.release"),
              "cases": [], "passed": False, "restored": False}

    def save():
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    def scoped(module, value):
        existing = any(row["APP_PACKAGE"] == PKG and row["USER_ID"] == 0
                       for row in cli("scope", "ls", module))
        if value != existing:
            cli("scope", "add" if value else "rm", module, PKG + "/0")

    def kill_reader():
        # Keep the independent :vpn service alive while creating a fresh reader process.
        rows = [line.split() for line in shell("ps", "-A", "-o", "PID,NAME").splitlines()[1:]]
        for row in rows:
            if len(row) == 2 and row[1] == PKG:
                shell("kill", "-9", row[0])

    def snapshot():
        kill_reader()
        shell("rm", "-f", "/data/user/0/" + PKG + "/files/result.json")
        shell("am", "start", "-W", "-n", PKG + "/.ProbeActivity", "--es", "action", "read")
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            path = "/data/user/0/" + PKG + "/files/result.json"
            if subprocess.run([ADB, "-s", args.serial, "shell", "test", "-s", path],
                              capture_output=True, timeout=10).returncode == 0:
                return json.loads(shell("cat", path))
            time.sleep(0.5)  # bounded polling of our own result file
        raise TimeoutError("Probe produced no result.")

    def check(case, vpn, dev):
        errors = []
        data = case["observed"]
        for key in KEYS:
            expected = 0 if dev else int(case["actualSystem"][key])
            for route in ["global", "float", "long", "call", "clientCall"]:
                if str(data.get(key + "." + route)).removesuffix(".0") != str(expected):
                    errors.append(key + "." + route)
            for route in ["query", "valueOnly", "bundleQuery"]:
                query = data.get(key + "." + route, {})
                if not isinstance(query, dict) or str(query.get("value")) != str(expected):
                    errors.append(key + "." + route)
                elif query["int"] != expected or query["long"] != expected or query["float"] != expected:
                    errors.append(key + "." + route + ".numeric")
                if route != "query" and isinstance(query, dict) and query.get("columns") != ["value"]:
                    errors.append(key + "." + route + ".projection")
            if dev:
                for route in ["secure", "system"]:
                    if data.get(key + "." + route) != "0": errors.append(key + "." + route)
        for route in ["activeVpn", "parcelVpn", "callbackVpn", "tunByName", "linkTextTunnel", "legacyVpn"]:
            if data.get(route) is not (not vpn): errors.append(route)
        if data.get("vpnNetworks") != (0 if vpn else 1): errors.append("vpnNetworks")
        if data.get("activeNotVpn") is not vpn: errors.append("activeNotVpn")
        if data.get("wifiTransport") is not True or data.get("activeInfoConnected") is not True:
            errors.append("ordinary.connectivity")
        if result["cases"] and data.get("networks") != result["cases"][0]["observed"].get("networks"):
            errors.append("ordinary.networkHandles")
        native = data.get("native", {})
        for route in ["interfaces", "native"]:
            names = data.get("interfaces", []) if route == "interfaces" else native.get("interfaces", [])
            if any(re.match(r"(tun|tap|ppp|ipsec|vti|wg|utun)\d", name) for name in names) == vpn:
                errors.append(route + ".tunnel")
            if not any(name in names for name in ["eth0", "wlan0"]): errors.append(route + ".ordinaryInterface")
        if not native.get("listLifetimeOk") or not native.get("getpidOk"): errors.append("native.controls")
        if dev:
            for route in ["get", "read", "callback"]:
                if native.get("init.svc.adbd." + route) != "stopped": errors.append("native.adbd." + route)
                for key in ["sys.usb.config", "sys.usb.state"]:
                    if "adb" in native.get(key + "." + route, "").split(","): errors.append("native.usb." + route)
            if data.get("init.svc.adbd.java") != "stopped": errors.append("java.adbd")
        elif native.get("init.svc.adbd.get") != "running": errors.append("baseline.adbd")
        if data.get("internet") != 204: errors.append("internet")
        proxy = data.get("proxyFixture", {})
        if not isinstance(proxy, dict) or proxy.get("response") != 204 or not proxy.get("actualHttpProxyUsed"):
            errors.append("ordinary.httpProxyRouting")
        else:
            for key in ["hostVisible", "portVisible", "bulkHostVisible"]:
                if proxy.get(key) is not (not vpn): errors.append("proxy." + key)
            if proxy.get("ordinaryProperty") is None: errors.append("ordinary.javaProperty")
        if data.get("airplane_mode_on.global") != int(original_airplane): errors.append("ordinary.setting")
        if native.get("ro.build.version.sdk.get") != "36": errors.append("ordinary.property")
        system = case["actualSystem"]
        if any(system[key] != "1" for key in KEYS[:2]) or not system["tunPresent"]: errors.append("actual.system")
        case["errors"] = errors
        case["passed"] = not errors
        return not errors

    try:
        for key in KEYS[:2]: shell("settings", "put", "global", key, "1")
        result["wirelessDebuggingEnabledBaseline"] = False
        result["wirelessDebuggingNote"] = "The emulator resets adb_wifi_enabled to 0. Enabled wireless debugging is not validated."
        shell("appops", "set", PKG, "ACTIVATE_VPN", "allow")
        for module in [VPN, DEV]:
            scoped(module, False)
            cli("modules", "enable", module)
        shell("am", "start", "-W", "-n", PKG + "/.ProbeActivity", "--es", "action", "vpn-start")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not re.search(r"\btun\d+\b", shell("ip", "link")):
            time.sleep(0.5)
        for name, vpn, dev, status in [
            ("modules-disabled", False, False, False),
            ("vpn-only", True, False, True),
            ("developer-only", False, True, True),
            ("both", True, True, True),
            ("outside-scope", False, False, True),
        ]:
            for module, in_scope in [(VPN, vpn), (DEV, dev)]:
                scoped(module, in_scope if status else True)
                cli("modules", "enable" if status else "disable", module)
            observed = snapshot()
            actual = {key: shell("settings", "get", "global", key) for key in KEYS}
            actual["tunPresent"] = bool(re.search(r"\btun\d+\b", shell("ip", "link")))
            case = {"name": name, "observed": observed, "actualSystem": actual}
            result["cases"].append(case)
            passed = check(case, vpn, dev)
            save()
            print(name + ": " + ("PASS" if passed else "FAIL " + ", ".join(case["errors"])), flush=True)
        result["passed"] = all(case["passed"] for case in result["cases"])
    finally:
        shell("am", "force-stop", PKG)
        for key, value in original_settings.items():
            shell("settings", "delete" if value == "null" else "put", "global", key,
                  *([] if value == "null" else [value]))
        for module in [VPN, DEV]:
            originally_scoped = any(row["APP_PACKAGE"] == PKG and row["USER_ID"] == 0 for row in scopes[module])
            scoped(module, originally_scoped)
            cli("modules", "enable" if enabled[module] else "disable", module)
        match = re.search(r"ACTIVATE_VPN: (\w+)", original_appop)
        shell("appops", "set", PKG, "ACTIVATE_VPN", match.group(1) if match else "default")
        result["restored"] = all(shell("settings", "get", "global", key) == value
                                 for key, value in original_settings.items())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and re.search(r"\btun\d+\b", shell("ip", "link")):
            time.sleep(0.2)
        result["restored"] &= not bool(re.search(r"\btun\d+\b", shell("ip", "link")))
        save()
    if not result["passed"] or not result["restored"]: raise SystemExit(1)


if __name__ == "__main__":
    main()
