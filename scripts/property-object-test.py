#!/usr/bin/env python3
"""0.4.6 object reads and one shared-native matrix, dedicated emulator only."""
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
VERSION="0.4.6"
STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/property-objects-0.4.6"
os.environ["APPSTATE_TEST_VERSION"]=VERSION
os.environ["APPSTATE_TEST_STATE"]=str(STATE)

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

ui=load("object_ui","requirement-ui-test.py")
ui.machine.STATE=STATE
ui.machine.REPORT=OUT/"property-objects-0.4.6-results.json"
ui.machine.PACKAGES=(ui.MODULE,ui.PRIMARY,ui.machine.A,ui.machine.B)
matrix=load("object_matrix","selinux-test.py")
KEYS=["ro.build.fingerprint","ro.system.build.fingerprint","ro.system_ext.build.fingerprint",
      "ro.vendor.build.fingerprint","ro.product.build.fingerprint","ro.odm.build.fingerprint"]
MODEL=["brand","manufacturer","model","device","product","board","hardware","release","incremental","fingerprint"]
COMPATIBILITY="Must use __system_property_read_callback() to read"
def fingerprint(length,letter):
    prefix="Acme/product/device:16/ID/"
    suffix=":user/release-keys"
    return prefix+letter*(length-len(prefix)-len(suffix))+suffix

class Audit(ui.Audit):
    def prepare(self):
        d=self.d
        if not (STATE/"state.json").exists():
            assert "tun0" not in d.shell("ip","link","show")
            assert "absent"==d.shell("sh","-c","test ! -e "+matrix.FIXTURE+" && echo absent")
            self.capture()
            original=json.loads((STATE/"state.json").read_text())
            extras={}
            for pkg in original["packages"]:
                extras[pkg]={"grants":re.findall(r"(android\.permission\.[\w.]+): granted=true",
                    d.shell("dumpsys","package",pkg)),
                    "locale":re.search(r"\[([^\]]*)\]",d.shell("cmd","locale","get-app-locales",pkg)).group(1)}
            path=STATE/"grants-locales.json";path.write_text(json.dumps(extras));path.chmod(0o600)
        self.report["artifacts"]={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()
            for name in ["AppStateShield-0.4.6.apk","AppStateVerifier-0.4.6.apk"]}
        self.regression=matrix.Run()
        if self.report.get("prepared"):
            # A targeted repair may change only one APK. Preserve the original
            # snapshot and live VPN; update bytes without rebuilding fixtures.
            for pkg,name in [(ui.MODULE,"AppStateShield-0.4.6.apk"),(ui.PRIMARY,"AppStateVerifier-0.4.6.apk"),
                             (ui.machine.A,"Verifier-A-0.4.6.apk"),(ui.machine.B,"Verifier-B-0.4.6.apk")]:
                remote=d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
                if d.shell("sha256sum",remote).split()[0]!=hashlib.sha256((OUT/name).read_bytes()).hexdigest():
                    d.adb("install","--no-incremental","-r",str(OUT/name))
            if "tun0" not in d.shell("ip","link","show"):
                d.shell("am","start","-W","-n",ui.machine.B+"/io.github.lwtdzh.devicestateprobe.ProbeActivity",
                        "--es","action","vpn-start")
                consent=next((n for n in d.nodes() if n.get("resource-id")=="android:id/button1"),None)
                if consent is not None:d.tap(consent)
                self.wait(lambda:"tun0" in d.shell("ip","link","show"),"VPN fixture failed to restart",timeout=10)
            self.regression.validate_setup()
        else:
            self.regression.prepare()
            self.report["prepared"]=True
        self.input_metadata=ui.case_inputs(d,self.report["artifacts"])
        self.input_metadata["executorSHA256"]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
        assert self.input_metadata.get("buildInputsSHA256")
        self.regression.input_metadata=self.input_metadata
        ui.machine.REPORT.write_text(json.dumps(self.report,ensure_ascii=False,indent=2)+"\n")

    def revision(self,profile):
        def current():
            sample=self.read()
            if sample["module"]["deviceRevision"]!=profile["revision"]:return None
            if "value" not in sample["reads"]["native"]:
                (OUT/"property-object-last-diagnostic.json").write_text(json.dumps(sample,indent=2))
                return None
            return sample
        return self.wait(current,"No native sample at current revision",timeout=12)

    def native(self,sample):
        assert "value" in sample["reads"]["native"],sample["reads"]["native"]
        return sample["reads"]["native"]["value"]

    def check(self,profile,sample):
        marker=sample["module"]
        assert marker["injected"] and marker["deviceNative"] and marker["deviceNativeObjects"],marker
        assert marker["deviceRevision"]==profile["revision"]
        native=self.native(sample)
        fingerprint=profile["values"]["fingerprint"]
        for key in KEYS:
            row=native["properties"][key]
            assert row["callback"]==fingerprint,(key,row)
            wanted=fingerprint if len(fingerprint.encode())<=91 else COMPATIBILITY
            assert row["get"]==wanted and row["read"]==wanted,(key,row)
            controls=native["legacyControls"][key]
            assert controls["buffersIntact"]
            for slot in ["getBytes","readBytes","nullNameBytes"]:
                data=bytes.fromhex(controls[slot]);text=data.split(b"\0",1)[0]
                assert data[len(text):]==bytes(92-len(text)),(key,slot)
        for key in ["ro.build.fingerprint","ro.product.model","ro.product.system_ext.manufacturer",
                    "ro.system_ext.build.id","ro.sf.lcd_density"]:
            obj=native["propertyObjects"][key]
            assert obj is not None,(key,"selected absent property must get an object")
            assert obj["rawMatchesCallback"] and obj["nameMatches"],(key,obj)
            assert obj["headerSerial"]==obj["apiSerial"]==obj["callbackSerial"]==obj["expectedSerial"],(key,obj)
            assert not obj["zeroWaitChanged"] and obj["waitOutput"]==0x12345678,(key,obj)
        enumeration=native["propertyEnumeration"]
        assert enumeration["result"]==0 and enumeration["pastEndNull"]
        names=[row["object"]["name"] for row in enumeration["selected"]]
        assert len(names)==len(set(names)) and "ro.build.fingerprint" in names
        for row in enumeration["selected"]:
            assert row["sameFindPointer"] and row["sameNthPointer"],row
        assert native["properties"]["appstate.probe.absent"]=={"get":"","read":None,"callback":None}
        assert native["interfaceFreeControl"] and native["propertyCallbackLifetimeControl"]
        assert sample["reads"]["ordinary"]["value"]["file"]=="ordinary-device-control"
        return {"rawHeaderCallbackSerialAgree":True,"enumerationFindNthAgree":True,
                "legacyBuffersIntactAndCleared":True,"zeroTimeoutWait":True,"ordinaryControls":True}

    def selected(self):
        d=self.d;self.budget_seconds=300
        def baseline():
            d.scope(ui.MODULE,ui.PRIMARY,False);d.shell("setenforce","0")
            raw=self.regression.sample(set(),injected=False)
            d.scope(ui.MODULE,ui.PRIMARY,True);d.batch_policy(ui.PRIMARY,set())
            profile=d.batch_profile(ui.PRIMARY,{"schema":1,"enabled":False,"preset":"custom",
                "values":{},"selected":[],"networkMode":"off"})
            observed=self.read(cold=True)
            assert not observed["module"]["deviceNative"]
            assert self.native(observed)["properties"]["ro.build.fingerprint"]["callback"]
            return {"observed":observed,"outsideScope":raw,"profile":profile}
        self.case("P01-original-and-uninjected-baselines",baseline)
        self.baseline=self.report["cases"]["P01-original-and-uninjected-baselines"]["evidence"]["observed"]
        fixture=json.loads((OUT/"environment-0.4.5-results.json").read_text())["cases"][
            "E02-first-enable-ui-and-reads"]["evidence"]["profile"]
        self.good=json.loads(json.dumps(fixture))
        self.good.update(preset="custom",enabled=True,selected=MODEL+["density"],networkMode="off")
        self.good["values"]["fingerprint"]=fingerprint(128,"T")
        self.good["values"]["model"]="Object probe fixture"
        def enable():
            profile=d.batch_profile(ui.PRIMARY,self.good);sample=self.revision(profile)
            assert sample["pid"]==self.baseline["pid"]
            checks=self.check(profile,sample)
            missing=[key for key,obj in self.native(self.baseline)["properties"].items()
                     if obj["callback"] is None and self.native(sample)["properties"][key]["callback"] is not None]
            assert missing,"No actual selected-missing baseline; do not claim synthetic-find coverage"
            return {"profile":profile,"observed":sample,"samePid":True,"syntheticFixtureBytes":128,
                    "actualMissingProperties":missing,**checks}
        self.case("P02-enable-long-object-and-missing-property",enable)
        first=self.report["cases"]["P02-enable-long-object-and-missing-property"]["evidence"]["observed"]
        for length in [256,48]:
            def update(length=length):
                profile=json.loads(json.dumps(self.good));profile["values"]["fingerprint"]=fingerprint(length,"U")
                profile=d.batch_profile(ui.PRIMARY,profile);sample=self.revision(profile)
                assert sample["pid"]==first["pid"]
                cached=self.native(sample)["cachedPropertyObjects"]["firstChanged"]
                assert cached["callback"]==fingerprint(128,"T") and cached["rawMatchesCallback"],cached
                assert cached["headerSerial"]==cached["apiSerial"]==cached["callbackSerial"]
                return {"profile":profile,"observed":sample,"samePid":True,"immutableOldCache":True,
                        "syntheticFixtureBytes":length,**self.check(profile,sample)}
            self.case("P03-live-update-"+str(length),update)
        def collision():
            profile=json.loads(json.dumps(self.good))
            host=self.native(self.baseline)["properties"]["ro.build.fingerprint"]["callback"]
            profile["values"]["fingerprint"]=host
            profile=d.batch_profile(ui.PRIMARY,profile);one=self.revision(profile);self.check(profile,one)
            profile["values"]["fingerprint"]=fingerprint(128,"C")
            profile=d.batch_profile(ui.PRIMARY,profile);two=self.revision(profile)
            assert two["pid"]==one["pid"]==first["pid"]
            # The original pointer's text may equal an old fake value. Mapping
            # must follow pointer ownership and current selection, not equality.
            old=self.native(two)["cachedPropertyObjects"]["initial"]
            assert old["callback"]==fingerprint(128,"C"),old
            return {"profile":profile,"observed":two,"samePid":True,"oldValueEqualsHostCase":True,
                    **self.check(profile,two)}
        self.case("P04-host-equals-old-value-then-update",collision)
        def disable():
            current=self.profile()
            for changes in [{"selected":[]},{"enabled":False}]:
                current=d.batch_profile(ui.PRIMARY,dict(current,**changes));sample=self.revision(current)
                assert sample["pid"]==first["pid"]
                for key in KEYS:
                    assert self.native(sample)["properties"][key]==self.native(self.baseline)["properties"][key]
                cached=self.native(sample)["cachedPropertyObjects"]["firstChanged"]
                assert cached["callback"]==fingerprint(128,"T") and cached["rawMatchesCallback"]
            return {"observed":sample,"samePid":True,"freshReadsRestore":True,"oldReadOnlyCacheRetained":True}
        self.case("P05-selected-and-master-off-restore",disable)
        for methods in [{"debug"},{"selinux"},{"debug","selinux"}]:
            def shared(methods=methods):
                d.batch_policy(ui.PRIMARY,methods);profile=d.batch_profile(ui.PRIMARY,self.good)
                sample=self.read(cold=True);assert set(sample["module"]["enabled"])==methods
                return {"profile":profile,"observed":sample,**self.check(profile,sample)}
            self.case("P06-shared-"+"-".join(sorted(methods)),shared)

    def combinations(self):
        self.budget_seconds=1200;self.started=time.monotonic()
        profile=self.profile()
        if not profile or not profile["enabled"]:
            profile=self.d.batch_profile(ui.PRIMARY,self.good)
        if "serial" not in profile["selected"]:
            # This matrix tests properties and the six existing methods, not
            # telephony permissions. The AVD's missing modem makes unselected
            # Build.getSerial requests consume system_server Binder threads.
            # Use the existing serial adapter in the test fixture; do not
            # change the APK or relabel the earlier 21 completed observations.
            profile["selected"].append("serial")
            profile=self.d.batch_profile(ui.PRIMARY,profile)
            self.report["matrixFixtureAdjustment"]={
                "reason":"Unavailable emulator modem; repeated unselected Build.getSerial blocked system_server Binder pool",
                "selectedFieldAdded":"serial","revision":profile["revision"],
                "priorPassedCasesRetained":True,"apkUnchanged":True}
        self.case("P07-policy-real-ui-save",lambda:(self.d.set_policy(ui.PRIMARY,set()) or {"realUiSave":True}))
        print("64 shared-native combinations, retain completed cases; expected 4–8 minutes",flush=True)
        for i in range(64):
            bits=format(i^(i>>1),"06b")
            methods={key for key,bit in zip(ui.machine.METHODS,bits) if bit=="1"}
            def combined(methods=methods):
                self.d.batch_policy(ui.PRIMARY,methods)
                ordinary=self.regression.sample(methods)
                sample=self.read()
                return {"profile":profile,"methodReads":ordinary,"observed":sample,**self.check(profile,sample)}
            self.case("M6-"+bits,combined)

    def restore(self):
        d=self.d
        d.shell("am","force-stop",ui.machine.B)
        assert "tun0" not in d.shell("ip","link","show")
        d.shell("rm","-rf",matrix.FIXTURE)
        super().restore()
        extras=json.loads((STATE/"grants-locales.json").read_text())
        for pkg,saved in extras.items():
            for permission in ["android.permission.READ_EXTERNAL_STORAGE","android.permission.WRITE_EXTERNAL_STORAGE"]:
                if permission not in saved["grants"]:d.shell("pm","revoke",pkg,permission)
            d.shell("cmd","locale","set-app-locales",pkg,"--locales",saved["locale"])
            current=set(re.findall(r"(android\.permission\.[\w.]+): granted=true",d.shell("dumpsys","package",pkg)))
            assert set(saved["grants"])<=current,pkg
            assert all((p in current)==(p in saved["grants"]) for p in
                ["android.permission.READ_EXTERNAL_STORAGE","android.permission.WRITE_EXTERNAL_STORAGE"])
            assert re.search(r"\[([^\]]*)\]",d.shell("cmd","locale","get-app-locales",pkg)).group(1)==saved["locale"]
        self.report["restoration"].update(vpnStopped=True,temporaryFilesRemoved=True,grantsAndLocalesRestored=True)
        ui.machine.REPORT.write_text(json.dumps(self.report,ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["selected","matrix","restore"])
    args=parser.parse_args();run=Audit()
    if args.action=="restore":
        run.budget_seconds=1200;run.restore()
        run.d.adb("unroot");run.d.adb("wait-for-device",timeout=15)
        assert run.d.shell("id","-u")=="2000"
        assert "OK" in run.d.adb("emu","kill")
        run.report["restoration"].update(adbdUnrooted=True,emulatorShutdown=True)
        ui.machine.REPORT.write_text(json.dumps(run.report,ensure_ascii=False,indent=2)+"\n")
    else:
        run.prepare()
        if args.action=="selected":run.selected()
        else:
            run.good=run.report["cases"]["P02-enable-long-object-and-missing-property"]["evidence"]["profile"]
            run.combinations()
