#!/usr/bin/env python3
"""Deliver the specific 0.4.1 fix with current evidence and unchanged historical reports."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import zipfile
from test_evidence import source_inputs

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DEST=pathlib.Path.home()/"Downloads"
VERSION="0.4.1"
CASES=["U01-install-default","U02-home-timer-and-pause","U03-detail-directory-search",
       "U04-editor-preset-and-cancel","U05-row-random-selects","U06-enable-manual-update-disable",
       "U07-legacy-entry-switch","U08-visible-active-IMEI"]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    report=json.loads((OUT/"requirement-ui-0.4.1-results.json").read_text())
    build=OUT/"build-inputs.json";inputs=json.loads(build.read_text())
    assert inputs["files"]==source_inputs(),"Source changed after build"
    for name in CASES:
        row=report["cases"][name]
        assert row["status"]=="passed" and row["artifacts"]==report["artifacts"],"Missing final check: "+name
        assert row.get("buildInputsSHA256")==sha(build),"Case source binding differs: "+name
    assert all(report["restoration"].get(k) for k in [
        "originalAPKBytes","completeDataSnapshotRestored","modulesAndScopes","settings",
        "adbUnrooted","dedicatedEmulatorShutdownAccepted"])
    audit=json.loads((OUT/"machine-build-checks-0.4.1.json").read_text())
    for name in report["artifacts"]:
        assert sha(OUT/name)==report["artifacts"][name]==audit[name]["sha256"]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        assert len(audit[name]["fourABIs"])==4
        shutil.copy2(OUT/name,DEST/name)
    original=DEST/"AppStateShield-0.4.0-source.zip"
    paths=[]
    for folder in ["app/src/main/java","app/src/main/cpp","shared"]:
        paths.extend(p for p in (ROOT/folder).rglob("*") if p.is_file() and not p.name.startswith(".")
                     and p.name!="DeviceSettingsActivity.java")
    paths.extend(ROOT/p for p in [
        "verifier/src/main/java/io/github/lwtdzh/screenshotdetector/DeviceRead.java",
        "verifier/src/main/cpp/machineprobe.cpp"])
    with zipfile.ZipFile(original) as archive:
        for path in paths:
            assert archive.read(str(path.relative_to(ROOT)))==path.read_bytes(),"Unexpected runtime change: "+str(path)
    proof={"historicalSourceArchiveSHA256":sha(original),"unchangedRuntimeFiles":len(paths),
           "historicalAPKHashes":{
               name:sha(DEST/name) for name in ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk"]},
           "historicalCasesNotRelabeledOrRerun":True}
    report["historicalComparison"]=proof
    (OUT/"requirement-ui-0.4.1-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    report_file=DEST/"AppStateShield-0.4.1-复盘与验证.md"
    times=sum(report["cases"][k]["durationSeconds"] for k in CASES)
    text=(ROOT/"docs/REQUIREMENT-AUDIT-0.4.1.md").read_text()
    text+="\n## 本次实际验证\n\n"
    text+=f"正式 APK 的 8 个定向用例全部通过，累计用例执行时间 {times:.1f} 秒。平台为专用 Android 16 / API 36 / ARM64 / Vector 模拟器。未重新执行旧六项的 64 组合。\n\n"
    text+="| 用例 | 结果 | 秒 |\n|---|---|---:|\n"
    for name in CASES:text+=f"| {name} | 通过 | {report['cases'][name]['durationSeconds']:.3f} |\n"
    text+="\n首页、详情、旧状态页均可看到标识入口；IMEI 开启及修改后实际接口返回公共测试号码，首页和详情显示一致。关闭后恢复原值或原错误。两秒自动采样、后台暂停、同 PID 更新和页面切换后电话辅助进程返回均通过。\n\n"
    text+=f"对照 0.4.0 源码归档，{len(paths)} 个模块 Hook、共享字段及读取文件逐字节相同。原 64 组合及 46 字段还原结果保留原版本、原 APK 指纹；它们属于历史记录。电话解绑顺序和展示采样改变，本次另行检查。\n\n"
    text+="两个正式 APK 均通过签名身份、四 ABI 编译产物、debug 夹具排除及 lint 检查（0 个错误）。四 ABI 编译不等于四 ABI 运行。模拟器已恢复原模块/作用域、配置、安全模式、原包安装状态，ADB 已取消 root，专用模拟器已关闭。\n\n"
    text+="本轮保留的执行问题：最初测试未启用专用模拟器 ADB root，准备阶段没有开始应用用例；预设检查曾把 XML 叶节点当布尔值导致执行器误报，改为显式判断节点存在后只续跑剩余用例；显示对照曾在配置轮询完成前读到旧结果，执行器改为等待已保存 revision 后检查。构建期间的两个布局常量 lint 错误已修复。原失败条目和执行日志保留，未隐去。\n\n"
    text+="厂商 OAID、真实 SIM/基站、硬件认证和不同 ROM 的读取限制仍按原复盘表说明；模拟器夹具不能当作这些真实服务的验证。\n"
    report_file.write_text(text)
    copies={
        "docs/TEST-MANUAL.md":"AppStateShield-0.4.1-人工测试手册.md",
        "verification/requirement-ui-0.4.1-results.json":"AppStateShield-0.4.1-测试数据.json",
    }
    for source,name in copies.items():shutil.copy2(ROOT/source,DEST/name)
    files=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard"],cwd=ROOT,text=True).splitlines()
    sourcezip=DEST/"AppStateShield-0.4.1-source.zip"
    with zipfile.ZipFile(sourcezip,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(files)):
            path=ROOT/name
            if not path.is_file() or name.startswith("verification/"):continue
            if path.suffix in {".apk",".zip",".tar",".p12",".env"}:continue
            archive.write(path,name)
        for name in ["build-inputs.json","requirement-ui-0.4.1-results.json","requirement-ui-0.4.1.log",
                     "machine-build-checks-0.4.1.json","build-0.4.1.log"]:
            archive.write(OUT/name,"verification/"+name)
    names=list(report["artifacts"])+[report_file.name,copies["docs/TEST-MANUAL.md"],
        copies["verification/requirement-ui-0.4.1-results.json"],sourcezip.name]
    sums=DEST/"AppStateShield-0.4.1-SHA256SUMS.txt"
    sums.write_text("".join(sha(DEST/name)+"  "+name+"\n" for name in names))
    package=DEST/"AppStateShield-0.4.1-delivery.zip"
    with zipfile.ZipFile(package,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in names+[sums.name]:archive.write(DEST/name,name)
        for path in sorted(OUT.glob("requirement-*-0.4.1.png")):archive.write(path,"screenshots/"+path.name)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        for name in names:assert hashlib.sha256(archive.read(name)).hexdigest()==sha(DEST/name)
    print(json.dumps({"package":str(package),"sha256":sha(package),"casesPassed":len(CASES),
                      "caseSeconds":round(times,3),"unchangedRuntimeFiles":len(paths)},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
