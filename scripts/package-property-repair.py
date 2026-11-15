#!/usr/bin/env python3
"""Deliver repaired APKs only after current native, JVM and 64-combination checks."""
import hashlib
import json
import pathlib
import shutil
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DELIVERY=pathlib.Path.home()/"Downloads"
VERSION="0.4.4"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    report=json.loads((OUT/"property-repair-0.4.4-results.json").read_text())
    audit=json.loads((OUT/"machine-build-checks-0.4.4.json").read_text())
    cases=report["cases"]
    matrix=[key for key in cases if key.startswith("M6-")]
    expected=["R01-original-fingerprint-baseline","R02-xiaomi-independent-hook",
        "R03-shared-selinux","R03-shared-debug","R03-shared-debug-selinux",
        "R04-live-fingerprint-91","R04-live-fingerprint-92","R04-live-fingerprint-128",
        "R04-live-fingerprint-256","R04-live-fingerprint-48","R05-field-and-master-off"]
    assert len(matrix)==64
    for key in matrix+expected:
        row=cases[key]
        assert row["status"]=="passed" and row["artifacts"]==report["artifacts"],key
        assert row["buildInputsSHA256"]==sha(OUT/"build-inputs.json"),key
    restored=report["restoration"]
    assert all(restored[key] for key in ["originalAPKBytes","completeDataSnapshotRestored",
        "modulesAndScopes","settings","vpnStopped","temporaryFilesRemoved",
        "temporaryStorageGrantsRemoved","appLocalesRestored","adbdUnrooted","emulatorShutdown"])
    for name,digest in report["artifacts"].items():
        assert digest==sha(OUT/name)==audit[name]["sha256"]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        shutil.copyfile(OUT/name,DELIVERY/name)
    local=(OUT/"property-native-unit-0.4.4.log").read_text().strip()
    java=(OUT/"property-java-unit-0.4.4.log").read_text().strip()
    assert local.startswith("PASS") and java.startswith("PASS")
    duration=sum(cases[key]["durationSeconds"] for key in matrix)
    targeted=sum(cases[key]["durationSeconds"] for key in expected)
    failures=sum(len(rows) for rows in report.get("previousRuns",{}).values()
                 if isinstance(rows,list))
    table="\n".join("| "+key+" | 通过 | "+str(cases[key]["durationSeconds"])+" 秒 |"
                    for key in expected)
    install_path=OUT/"vivo-property-0.4.4-installed.json"
    installed=json.loads(install_path.read_text()) if install_path.exists() else None
    phone=("两个 0.4.4 APK 已安装到 vivo X200 Pro mini，安装字节与交付物一致，"
           "原配置、权限、UID、分身安装状态和 Vector 作用域均保留。"
           if installed else "本次交付已验证的两个 APK；没有本次 0.4.4 真机安装记录。")
    report_text=f"""# AppStateShield 0.4.4 指纹读取修复与测试

已修复长属性名导致预设匹配失败、超长指纹返回残缺前缀和旧值尾部残留。机器伪装已开启且指纹选中、配置有效时，本次验证的六个指纹属性通过 Java/Build 与 native callback 返回完整预设指纹；旧 get/read 返回预设短值或 Android 的超长只读属性兼容提示。整个 92 字节旧接口值缓冲区经检查没有本机原指纹残留。

## 代码改动

shared/native/property-read.h 通过所属库的原始 callback 取得完整属性名称，旧 read 支持 nullptr 名称参数。超过 91 字节的只读预设值返回“Must use __system_property_read_callback() to read”，保持原缓冲区大小。每次替换会清零整个值缓冲区。devicestate、developerstate 和 selinuxstate 共用该实现。指纹字段允许完整 256 个 UTF-8 字节，其他文本长度规则保留。

## 本次实际验证

{local}

{java}

本地 native 测试启用 AddressSanitizer 和 UndefinedBehaviorSanitizer，覆盖 0/1/48/90/91/92/93/128/256 字节、完整名称及同前缀名称、错误码保留、原值尾部清理和缓冲区前后哨兵。

Android 16 ARM64 / Vector / ScreenshotShield_API36 / emulator-5584：11 项定向检查通过，耗时 {targeted:.1f} 秒。完整六项开关 64 组合通过，耗时 {duration:.1f} 秒。每项均绑定本次 APK 与构建输入，没有把历史版本的运行结果改标为本次结果。

| 定向用例 | 结果 | 耗时 |
|---|---|---|
{table}

检查根、system、system_ext、vendor、product、odm 六个指纹，以及 system_ext 的 manufacturer、device、name 三项长属性名。对照 Java、Build、native get/read/callback、空名称 read、返回长度及值缓冲区的所有字节。91/92/128/256 字节和长值换短值的每次更新均核对当次进程 PID 保持不变；续跑分为不同执行批次，批次间 PID 不同。128 字节还通过真实设置界面编辑并保存。关闭字段和主开关后恢复原读数。

64 组合复用现有六项方法执行器的实际断言：截图文件夹具、VPN、代理实际请求、开发者选项、USB 调试、SELinux 真实模式/Java/native 文件读数、普通文件、内存释放和方法独立性；每组合另核对上述指纹入口及缓冲区。截图文件为合成夹具，不能代替 SystemUI 截图事件。此次没有修改截图事件 Hook。

## 测试中发现的问题

首轮 92 字节手工指纹档案被现有 91 字节文本校验拒绝，导致档案关闭、版本回到 0。现仅放宽指纹字段到 256 个 UTF-8 字节，补充 JVM 校验、档案解析和真实 UI 保存后重新构建并验证。失败和前一构建记录保留在测试 JSON/log 中。

128 字节 UI 用例曾因专用模拟器没有预装应用、应用使用英文，而执行器查找中文按钮失败。执行器为本次测试明确设置中文，结束后恢复原语言；该次失败不记为应用保存错误。同一 APK 的已通过步骤保留，只继续剩余用例。

## 构建、恢复与安装

四 ABI 编译齐全，正式 APK 排除 debug 厂商夹具，保持原签名。Lint 无错误；模块 {audit["app/build/reports/lint-results-release.xml"]["warnings"]} 个警告，验证器 {audit["verifier/build/reports/lint-results-primaryRelease.xml"]["warnings"]} 个警告。模拟器原 APK、完整数据、设置、模块作用域、权限和应用语言已恢复，测试 VPN/文件已清理，adbd 已解除 root，专用模拟器已关闭。

{phone}

| 安装包 | SHA-256 |
|---|---|
| AppStateShield-0.4.4.apk | {report["artifacts"]["AppStateShield-0.4.4.apk"]} |
| AppStateVerifier-0.4.4.apk | {report["artifacts"]["AppStateVerifier-0.4.4.apk"]} |

## 本次保证范围

保证针对成功安装的本次读取适配器中，已选择且配置有效的指纹返回和值缓冲区。字段或机器关闭后读取原值是用户选择的正常行为。直接读取 prop_info/属性区内存、未注入进程、其他未适配属性和保留的外部 Hook 入口不在这次验证内；callback serial 元数据没有虚拟化。本报告不宣称任意读取方式都无法识别设备。
"""
    note="AppStateShield-0.4.4-指纹修复与测试.md"
    (DELIVERY/note).write_text(report_text)
    data="AppStateShield-0.4.4-测试数据.json"
    (DELIVERY/data).write_text(json.dumps({"tests":report,"buildAudit":audit,"phoneInstall":installed},
        ensure_ascii=False,indent=2)+"\n")
    files=set()
    for folder in ["app/src","verifier/src","shared","gradle","scripts","docs"]:
        files.update(p for p in (ROOT/folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.name!=".DS_Store")
    for name in ["AGENTS.md","README.md","PROJECT-RELATIONSHIPS.md","build.gradle","settings.gradle",
                 "gradle.properties","gradlew","gradlew.bat","app/build.gradle","verifier/build.gradle"]:
        files.add(ROOT/name)
    assert not any(p.suffix in {".p12",".jks",".keystore"} or p.name in {"keystore-password",".env"} for p in files)
    source="AppStateShield-0.4.4-source.zip"
    with zipfile.ZipFile(DELIVERY/source,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):archive.write(path,str(path.relative_to(ROOT)))
    members=list(report["artifacts"])+[note,data,source]
    sums="AppStateShield-0.4.4-SHA256SUMS.txt"
    (DELIVERY/sums).write_text("".join(sha(DELIVERY/name)+"  "+name+"\n" for name in members))
    bundle=DELIVERY/"AppStateShield-0.4.4-delivery.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in members+[sums]:archive.write(DELIVERY/name,name)
        for name in ["property-repair-0.4.4.log","property-native-unit-0.4.4.log",
                     "property-java-unit-0.4.4.log","build-0.4.4.log","build-inputs.json",
                     "selinux-0.4.4-results.json"]:
            archive.write(OUT/name,"verification/"+name)
    for name in [source,bundle.name]:
        with zipfile.ZipFile(DELIVERY/name) as archive:assert archive.testzip() is None
    print("Packaged 0.4.4 repair: 11 targeted checks and all 64 combinations passed")

if __name__=="__main__":main()
