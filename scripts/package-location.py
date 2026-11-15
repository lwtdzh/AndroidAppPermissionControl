#!/usr/bin/env python3
"""Package 0.4.2 only after current artifacts, selected cases and restoration pass."""
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import zipfile
from test_evidence import source_inputs

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DEST=pathlib.Path.home()/"Downloads"
VERSION="0.4.2"
CASES=["L01-default-and-baseline","L02-region-UI-draft-save","L03-location-three-gates",
       "N01-present-SIM-coherence","N02-no-SIM-and-real-restoration","R01-category-refresh"]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    report=json.loads((OUT/"location-ui-0.4.2-results.json").read_text())
    build=OUT/"build-inputs.json";inputs=json.loads(build.read_text())
    assert inputs["files"]==source_inputs(),"Build no longer matches source"
    for name in CASES:
        row=report["cases"][name]
        assert row["status"]=="passed",name
        assert row["artifacts"]==report["artifacts"],"Final APK case missing: "+name
        if row.get("buildInputsSHA256")!=sha(build):
            prior=OUT/("location-build-inputs-"+row["buildInputsSHA256"]+".json")
            assert prior.exists() and sha(prior)==row["buildInputsSHA256"],"Original case source binding missing"
            previous=json.loads(prior.read_text())
            assert previous["apkPayloads"]==inputs["apkPayloads"],"Case APK contents differ"
            changed={p for p in set(inputs["files"])|set(previous["files"])
                     if inputs["files"].get(p)!=previous["files"].get(p)}
            assert name in {"L01-default-and-baseline","L02-region-UI-draft-save","L03-location-three-gates","N01-present-SIM-coherence"} and changed<={
                "scripts/location-ui-test.py"},"Observed behavior was changed after passing case"
            report.setdefault("evidenceReuse",{})[name]={
                "reason":"同一 APK 字节及运行源码；执行器修正其他步骤的位置开关、连续采样比较、无服务占位注册项和分类搜索。已通过的实际读取断言保持不变。",
                "originalBuildInputsSHA256":row["buildInputsSHA256"],"changedFiles":sorted(changed)}
    assert all(report["restoration"].get(key) for key in [
        "originalAPKBytes","completeDataSnapshotRestored","modulesAndScopes","settings",
        "adbUnrooted","dedicatedEmulatorShutdownAccepted"])
    restored=report["cases"]["D18-restored"]
    assert restored["status"]=="passed" and restored["startedAtUTC"]>=max(
        report["cases"][name]["startedAtUTC"] for name in CASES),"Final restoration missing"
    (OUT/"location-ui-0.4.2-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    audit=json.loads((OUT/"machine-build-checks-0.4.2.json").read_text())
    for name,value in report["artifacts"].items():
        assert sha(OUT/name)==value==audit[name]["sha256"]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        assert len(audit[name]["fourABIs"])==4
        shutil.copy2(OUT/name,DEST/name)
    duration=sum(report["cases"][name]["durationSeconds"] for name in CASES)
    text=(ROOT/"docs/LOCATION-0.4.2.md").read_text()
    text+="\n## 本次实际结果\n\n"
    text+=f"正式 APK 的 {len(CASES)} 项定向用例全部通过，累计用例时间 {duration:.1f} 秒。运行平台为专用 Android 16 / API 36 / ARM64 / Vector 模拟器。四 ABI 编译、签名身份、正式包不含 debug 夹具和 lint 零错误均通过；其他 ABI 和厂商 ROM 未做本轮运行验证。\n\n"
    text+="| 用例 | 结果 | 秒 |\n|---|---|---:|\n"
    for name in CASES:text+=f"| {name} | 通过 | {report['cases'][name]['durationSeconds']:.3f} |\n"
    text+="\nSIM 与订阅、运营商、网络注册、同步/异步小区和 Parcel 的实际读取均核对，含有卡、无卡、不模拟以及机器总开关关闭。地区草稿、取消、旋转、单项修改和三层开关通过。旧六项策略的 64 组合未重新执行，历史结果保留原 APK 指纹，不作为本轮 APK 的全量测试声明。\n\n"
    text+="模拟器的原应用安装状态、数据、模块/作用域、系统设置与安全模式已恢复，ADB 已取消 root，专用模拟器已关闭。此次没有安装到 vivo，也没有提交、推送或发布。\n\n"
    text+="单元检查记录：\n\n"+(OUT/"location-unit-0.4.2.log").read_text()+"\n"
    failures={key:value for key,value in report.get("previousRuns",{}).items()
              if any(row.get("status")=="failed" for row in value)}
    text+="运行过程中保留的失败记录："+("无应用用例失败。" if not failures else
        "详见测试数据 previousRuns："+", ".join(failures)+"。修复后仅续跑相应用例。")+"\n"
    text+="构建阶段曾修复隐藏 SDK 常量/方法的编译错误和异步回调的 API 版本检查，原失败日志随源码保留。真实基站库、厂商 OAID、不同 ROM 的隐藏接口兼容性及硬件认证仍有前文所列限制。\n"
    report_file=DEST/f"AppStateShield-{VERSION}-位置与网络验证.md";report_file.write_text(text)
    manual=DEST/f"AppStateShield-{VERSION}-人工测试手册.md";shutil.copy2(ROOT/"docs/TEST-MANUAL.md",manual)
    data=DEST/f"AppStateShield-{VERSION}-测试数据.json";shutil.copy2(OUT/"location-ui-0.4.2-results.json",data)
    files=subprocess.check_output(["git","ls-files","--cached","--others","--exclude-standard"],cwd=ROOT,text=True).splitlines()
    source=DEST/f"AppStateShield-{VERSION}-source.zip"
    with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(files)):
            path=ROOT/name
            if not path.is_file() or name.startswith("verification/") or path.suffix in {".apk",".zip",".tar",".p12",".env",".pyc"}:continue
            archive.write(path,name)
        for name in ["build-inputs.json","location-ui-0.4.2-results.json","location-ui-0.4.2.log",
                     "location-unit-0.4.2.log","machine-build-checks-0.4.2.json","build-0.4.2.log",
                     "build-0.4.2-compile-failure.log","build-0.4.2-verifier-compile-failure.log","build-0.4.2-lint-failure.log"]:
            if (OUT/name).exists():archive.write(OUT/name,"verification/"+name)
        if (OUT/"build-0.4.2-verifier-lint-failure.log").exists():
            archive.write(OUT/"build-0.4.2-verifier-lint-failure.log","verification/build-0.4.2-verifier-lint-failure.log")
        for path in OUT.glob("location-build-inputs-*.json"):archive.write(path,"verification/"+path.name)
    names=list(report["artifacts"])+[report_file.name,manual.name,data.name,source.name]
    sums=DEST/f"AppStateShield-{VERSION}-SHA256SUMS.txt"
    sums.write_text("".join(sha(DEST/name)+"  "+name+"\n" for name in names))
    package=DEST/f"AppStateShield-{VERSION}-delivery.zip"
    with zipfile.ZipFile(package,"w",zipfile.ZIP_DEFLATED) as archive:
        for name in names+[sums.name]:archive.write(DEST/name,name)
        for image in sorted(OUT.glob("location-*-0.4.2.png")):archive.write(image,"screenshots/"+image.name)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        for name in names:assert hashlib.sha256(archive.read(name)).hexdigest()==sha(DEST/name)
    print(json.dumps({"package":str(package),"sha256":sha(package),"casesPassed":len(CASES),
                      "caseSeconds":round(duration,3)},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
