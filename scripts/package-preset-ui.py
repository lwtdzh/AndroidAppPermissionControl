#!/usr/bin/env python3
"""Package small editor updates; no runtime tests or phone actions."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DOWNLOADS=pathlib.Path.home()/"Downloads"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cert(path):
    result=subprocess.check_output([
        "/opt/homebrew/share/android-commandlinetools/build-tools/36.0.0/apksigner",
        "verify","--print-certs",str(path)],text=True,
        env=dict(os.environ,JAVA_HOME="/opt/homebrew/opt/openjdk@17"))
    return re.findall(r"certificate SHA-256 digest: ([0-9a-f]+)",result)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",choices=["0.4.8","0.4.9","0.4.10"],default="0.4.8")
    version=parser.parse_args().version
    assert 'versionName "'+version+'"' in (ROOT/"app/build.gradle").read_text()
    apk=OUT/("AppStateShield-"+version+".apk");old=OUT/"AppStateShield-0.4.7.apk"
    assert cert(apk)==cert(old) and cert(apk)
    with zipfile.ZipFile(apk) as current,zipfile.ZipFile(old) as previous:
        names={n for n in current.namelist() if n.startswith("lib/") and n.endswith(".so")}
        old_names={n for n in previous.namelist() if n.startswith("lib/") and n.endswith(".so")}
        assert names==old_names and all(current.read(n)==previous.read(n) for n in names)
        assert {n.split("/")[1] for n in names}=={"arm64-v8a","armeabi-v7a","x86","x86_64"}
    issues=ET.parse(ROOT/"app/build/reports/lint-results-release.xml").getroot().findall("issue")
    assert not any(i.get("severity") in {"Fatal","Error"} for i in issues)
    target=DOWNLOADS/apk.name;shutil.copyfile(apk,target)
    files=set()
    for folder in ["app/src","verifier/src","shared","gradle","scripts","docs"]:
        files.update(p for p in (ROOT/folder).rglob("*") if p.is_file() and
            "__pycache__" not in p.parts and p.name!=".DS_Store")
    files.update(ROOT/n for n in ["AGENTS.md","README.md","PROJECT-RELATIONSHIPS.md",
        "build.gradle","settings.gradle","gradle.properties","gradlew","gradlew.bat",
        "app/build.gradle","verifier/build.gradle"])
    source=DOWNLOADS/("AppStateShield-"+version+"-source.zip")
    with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(files):
            assert p.suffix not in {".p12",".jks",".keystore"} and p.name not in {".env","keystore-password"}
            archive.write(p,str(p.relative_to(ROOT)))
    note=DOWNLOADS/("AppStateShield-"+version+"-更新说明.md")
    notes={"0.4.8":"""# 0.4.8：机型预设归入机型与系统

小米 14、vivo X200 Pro mini 的预设选择已移入“机型与系统”，位于这一节的总开关下方，分类展开后显示。顶部不再显示机型预设名称和选择入口。

更换预设只更新机型、系统和屏幕参数，保留设备标识、网络、位置、其他环境字段和各总开关。保存后生效。机型总开关继续默认关闭。
""","0.4.9":"""# 0.4.9：统一刷新只放在对应分类

顶部“更新随机标识”及其跨分类刷新操作已移除。设备标识、网络与基站、机型与系统各自保留统一刷新按钮，每个按钮只更新所在分类。

单项刷新、保存和开关规则保持原样。刷新完成后仍需保存才生效。
""","0.4.10":"""# 0.4.10：按预设机型填写参数

“机型与系统”中的预设选择和机型刷新合并为“按预设机型填写参数”一个按钮。按钮显示当前预设；点击后选择小米 14 或 vivo X200 Pro mini，确认后填写下方机型、系统和屏幕参数。

填写只更新本分类，其他参数和各总开关保留，保存后生效。设备标识与网络的统一刷新保持原样。
"""}
    note.write_text(notes[version]+"\n模块版本 "+version+"，验证器保持 0.4.7。构建和签名检查完成，四 ABI 原生库与 0.4.7 完全一致；未运行验证器或真机测试。\n")
    members=[target,source,note]
    sums=DOWNLOADS/("AppStateShield-"+version+"-SHA256SUMS.txt")
    sums.write_text("".join(sha(p)+"  "+p.name+"\n" for p in members))
    bundle=DOWNLOADS/("AppStateShield-"+version+"-delivery.zip")
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as archive:
        for p in members+[sums]:archive.write(p,p.name)
    for p in [source,bundle]:
        with zipfile.ZipFile(p) as archive:assert archive.testzip() is None
    record={"moduleVersion":version,"verifierVersion":"0.4.7","signingIdentityPreserved":True,
        "nativeLibrariesUnchanged":True,"runtimeTestsRun":False,
        "artifacts":{p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in members+[sums,bundle]}}
    (OUT/("preset-ui-"+version+"-build.json")).write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(record,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
