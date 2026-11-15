#!/usr/bin/env python3
"""Only 0.4.7 new paths on the dedicated AVD. Explicit stages preserve failures."""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("incremental_machine",ROOT/"scripts/machine-test.py")
machine=importlib.util.module_from_spec(spec);spec.loader.exec_module(machine)
machine.STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/incremental-0.4.7"
machine.REPORT=ROOT/"verification/incremental-0.4.7-results.json"
machine.PACKAGES=(machine.MODULE,machine.A)
run=machine.Run();run.budget_seconds=180
d=run.d;A=machine.A
activity=A+"/io.github.lwtdzh.screenshotdetector.IncrementalProbeActivity"
output="/data/user/0/"+A+"/files/incremental-result.json"

def probe(model,fingerprint,keys=False,cold=False,revision=-1):
    if cold:d.shell("am","force-stop",A)
    d.shell("rm","-f",output)
    d.shell("am","start","-W","--activity-single-top","--activity-clear-top","-n",activity,
        "--es","model",model,"--es","fingerprint",fingerprint,"--ez","keys",str(keys).lower(),"--el","revision",str(revision))
    def ready():
        raw=d.shell("sh","-c","test ! -f "+output+" || cat "+output)
        try:return json.loads(raw) if raw else None
        except ValueError:return None
    value=run.wait(ready,"New native probe did not finish",timeout=25)
    assert "error" not in value,value
    return value

def property_checks(value):
    assert len(value["properties"])>=2,value
    assert all(all(row[key] for key in ["libcRead","libcMmap","inlineRead","inlineMmap",
        "cachedFdInlineRead","cachedFdInlineMmap"]) for row in value["properties"]),value
    assert all(value["ordinary"].values()),value

def previous(stage):
    return run.report["cases"][stage]["evidence"]["observation"]

def expected_profile(long=True,enabled=True,selected=True):
    fingerprint=("incremental/product/device:16/TEST047/"+("7"*78)+":user/release-keys") if long else (
        "incremental/product/device:16/T047/123456:user/release-keys")
    values={"model":"Incremental Device 047","fingerprint":fingerprint,"brand":"incremental",
        "manufacturer":"incremental","device":"device","product":"product"}
    return {"schema":1,"enabled":enabled,"modelEnabled":True,"preset":"custom","values":values,
        "selected":list(values) if selected else [],"networkMode":"off","locationEnabled":False}

def stage(name):
    if name=="save-keystore":
        observed=json.loads(d.shell("cat",output))
        keys=observed["keystore"]
        assert keys["ordinarySignVerify"] and keys["normalCertificateKeyMatches"]
        assert keys["attestationGenerated"] and keys["challengePreserved"] and keys["chainSignaturesUnmodified"]
        assert observed["module"]["deviceAttestationIdsRemoved"]==5
        sources=["shared/java/io/github/lwtdzh/deviceprofile/AttestationPrivacy.java",
            "shared/java/io/github/lwtdzh/deviceprofile/DeviceProfile.java",
            "app/src/main/java/io/github/lwtdzh/appstateshield/AttestationHooks.java"]
        run.case("I06-key-request-privacy",lambda:{"observation":keys,"removedTags":5,
            "sourceSHA256":{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}})
    elif name=="setup":
        if not (machine.STATE/"state.json").exists():run.capture()
        for pkg,apk in [(machine.MODULE,"AppStateShield-0.4.7.apk"),(A,"Verifier-A-0.4.7.apk")]:
            path=ROOT/"verification"/apk;d.adb("install","--no-incremental","-r",str(path))
            remote=d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
            assert d.shell("sha256sum",remote).split()[0]==hashlib.sha256(path.read_bytes()).hexdigest()
        run.report["artifacts"]={name:hashlib.sha256((ROOT/"verification"/name).read_bytes()).hexdigest()
            for name in ["AppStateShield-0.4.7.apk","Verifier-A-0.4.7.apk"]}
        for module in d.cli("modules","ls"):d.scope(module["PACKAGE"],A,False)
        d.cli("modules","enable",machine.MODULE);d.scope(machine.MODULE,A,True)
        d.shell("settings","put","global","hidden_api_policy","1")
        d.batch_policy(A,set());d.batch_profile(A,expected_profile(enabled=False))
        realModel=d.shell("getprop","ro.product.model");realFingerprint=d.shell("getprop","ro.build.fingerprint")
        observed=probe(realModel,realFingerprint,keys="baselineKeystore" not in run.report,cold=True)
        if "baselineKeystore" in run.report:observed["keystore"]=run.report["baselineKeystore"]
        property_checks(observed)
        assert observed["module"]["injected"] and not observed["module"]["deviceEnabled"],observed
        assert observed["keystore"]["ordinarySignVerify"] and observed["keystore"]["normalCertificateKeyMatches"]
        run.case("I00-existing-worker-baseline",lambda:{"observation":observed,"actualUIDNative":True})
    elif name in {"enabled","short","deselected","off"}:
        profile=expected_profile(long=name=="enabled",enabled=name!="off",selected=name!="deselected")
        written=d.batch_profile(A,profile)
        # Wait by the published revision, not by launching old broad samplers.
        if name in {"deselected","off"}:
            model=d.shell("getprop","ro.product.model");fingerprint=d.shell("getprop","ro.build.fingerprint")
        else:model=profile["values"]["model"];fingerprint=profile["values"]["fingerprint"]
        reused=run.report["cases"].get("I06-key-request-privacy",{}).get("evidence")
        if reused:
            assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==digest
                for n,digest in reused["sourceSHA256"].items())
        observed=probe(model,fingerprint,keys=name=="enabled" and not reused,revision=written["revision"])
        assert observed["module"].get("deviceRevision")==written["revision"],observed
        property_checks(observed)
        baseline=previous("I00-existing-worker-baseline")
        assert observed["pid"]==baseline["pid"] and observed["workerTid"]==baseline["workerTid"],observed
        if name in {"enabled","short"}:
            assert observed["module"]["deviceSyscallView"]==1,observed
            assert all(observed["code"][key] for key in [
                "available","apiMatchesDisk","inlineMatchesDisk","executableRemainsHooked"]),observed
        else:
            assert all(row["cachedAreaSubstituted"] for row in observed["properties"]),observed
        if name=="enabled":
            if reused:observed["keystoreEvidenceReused"]="I06-key-request-privacy"
            else:
                assert observed["keystore"]["ordinarySignVerify"] and observed["keystore"]["normalCertificateKeyMatches"],observed
                assert observed["module"]["deviceAttestationIdsRemoved"]>0,observed
        case={"enabled":"I01-tsync-raw-long-and-attestation","short":"I02-live-short-update",
            "deselected":"I03-fields-deselected-restoration","off":"I04-master-off-restoration"}[name]
        run.case(case,lambda:{"observation":observed,"sameProcessAndPreexistingThread":True})
    elif name=="screenshot":
        path=ROOT/"verification/AppStateShield-0.4.7.apk"
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        remote=d.shell("pm","path",machine.MODULE).splitlines()[0].removeprefix("package:")
        if d.shell("sha256sum",remote).split()[0]!=digest:d.adb("install","--no-incremental","-r",str(path))
        run.report["artifacts"][path.name]=digest
        profile=expected_profile(long=False);d.batch_profile(A,profile);d.batch_policy(A,{"screenshot"})
        observed=probe(profile["values"]["model"],profile["values"]["fingerprint"],cold=True)
        property_checks(observed)
        assert observed["module"]["enabled"]==["screenshot"],observed
        assert all(observed["code"][key] for key in [
            "available","apiMatchesDisk","inlineMatchesDisk","executableRemainsHooked"]),observed
        run.case("I05-screenshot-file-owner-composition",lambda:{"observation":observed,"newFileAdapterComposition":True})
    elif name=="edges":
        # A separate JNI entry runs only new vector/error/position cases.
        profile=expected_profile(long=False)
        written=d.batch_profile(A,profile);d.batch_policy(A,set())
        d.shell("am","force-stop",A);d.shell("rm","-f",output)
        d.shell("am","start","-W","-n",activity,"--ez","edges","true",
            "--es","model",profile["values"]["model"],"--el","revision",str(written["revision"]))
        def ready():
            raw=d.shell("sh","-c","test ! -f "+output+" || cat "+output)
            try:return json.loads(raw) if raw else None
            except ValueError:return None
        observed=run.wait(ready,"New I/O edges did not finish",timeout=20)
        assert "error" not in observed,observed
        keys=["rawReadvSelected","rawPreadv2Selected","rawPreadv2CurrentOffset","preadvKeepsPosition",
            "independentOpenPosition","invalidBufferPreservesErrorAndOffset","oPathReadError",
            "writeSharedMapDenied","iovLimitError","vectorEOF"]
        assert all(observed[key] for key in keys),observed
        run.case("I07-new-vector-and-error-edges",lambda:{"observation":observed,
            "newAssertions":len(keys),"oldNativeChecksSkipped":True})
    elif name=="restore":
        original=json.loads((machine.STATE/"state.json").read_text())
        # Remove new fixture files before extracting original private data.
        for pkg in original["packages"]:
            d.shell("am","force-stop",pkg)
            d.shell("rm","-f","/data/user/0/"+pkg+"/files/incremental-result.json",
                "/data/user/0/"+pkg+"/files/incremental-control")
        run.restore()
        assert d.cli("modules","ls")==original["modules"]
        run.report["restoration"]={"originalAPKAndData":True,"scopesAndModules":True,"settings":True}
        d.adb("unroot");d.adb("wait-for-device",timeout=15);assert d.shell("id","-u")=="2000"
        assert "OK" in d.adb("emu","kill")
        run.report["restoration"].update(adbUnrooted=True,emulatorShutdown=True)
    else:raise ValueError(name)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("stage",
        choices=["save-keystore","setup","enabled","short","deselected","off","screenshot","edges","restore"])
    args=parser.parse_args()
    try:stage(args.stage)
    finally:machine.REPORT.write_text(json.dumps(run.report,ensure_ascii=False,indent=2)+"\n")
