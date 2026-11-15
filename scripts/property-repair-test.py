#!/usr/bin/env python3
"""Current-APK fingerprint reads, restoration and all six-method combinations."""
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/property-repair-0.4.4"
VERSION="0.4.4"
COMPATIBILITY="Must use __system_property_read_callback() to read"

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

ui=load("property_ui","requirement-ui-test.py")
ui.machine.STATE=STATE
ui.machine.REPORT=OUT/"property-repair-0.4.4-results.json"
ui.machine.PACKAGES=(ui.MODULE,ui.PRIMARY,ui.machine.A,ui.machine.B)
os.environ["APPSTATE_TEST_VERSION"]=VERSION
os.environ["APPSTATE_TEST_STATE"]=str(STATE)
matrix=load("property_matrix","selinux-test.py")
KEYS=["ro.build.fingerprint","ro.system.build.fingerprint","ro.system_ext.build.fingerprint",
      "ro.vendor.build.fingerprint","ro.product.build.fingerprint","ro.odm.build.fingerprint"]
MODEL=["brand","manufacturer","model","device","product","board","hardware","release","incremental","fingerprint"]

class Audit(ui.Audit):
    def revision_read(self,profile):
        latest={}
        def ready():
            sample=self.read();latest.update(sample)
            return sample if sample["module"]["deviceRevision"]==profile["revision"] else None
        try:return self.wait(ready,"Main property reader revision not updated",timeout=12)
        except Exception:
            (OUT/"property-revision-failure-0.4.4.json").write_text(json.dumps(latest,indent=2)+"\n")
            raise

    def compare(self,profile,sample,expected):
        assert sample["module"]["injected"] and sample["module"]["deviceEnabled"]
        assert sample["module"]["deviceNative"] and sample["module"]["deviceRevision"]==profile["revision"]
        native=sample["reads"]["native"]["value"]
        java=sample["reads"]["java_properties"]["value"]
        assert sample["reads"]["fingerprint"]["value"]==profile["values"]["fingerprint"]
        for key,value in expected.items():
            assert java[key]==value,(key,"Java",java[key],value)
            legacy=COMPATIBILITY if key.startswith("ro.") and len(value.encode())>=92 else value
            observed=native["properties"][key]
            assert observed=={"get":legacy,"read":legacy,"callback":value},(key,observed,value)
            control=native["legacyControls"][key]
            assert control["buffersIntact"]
            assert control["getLength"]==control["readLength"]==control["nullNameLength"]==len(legacy.encode())
            assert control["nullNameValue"]==legacy
            assert control["readName"]==key[:31]
            for label in ["getBytes","readBytes","nullNameBytes"]:
                slot=bytes.fromhex(control[label]);assert len(slot)==92
                assert slot[:len(legacy.encode())]==legacy.encode()
                assert slot[len(legacy.encode())]==0
                # After a replacement, no original fingerprint may survive past NUL.
                assert slot[len(legacy.encode()):]==bytes(92-len(legacy.encode()))
        assert native["interfaceFreeControl"] and native["propertyCallbackLifetimeControl"]
        assert sample["reads"]["ordinary"]["value"]["file"]=="ordinary-device-control"
        assert native["properties"]["appstate.probe.absent"]=={"get":"","read":None,"callback":None}
        assert native["legacyControls"]["appstate.probe.absent"]["buffersIntact"]
        # Only compare against baseline fingerprint strings, never other profile data.
        exposed=json.dumps({"build":sample["reads"]["fingerprint"],"java":java,"native":native})
        baseline=self.baseline["reads"]["java_properties"]["value"]
        for key in KEYS:
            original=baseline[key]
            if original and original not in expected.values():
                assert original not in exposed,(key,"original fingerprint exposed")
                for data in native["legacyControls"].values():
                    for slot in ["getBytes","readBytes","nullNameBytes"]:
                        if data.get(slot):assert original.encode() not in bytes.fromhex(data[slot])
        return {"fingerprintsChecked":6,"longNameFieldsChecked":3,"legacyNullName":True,
                "zeroTailAndCanaries":True,"javaAndCallbackComplete":True,"originalFingerprintAbsent":True}

    def expected(self,profile):
        value=profile["values"]["fingerprint"]
        if profile["preset"]=="xiaomi-14":
            incremental=profile["values"]["incremental"]
            return {
                KEYS[0]:value,
                KEYS[1]:"qti/missi/missi:15/AQ3A.240627.003/"+incremental+":user/release-keys",
                KEYS[2]:"qti/missi/missi:15/AQ3A.240627.003/"+incremental+":user/release-keys",
                KEYS[3]:"Xiaomi/mivendor_sm8650_global/mivendor:14/UKQ1.240523.001/"+incremental+":user/release-keys",
                KEYS[4]:"Xiaomi/houji/miproduct:15/AQ3A.240627.003/"+incremental+":user/release-keys",
                KEYS[5]:"Xiaomi/houji_global/houji:14/UKQ1.240523.001/"+incremental+":user/release-keys",
                "ro.product.system_ext.manufacturer":"QUALCOMM",
                "ro.product.system_ext.device":"missi","ro.product.system_ext.name":"missi"}
        return dict({key:value for key in KEYS},
            **{"ro.product.system_ext.manufacturer":profile["values"]["manufacturer"],
               "ro.product.system_ext.device":profile["values"]["device"],
               "ro.product.system_ext.name":profile["values"]["product"]})

    def baseline_matches(self,sample):
        for field in MODEL:assert sample["reads"][field]==self.baseline["reads"][field],field
        assert sample["reads"]["java_properties"]==self.baseline["reads"]["java_properties"]
        before=self.baseline["reads"]["native"]["value"];after=sample["reads"]["native"]["value"]
        assert after["properties"]==before["properties"]
        assert after["legacyControls"]==before["legacyControls"]
        assert after["interfaceFreeControl"] and after["propertyCallbackLifetimeControl"]

    def run_checks(self):
        d=self.d
        self.budget_seconds=1200
        if not (STATE/"state.json").exists():
            assert "tun0" not in d.shell("ip","link","show"),"Existing VPN must not be replaced"
            assert "absent"==d.shell("sh","-c","test ! -e "+matrix.FIXTURE+" && echo absent")
            self.capture()
            original=json.loads((STATE/"state.json").read_text())
            permissions={}
            for pkg in original["packages"]:
                raw=d.shell("dumpsys","package",pkg)
                locale=d.shell("cmd","locale","get-app-locales",pkg)
                permissions[pkg]={
                    "granted":re.findall(r"(android\.permission\.[\w.]+): granted=true",raw),
                    "locales":re.search(r"\[([^\]]*)\]",locale).group(1)}
            path=STATE/"permissions-and-locales.json"
            with os.fdopen(os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),"w") as stream:
                json.dump(permissions,stream)
        self.report["artifacts"]={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()
            for name in ["AppStateShield-0.4.4.apk","AppStateVerifier-0.4.4.apk"]}
        self.regression=matrix.Run()
        self.regression.prepare()
        d.shell("cmd","locale","set-app-locales",ui.MODULE,"--locales","zh-CN")
        self.input_metadata=ui.case_inputs(d,self.report["artifacts"])
        assert self.input_metadata.get("buildInputsSHA256")
        self.regression.input_metadata=self.input_metadata
        # Real raw read baseline, outside the module scope.
        d.scope(ui.MODULE,ui.PRIMARY,False)
        d.shell("setenforce","0")
        raw=self.regression.sample(set(),injected=False)
        self.regression.case("R00-real-uninjected-permissive",lambda:raw)
        d.scope(ui.MODULE,ui.PRIMARY,True)
        d.batch_policy(ui.PRIMARY,set())
        d.batch_profile(ui.PRIMARY,{"schema":1,"enabled":False,"preset":"custom","values":{},"selected":[]})
        self.baseline=self.read(cold=True)
        self.case("R01-original-fingerprint-baseline",lambda:{"observed":self.baseline,"outsideScope":raw})

        def saved():
            self.open_editor();d.click("device-enabled");self.save()
            profile=self.profile();assert profile["preset"]=="xiaomi-14"
            # Keep display/network/environment original while exercising model adapters.
            profile=d.batch_profile(ui.PRIMARY,dict(profile,selected=MODEL))
            sample=self.revision_read(profile)
            assert sample["pid"]==self.baseline["pid"]
            self.good_profile=profile
            return {"profile":profile,"observed":sample,"uiSave":True,**self.compare(profile,sample,self.expected(profile))}
        self.case("R02-xiaomi-independent-hook",saved)
        if not hasattr(self,"good_profile"):
            self.good_profile=d.batch_profile(ui.PRIMARY,self.report["cases"]["R02-xiaomi-independent-hook"]["evidence"]["profile"])

        for enabled,label in [({"selinux"},"selinux"),({"debug"},"debug"),({"debug","selinux"},"debug-selinux")]:
            def shared(enabled=enabled):
                d.batch_policy(ui.PRIMARY,enabled)
                profile=d.batch_profile(ui.PRIMARY,self.good_profile)
                sample=self.read(cold=True)
                assert set(sample["module"]["enabled"])==enabled
                return {"profile":profile,"observed":sample,**self.compare(profile,sample,self.expected(profile))}
            self.case("R03-shared-"+label,shared)
        d.batch_policy(ui.PRIMARY,{"debug","selinux"})
        profile=d.batch_profile(ui.PRIMARY,self.good_profile)
        live=self.read(cold=True)
        self.compare(profile,live,self.expected(profile))

        for length in [91,92,128,256,48]:
            def update(length=length):
                original=self.good_profile
                updated=json.loads(json.dumps(original));updated["preset"]="custom"
                # Boundary fixtures are explicitly synthetic, not real model presets.
                updated["values"]["fingerprint"]="T"*length
                if length==128:
                    d.batch_profile(ui.PRIMARY,dict(updated,values=dict(updated["values"],fingerprint="T"*92)))
                    self.open_editor();self.edit("fingerprint","T"*128,True);self.save()
                    updated=self.profile()
                    assert updated["values"]["fingerprint"]=="T"*128
                else:
                    updated=d.batch_profile(ui.PRIMARY,updated)
                sample=self.revision_read(updated)
                assert sample["pid"]==live["pid"]
                return {"profile":updated,"observed":sample,"samePid":sample["pid"],
                        "syntheticByteLength":length,"realUiSave":length==128,
                        **self.compare(updated,sample,self.expected(updated))}
            self.case("R04-live-fingerprint-"+str(length),update)

        def off():
            active=d.batch_profile(ui.PRIMARY,self.good_profile)
            self.revision_read(active)
            empty=d.batch_profile(ui.PRIMARY,dict(active,selected=[]))
            sample=self.revision_read(empty)
            # Baseline was all six methods off; compare only machine properties.
            original_native=self.baseline["reads"]["native"]["value"]
            for key in KEYS+["ro.product.system_ext.manufacturer","ro.product.system_ext.device","ro.product.system_ext.name"]:
                assert sample["reads"]["java_properties"]["value"][key]==self.baseline["reads"]["java_properties"]["value"][key]
                assert sample["reads"]["native"]["value"]["properties"][key]==original_native["properties"][key]
                assert sample["reads"]["native"]["value"]["legacyControls"][key]==original_native["legacyControls"][key]
            disabled=d.batch_profile(ui.PRIMARY,dict(empty,enabled=False))
            restored=self.revision_read(disabled)
            assert restored["pid"]==sample["pid"]==live["pid"]
            for key in KEYS:
                assert restored["reads"]["native"]["value"]["properties"][key]==original_native["properties"][key]
            return {"emptySelectedAndMasterOffRestore":True,"samePid":restored["pid"],"observed":restored}
        self.case("R05-field-and-master-off",off)
        self.run_matrix()

    def run_matrix(self):
        d=self.d
        profile=d.batch_profile(ui.PRIMARY,self.good_profile)
        self.regression.case("R10-policy-real-ui-save",lambda:self.policy_ui())
        print("64 combinations: actual six-method assertions plus fingerprint properties; expected 4–8 minutes",flush=True)
        for i in range(64):
            bits=format(i^(i>>1),"06b")
            enabled={key for key,bit in zip(ui.machine.METHODS,bits) if bit=="1"}
            def combined(enabled=enabled):
                d.batch_policy(ui.PRIMARY,enabled)
                old=self.regression.sample(enabled)
                sample=self.read()
                assert sample["module"]["deviceRevision"]==profile["revision"]
                return {"methods":sorted(enabled),"methodReads":old,"propertyReads":sample,
                        **self.compare(profile,sample,self.expected(profile))}
            self.case("M6-"+bits,combined)

    def policy_ui(self):
        self.d.set_policy(ui.PRIMARY,set())
        return {"realUiSave":True}

    def restore(self):
        d=self.d
        original=json.loads((STATE/"state.json").read_text())
        # Only our temporary VPN package; leave every unrelated package alone.
        d.shell("am","force-stop",ui.machine.B)
        assert "tun0" not in d.shell("ip","link","show")
        d.shell("rm","-rf",matrix.FIXTURE)
        super().restore()
        permissions=json.loads((STATE/"permissions-and-locales.json").read_text())
        for pkg,saved in permissions.items():
            for permission in ["android.permission.READ_EXTERNAL_STORAGE","android.permission.WRITE_EXTERNAL_STORAGE"]:
                if permission not in saved["granted"]:d.shell("pm","revoke",pkg,permission)
            d.shell("cmd","locale","set-app-locales",pkg,"--locales",saved["locales"])
            granted=set(re.findall(r"(android\.permission\.[\w.]+): granted=true",
                                   d.shell("dumpsys","package",pkg)))
            assert set(saved["granted"])<=granted,"Original permission lost: "+pkg
            for permission in ["android.permission.READ_EXTERNAL_STORAGE","android.permission.WRITE_EXTERNAL_STORAGE"]:
                assert (permission in granted)==(permission in saved["granted"])
            locales=d.shell("cmd","locale","get-app-locales",pkg)
            assert re.search(r"\[([^\]]*)\]",locales).group(1)==saved["locales"]
        self.report["restoration"].update({"vpnStopped":True,"temporaryFilesRemoved":True,
            "temporaryStorageGrantsRemoved":True,"appLocalesRestored":True})
        ui.machine.REPORT.write_text(json.dumps(self.report,ensure_ascii=False,indent=2)+"\n")

if __name__=="__main__":
    run=Audit()
    try:run.run_checks()
    finally:
        if (STATE/"state.json").exists():run.restore()
        run.d.adb("unroot");run.d.adb("wait-for-device")
        assert run.d.shell("id","-u")=="2000"
        run.d.adb("emu","kill")
        run.report["restoration"].update({"adbdUnrooted":True,"emulatorShutdown":True})
        ui.machine.REPORT.write_text(json.dumps(run.report,ensure_ascii=False,indent=2)+"\n")
