#!/usr/bin/env python3
"""Package current preset evidence and source; no historical results relabeled."""
import hashlib
import json
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT/"verification"
DELIVERY = pathlib.Path.home()/"Downloads"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    tests = json.loads((OUT/"model-presets-0.4.3-results.json").read_text())
    audit = json.loads((OUT/"machine-build-checks-0.4.3.json").read_text())
    rows = [(key, value) for key, value in tests["cases"].items() if key.startswith("P")]
    assert len(rows) == 6 and all(row["status"] == "passed" for _, row in rows)
    assert all(row["buildInputsSHA256"] == sha(OUT/"build-inputs.json") for _, row in rows)
    assert all(row["artifacts"] == tests["artifacts"] for _, row in rows)
    assert tests["restoration"]["completeDataSnapshotRestored"] and tests["restoration"]["emulatorShutdown"]
    assert tests["restoration"]["adbdUnrooted"]
    for name, digest in tests["artifacts"].items():
        assert sha(OUT/name) == digest == audit[name]["sha256"]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        shutil.copyfile(OUT/name, DELIVERY/name)
    installed_path = OUT/"vivo-model-0.4.3-installed.json"
    assert installed_path.exists(), "Phone installation evidence missing"
    installed = json.loads(installed_path.read_text())
    assert installed["preferencesPreserved"] and installed["vectorPreserved"]
    for pkg, name in [("io.github.lwtdzh.appstateshield", "AppStateShield-0.4.3.apk"),
                      ("io.github.lwtdzh.screenshotdetector", "AppStateVerifier-0.4.3.apk")]:
        assert installed["installed"][pkg]["sha256"] == tests["artifacts"][name]
    durations = sum(row["durationSeconds"] for _, row in rows)
    table = "\n".join(f"| {key} | 通过 | {row['durationSeconds']:.3f} 秒 |" for key, row in rows)
    source_note = (ROOT/"docs/MODEL-PRESETS-0.4.3.md").read_text()
    report = f"""# AppStateShield 0.4.3 预设与安装验证

新增 vivo X200 Pro mini，软件内名称不附带“本机实测”；保留小米 14 国际版，移除 Find X9s。两套预设的机型、代号、主板、硬件、版本和指纹来自真实数据。统一刷新不生成随机代号。个人标识独立生成，不复制用户本机的 IMEI、序列号、MAC 或 Wi-Fi 名称。

## 本次实际检查

{(OUT/"model-unit-0.4.3.log").read_text().strip()}

Android 16 / ARM64 专用模拟器 emulator-5584 / Vector：六个定向用例，操作与采样共 {durations:.1f} 秒。

| 用例 | 结果 | 耗时 |
|---|---|---|
{table}

检查预设列表、默认折叠、vivo 保存、小米切换与固定刷新、丢弃草稿、手工代号优先、旧 OPPO 档案迁移、关闭后的原值恢复。机型十个 Build 字段、十三个 Java 属性和原生 callback 对照通过；旧原生接口的限制单独列在下面。同进程更新和普通文件、网卡释放、嵌套属性回调对照通过。模拟器原 APK、完整数据、模块作用域与设置已恢复，adbd 已解除 root，模拟器已关闭。

四 ABI 编译齐全，正式 APK 排除 debug 厂商夹具，沿用原签名。Lint 无错误；模块 {audit["app/build/reports/lint-results-release.xml"]["warnings"]} 个警告，验证器 {audit["verifier/build/reports/lint-results-primaryRelease.xml"]["warnings"]} 个警告。

本轮只执行受预设与属性转换影响的步骤；旧六项屏蔽的 64 组合没有重新执行，也没有在本报告中改标为新 APK 实测。

## 实测限制与失败记录

旧 __system_property_read 会截断超过 31 字节的属性名。ro.product.system_ext.manufacturer 在该入口保留模拟器原值 unknown；Java 与原生 get/callback 返回预设厂商值。旧 get/read 的值缓冲区最多返回 91 字节，小米 vendor 指纹在这两个入口被截断；Java 与 callback 返回完整值。这两项仍是现有读取限制，未声称全部原生入口成功替换。

初次断言要求所有旧接口返回完整值，分别发现上述长名称和长指纹问题；调整测试后单独验证这些限制并保留失败记录。原始错误及修订后的观察值随 JSON 与日志交付。两套预设数据不因接口限制而改成伪造短值。

手工代号用例曾等待主进程和电话辅助进程的版本同时匹配而超时。该用例只检查主进程的机型属性，执行器改为等待主进程档案版本，并保留原失败；电话辅助进程的同步不计入该用例的通过结论。续跑保留同一 APK 已通过的预设保存、刷新和丢弃草稿结果，只继续剩余步骤。

Android 版本文本不更改 SDK_INT；模拟器验证不能代表所有厂商服务和硬件认证均已覆盖。IMEI、OAID、MAC、网络与基站的个人或合成参数不属于真实机型的固定硬件字段。

## 手机安装

本机 V2419A 已安装模块与验证器 0.4.3；安装后的 APK SHA-256 与交付文件一致。原配置、权限、UID、Android 用户与分身安装状态、Vector 模块及作用域均已核对保留，两个应用启动正常。已有机器档案没有自动切换到 vivo；需要在应用详情选择新预设并保存。

| 安装包 | SHA-256 |
|---|---|
| AppStateShield-0.4.3.apk | {tests["artifacts"]["AppStateShield-0.4.3.apk"]} |
| AppStateVerifier-0.4.3.apk | {tests["artifacts"]["AppStateVerifier-0.4.3.apk"]} |

## 来源与操作说明

{source_note}
"""
    report_name = "AppStateShield-0.4.3-预设与验证.md"
    (DELIVERY/report_name).write_text(report)
    data_name = "AppStateShield-0.4.3-测试数据.json"
    (DELIVERY/data_name).write_text(json.dumps({"tests": tests, "buildAudit": audit, "phoneInstall": installed}, ensure_ascii=False, indent=2)+"\n")
    source_name = "AppStateShield-0.4.3-source.zip"
    files = set()
    for folder in ["app/src", "verifier/src", "shared", "gradle", "scripts", "docs"]:
        files.update(p for p in (ROOT/folder).rglob("*") if p.is_file() and
                     "__pycache__" not in p.parts and p.name != ".DS_Store")
    for name in ["AGENTS.md", "README.md", "PROJECT-RELATIONSHIPS.md", "build.gradle",
                 "settings.gradle", "gradle.properties", "gradlew", "gradlew.bat",
                 "app/build.gradle", "verifier/build.gradle"]:
        files.add(ROOT/name)
    with zipfile.ZipFile(DELIVERY/source_name, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, str(path.relative_to(ROOT)))
    members = list(tests["artifacts"]) + [report_name, data_name, source_name]
    sums_name = "AppStateShield-0.4.3-SHA256SUMS.txt"
    (DELIVERY/sums_name).write_text("".join(sha(DELIVERY/name)+"  "+name+"\n" for name in members))
    with zipfile.ZipFile(DELIVERY/"AppStateShield-0.4.3-delivery.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in members+[sums_name]:
            archive.write(DELIVERY/name, name)
        for name in ["model-presets-0.4.3.log", "build-0.4.3.log", "model-unit-0.4.3.log",
                     "build-inputs.json", "model-vivo-collapsed-0.4.3.png"]:
            archive.write(OUT/name, "verification/"+name)
    for name in [source_name, "AppStateShield-0.4.3-delivery.zip"]:
        with zipfile.ZipFile(DELIVERY/name) as archive:
            assert archive.testzip() is None
    print("Packaged 0.4.3 APKs, source, report, test evidence and checksums")

if __name__ == "__main__":
    main()
