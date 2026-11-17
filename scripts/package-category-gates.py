#!/usr/bin/env python3
"""Audit and package 0.4.13 with the actual selected checks and restoration evidence."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import zipfile
from test_evidence import payload, source_inputs

ROOT = pathlib.Path(__file__).resolve().parents[1]
VER = ROOT / "verification"
STATE = pathlib.Path.home() / "Library/Application Support/ScreenshotShield/category-gates-0.4.13"
TOOLS = pathlib.Path("/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0")
ENV = dict(os.environ, JAVA_HOME="/opt/homebrew/opt/openjdk@17")
ABIS = {"arm64-v8a", "armeabi-v7a", "x86", "x86_64"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def signer(path):
    text = subprocess.check_output([str(TOOLS / "apksigner"), "verify", "--print-certs", str(path)],
                                   env=ENV, text=True)
    return next(line for line in text.splitlines() if "certificate SHA-256 digest:" in line)


def audit():
    binding = json.loads((VER / "build-inputs.json").read_text())
    assert binding["files"] == source_inputs(), "Application source no longer matches its build"
    result, certificates = {}, []
    for product, code in (("AppStateShield", 23), ("AppStateVerifier", 19)):
        path = VER / (product + "-0.4.13.apk")
        old = VER / (product + "-0.4.12.apk")
        assert payload(path) == binding["apkPayloads"][product], "Signed APK payload differs from build"
        def libraries(archive):
            return {name: digest(archive.read(name)) for name in archive.namelist()
                    if name.startswith("lib/") and name.endswith(".so")}
        with zipfile.ZipFile(path) as archive, zipfile.ZipFile(old) as prior:
            libs = libraries(archive)
            assert libs == libraries(prior), "Native payload changed"
            assert {name.split("/")[1] for name in libs} == ABIS
            assert not any("incrementalprobe" in name or "capabilityprobe" in name for name in archive.namelist())
            dex = b"".join(archive.read(name) for name in archive.namelist() if name.endswith(".dex"))
            for fixture in (b"Landroid/telephony/VivoTelephonyManager;",
                            b"Lcom/bun/miitmdid/core/MdidSdkHelper;",
                            b"Lio/github/lwtdzh/screenshotdetector/MachineFixtures;"):
                assert fixture not in dex
        cert = signer(path)
        assert cert == signer(old)
        certificates.append(cert)
        badging = subprocess.check_output([str(TOOLS / "aapt"), "dump", "badging", str(path)], text=True)
        package = next(line for line in badging.splitlines() if line.startswith("package:"))
        assert "versionName='0.4.13'" in package and ("versionCode='" + str(code) + "'") in package
        result[product] = {"sha256": sha(path), "package": package, "nativeLibraries": libs,
                          "nativeIdenticalTo0412": True, "signingIdentityPreserved": True,
                          "debugFixturesExcluded": True}
    assert certificates[0] == certificates[1]
    (VER / "category-gates-0.4.13-artifacts.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS version, signature, four ABIs, debug exclusions; native libraries unchanged", flush=True)
    return result


def package():
    artifacts = audit()
    results = json.loads((VER / "category-gates-0.4.13-results.json").read_text())
    unit = json.loads((VER / "category-gates-0.4.13-unit.json").read_text())
    restored = json.loads((VER / "category-gates-0.4.13-restoration.json").read_text())
    assert unit["passed"] and restored["passed"] and restored["exactFileTreeAndSHA256"]
    assert len(results["cases"]) == results["expectedCases"] == 13
    assert all(row["status"] == "passed" for row in results["cases"].values())
    for product in artifacts:
        assert artifacts[product]["sha256"] == results["artifacts"][product + "-0.4.13.apk"]
    rows = "\n".join("| " + name + " | 通过 | " + str(row["seconds"]) + " |"
                     for name, row in results["cases"].items())
    counts = "\n".join("- " + name + "：" + row["output"] +
                       ("（字段格式与生成规则未修改，沿用既有结果，本轮未重跑）" if row.get("reuseReason") else "")
                       for name, row in unit["tests"].items())
    report = f"""# AppStateShield / 应用状态验证器 0.4.13

每个字段的已保存参数同时受机器伪装总开关、分类总控制与单项开关约束。设备标识、机型与系统、位置和其他环境有独立总开关，新档案默认关闭；标题显式显示已开启或已关闭。网络与基站保留已关闭、模拟 SIM 卡、模拟无 SIM 卡三档，标题显示选中的状态。

关闭分类保留参数和单项选择。统一刷新、填写机型预设、保存与旋转保持分类状态。模拟 SIM 提供虚拟有卡/注册状态，但不强制选中字段；虚拟对象未选参数使用空值或未知值。模拟无 SIM 清除蜂窝信息，同时保留设备标识分类控制的 IMEI，以及独立选择的 Wi-Fi/蓝牙参数。

旧档案缺失的新分类控制默认关闭，既有机型、位置和网络显式状态保留。未知字段继续保存，缺少字段目录元数据时不会应用。实现和使用说明见 docs/CATEGORY-GATES-0.4.13.md。

## 本次验证

两个正式 APK 构建与 lint 通过，四 ABI 编译完成，原签名保持，调试厂商夹具未进入正式 APK。所有 native 库与 0.4.12 的字节相同。本次实际运行环境为专用 emulator-5584 / ScreenshotShield_API36，API36 ARM64；四 ABI 编译结果不代表另外三种 ABI 的运行验证。

JVM 检查：

{counts}

下表为本次最终 APK 的 13 个实测用例，原始快照、失败记录和每次耗时保留在 evidence/。设置页保存、单项开关、丢弃、旋转、刷新和预设通过真实 UI 操作；批量运行对照采用专用模拟器的原子配置夹具，保留其他应用配置，不增加正式写接口。

执行器修正了展开列表的滚动查找、电脑与恢复后模拟器时钟不同的判断，以及配置 Provider 停止时的客户端依赖。系统日志明确记录第一次重启由停止 Provider 引发；批量写入前返回桌面并等候界面停止回调后，最终 10 项读取对照全部使用 PID {results['runtimePid']}。原失败记录和第一次通过的对照另存为 runtimeSessions，未覆盖 UI 结果。交付截图为经过界面核对的设置页默认关闭状态；读数对照以对应 JSON 快照为准。

| 用例 | 结果 | 耗时（秒） |
|---|---|---|
{rows}

真实分类关闭基线中传感器列表非空。启用后 Android ID、机型、定位、内存、时区与 Wi-Fi 读数改变，Java/native 机型读数一致；字段关闭、分类关闭及机器总开关关闭恢复原读数或原异常，主 PID 保持不变。网络检查覆盖全部字段、部分字段、未选字段默认值、同步/异步读取及 Parcel 还原。返回的虚拟 SIM 状态与是否覆盖保存参数分别核对。

此正式验证器 UID 的原生 getifaddrs 没有返回 MAC 项，因此本轮原生网卡 MAC 缺少非空基线，未将空集合记作隐藏成功；Wi-Fi 地址通过 WifiInfo 与 Java wlan0 读取核对。原生机型的 get/read/callback 三种属性入口另有非空基线并进行实际对照。原系统电话与基站读取的超时保持为异常；虚拟 SIM 模式需要给出明确数值、对象和回调，不能以超时通过。

本次只改变机器档案和相关网络虚拟对象。六项状态屏蔽的策略、入口和共享 native Hook 未修改，因此没有重新执行旧 64 组合，也没有将旧运行记录当成本次 APK 的新证据。厂商 SDK 和其他 ROM 未在本轮运行；原有注入痕迹、硬件证明和 AVB 限制仍见项目说明。

## 环境与交付

完整原模拟器磁盘已恢复，文件树、权限及每个文件 SHA-256 与开始前一致，ramdisk 未修改，模拟器已停止；其他模拟器未操作。

发布文件见仓库的 v0.4.13 Release 页面。手机安装与模拟器测试分开记录，覆盖安装不等于完成真机功能验证。

- AppStateShield-0.4.13.apk：主模块，版本代码 23。
- AppStateVerifier-0.4.13.apk：检测器，版本代码 19。
- evidence/：本次运行、JVM、构建、最终产物审计与恢复记录。
- source/：本次修改文件和两个执行脚本。
- SHA256SUMS.txt：全部交付文件的校验值。
"""
    (VER / "CATEGORY-GATES-0.4.13-REPORT.md").write_text(report)
    destination = pathlib.Path.home() / "Downloads/AppStateShield-0.4.13-category-gates"
    assert destination.parent.is_dir()
    destination.mkdir(exist_ok=True)
    for folder in ("docs", "evidence", "source"):
        (destination / folder).mkdir(exist_ok=True)
    for product in artifacts:
        filename = product + "-0.4.13.apk"
        shutil.copy2(VER / filename, destination / filename)
        shutil.copy2(VER / filename, destination.parent / filename)
    shutil.copy2(VER / "CATEGORY-GATES-0.4.13-REPORT.md", destination / "REPORT.md")
    shutil.copy2(ROOT / "docs/CATEGORY-GATES-0.4.13.md", destination / "docs")
    for path in VER.glob("category-gates-0.4.13-*"):
        if path.is_file():
            shutil.copy2(path, destination / "evidence" / path.name)
    shutil.copy2(VER / "build-0.4.13-category-gates-final.log", destination / "evidence")
    shutil.copy2(STATE / "default-off.png", destination / "evidence" / "default-off.png")
    tracked = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).splitlines()
    extra = ["docs/CATEGORY-GATES-0.4.13.md", "shared/test/CategoryGateTest.java",
             "scripts/category-gates-test.py", "scripts/package-category-gates.py"]
    for name in tracked + extra:
        if name.startswith("verification/"):
            continue
        target = destination / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    paths = sorted(p for p in destination.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    (destination / "SHA256SUMS.txt").write_text("\n".join(sha(p) + "  " + str(p.relative_to(destination))
                                                       for p in paths) + "\n")
    archive = destination.parent / (destination.name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                output.write(path, destination.name + "/" + str(path.relative_to(destination)))
    with zipfile.ZipFile(archive) as output:
        assert output.testzip() is None
        for line in (destination / "SHA256SUMS.txt").read_text().splitlines():
            expected, filename = line.split("  ", 1)
            assert digest(output.read(destination.name + "/" + filename)) == expected
    print("PASS delivery archive and every file checksum:", archive, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("audit", "package"))
    {"audit": audit, "package": package}[parser.parse_args().phase]()
