#!/usr/bin/env python3
"""Deliver 0.4.7 with original incremental evidence, without rerunning tests."""
import hashlib
import json
import pathlib
import re
import shutil
import sys
import zipfile

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
DOWNLOADS=pathlib.Path.home()/"Downloads"
PRIVATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/deep-environment-review"
sys.path.insert(0,str(ROOT/"scripts"))
import test_evidence

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    report=json.loads((OUT/"incremental-0.4.7-results.json").read_text())
    audit=json.loads((OUT/"machine-build-checks-0.4.7.json").read_text())
    expected=[
        "I00-existing-worker-baseline","I01-tsync-raw-long-and-attestation","I02-live-short-update",
        "I03-fields-deselected-restoration","I04-master-off-restoration","I05-screenshot-file-owner-composition",
        "I06-key-request-privacy","I07-new-vector-and-error-edges","G00-original-model-display",
        "G01-default-merged-real-readings","G02-model-toggle-cancel","G03-model-display-opt-in",
        "G04-preset-preserves-on","G05-off-and-preset-restoration"]
    assert all(report["cases"][name]["status"]=="passed" for name in expected)
    assert all(report["restoration"][name] for name in [
        "originalAPKAndData","scopesAndModules","settings","adbUnrooted","emulatorShutdown"])
    inputs=json.loads((OUT/"build-inputs.json").read_text())
    assert inputs["files"]==test_evidence.source_inputs()
    products=[]
    for product in ["AppStateShield","AppStateVerifier"]:
        name=product+"-0.4.7.apk";path=OUT/name
        assert sha(path)==audit[name]["sha256"]
        assert audit[name]["signingIdentityPreserved"] and audit[name]["OEMDebugClassesExcluded"]
        assert set(audit[name]["fourABIs"])=={"arm64-v8a","armeabi-v7a","x86","x86_64"}
        assert test_evidence.payload(path)==inputs["apkPayloads"][product]
        target=DOWNLOADS/name;shutil.copyfile(path,target);products.append(target)
    for name in ["G03-model-display-opt-in","G04-preset-preserves-on","G05-off-and-preset-restoration",
                 "I07-new-vector-and-error-edges"]:
        assert report["cases"][name]["artifacts"][products[0].name]==sha(products[0])

    previous=DOWNLOADS/"AppStateShield-0.4.6-source.zip"
    changes=[]
    with zipfile.ZipFile(previous) as archive:
        old={name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
        for name,digest in inputs["files"].items():
            if old.get(name)!=digest:
                changes.append({"file":name,"previousSHA256":old.get(name),"currentSHA256":digest})
    (OUT/"process-privacy-source-comparison-0.4.7.json").write_text(
        json.dumps(changes,ensure_ascii=False,indent=2)+"\n")

    source_files=set()
    for folder in ["app/src","verifier/src","shared","gradle","scripts","docs"]:
        source_files.update(p for p in (ROOT/folder).rglob("*") if p.is_file() and
            "__pycache__" not in p.parts and p.name!=".DS_Store")
    source_files.update(ROOT/name for name in ["AGENTS.md","README.md","PROJECT-RELATIONSHIPS.md",
        "build.gradle","settings.gradle","gradle.properties","gradlew","gradlew.bat",
        "app/build.gradle","verifier/build.gradle"])
    source_files.add(ROOT/".trae/skills/android-permission-workflow/SKILL.md")
    assert not any(p.suffix in {".p12",".jks",".keystore"} or p.name in {".env","keystore-password"}
        for p in source_files)
    source=DOWNLOADS/"AppStateShield-0.4.7-source.zip"
    with zipfile.ZipFile(source,"w",zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(source_files):archive.write(p,str(p.relative_to(ROOT)))

    note=DOWNLOADS/"AppStateShield-0.4.7-实现与未覆盖原因.md"
    shutil.copyfile(ROOT/"docs/PROCESS-PRIVACY-0.4.7.md",note)
    manual=DOWNLOADS/"AppStateShield-0.4.7-人工测试手册.md"
    shutil.copyfile(ROOT/"docs/TEST-MANUAL.md",manual)
    data=DOWNLOADS/"AppStateShield-0.4.7-测试数据.json"
    data.write_text(json.dumps({
        "version":"0.4.7","newRuntimeCases":len(expected),
        "tests":report,"buildAudit":audit,"buildInputsSHA256":sha(OUT/"build-inputs.json"),
        "sourceComparison":changes,"finalAPKs":{p.name:sha(p) for p in products},
        "runtimeArchitecture":"Android 16 ARM64 / Vector / emulator-5584",
        "physicalDeviceDeployed":False,"commercialLoginVerified":False,
        "priorEvidenceRetainsOriginalArtifactHashes":True,
        "hostModelGateLog":(OUT/"model-gate-unit-0.4.7.log").read_text().strip(),
        "hostAreaCodeStageRecord":{
            "passedAsRecordedBeforeContextSwitch":True,"mutations":2000,
            "notRerun":True,"originalStdoutAvailableInDelivery":False,
            "sourceSHA256":{name:sha(ROOT/name) for name in
                ["shared/native/property-area.h","shared/native/code-view.h","shared/test/AreaCodeTest.cpp"]}}
        },ensure_ascii=False,indent=2)+"\n")
    image=DOWNLOADS/"AppStateShield-0.4.7-机型分类.png"
    shutil.copyfile(OUT/"model-system-merged-0.4.7.png",image)
    sums=DOWNLOADS/"AppStateShield-0.4.7-SHA256SUMS.txt"
    members=products+[source,note,manual,data,image]
    sums.write_text("".join(sha(p)+"  "+p.name+"\n" for p in members))

    evidence=set(OUT.glob("incremental*0.4.7.log"))|set(OUT.glob("model-gate*0.4.7.log"))
    evidence|=set(OUT.glob("build-0.4.7*.log"))|set(OUT.glob("signing*0.4.7.log"))
    evidence|={OUT/"incremental-0.4.7-results.json",OUT/"build-inputs.json",
        OUT/"machine-build-checks-0.4.7.json",OUT/"build-audit-0.4.7.log",
        OUT/"process-privacy-source-comparison-0.4.7.json"}
    # Explicit public source allowlist; never include private state or key files.
    research={}
    for folder in ["aosp-bionic","aosp-framework"]:
        for p in (PRIVATE/"sources"/folder).rglob("*"):
            if p.is_file():research["research/0.4.7/sources/"+str(p.relative_to(PRIVATE/"sources"))]=p
    for name in ["linux-seccomp.c","linux-seccomp.source.json"]:
        research["research/0.4.7/sources/"+name]=PRIVATE/"sources"/name
    for label,folder in [
        ("initial",DOWNLOADS/"AppStateShield-environment-research-20261114"),
        ("deep-review",DOWNLOADS/"AppStateShield-deep-review-research-20261114")]:
        for p in folder.rglob("*"):
            if p.is_file() and ("sources" in p.relative_to(folder).parts or p.suffix in {".md",".json"}):
                research["research/"+label+"/"+str(p.relative_to(folder))]=p
    index={"sha256":{name:sha(p) for name,p in sorted(research.items())}}
    bundle=DOWNLOADS/"AppStateShield-0.4.7-delivery.zip"
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as archive:
        for p in members+[sums]:archive.write(p,p.name)
        for p in sorted(evidence):
            if p.is_file():archive.write(p,"evidence/"+p.name)
        for name,p in sorted(research.items()):archive.write(p,name)
        archive.writestr("research/source-index-0.4.7.json",json.dumps(index,ensure_ascii=False,indent=2)+"\n")
    for p in [source,bundle]:
        with zipfile.ZipFile(p) as archive:assert archive.testzip() is None
    with zipfile.ZipFile(bundle) as archive:
        for p in members:
            assert hashlib.sha256(archive.read(p.name)).hexdigest()==sha(p)
        assert not any(re.search(r"(^|/)(release\.p12|keystore-password|state\.json)$",n)
            for n in archive.namelist())
    manifest={"artifacts":{p.name:{"bytes":p.stat().st_size,"sha256":sha(p)} for p in members+[sums,bundle]},
        "runtimeCases":len(expected),"publicSourceFiles":len(research),"restoration":report["restoration"]}
    (OUT/"delivery-0.4.7-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
