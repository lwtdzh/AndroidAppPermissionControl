#!/usr/bin/env python3
"""Authorized vivo upgrade, preserving preferences/scopes; record only hashes and check results."""
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADB = "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"
SERIAL = os.environ.get("APPSTATE_VIVO_SERIAL", "")
MODULE = "io.github.lwtdzh.appstateshield"
PRIMARY = "io.github.lwtdzh.screenshotdetector"
CLI = "/data/adb/modules/zygisk_vector/cli"


def adb(*args):
    return subprocess.check_output([ADB, "-s", SERIAL, *args], text=True, timeout=60).strip()


def shell(*args):
    return adb("shell", shlex.join(str(value) for value in args))


def root(*args):
    return shell("su", "-c", shlex.join(str(value) for value in args))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def framework():
    modules = json.loads(root(CLI, "--json", "modules", "ls"))["data"]
    # Version metadata is expected to change during an upgrade; enable state and scopes must not.
    return {"enabled": {m["PACKAGE"]: m["STATUS"] for m in modules},
            "scopes": {m["PACKAGE"]: json.loads(root(CLI, "--json", "scope", "ls", m["PACKAGE"]))["data"]
                       for m in modules}}


def preferences(pkg):
    folder = "/data/user/0/" + pkg + "/shared_prefs"
    command = "if [ -d " + shlex.quote(folder) + " ]; then find " + shlex.quote(folder) + " -type f -exec sha256sum {} \\;; fi"
    output = root("sh", "-c", command)
    return {path.rsplit("/", 1)[-1]: digest for digest, path in (line.split(None, 1) for line in output.splitlines())}


def metadata(pkg):
    dump = shell("dumpsys", "package", pkg)
    uid = re.search(r"^package:" + re.escape(pkg) + r" uid:(\d+)$",
                    shell("pm", "list", "packages", "-U", "--user", "0", pkg), re.M).group(1)
    version = re.search(r"versionName=([^\s]+)", dump).group(1)
    code = re.search(r"versionCode=(\d+)", dump).group(1)
    # Retain only effective granted permission names, not the whole package dump.
    permissions = sorted(set(re.findall(r"^\s+(android\.permission\.[\w.]+): granted=true", dump, re.M)))
    return {"uid": uid, "version": version, "versionCode": int(code), "grantedPermissions": permissions}


def main():
    assert SERIAL, "Set APPSTATE_VIVO_SERIAL to the already authorized physical device"
    assert shell("getprop", "ro.product.model") == "V2419A", "Unexpected phone"
    assert root("id", "-u") == "0", "Rooted package installer unavailable"
    before = {"framework": framework(), "mode": root("getenforce"),
              "preferences": {p: preferences(p) for p in (MODULE, PRIMARY)},
              "packages": {p: metadata(p) for p in (MODULE, PRIMARY)}}
    report = {"version": "0.4.12", "model": "vivo V2419A", "atUTC": datetime.now(timezone.utc).isoformat(),
              "packages": {}}
    for pkg, filename, code in ((MODULE, "AppStateShield-0.4.12.apk", 22), (PRIMARY, "AppStateVerifier-0.4.12.apk", 18)):
        local = ROOT / "verification" / filename
        expected = sha(local.read_bytes())
        temporary = "/data/local/tmp/" + filename
        current = shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
        if root("sha256sum", current).split()[0] != expected:
            adb("push", str(local), temporary)
            try:
                assert root("sha256sum", temporary).split()[0] == expected
                assert "Success" in root("pm", "install", "-r", "--user", "0", temporary)
            finally:
                root("rm", "-f", temporary)
        installed = shell("pm", "path", pkg).splitlines()[0].removeprefix("package:")
        assert root("sha256sum", installed).split()[0] == expected
        after = metadata(pkg)
        assert after["version"] == "0.4.12" and after["versionCode"] == code
        assert after["uid"] == before["packages"][pkg]["uid"]
        previous_grants = set(before["packages"][pkg]["grantedPermissions"])
        current_grants = set(after["grantedPermissions"])
        assert previous_grants <= current_grants, "An existing permission grant was removed"
        added_grants = current_grants - previous_grants
        allowed_added = {"android.permission.RECEIVE_BOOT_COMPLETED"} if pkg == MODULE else set()
        assert added_grants <= allowed_added, "Unexpected new permission grant"
        report["packages"][pkg] = dict(after, sha256=expected,
            previousVersion=before["packages"][pkg]["version"], installed=True,
            addedNormalPermissions=sorted(added_grants))
    assert framework() == before["framework"]
    assert root("getenforce") == before["mode"]
    assert {p: preferences(p) for p in (MODULE, PRIMARY)} == before["preferences"]
    report["preserved"] = {"configurationHashes": True, "uid": True, "grantedPermissions": True,
        "vectorScopesAndEnabledState": True, "realSELinuxMode": True}
    shell("am", "force-stop", PRIMARY)
    # Upgrade replaces APKs, but keeps all existing policy choices and scopes.
    started = int(time.time() * 1000) - 1000
    shell("am", "start", "-W", "-n", PRIMARY + "/.MainActivity")
    ui = "/data/local/tmp/appstate-environment-vivo.xml"
    deadline = time.monotonic() + 40
    result = None
    try:
        while time.monotonic() < deadline:
            shell("uiautomator", "dump", "--compressed", ui)
            nodes = list(ET.fromstring(shell("cat", ui)).iter("node"))
            chooser = next((n for n in nodes if n.get("resource-id") == "com.vivo.doubleinstance:id/main"), None)
            if chooser is not None:
                x1, y1, x2, y2 = map(int, re.findall(r"\d+", chooser.get("bounds")))
                shell("input", "tap", (x1+x2)//2, (y1+y2)//2)
                continue
            try:
                observed = json.loads(root("cat", "/data/user/0/" + PRIMARY + "/files/environment-result.json"))
                if observed["timestamp"] > started and "summary" in observed:
                    result = observed
                    assert result["version"] == "0.4.12"
                    assert any(n.get("content-desc") == "environment-summary" for n in nodes)
                    break
            except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
                continue
        assert result is not None, "Phone environment output did not complete"
        checks = {row["id"]: row for row in result["checks"]}
        assert checks["attestation.cleanup"]["value"] == "true"
        # Never require a healthy attestation result to approve an installation.
        report["environmentSummary"] = result["summary"]
        report["environmentChecks"] = result["checks"]
        report["environmentModule"] = result["module"]
        report["environmentVisible"] = True
        assert preferences(MODULE) == before["preferences"][MODULE]
        assert framework() == before["framework"] and root("getenforce") == before["mode"]
    finally:
        shell("rm", "-f", ui)
    (ROOT / "verification/vivo-environment-0.4.12-installed.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("PASS both 0.4.12 APKs installed and environment output visible; configuration, UID, grants and scopes preserved")


if __name__ == "__main__":
    main()
