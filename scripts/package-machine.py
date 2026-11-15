#!/usr/bin/env python3
"""Package actual tested APKs, source, manual and evidence. No private backups or keys."""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta
from test_evidence import accepted, local

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DEST=pathlib.Path.home()/"Downloads"
VERSION="0.4.0"

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    report=json.loads((OUT/"machine-0.4.0-results.json").read_text())
    regression=json.loads((OUT/"selinux-0.4.0-results.json").read_text())
    audit=json.loads((OUT/"machine-build-checks-0.4.0.json").read_text())
    restored=json.loads((OUT/"machine-finalization-0.4.0.json").read_text())
    if restored.get("artifacts")!=report["artifacts"]:
        raise RuntimeError("Restoration record belongs to an earlier APK")
    for key in ["settings","scopes","modules","originalPackages","vpnStopped","fixturesRemoved",
        "clipboardBackupRestored","adbUnrooted","dedicatedEmulatorShutdownAccepted"]:
        if restored.get(key) is not True:raise RuntimeError("Incomplete restoration: "+key)
    required=["D00-capture","D01-upgrade-default","D02-drafts-rotation","D03-xiaomi-smoke",
        "D03-oppo-preset","D04-invalid-input","D04-valid-manual-imei","D04-single-preset-group-random","D05-imei-live",
        "D05-stable-reads","D05-D10-live-fields-OEM-fixtures","D07-apps-processes-delete",
        "D08-D12-multiple-paths","D06-fieldoff-masteroff","D06-all-fields-off","D14-optional-environment",
        "D13-display-rotation","D15-two-second-foreground","D15-cached-binder","D16-D17-legacy-regression",
        "D16-actual-system-screenshot","D08-native-callback-ownership","D18-restored"]
    effective={}
    for key in required:
        if key=="D00-capture":
            if report["cases"].get(key,{}).get("status")!="passed":raise RuntimeError("Missing original snapshot")
            effective[key]=report["cases"][key]
        else:effective[key]=accepted(OUT/"machine-0.4.0-results.json",key,report["artifacts"])[0]
    timer=effective["D15-two-second-foreground"]["evidence"]
    if timer.get("activityRelaunchBetweenTimerSamples") is not False:
        raise RuntimeError("Autonomous foreground timer evidence is missing")
    empty=effective["D06-all-fields-off"]["evidence"]
    if empty.get("fields")!=46 or empty.get("masterRemainsOn") is not True or empty.get("selectedFields")!=[]:
        raise RuntimeError("All-fields-off runtime evidence is missing")
    activation=empty["enabledProfileObservedBeforeClearing"]
    if not activation["module"]["deviceNative"]:
        raise RuntimeError("First active snapshot preceded native initialization")
    active=activation["reads"]
    properties=active["native"]["value"]["properties"]
    for property_name,field in [("ro.product.model","model"),("ro.product.brand","brand")]:
        routes=properties[property_name]
        if len(routes)!=3 or any(value!=active[field]["value"] for value in routes.values()):
            raise RuntimeError("Live native activation did not match Java reads: "+property_name)
    for i in range(64):
        accepted(OUT/"selinux-0.4.0-results.json","M6-"+format(i,"06b"),regression["artifacts"])
    for stage in ["baseline","observed","enabledProfileObservedBeforeClearing"]:
        snapshot=empty[stage]
        if snapshot.get("phoneWorker",{}).get("revision")!=snapshot["module"]["deviceRevision"]:
            raise RuntimeError("Field restoration phone worker revision differs: "+stage)
    for name in ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk"]:
        if digest(OUT/name)!=report["artifacts"][name]:raise RuntimeError("APK differs from installed evidence: "+name)
        if digest(OUT/name)!=regression["artifacts"][name]:raise RuntimeError("APK differs from regression evidence: "+name)
        if digest(OUT/name)!=audit[name]["sha256"]:raise RuntimeError("APK differs from build audit: "+name)
        if not audit[name]["OEMDebugClassesExcluded"] or not audit[name]["signingIdentityPreserved"]:
            raise RuntimeError("Release fixture/signature audit failed: "+name)
        if set(audit[name]["fourABIs"])!={"arm64-v8a","armeabi-v7a","x86","x86_64"}:
            raise RuntimeError("Incomplete release ABI set: "+name)
        shutil.copy2(OUT/name,DEST/name)
    if audit["AppStateShield-0.4.0.apk"]["nativeExportChecks"]!=64:
        raise RuntimeError("Four-ABI native export audit is incomplete")
    for name in ["app/build/reports/lint-results-release.xml","verifier/build/reports/lint-results-primaryRelease.xml"]:
        if audit[name]["errors"]!=0:raise RuntimeError("Release lint failed: "+name)
    unit=(OUT/"device-field-unit-0.4.0.log").read_text().strip()
    timed=[v for k,v in regression["cases"].items() if k.startswith("M6-") and
        v.get("artifacts")==regression["artifacts"] and v.get("status")=="passed" and "startedAtUTC" in v]
    timing=""
    if timed:
        start=min(datetime.fromisoformat(v["startedAtUTC"]) for v in timed)
        end=max(datetime.fromisoformat(v["startedAtUTC"])+timedelta(seconds=v["durationSeconds"]) for v in timed)
        timing=f"有耗时记录的 {len(timed)} 个组合，从首项开始到末项结束共 {(end-start).total_seconds():.1f} 秒（含批量配置）；先前保留结果没有补写耗时。"
    lines=["# AppStateShield 0.4.0 · 模拟器测试报告","",
        "模块和验证器均为 0.4.0。运行环境是专用 ScreenshotShield_API36、Android 16 / API 36、ARM64、Vector。四 ABI 构建通过与运行检查分别记录。",
        "",f"设备字段检查：{unit}。机器伪装已选择字段、设置操作、实时更新与多应用隔离按下表执行；原有六种屏蔽在机器伪装开启时完成 64 种组合。",
        timing,
        "","| 执行条目 | 结果 | 当次模块 / 验证器 SHA-256 前 12 位 |","|---|---|---|"]
    for key in required:
        row,attribution=(report["cases"][key],"原始快照") if key=="D00-capture" else accepted(
            OUT/"machine-0.4.0-results.json",key,report["artifacts"])
        hashes=row.get("artifacts",{})
        stamp=" / ".join(hashes.get(n,"原始快照")[:12] for n in ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk"])
        lines.append("| "+key+" | 通过；"+attribution+" | "+stamp+" |")
    lines.extend(["","原始数据见 machine-0.4.0-results.json、selinux-0.4.0-results.json；安装包 SHA-256 见随包校验文件。报告保留先前失败记录，最新结果与修复后重测分开。",
        "已通过的最终 APK 结果在中断后原样保留，剩余组合使用专用模拟器批量配置。跨 APK 复用须通过构建时源码、读取断言、环境和本次集成对照，保留原 APK 哈希；缺少这些资料的历史结果不用于交付判断。",
        "首次开启的失败原始证据保存在 machine-activation-before-fix-0.4.0.json：当时 Java 机型已变化，deviceNative 为 false，三个原生入口仍返回模拟器机型。修复后须确认新配置版本、Java 字段和三个原生入口一致，才允许生成交付包。",
        "后台进程结束的问题另有 machine-cached-binder-before-fix-0.4.0.json：真实电话 Binder 请求超时后仍等待回复。电话检测现由同包、同 UID 的辅助进程调用，结果保留来源、辅助 PID 和配置版本，结束辅助进程释放未完成请求；检测页保留 PID。模块周期查询也在页面后台停止。已用未伪装电话请求、系统缓存冻结、返回页面的同 PID 对照重测。",
        "批量还原的第一次比较在 IMEI 项失败，该次未保存前后读数，无法据此确认原因或认定真实 IMEI 泄漏。保留失败记录后，增加前后完整快照，仅定向执行还原：同 PID 下 46 个原值/原错误、Java/native 属性全部一致，三阶段电话辅助进程与主进程配置版本相同；IMEI 的原始与还原结果均为电话 API 超时。完整诊断见 machine-all-fields-off-diagnostic-0.4.0.json，不能把超时结果写成真实 IMEI 可读基线。",
        "","## 实际核对范围","",
        "- 默认关闭、按应用保存、两种机型预设、单字段预设、手工编辑、IMEI 校验、已选择随机字段刷新、取消/丢弃、旋转保留草稿。",
        "- 同 PID 的 IMEI / Android ID / OAID / 坐标读取、静态字段还原、单字段关闭、主开关关闭、删除档案、多 UID 与同包多进程。",
        "- 保持机器伪装主开关开启，用专用模拟器批量配置关闭全部字段；46 个字段逐项对比总开关关闭时的原值/原错误，随后恢复原档案的字段和值。手工 IMEI 保存和界面交互仍走真实 UI。",
        "- Java 属性与 Bionic get/read/callback，Display 横竖屏及资源 metrics，总内存/容量/语言/时区/传感器选择，普通文件和显式 Locale/TimeZone。",
        "- 明确命名的 vivo/Xiaomi/MSA/HeyTap/Google 调试夹具；定位 getter、对象回调、原始 Parcel 字段与 NMEA，LTE 标识的 Parcel。",
        "- 真实 SELinux Permissive/Enforcing、普通 FD/EOF/错误、原生截图文件/已有 FD、syscall 六参数、clone 新栈、实际代理请求、HTTPS 与 Provider 越权读写拒绝。",
        "- 机器伪装开启时，真实 SystemUI 截图保存与两种截图回调按关闭、开启、重新关闭截图屏蔽执行对照。",
        "","## 尚未证明的项目","",
        "- AOSP 没有真实厂商标识服务；SDK 形状夹具不能证明 vivo、OPPO、小米各 ROM 的全部路径。",
        "- 模拟器电话 HAL 存在等待不返回的入口；合成基站对象证明适配器行为，不能当真实 modem 回调验证。定位/NMEA 的对象夹具也不能代替真实 GPS 事件。",
        "- Widevine 实例在此模拟器不支持，DRM ID 缺少可读取基线。native 网卡地址若未返回 AF_PACKET 数据，只能确认接口列表释放测试。",
        "- 应用私有缓存、反射/JNI 直读原对象字段、ART 内联、任意 Binder/内核直读、硬件认证、公网 IP、账号和服务端关联仍可能暴露真实信息。需要按具体应用继续验证。",
        "- 定位权限撤回、不同 ROM 的 Wi-Fi 扫描和实机窗口布局留在人工计划中，未以模拟器空数据判作通过。",
        "","本轮只在专用模拟器执行；最终已恢复原状态并关闭专用 AVD。"])
    catalog=(ROOT/"shared/java/io/github/lwtdzh/deviceprofile/DeviceField.java").read_text()
    fields=re.findall(r'f\("([^"]+)","[^"]+","([^"]+)"',catalog)
    if len(fields)!=46:raise RuntimeError("Field report no longer matches the shared catalog")
    baseline=effective["D01-upgrade-default"]["evidence"]["reads"]
    smoke=effective["D03-xiaomi-smoke"]["evidence"]
    environment=effective["D14-optional-environment"]["evidence"]["observed"]["reads"]
    lines.extend(["","## 每个字段的观察情况","",
        "未开启时一栏仅记录接口是否可读；开启后返回保存值不代表这个模拟器拥有真实 SIM、GPS 或厂商服务。厂商夹具与正式验证器分别标注。",
        "","| 字段 | 未开启时 | 开启后的观察 | 读取入口 |","|---|---|---|---|"])
    for key,label in fields:
        before=baseline.get(key,{})
        state=("无法读取："+before["error"]) if "error" in before else ("无数据" if before.get("value") is None else "可读取")
        row=smoke["observed"]["reads"].get(key,{})
        if key in {"oaid","vaid","aaid","gaid"}:
            result="厂商/广告 SDK 夹具通过；真实服务未验证"
        elif key=="drm_id":
            row=environment.get(key,{})
            result="无法核对："+row.get("error","无可读取基线")
        elif key in smoke["profile"]["selected"]:
            result="正式验证器接口返回保存值"
        elif key in {"total_ram","storage","timezone","language","hide_sensors"}:
            row=environment.get(key,{})
            result="单独勾选后返回保存值；测试后关闭"
        else:
            result="未验证"
        cells=[label,state,result,row.get("source","—")]
        lines.append("| "+" | ".join(str(cell).replace("|","/").replace("\n"," ") for cell in cells)+" |")
    text="\n".join(lines)+"\n"
    (OUT/"MACHINE-0.4.0.md").write_text(text)
    (DEST/"AppStateShield-0.4.0-测试报告.md").write_text(text)
    manual=(ROOT/"docs/TEST-MANUAL.md").read_text()+"\n\n"+(ROOT/"docs/DEVICE-TEST-MATRIX.md").read_text()
    manual+="\n\n"+(ROOT/"docs/DEVICE-SPOOFING.md").read_text()
    manual+="\n\n"+(ROOT/"docs/TEST-EXECUTION-POLICY.md").read_text()
    manual=manual.replace("(DEVICE-TEST-MATRIX.md)","(#机器伪装测试计划)")
    manual=manual.replace("(DEVICE-SPOOFING.md)","(#机器伪装实现与逐项核对)")
    manual=manual.replace("(TEST-EXECUTION-POLICY.md)","(#测试范围结果复用与停止规则)")
    (DEST/"AppStateShield-0.4.0-人工测试手册.md").write_text(manual)
    # Include the actual worktree source, including new files; no build folders or key storage.
    names=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard","-z"],cwd=ROOT).decode().split("\0")
    source=DEST/"AppStateShield-0.4.0-source.zip"
    allowed=("app/src/","verifier/src/","shared/","scripts/","docs/","gradle/",".github/",".trae/skills/")
    rootfiles={"README.md","AGENTS.md","PROJECT-RELATIONSHIPS.md","build.gradle","settings.gradle",
        "gradle.properties","gradlew","gradlew.bat",".gitignore","app/build.gradle","verifier/build.gradle"}
    with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names)):
            path=ROOT/name
            if path.is_file() and (name in rootfiles or name.startswith(allowed)):
                if not any(part in {"build",".cxx","__pycache__"} for part in path.parts):archive.write(path,name)
    with zipfile.ZipFile(source) as archive:
        if archive.testzip() is not None:raise RuntimeError("Source ZIP verification failed")
        for name in archive.namelist():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest(ROOT/name):
                raise RuntimeError("Source ZIP differs from worktree: "+name)
    notes=DEST/"AppStateShield-0.4.0-使用说明.md"
    notes.write_text("""# AppStateShield 0.4.0

安装 AppStateShield 和 AppStateVerifier 两个正式 APK。在 Vector 启用整合模块，选中需要保护的应用。模块设置 → 应用详情 → 配置机器伪装，单独打开主开关。首次开启生成小米 14 档案，可换 OPPO Find X9s。

每个字段可选择是否伪装、编辑、随机刷新；非随机字段可单独从预设填入。保存后到验证器的“设备信息 · 实际读取”页观察时间、PID 和变化。读取方法通常随两秒轮询更新，目标应用已有缓存或启动判断需强行停止后重开。

机器伪装默认关闭，六项旧屏蔽的默认规则不变。关闭主开关保留档案，删除定制恢复默认。sampleA/B 是临时测试目标，不需要安装到手机。

报告、人工手册、资料核对和源码都在交付包内。厂商 ROM、硬件认证、内核/任意 Binder 直读和服务端关联的限制见测试报告。
""")
    deliver=DEST/"AppStateShield-0.4.0-delivery.zip"
    paths=[DEST/n for n in ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk",
        "AppStateShield-0.4.0-source.zip","AppStateShield-0.4.0-测试报告.md","AppStateShield-0.4.0-人工测试手册.md",
        "AppStateShield-0.4.0-使用说明.md","机器伪装-资料核对.md","机器伪装-产品说明.html"]]
    evidence=[OUT/n for n in ["machine-0.4.0-results.json","selinux-0.4.0-results.json",
        "build-0.4.0.log","device-field-unit-0.4.0.log","machine-editor-0.4.0.png",
        "machine-verifier-0.4.0.png","machine-landscape-0.4.0.png","machine-runtime-0.4.0.log",
        "selinux-0.4.0-test.log","machine-events-0.4.0.log","machine-build-checks-0.4.0.json",
        "machine-ownership-0.4.0.log","machine-smoke-0.4.0.log","machine-ui-0.4.0.log",
        "machine-prepare-0.4.0.log","machine-restore-start-0.4.0.log","machine-imei-editor-0.4.0.png",
        "machine-finalization-0.4.0.json","machine-activation-before-fix-0.4.0.json",
        "machine-cached-binder-before-fix-0.4.0.json","machine-cached-binder-0.4.0.log",
        "machine-all-fields-off-diagnostic-0.4.0.json","test-executor-checks-0.4.0.log"]]
    for source in [report,regression]:
        for proof in source.get("reuse",{}).values():
            for key in ["originalReport","originalInputs","currentInputs","currentIntegration"]:
                path=local(proof[key])
                if path not in evidence:evidence.append(path)
            integration=json.loads(local(proof["currentIntegration"]).read_text())
            for key in ["report","baselineReport"]:
                path=local(integration[key])
                if path not in evidence:evidence.append(path)
    manifest=DEST/"AppStateShield-0.4.0-SHA256SUMS.txt"
    manifest.write_text("".join(digest(p)+"  "+p.name+"\n" for p in paths+evidence))
    with zipfile.ZipFile(deliver,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in paths+[manifest]:archive.write(path,path.name)
        for path in evidence:archive.write(path,"evidence/"+path.name)
    with zipfile.ZipFile(deliver) as archive:
        if archive.testzip() is not None:raise RuntimeError("Delivery ZIP verification failed")
        for path in paths+evidence:
            name=path.name if path in paths else "evidence/"+path.name
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest(path):raise RuntimeError("ZIP hash mismatch")
    print("Delivery verified: "+str(deliver))
    print("SHA-256: "+digest(deliver))

if __name__=="__main__":main()
