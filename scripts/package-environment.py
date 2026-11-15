#!/usr/bin/env python3
"""Package research, verified repairs and honest limitations without replaying tests."""
import hashlib
import json
import pathlib
import shutil
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DOWNLOADS=pathlib.Path.home()/"Downloads"
RESEARCH=DOWNLOADS/"AppStateShield-environment-research-20261114"
VERSION="0.4.5"
CASES=["E01-never-enabled-baseline","E02-first-enable-ui-and-reads","E03-warning-draft-discard",
       "E04-live-custom-metadata-capacity","E05-field-and-master-restore","E06-authentic-sample-accepted",
       "E07-foreign-same-class-rejected","E08-wrong-signer-rejected","E09-shared-debug-selinux",
       "E10-all-methods-startup"]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    report_path=OUT/"environment-0.4.5-results.json"
    report=json.loads(report_path.read_text())
    audit=json.loads((OUT/"machine-build-checks-0.4.5.json").read_text())
    inputs=OUT/"build-inputs.json"
    for case in CASES:
        row=report["cases"][case]
        assert row["status"]=="passed",case
        assert row["artifacts"]==report["artifacts"] and row["buildInputsSHA256"]==sha(inputs),case
    for key in ["originalAPKBytes","completeDataSnapshotRestored","modulesAndScopes","settings",
                "appLocalesRestored","adbdUnrooted","emulatorShutdownAccepted"]:
        assert report["restoration"][key],key
    unit=(OUT/"environment-unit-0.4.5.log").read_text().strip()
    assert unit.startswith("PASS ")
    typed_unit=(OUT/"environment-typed-unit-0.4.5.log").read_text().strip()
    assert typed_unit.startswith("PASS ")
    for product in ["AppStateShield","AppStateVerifier"]:
        name=product+"-"+VERSION+".apk"
        assert sha(OUT/name)==audit[name]["sha256"]==report["artifacts"][name]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        shutil.copyfile(OUT/name,DOWNLOADS/name)
    index=json.loads((RESEARCH/"source-index.json").read_text())
    for name,digest in index["sha256"].items():assert sha(RESEARCH/name)==digest,name
    previous_source=DOWNLOADS/"AppStateShield-0.4.4-source.zip"
    changes=[]
    with zipfile.ZipFile(previous_source) as old:
        for path in sorted((ROOT/"app/src").rglob("*")):
            if path.is_file():
                name=str(path.relative_to(ROOT))
                if name not in old.namelist() or hashlib.sha256(old.read(name)).hexdigest()!=sha(path):
                    changes.append(name)
        unchanged=[
            "app/src/main/java/io/github/lwtdzh/appstateshield/Methods.java",
            "app/src/main/java/io/github/lwtdzh/appstateshield/RuntimePolicy.java",
            "app/src/main/java/io/github/lwtdzh/appstateshield/PolicyStore.java",
            "app/src/main/java/io/github/lwtdzh/appstateshield/PolicyProvider.java",
            "app/src/main/cpp/devicestate.cpp","app/src/main/cpp/developerstate.cpp",
            "app/src/main/cpp/selinuxstate.cpp","app/src/main/cpp/vpnstate.cpp",
            "shared/native/property-read.h"]
        for name in unchanged:assert old.read(name)==(ROOT/name).read_bytes(),name
    historical=json.loads((OUT/"property-repair-0.4.4-results.json").read_text())
    assert len([k for k,v in historical["cases"].items() if k.startswith("M6-") and v["status"]=="passed"])==64
    comparison={"historicalSourceSHA256":sha(previous_source),"unchangedFiles":{n:sha(ROOT/n) for n in unchanged},
                "changedAppSources":changes,"historicalAPK":historical["artifacts"],
                "historicalReportSHA256":sha(OUT/"property-repair-0.4.4-results.json"),
                "currentAPK":report["artifacts"],"historical64CasesNotRelabeled":True,
                "reason":"Methods、策略和共享 native 实现未改；本次验证首次启用、共享属性及全开启动，不重复旧 64 组合。检测器新增读数，旧结果仅保留历史归属。"}
    comparison_path=OUT/"environment-source-comparison-0.4.5.json"
    comparison_path.write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+"\n")
    names=["AppStateShield-0.4.5.apk","AppStateVerifier-0.4.5.apk"]
    table="\n".join("| "+name+" | 通过 | "+str(report["cases"][name]["durationSeconds"])+" 秒 |" for name in CASES)
    note="AppStateShield-0.4.5-调研修复与测试.md"
    text=f"""# AppStateShield 0.4.5 调研、修复与验证

已完成公开资料和源码调研，保存 32 类环境检测与本应用对照，归档 9 个项目的固定提交源码及 Vector 2.2、AOSP 版本依据。调研主报告与原文索引在交付包 research 目录；每份源码保留许可证、来源及 SHA-256。Momo 没有可核对完整源码，reveny 仓库没有对应 native 实现，均明确标注；没有冒充已经解析其算法。

## 已修复

1. 完整指纹同步 Build.ID、TYPE、TAGS 及各分区编译属性。真实预设保留自己的分区差异；手工指纹按输入推导，不猜固件值。指纹字段关闭后关联值恢复。
2. 验证器状态接口固定包名与发布签名；同名状态类的其他包，以及允许包的其他签名都不会收到模块状态。
3. 设备伪装从未开启时不安装设备 Java Hook；首次开启时安装，前台轮询与保存通知继续支持更新，关闭恢复，避免重复安装。
4. 设置页按草稿提示不一致字段、跨 Android 大版本、隐藏传感器和 SIM 对运营商一键登录的影响；保存/丢弃通过真实 UI 核对。
5. 可选容量按真实占比同步总量、可用/剩余量和块数。StatFs 和普通 File 按设备号识别数据文件系统，系统分区保留原值。实际内存和磁盘不变。
6. 验证器新增真实读取的编译元数据、类型化属性和内存/数据分区容量，结果来源与模块配置分开。

实现和 32 项处理状态详见 docs/ENVIRONMENT-0.4.5.md。源码压缩包包含这些文档及测试脚本。

## 本次实际检查

{unit}

{typed_unit}

Android 16 / ARM64 / Vector / 专用 ScreenshotShield_API36：10 项定向检查通过，合计 {sum(report["cases"][k]["durationSeconds"] for k in CASES):.1f} 秒。每项记录本次 APK、构建输入、开始时间和耗时。开启/自定义更新/关闭检查确认阶段内 PID 不变。单独冷启动用于共享入口和身份反例，不把不同阶段的 PID 写成一直相同。

| 用例 | 结果 | 耗时 |
|---|---|---|
{table}

根与五个分区的 ID/TYPE/TAGS 通过 Java/native 对照。原系统缺少某属性时 native find 没有 prop_info，旧 read/callback 仍可能没有数据；没有把缺失值当作完整虚拟属性区成功。指纹的 get/read/callback、值缓冲区及哨兵在相关启用/更新/共享入口中检查；0.4.4 的不变 sanitizer 边界矩阵没有重复执行。

类型化属性确认密度 getInt/getLong 与设置一致，未知属性保留默认值。容量确认 available ≤ free ≤ total，字节与块数一致，File 总量与 StatFs 一致，系统分区保留；普通文件读写正常。内存确认可用量和阈值不大于总量，关闭时恢复总量。

首轮真实检查发现密度的字符串属性已替换，getInt/getLong 仍返回缺省值 -17。已补 getInt/getLong/getBoolean 的选定属性适配，保持默认值、整数溢出和布尔文本语义。新增 22 条类型化解析检查单独执行，没有重复前面已通过的 241 条纯逻辑检查。首轮 API 27 签名接口的 lint 错误也已增加版本守卫修复。执行器初次遇到未安装包的 pm path 非零返回，已改用实际安装列表；原快照保留，未从头重建。

错误签名反例首轮在卸载/重装目标包后没有获得设备适配读数，不能当作签名校验成功。保留其他 9 项通过结果，仅对这一项重建作用域绑定并冷启动；此后既能读取指定伪装编号，又没有模块状态上报，反例才判为通过。失败和续跑日志均保留。

身份反例使用同名状态类：错误包与错误签名不收到上报，但仍读到专门设置的伪装编译编号，确认模块确实已进入该进程。反例属于测试包，不在正式交付安装包中。

四 ABI 编译齐全，正式 APK 排除 debug 厂商夹具，签名沿用原身份。Lint 无错误；模块 {audit["app/build/reports/lint-results-release.xml"]["warnings"]} 项警告，验证器 {audit["verifier/build/reports/lint-results-primaryRelease.xml"]["warnings"]} 项警告。API 27 上不提供仅 API 28+ 验证器可用的状态上报；API 27/其他 ABI 未做运行验证。

0.4.4 的 64 组合保留原哈希与原报告。Methods、策略和共享 native 实现按旧源码归档逐字节对照未变；本次新增共享 debug/SELinux 和六项全开启动核对。旧检测器没有这次新增读数，旧记录没有改标为 0.4.5，也没有升级为程序化跨 APK 复用。

## 未完成的能力与登录结论

没有连接 vivo，本次没有安装到真机，也没有执行淘宝/拼多多真实登录。当前结果不能证明这两款应用恢复登录。

Vector 2.2 排除隔离 UID/AppZygote；原始属性区/serial、外部 exec、任意内联 SVC、ART 根引用、代码与磁盘对照、CPU/GPU/HAL/内核及 TEE 证明仍不完全受本模块控制。完整硬件互换、服务端账号/行为关联也未实现。调研把这些入口逐项列出，未用重命名或清空列表冒充修复。

模拟无 SIM 或模拟有 SIM 不创建真实运营商通道，运营商一键登录可能失败；密码/短信登录也由真实服务端决定。跨 Android 大版本预设仍有实际 API/内核矛盾。首次开启前已缓存的 StatFs 对象、静态字段内联和应用缓存需冷启动。

## 恢复与安装

专用模拟器原 APK、数据、设置、作用域、模式及应用语言已恢复；身份反例包已移除。ADB 已解除 root，专用模拟器关闭。未操作无关 emulator-5594。手机尚未连接，交付两个同签名 APK；安装后目标应用需彻底关闭再打开。

| 安装包 | SHA-256 |
|---|---|
| AppStateShield-0.4.5.apk | {sha(OUT/names[0])} |
| AppStateVerifier-0.4.5.apk | {sha(OUT/names[1])} |
"""
    (DOWNLOADS/note).write_text(text)
    (OUT/"ENVIRONMENT-0.4.5-REPORT.md").write_text(text)
    data="AppStateShield-0.4.5-测试数据.json"
    (DOWNLOADS/data).write_text(json.dumps({"tests":report,"buildAudit":audit,"sourceComparison":comparison},
        ensure_ascii=False,indent=2)+"\n")
    source="AppStateShield-0.4.5-source.zip"
    files=set()
    for folder in ["app/src","verifier/src","shared","gradle","scripts","docs"]:
        files.update(p for p in (ROOT/folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.name!=".DS_Store")
    for name in ["AGENTS.md","README.md","PROJECT-RELATIONSHIPS.md","build.gradle","settings.gradle",
                 "gradle.properties","gradlew","gradlew.bat","app/build.gradle","verifier/build.gradle"]:
        files.add(ROOT/name)
    assert not any(p.suffix in {".p12",".jks",".keystore"} or p.name in {".env","keystore-password"} for p in files)
    with zipfile.ZipFile(DOWNLOADS/source,"w",zipfile.ZIP_DEFLATED) as z:
        for path in sorted(files):z.write(path,str(path.relative_to(ROOT)))
    members=names+[note,data,source]
    sums="AppStateShield-0.4.5-SHA256SUMS.txt"
    (DOWNLOADS/sums).write_text("".join(sha(DOWNLOADS/n)+"  "+n+"\n" for n in members))
    bundle=DOWNLOADS/"AppStateShield-0.4.5-delivery.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        for name in members+[sums]:z.write(DOWNLOADS/name,name)
        for path in sorted(RESEARCH.rglob("*")):
            if path.is_file() and ("sources" in path.parts or path.name in
                {"Android设备环境检测调研.md","source-index.json"}):
                z.write(path,"research/"+str(path.relative_to(RESEARCH)))
        for name in ["environment-0.4.5-results.json","environment-unit-0.4.5.log","environment-typed-unit-0.4.5.log",
            "build-0.4.5.log","build-0.4.5-api27-lint-failure.log","build-inputs.json",
            "build-0.4.5-before-typed-repair.log","environment-restore-0.4.5.log",
            "environment-source-comparison-0.4.5.json","machine-build-checks-0.4.5.json",
            "environment-runtime-0.4.5.log","environment-runtime-0.4.5-resume.log","environment-hints-0.4.5.png"]:
            if (OUT/name).exists():z.write(OUT/name,"verification/"+name)
        for path in sorted(OUT.glob("environment-runtime-0.4.5-*.log")):
            if "verification/"+path.name not in z.namelist():z.write(path,"verification/"+path.name)
    for path in [DOWNLOADS/source,bundle]:
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
    with zipfile.ZipFile(bundle) as z:
        for name in members:assert hashlib.sha256(z.read(name)).hexdigest()==sha(DOWNLOADS/name),name
    print("Verified delivery:",bundle)
    print("10 selected Android cases; research files verified:",len(index["sha256"]))

if __name__=="__main__":main()
