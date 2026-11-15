#!/usr/bin/env python3
"""Deliver current object repair and pinned research; never replay runtime tests."""
import hashlib
import json
import pathlib
import shutil
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DOWNLOADS=pathlib.Path.home()/"Downloads"
REVIEW=DOWNLOADS/"AppStateShield-设备检测深入复核与模块协作.md"
PRIVATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/deep-environment-review"
OLD_RESEARCH=DOWNLOADS/"AppStateShield-environment-research-20261114"

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    report=json.loads((OUT/"property-objects-0.4.6-results.json").read_text())
    audit=json.loads((OUT/"machine-build-checks-0.4.6.json").read_text())
    cases={k:v for k,v in report["cases"].items() if k.startswith(("P","M6-"))}
    assert len([k for k in cases if k.startswith("M6-")])==64
    assert len([k for k in cases if k.startswith("P")])==10
    for key,row in cases.items():
        assert row["status"]=="passed",key
        assert row["artifacts"]==report["artifacts"],key
        assert row["buildInputsSHA256"]==sha(OUT/"build-inputs.json"),key
    for key in ["originalAPKBytes","completeDataSnapshotRestored","modulesAndScopes","settings",
                "vpnStopped","temporaryFilesRemoved","grantsAndLocalesRestored","adbdUnrooted","emulatorShutdown"]:
        assert report["restoration"][key],key
    for product in ["AppStateShield","AppStateVerifier"]:
        name=product+"-0.4.6.apk"
        assert sha(OUT/name)==report["artifacts"][name]==audit[name]["sha256"]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        shutil.copyfile(OUT/name,DOWNLOADS/name)
    unit=(OUT/"property-view-unit-0.4.6-final.log").read_text().strip()
    assert unit.startswith("PASS ")
    previous=DOWNLOADS/"AppStateShield-0.4.5-source.zip"
    unchanged=["app/src/main/java/io/github/lwtdzh/appstateshield/"+n+".java" for n in
               ["Methods","RuntimePolicy","PolicyStore","PolicyProvider","DeviceHooks","DeviceStore","VerifierIdentity"]]
    unchanged+=["app/src/main/cpp/"+n+".cpp" for n in ["shield","vpnstate"]]
    with zipfile.ZipFile(previous) as old:
        for name in unchanged:assert old.read(name)==(ROOT/name).read_bytes(),name
        changed=[str(p.relative_to(ROOT)) for p in sorted((ROOT/"app/src").rglob("*")) if p.is_file() and p.name!=".DS_Store"
                 and (str(p.relative_to(ROOT)) not in old.namelist() or
                      old.read(str(p.relative_to(ROOT)))!=p.read_bytes())]
        shared_changed=[str(p.relative_to(ROOT)) for p in sorted((ROOT/"shared/native").glob("*")) if p.is_file()
                        and (str(p.relative_to(ROOT)) not in old.namelist() or
                             old.read(str(p.relative_to(ROOT)))!=p.read_bytes())]
    comparison={"previousSourceSHA256":sha(previous),"changedAppSources":changed,
        "changedSharedNative":shared_changed,
        "unchangedPolicyAndAdapters":{n:sha(ROOT/n) for n in unchanged},
        "currentArtifacts":report["artifacts"],"current64CombinationCases":True,
        "historical0.4.5UnitAndUICasesNotReplayed":True}
    comparison["executors"]={"currentSHA256":sha(ROOT/"scripts/property-object-test.py"),
        "beforeRadioStallSHA256":sha(OUT/"property-object-executor-before-radio-stall.py")}
    (OUT/"property-object-source-comparison-0.4.6.json").write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+"\n")

    # Archive licensed source excerpts; closed release descriptions remain URLs and hashes.
    supplementary=DOWNLOADS/"AppStateShield-deep-review-research-20261114"
    supplementary.mkdir(exist_ok=True)
    source_index={"date":"2026-11-14","repositories":[],"sha256":{}}
    release=json.loads((PRIVATE/"shamiko-release.json").read_text())
    source_index["publicReleaseDescription"]={"url":release.get("html_url"),"tag":release.get("tag_name"),
        "sha256":sha(PRIVATE/"shamiko-release.json"),"implementationReviewed":False}
    for folder in sorted((PRIVATE/"sources").iterdir()):
        manifest=folder/"manifest.json"
        if manifest.exists():
            meta=json.loads(manifest.read_text())
            for row in meta["files"]:assert sha(folder/row["path"])==row["sha256"],row["path"]
            source_index["repositories"].append(meta)
            if not meta.get("license"):continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file():continue
            relative=path.relative_to(PRIVATE/"sources")
            target=supplementary/"sources"/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
            source_index["sha256"][str(pathlib.Path("sources")/relative)]=sha(target)
    (supplementary/"source-index.json").write_text(json.dumps(source_index,ensure_ascii=False,indent=2)+"\n")
    shutil.copyfile(REVIEW,supplementary/REVIEW.name)
    shutil.copyfile(OUT/"deep-review-capabilities.json",supplementary/"deep-review-capabilities.json")
    for name,digest in json.loads((OLD_RESEARCH/"source-index.json").read_text())["sha256"].items():
        assert sha(OLD_RESEARCH/name)==digest,name

    note=DOWNLOADS/"AppStateShield-0.4.6-深入复核与属性修复.md"
    selected=sum(v["durationSeconds"] for k,v in cases.items() if k.startswith("P"))
    matrix=sum(v["durationSeconds"] for k,v in cases.items() if k.startswith("M6-"))
    missing=cases["P02-enable-long-object-and-missing-property"]["evidence"]["actualMissingProperties"]
    text=f"""# AppStateShield 0.4.6 深入复核与属性对象修复

本次仔细复核原 9 个项目资料，补充 HMA-OSS、Zygisk Assistant、SUSFS LKM、ReSuSFS 的固定提交源码与 Bionic 属性对象布局。Zygisk Next/Shamiko 只按公开说明引用，未声称取得闭源实现。完整分析见《{REVIEW.name}》和交付包 research 目录。

## 修复了什么

0.4.5 返回的属性文本与真实 prop_info 头部、serial 可能不一致。0.4.6 在本 APK 的设备 native 层创建不可变只读对象；find/foreach/find_nth 提供同一对象，长值保留完整 callback 内容与 Android 兼容槽，serial 自然读取对应对象头部。developerstate/selinuxstate 通过本 APK 内部 HandleAdapter 共用对象，不重复过滤旧缓存。

首次配置前已缓存的原指针，经本模块 read/callback 会读取当前替换值；如果应用直接读取该原指针的内存，仍可读到原始数据。已返回的合成只读对象终身保留旧值，重新 find 才读取新值；没有把旧缓存说成已经实时更新。

对象使用密封 memfd 的 PROT_READ 私有文件映射，初始化后不保留写映射和 FD。原型的“只读”是 ro.* 语义，原型 vector 内存仍可写。正式集成首次采用私有匿名只读映射时，Bionic 的 shared futex 空转，采样超时；线程栈定位到 SystemProperties::Wait。尝试密封文件后的共享映射，实际在 mmap 阶段被拒绝（EPERM）；改成私有文件映射后原始 wait 的零超时检查通过。这些失败日志均保留，不将原型结果用于证明生产映射。

机器伪装默认关闭；六项 Methods、Provider UID 权限、Vector、内核、系统分区、预设和设置交互没有修改。实现细节见源码包 docs/PROPERTY-OBJECTS-0.4.6.md；与 0.4.5 的源码对照随测试数据保存。

## 本次执行

{unit}

Android 16 ARM64 / Vector / ScreenshotShield_API36：10 项定向检查通过，累计 {selected:.1f} 秒；64 项共享 native 组合通过，累计 {matrix:.1f} 秒。每项保存时间、实际读数、APK SHA-256 和构建输入。10 项包括原始/未注入基线、首次开启、256/48 字节同进程更新、真实值等于旧替换值的反例、字段/总开关关闭，以及 debug、SELinux 和两者共用读取；最后有一次策略 UI 保存。

原始内存名称和值与 callback 一致；header/API/callback serial 一致；长值标志和相对偏移正确；read/get/nullName 值缓冲区清零、哨兵完整；枚举没有重复，find_nth 与 find 指向同一对象，越界为空。实际原系统缺失的选中属性：{", ".join(missing)}，开启后得到对象并进入枚举。其他机型属性在该 AVD 原本存在，没有把它们冒充缺失属性基线。

更新/关闭阶段保持 PID；旧合成缓存仍能安全读取旧替换值，新查找读取当前值/恢复原值。64 组合同时保留六项方法的真实模式、VPN/USB、代理请求、原生 FD/普通文件对照及属性对象断言。截图文件属于构造夹具；不声称本次重复验证了 SystemUI 截图事件。

联测在已通过 21 项后遇到系统 Watchdog 重启。无线电服务原本未启动，验证器反复读取未选择的 Build.getSerial，让 system_server 的权限检查阻塞在电话服务，Binder 线程池耗尽。系统 ANR 和启动日志已保存。恢复临时 VPN 后，仅在后续联测档案中增加现有 serial 字段，阻止这条无关电话权限读取；APK、六项断言、原 21 项读数及原快照均未改。剩余 43 项从失败处续跑，两个执行器版本及各自 SHA-256 保留。没有把失效的模拟器无线电服务标成已恢复或通过。

四 ABI 编译和正式 APK 签名/导出/夹具排除检查通过。API 27、其他 ABI 及 vivo 没有运行结果。0.4.5 的 241+22 条纯逻辑及不变 UI 检查未重复执行，原记录保留原 APK 归属。早期失败及必要的基线冷启动保留在 previousRuns 和运行日志，未覆盖原快照。

Lint 没有错误；主模块保留 {audit["app/build/reports/lint-results-release.xml"]["warnings"]} 项警告，验证器 {audit["verifier/build/reports/lint-results-primaryRelease.xml"]["warnings"]} 项警告。构建日志和导出检查数据随包保存。

## 为什么仍有检测无法通过，是否需要其他模块

| 检测入口 | 当前状态与可能的协作 |
|---|---|
| 公共属性对象读取 | 本次在现有模块内修复；直接系统属性区和映射来源检查仍可区分 |
| 直接 SVC 读取文件/系统状态 | 普通应用 seccomp 原型已经拦截直接 getpid；尚无通用路径代理、多线程和信号处理的生产实现 |
| 挂载及注入来源 | 普通应用 unshare 原型返回 EPERM；Zygisk Assistant 在降权前可辅助命名空间与卸载，SUSFS/LKM 可辅助内核文件视图 |
| 应用列表及直接 PMS Binder | HMA-OSS 的服务端按 UID 过滤可辅助；需要 system_server 作用域及受信配置，不是增加一个 getter |
| Vector 排除的隔离进程 | 本模块没有执行点；需要框架/更早组件；仅更换 Zygisk 实现不自动消除 Vector 排除条件 |
| ART、代码校验、GPU/HAL/TEE、服务端登录 | 更多本地 Hook 不能提供通用保证，真实证明/协议与账号风险另有数据所有者 |

辅助模块需要验证与 Vector 同时工作且本模块仍注入；没有安装或修改它们。普通 fork 会继承 native 映射，但多线程 fork 中缓存锁及配置刷新未专测；exec 会更换地址空间。未注入进程、全局属性更新通知、任意代码完整性、硬件证明和真实服务端登录仍未解决。

## 交付和环境

专用模拟器原 APK、完整数据、授权/语言、设置、作用域和 SELinux 模式已恢复；临时 VPN/文件已清理，ADB 解除 root，模拟器关闭。未操作无关 emulator-5594。vivo 未连接，没有把新版装到手机，也没有淘宝/拼多多登录成功证据。

交付包含两个同签名 APK、完整项目源码、验证器/执行器、人工说明、测试数据、构建日志、失败记录、复核资料及 SHA-256。安装后目标应用需冷启动。

| APK | SHA-256 |
|---|---|
| AppStateShield-0.4.6.apk | {sha(DOWNLOADS/"AppStateShield-0.4.6.apk")} |
| AppStateVerifier-0.4.6.apk | {sha(DOWNLOADS/"AppStateVerifier-0.4.6.apk")} |
"""
    note.write_text(text)
    (OUT/"PROPERTY-OBJECTS-0.4.6-REPORT.md").write_text(text)
    data=DOWNLOADS/"AppStateShield-0.4.6-测试数据.json"
    data.write_text(json.dumps({"tests":report,"buildAudit":audit,"sourceComparison":comparison},ensure_ascii=False,indent=2)+"\n")
    files=set()
    for folder in ["app/src","verifier/src","shared","gradle","scripts","docs"]:
        files.update(p for p in (ROOT/folder).rglob("*") if p.is_file() and
                     "__pycache__" not in p.parts and p.name!=".DS_Store")
    files.update(ROOT/n for n in ["AGENTS.md","README.md","PROJECT-RELATIONSHIPS.md","build.gradle",
        "settings.gradle","gradle.properties","gradlew","gradlew.bat","app/build.gradle","verifier/build.gradle"])
    assert not any(p.suffix in {".p12",".jks",".keystore"} or p.name in {".env","keystore-password"} for p in files)
    source=DOWNLOADS/"AppStateShield-0.4.6-source.zip"
    with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):z.write(p,str(p.relative_to(ROOT)))
    members=[DOWNLOADS/"AppStateShield-0.4.6.apk",DOWNLOADS/"AppStateVerifier-0.4.6.apk",note,data,source,REVIEW]
    sums=DOWNLOADS/"AppStateShield-0.4.6-SHA256SUMS.txt"
    sums.write_text("".join(sha(p)+"  "+p.name+"\n" for p in members))
    bundle=DOWNLOADS/"AppStateShield-0.4.6-delivery.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        for p in members+[sums]:z.write(p,p.name)
        for root,label in [(OLD_RESEARCH,"research/initial"),(supplementary,"research/deep-review")]:
            for p in sorted(root.rglob("*")):
                if p.is_file() and ("sources" in p.parts or p.suffix in {".md",".json"}):
                    z.write(p,label+"/"+str(p.relative_to(root)))
        evidence=set(OUT.glob("property-object*.log"))|set(OUT.glob("property-object*.json"))
        evidence|=set(OUT.glob("property-view-unit-0.4.6*.log"))|set(OUT.glob("build-0.4.6*.log"))
        evidence|={OUT/"build-inputs.json",OUT/"machine-build-checks-0.4.6.json",OUT/"selinux-0.4.6-results.json",
                   OUT/"deep-review-capabilities.json",OUT/"deep-review-capability-runtime.log",
                   OUT/"property-object-executor-before-radio-stall.py"}
        for p in sorted(evidence):
            if not p.is_file():continue
            if p.suffix==".log":
                lines=p.read_text(errors="replace").splitlines()
                lines=["[public ADB key omitted]" if "adb public key" in line or "qemu.adb.pubkey=" in line
                       else line for line in lines]
                z.writestr("verification/"+p.name,"\n".join(lines)+"\n")
            else:z.write(p,"verification/"+p.name)
    for p in [source,bundle]:
        with zipfile.ZipFile(p) as z:assert z.testzip() is None
    with zipfile.ZipFile(bundle) as z:
        for p in members:assert hashlib.sha256(z.read(p.name)).hexdigest()==sha(p),p.name
    print("Verified delivery:",bundle)
    print("10 targeted checks and 64 current combinations; licensed supplementary source files:",
          len(source_index["sha256"]))

if __name__=="__main__":main()
