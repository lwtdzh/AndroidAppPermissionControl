#!/usr/bin/env python3
"""Selected 0.4.5 checks, only on the dedicated AVD; retain completed cases."""
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/environment-0.4.5"
spec=importlib.util.spec_from_file_location("environment_ui",ROOT/"scripts/requirement-ui-test.py")
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
import test_device
FOREIGN=ui.PRIMARY+".foreignprobe"
test_device.TEST_TARGETS.add(FOREIGN)
ui.machine.STATE=STATE
ui.machine.REPORT=OUT/"environment-0.4.5-results.json"
ui.machine.PACKAGES=(ui.MODULE,ui.PRIMARY,ui.machine.A,FOREIGN)
MODEL=["brand","manufacturer","model","device","product","board","hardware","release","incremental","fingerprint"]

class Audit(ui.Audit):
    def revision_read(self,profile,pkg=ui.PRIMARY):
        return self.wait(lambda:self.current(profile,pkg),"Revision did not reach actual reader",timeout=12)
    def current(self,profile,pkg):
        value=self.read(pkg)
        return value if value["module"].get("deviceRevision")==profile["revision"] else None
    def prepare_selected(self):
        if not (STATE/"state.json").exists():self.capture()
        files={ui.MODULE:"AppStateShield-0.4.5.apk",ui.PRIMARY:"AppStateVerifier-0.4.5.apk",
               ui.machine.A:"Verifier-A-0.4.5.apk",FOREIGN:"Verifier-Foreign-0.4.5.apk"}
        self.report["artifacts"]={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in files.values()}
        packages=set(self.d.shell("pm","list","packages").splitlines())
        for pkg,name in files.items():
            current=self.d.shell("pm","path",pkg) if "package:"+pkg in packages else ""
            installed=(self.d.shell("sha256sum",current.splitlines()[0].removeprefix("package:")).split()[0]
                       if current else None)
            if installed!=self.report["artifacts"][name]:
                if pkg==ui.machine.A and installed==hashlib.sha256(
                    (ROOT/"verifier/build/outputs/apk/sampleA/debug/verifier-sampleA-debug.apk").read_bytes()).hexdigest():
                    self.d.adb("uninstall",pkg)
                self.d.adb("install","--no-incremental","-r",str(OUT/name))
            remote=self.d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
            assert self.d.shell("sha256sum",remote).split()[0]==self.report["artifacts"][name],pkg
        if not (STATE/"locales.json").exists():
            original=json.loads((STATE/"state.json").read_text())
            locales={pkg:re.search(r"\[([^\]]*)\]",self.d.shell("cmd","locale","get-app-locales",pkg)).group(1)
                     for pkg in original["packages"]}
            (STATE/"locales.json").write_text(json.dumps(locales))
            (STATE/"locales.json").chmod(0o600)
        for row in self.d.cli("modules","ls"):
            for pkg in [ui.PRIMARY,ui.machine.A,FOREIGN]:self.d.scope(row["PACKAGE"],pkg,False)
        self.d.cli("modules","enable",ui.MODULE)
        for pkg in [ui.PRIMARY,ui.machine.A,FOREIGN]:
            self.d.scope(ui.MODULE,pkg,True);self.d.batch_policy(pkg,set())
        self.d.shell("settings","put","global","hidden_api_policy","1")
        self.d.shell("cmd","locale","set-app-locales",ui.MODULE,"--locales","zh-CN")
        self.input_metadata=ui.case_inputs(self.d,self.report["artifacts"])
        self.input_metadata["executorSHA256"]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
        assert self.input_metadata.get("buildInputsSHA256"),"Build provenance missing"
    def off_document(self):
        return {"schema":1,"enabled":False,"preset":"custom","values":{},"selected":[],"networkMode":"off"}
    def metadata(self,sample,profile):
        java=sample["reads"]["metadata_properties"]["value"]
        native=sample["reads"]["native"]["value"]["properties"]
        fingerprints=sample["reads"]["java_properties"]["value"]
        assert sample["reads"]["fingerprint"]["value"]==profile["values"]["fingerprint"]
        for part in ["","system.","system_ext.","vendor.","product.","odm."]:
            prefix="ro."+part+"build."
            f=fingerprints[prefix+"fingerprint"]
            paths=native[prefix+"fingerprint"]
            for method,actual in paths.items():
                if actual is not None:
                    expected=f if method=="callback" or len(f.encode())<=91 else "Must use __system_property_read_callback() to read"
                    assert actual==expected,(prefix,method,actual,expected)
            control=sample["reads"]["native"]["value"]["legacyControls"][prefix+"fingerprint"]
            assert control["buffersIntact"]
            for method in ["get","read","nullName"]:
                buffer=control.get(method+"Bytes")
                if buffer is not None:
                    full=bytes.fromhex(buffer)
                    assert len(full)==92
                    assert full[len(full.split(b"\0",1)[0]):]==bytes(92-len(full.split(b"\0",1)[0]))
            left,tail=f.rsplit(":",1);id=left.split("/")[-2];kind,tags=tail.split("/")
            for field,value in [("id",id),("type",kind),("tags",tags)]:
                key=prefix+field
                assert java[key]==value,(key,java[key],value)
                for method,actual in native[key].items():
                    # Missing stock properties have no prop_info for deprecated read/callback.
                    if actual is not None:assert actual==value,(key,method,actual,value)
        root=profile["values"]["fingerprint"].split(":")
        static=sample["reads"]["build_metadata"]["value"]
        assert static["id"]==root[1].split("/")[-2]
        assert static["type"]==root[2].split("/")[0] and static["tags"]==root[2].split("/")[1]
        assert static["sdk"]==self.baseline["reads"]["build_metadata"]["value"]["sdk"]
    def capacity(self,sample,profile):
        mem=sample["reads"]["memory_view"]["value"];fs=sample["reads"]["storage_view"]["value"]
        total=int(profile["values"]["total_ram"])<<30
        assert mem["total"]==total and 0<=mem["available"]<=total and 0<=mem["threshold"]<=total
        target=int(profile["values"]["storage"])<<30
        assert fs["total"]==fs["blocks"]*fs["blockSize"]==target
        assert 0<=fs["available"]<=fs["free"]<=fs["total"]
        assert fs["available"]==fs["availableBlocks"]*fs["blockSize"]
        assert fs["free"]==fs["freeBlocks"]*fs["blockSize"]
        assert fs["blocks32"]==fs["blocks"] and fs["freeBlocks32"]==fs["freeBlocks"]
        assert fs["availableBlocks32"]==fs["availableBlocks"]
        assert fs["fileTotal"]==target and 0<=fs["fileUsable"]<=fs["fileFree"]<=target
        assert fs["systemTotal"]==self.baseline["reads"]["storage_view"]["value"]["systemTotal"]
        assert sample["reads"]["ordinary"]["value"]["file"]=="ordinary-device-control"
    def run_selected(self):
        d=self.d
        def baseline():
            d.batch_profile(ui.PRIMARY,self.off_document());value=self.read(cold=True)
            assert value["module"]["injected"] and not value["module"]["deviceEnabled"]
            assert value["module"]["deviceHooks"]==0 and not value["module"]["deviceNative"]
            return {"observed":value,"neverEnabledDeviceHooks":0,"actualReads":True}
        self.case("E01-never-enabled-baseline",baseline)
        self.baseline=self.report["cases"]["E01-never-enabled-baseline"]["evidence"]["observed"]
        def enabled():
            # Resume a failed first-enable check without reusing its modified saved draft.
            if (self.profile() or {}).get("enabled"):
                d.batch_profile(ui.PRIMARY,self.off_document())
                current=self.read(cold=True)
                assert current["module"]["deviceHooks"]==0
                self.baseline=current
            else:
                self.baseline=self.read()
            self.open_editor();d.click("device-enabled")
            hint=d.find("device-consistency-hint").get("text","")
            assert "实际 API" in hint and "一键登录" in hint
            # All category rows remain collapsed.
            assert not any(n.get("content-desc","").startswith("device-edit:") for n in d.nodes())
            d.screenshot(str(OUT/"environment-hints-0.4.5.png"))
            self.save();profile=self.profile()
            profile["networkMode"]="off";profile["selected"]=MODEL+["total_ram","storage","density"]
            profile["values"].update(total_ram="1",storage="8")
            profile=d.batch_profile(ui.PRIMARY,profile);sample=self.revision_read(profile)
            assert sample["pid"]==self.baseline["pid"]
            assert sample["module"]["deviceHooks"]>0 and sample["module"]["deviceNative"]
            self.metadata(sample,profile);self.capacity(sample,profile)
            typed=sample["reads"]["typed_properties"]["value"]
            assert typed=={"densityInt":480,"densityLong":480,"missingInt":-17,"missingBool":True},typed
            return {"profile":profile,"observed":sample,"samePid":True,"uiSaved":True,"warnings":hint,
                    "18JavaMetadataReads":True,"nativeMetadataReads":True,"capacityRelations":True,"typedProperties":typed}
        self.case("E02-first-enable-ui-and-reads",enabled)
        self.good=self.report["cases"]["E02-first-enable-ui-and-reads"]["evidence"]["profile"]
        def cancel():
            d.batch_profile(ui.PRIMARY,self.good);before=self.profile()
            self.open_editor();self.edit("device","custom-device",True)
            for _ in range(3):d.swipe_down()
            assert "设备代号与固件指纹不一致" in d.find("device-consistency-hint",scroll=True).get("text","")
            d.click("device-back");d.click("丢弃","text");assert self.profile()==before
            return {"mismatchDisplayed":True,"discardPreservesSavedProfile":True}
        self.case("E03-warning-draft-discard",cancel)
        def update():
            before=self.read();profile=json.loads(json.dumps(self.good))
            profile["preset"]="custom"
            profile["values"]["fingerprint"]="Acme/product/device:16/CUSTOM.2026/42:userdebug/test-keys"
            profile["values"].update(total_ram="2",storage="16")
            profile=d.batch_profile(ui.PRIMARY,profile);sample=self.revision_read(profile)
            assert sample["pid"]==before["pid"]
            self.metadata(sample,profile);self.capacity(sample,profile)
            return {"profile":profile,"observed":sample,"samePid":True}
        self.case("E04-live-custom-metadata-capacity",update)
        def restoration():
            before=self.read();profile=self.profile();profile["selected"]=[]
            profile=d.batch_profile(ui.PRIMARY,profile);sample=self.revision_read(profile)
            assert sample["pid"]==before["pid"] and sample["module"]["deviceEnabled"]
            for key in ["fingerprint","build_metadata","metadata_properties","typed_properties"]:
                assert sample["reads"][key]==self.baseline["reads"][key],key
            for key in ["blockSize","total","blocks","blocks32","fileTotal","systemTotal"]:
                assert sample["reads"]["storage_view"]["value"][key]==self.baseline["reads"]["storage_view"]["value"][key],key
            assert sample["reads"]["memory_view"]["value"]["total"]==self.baseline["reads"]["memory_view"]["value"]["total"]
            profile["enabled"]=False;profile=d.batch_profile(ui.PRIMARY,profile);disabled=self.revision_read(profile)
            assert disabled["pid"]==before["pid"] and not disabled["module"]["deviceEnabled"]
            assert disabled["reads"]["build_metadata"]==self.baseline["reads"]["build_metadata"]
            assert disabled["module"]["deviceHooks"]==sample["module"]["deviceHooks"],"No duplicate install"
            return {"fieldOff":sample,"masterOff":disabled,"samePid":True,"originalValuesRestored":True}
        self.case("E05-field-and-master-restore",restoration)
        def shared():
            d.batch_policy(ui.PRIMARY,{"debug","selinux"})
            profile=d.batch_profile(ui.PRIMARY,self.good);sample=self.read(cold=True)
            assert set(sample["module"]["enabled"])=={"debug","selinux"}
            self.metadata(sample,profile);self.capacity(sample,profile)
            return {"observed":sample,"sharedNativeRegistration":True,"metadataAndCapacity":True}
        self.case("E09-shared-debug-selinux",shared)
        def all_methods():
            d.batch_policy(ui.PRIMARY,set(test_device.METHODS))
            profile=d.batch_profile(ui.PRIMARY,self.good);sample=self.read(cold=True)
            assert set(sample["module"]["enabled"])==set(test_device.METHODS)
            self.metadata(sample,profile);self.capacity(sample,profile)
            assert sample["reads"]["native"]["value"]["interfaceFreeControl"]
            assert sample["reads"]["native"]["value"]["propertyCallbackLifetimeControl"]
            return {"observed":sample,"allSixEnabledStartup":True,"nativeOwnership":True}
        self.case("E10-all-methods-startup",all_methods)
        def positive():
            d.batch_profile(ui.machine.A,self.off_document());sample=self.read(ui.machine.A,cold=True)
            assert sample["module"]["injected"] and sample["module"]["policyLoaded"]
            return {"observed":sample,"signedControlledVerifierAccepted":True}
        self.case("E06-authentic-sample-accepted",positive)
        def foreign():
            profile={"schema":1,"enabled":True,"preset":"custom","values":{
                "fingerprint":"Acme/product/device:16/FOREIGN.1/1:user/release-keys"},
                "selected":["fingerprint"],"networkMode":"off"}
            d.batch_profile(FOREIGN,profile);sample=self.read(FOREIGN,cold=True)
            assert not sample["module"]["injected"] and not sample["module"]["deviceEnabled"]
            assert sample["reads"]["build_metadata"]["value"]["id"]=="FOREIGN.1"
            assert sample["reads"]["fingerprint"]["value"]==profile["values"]["fingerprint"]
            return {"observed":sample,"sameClassSameSignatureWrongPackageRejected":True,"deviceHooksActuallyActive":True}
        self.case("E07-foreign-same-class-rejected",foreign)
        def signer():
            # Only our captured synthetic A package; the default Gradle debug key differs.
            d.adb("uninstall",ui.machine.A)
            d.adb("install","--no-incremental",str(ROOT/"verifier/build/outputs/apk/sampleA/debug/verifier-sampleA-debug.apk"))
            # Rebind after the package/UID replacement; a visible scope row can be stale.
            d.scope(ui.MODULE,ui.machine.A,False);d.scope(ui.MODULE,ui.machine.A,True)
            debug_apk=ROOT/"verifier/build/outputs/apk/sampleA/debug/verifier-sampleA-debug.apk"
            digest=hashlib.sha256(debug_apk.read_bytes()).hexdigest()
            remote=d.shell("pm","path",ui.machine.A).splitlines()[0].removeprefix("package:")
            assert d.shell("sha256sum",remote).split()[0]==digest
            profile={"schema":1,"enabled":True,"preset":"custom","values":{
                "fingerprint":"Acme/product/device:16/SIGNER.1/1:user/release-keys"},
                "selected":["fingerprint"],"networkMode":"off"}
            d.batch_profile(ui.machine.A,profile);sample=self.read(ui.machine.A,cold=True)
            assert not sample["module"]["injected"] and not sample["module"]["deviceEnabled"]
            assert sample["reads"]["build_metadata"]["value"]["id"]=="SIGNER.1"
            return {"observed":sample,"allowedPackageWrongSignerRejected":True,"deviceHooksActuallyActive":True,
                    "negativeAPKBytesMatch":True,"negativeAPKSHA256":digest}
        self.case("E08-wrong-signer-rejected",signer)
    def restore(self):
        original=json.loads((STATE/"state.json").read_text())
        # A was intentionally re-signed; uninstall its negative fixture before restoring.
        if "package:"+ui.machine.A in self.d.shell("pm","list","packages").splitlines():
            self.d.adb("uninstall",ui.machine.A)
        super().restore()
        for pkg,locale in json.loads((STATE/"locales.json").read_text()).items():
            self.d.shell("cmd","locale","set-app-locales",pkg,"--locales",locale)
            assert re.search(r"\[([^\]]*)\]",self.d.shell("cmd","locale","get-app-locales",pkg)).group(1)==locale
        self.report["restoration"]["appLocalesRestored"]=True
        ui.machine.REPORT.write_text(json.dumps(self.report,ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",action="append")
    parser.add_argument("--finish",action="store_true")
    args=parser.parse_args();run=Audit();run.only=set(args.case or [])
    if args.finish:
        run.restore();run.d.adb("unroot");run.d.adb("wait-for-device",timeout=15)
        assert run.d.shell("id","-u")=="2000"
        assert "OK" in run.d.adb("emu","kill")
        run.report["restoration"].update(adbdUnrooted=True,emulatorShutdownAccepted=True)
        ui.machine.REPORT.write_text(json.dumps(run.report,ensure_ascii=False,indent=2)+"\n")
    else:
        run.prepare_selected();run.run_selected()
