#!/usr/bin/env python3
"""Machine profile checks. Only dedicated emulator-5584; capture before preparation."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import time
import secrets
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from test_evidence import case_inputs
from test_device import Device, MODULE, PRIMARY, METHODS

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/machine-0.4.0"
A=PRIMARY+".samplea"
B=PRIMARY+".sampleb.screenshot"
PACKAGES=(MODULE,PRIMARY,A,B)
REPORT=OUT/"machine-0.4.0-results.json"

def check(value,message):
    if not value: raise AssertionError(message)

class Run:
    def __init__(self):
        self.d=Device()
        self.only=set()
        self.input_metadata=None
        self.started=time.monotonic()
        self.budget_seconds=300
        self.report=json.loads(REPORT.read_text()) if REPORT.exists() else {"cases":{}}
    def case(self,name,action):
        if self.only and name not in self.only:return
        prior=self.report["cases"].get(name,{})
        if (name!="D18-restored" and prior.get("status")=="passed" and
            prior.get("artifacts")==self.report.get("artifacts")):
            print("KEEP verified "+name,flush=True)
            return prior.get("evidence")
        check(time.monotonic()-self.started<=self.budget_seconds,
            "Execution budget reached; preserve results and inspect durations")
        print("START "+name,flush=True)
        started=time.monotonic()
        stamp=datetime.now(timezone.utc).isoformat()
        try:
            value=action()
            if self.input_metadata is None:
                self.input_metadata=case_inputs(self.d,self.report.get("artifacts",{})) if name!="D18-restored" else {}
            if name in self.report["cases"]:
                self.report.setdefault("previousRuns",{}).setdefault(name,[]).append(self.report["cases"][name])
            self.report["cases"][name]={"status":"passed","evidence":value,"artifacts":self.report.get("artifacts",{}).copy(),
                "startedAtUTC":stamp,"durationSeconds":round(time.monotonic()-started,3),**self.input_metadata}
            print("PASS "+name,flush=True)
            return value
        except Exception as error:
            if prior:self.report.setdefault("previousRuns",{}).setdefault(name,[]).append(prior)
            self.report["cases"][name]={"status":"failed","error":repr(error),
                "startedAtUTC":stamp,"durationSeconds":round(time.monotonic()-started,3)}
            raise
        finally:
            REPORT.write_text(json.dumps(self.report,ensure_ascii=False,indent=2)+"\n")
    def wait(self,read,message,timeout=30):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=read()
            if value:return value
            time.sleep(.1)
        raise AssertionError(message)
    def capture(self):
        d=self.d
        check(not (STATE/"state.json").exists(),"Existing original snapshot; do not overwrite")
        STATE.mkdir(mode=0o700,parents=True)
        original={"mode":d.shell("getenforce"),"modules":d.cli("modules","ls"),"packages":{},"settings":{}}
        original["scopes"]={m["PACKAGE"]:d.cli("scope","ls",m["PACKAGE"]) for m in original["modules"]}
        for namespace,keys in {
            "global":["hidden_api_policy","development_settings_enabled","adb_enabled","adb_wifi_enabled","http_proxy"],
            "system":["accelerometer_rotation","user_rotation","font_scale"],
            "secure":["enabled_notification_listeners","enabled_accessibility_services","accessibility_enabled"]
        }.items():
            original["settings"][namespace]={key:d.shell("settings","get",namespace,key) for key in keys}
        installed=set(d.shell("pm","list","packages").splitlines())
        for pkg in PACKAGES:
            if "package:"+pkg not in installed:continue
            remote=d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
            local=STATE/(pkg+".apk");d.adb("pull",remote,str(local));local.chmod(0o600)
            # Private full package snapshot preserves preferences, probe files and permission caches.
            tar="/data/local/tmp/machine-backup.tar"
            d.shell("am","force-stop",pkg)
            d.shell("tar","-cf",tar,"-C","/data/user/0/"+pkg,".")
            backup=STATE/(pkg+".tar");d.adb("pull",tar,str(backup));backup.chmod(0o600);d.shell("rm","-f",tar)
            original["packages"][pkg]={"apk":str(local),"data":str(backup)}
        with os.fdopen(os.open(STATE/"state.json",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),"w") as stream:
            json.dump(original,stream)
        self.case("D00-capture",lambda:{"serial":"emulator-5584","sdk":d.shell("getprop","ro.build.version.sdk"),
            "abi":d.shell("getprop","ro.product.cpu.abi"),"originalMode":original["mode"],"privateBackup":True})
    def prepare(self):
        d=self.d;check((STATE/"state.json").exists(),"Capture original state first")
        for pkg,name in [(MODULE,"AppStateShield-0.3.1.apk"),(PRIMARY,"AppStateVerifier-0.3.1.apk")]:
            if "package:"+pkg not in d.shell("pm","list","packages").splitlines():
                d.adb("install","--no-incremental","-r",str(OUT/name))
        for name in ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk","Verifier-A-0.4.0.apk","Verifier-B-0.4.0.apk"]:
            d.adb("install","--no-incremental","-r",str(OUT/name))
        self.report["artifacts"]={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in
            ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk","Verifier-A-0.4.0.apk","Verifier-B-0.4.0.apk"]}
        for module in d.cli("modules","ls"):
            for pkg in [PRIMARY,A,B]:d.scope(module["PACKAGE"],pkg,False)
        d.cli("modules","enable",MODULE)
        for pkg in [PRIMARY,A,B]:
            d.scope(MODULE,pkg,True)
            for permission in ["READ_PHONE_STATE","ACCESS_FINE_LOCATION","ACCESS_COARSE_LOCATION","BLUETOOTH_CONNECT"]:
                d.shell("pm","grant",pkg,"android.permission."+permission)
        d.shell("settings","put","global","hidden_api_policy","1")
        d.shell("cmd","locale","set-app-locales",MODULE,"--locales","zh-CN")
        d.shell("cmd","locale","set-app-locales",PRIMARY,"--locales","zh-CN")
        self.case("D01-upgrade-default",lambda:self.default())
    def install(self):
        for name in ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk","Verifier-A-0.4.0.apk","Verifier-B-0.4.0.apk"]:
            self.d.adb("install","--no-incremental","-r",str(OUT/name))
        self.report["artifacts"]={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in
            ["AppStateShield-0.4.0.apk","AppStateVerifier-0.4.0.apk","Verifier-A-0.4.0.apk","Verifier-B-0.4.0.apk"]}
        self.case("D18-installed-hashes",lambda:{pkg:self.d.shell("sha256sum",self.d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")).split()[0] for pkg in PACKAGES})
    def profile(self,pkg=PRIMARY):
        path="/data/user/0/"+MODULE+"/shared_prefs/device_profiles.xml"
        raw=self.d.shell("sh","-c","test ! -f "+path+" || cat "+path)
        if not raw:return None
        value=next((n.text for n in ET.fromstring(raw) if n.get("name")==pkg),None)
        return json.loads(value) if value else None
    def read(self,pkg=PRIMARY,cold=False,process=False):
        d=self.d;path="/data/user/0/"+pkg+"/files/machine-result.json"
        before=0
        raw=d.shell("sh","-c","test ! -f "+path+" || cat "+path)
        if raw:
            try:before=json.loads(raw)["timestamp"]
            except ValueError:pass
        if cold:d.shell("am","force-stop",pkg)
        d.shell("am","start","-W","--activity-clear-top","-n",pkg+"/io.github.lwtdzh.screenshotdetector."+
            ("DeviceProcessActivity" if process else "DeviceActivity"))
        def ready():
            raw=d.shell("sh","-c","test ! -f "+path+" || cat "+path)
            try:
                result=json.loads(raw)
                return result if result["timestamp"]>before and "ordinary" in result["reads"] else None
            except (ValueError,KeyError):return None
        return self.wait(ready,"No complete machine snapshot")
    def default(self):
        value=self.read(cold=True)
        check(value["module"]["injected"],"Vector injection absent")
        check(not value["module"]["deviceEnabled"],"Machine spoofing must default off")
        check(set(value["module"]["enabled"])==set(METHODS),"Original defaults changed")
        check(not self.profile(),"Unexpected profile before opt-in")
        return value
    def open_editor(self,pkg=PRIMARY):
        self.d.shell("am","force-stop",MODULE)
        self.d.shell("am","start","-W","-n",MODULE+"/.DeviceSettingsActivity","--es","package",pkg)
        self.d.find("device-enabled")
    def save(self):
        self.d.tap(self.d.find("device-save"))
    def find_edit(self,key):
        d=self.d;search=d.find("device-field-search",scroll=True);d.tap(search)
        text=search.get("text","")
        if text:
            d.shell("input","keyevent","KEYCODE_MOVE_END")
            d.shell("input","keyevent",*(["KEYCODE_DEL"]*len(text)))
        d.shell("input","text",key);d.back()
        return d.find("device-edit:"+key,scroll=True)
    def edit(self,key,value=None,on=True):
        d=self.d;d.tap(self.find_edit(key));node=d.find("device-use:"+key)
        if(node.get("checked")=="true")!=on:d.tap(node)
        if value is not None:
            node=d.find("device-input:"+key);d.tap(node);text=node.get("text","")
            d.shell("input","keyevent","KEYCODE_MOVE_END")
            if text:d.shell("input","keyevent",*(["KEYCODE_DEL"]*len(text)))
            d.shell("input","text",value.replace(" ","%s"));d.back()
        d.click("android:id/button1","resource-id")
    def smoke(self):
        d=self.d;self.open_editor()
        if d.find("device-enabled").get("checked")!="true":d.click("device-enabled")
        self.save()
        profile=self.profile();check(profile["enabled"],"Profile not saved")
        value=self.read(cold=True)
        self.case("D03-xiaomi-smoke",lambda:self.compare(profile,value))
        d.find("machine-summary")
        d.screenshot(str(OUT/"machine-verifier-0.4.0.png"))
        self.open_editor()
        d.find("device-preset")
        d.screenshot(str(OUT/"machine-editor-0.4.0.png"))
        d.tap(self.find_edit("imei"))
        d.click("device-dialog-random");d.click("更新草稿","text")
        self.save()
        next_profile=self.profile();check(next_profile["values"]["imei"]!=profile["values"]["imei"],"IMEI did not change")
        def updated():
            current=self.read()
            return current if current["module"]["deviceRevision"]==next_profile["revision"] else None
        next_read=self.wait(updated,"Profile update did not reach reader",timeout=8)
        self.case("D05-imei-live",lambda:self.live(value,next_read,next_profile,"imei"))
    def compare(self,profile,result):
        check(result["module"]["deviceEnabled"],"Profile not active")
        failed={}
        aliases={"total_ram":lambda x:int(x)*(1<<30),"storage":lambda x:int(x)*(1<<30),
            "ssid":lambda x:'"'+x.replace('"',"")+'"',"hide_sensors":lambda x:0 if x=="true" else None}
        unobservable={"oaid","vaid","aaid","gaid","drm_id"}
        for key in profile["selected"]:
            if key in unobservable:continue
            expected=aliases.get(key,lambda x:x)(profile["values"][key])
            row=result["reads"].get(key,{})
            actual=row.get("value")
            same=str(actual)==str(expected)
            if isinstance(actual,(int,float)):
                try:same=float(actual)==float(expected)
                except (ValueError,TypeError):pass
            if not same:failed[key]={"expected":expected,"actual":row}
        check(not failed,"Read mismatches: "+json.dumps(failed,ensure_ascii=False))
        native=result["reads"]["native"]["value"]
        check(native["interfaceFreeControl"],"Native interface destructor control failed")
        check(native["propertyCallbackLifetimeControl"],"Nested property read changed callback value")
        check(result["reads"]["ordinary"]["value"]["file"]=="ordinary-device-control","Ordinary file changed")
        return {"profile":profile,"observed":result,"OEMRealService":"Not available on AOSP",
            "drmBaseline":"Widevine constructor not supported by this AOSP emulator"}
    def live(self,before,after,profile,key):
        check(before["pid"]==after["pid"],"Reader was restarted")
        check(str(after["reads"][key].get("value"))==profile["values"][key],"Updated field not applied")
        return {"samePid":after["pid"],"revision":after["module"]["deviceRevision"],"updatedField":key,"observed":after}
    def rotate(self,rotation):
        self.d.shell("settings","put","system","accelerometer_rotation","0")
        self.d.shell("settings","put","system","user_rotation",str(rotation))
        return self.wait(lambda: "mRotation="+str(rotation)+" " in self.d.shell("dumpsys","window","displays"),"Rotation not applied")
    def revision_read(self,profile,pkg=PRIMARY):
        return self.wait(lambda:(lambda r:r if r["module"]["deviceRevision"]==profile["revision"] and
            r.get("phoneWorker",{}).get("revision")==profile["revision"] else None)(self.read(pkg)),
            "Reader did not receive saved revision",timeout=12)
    def ui(self):
        d=self.d
        def drafts():
            check(self.profile(B) is None,"Draft fixture requires unconfigured B")
            self.open_editor(B);d.click("device-enabled")
            d.tap(self.find_edit("imei"));d.click("device-dialog-random")
            pending=d.find("device-input:imei").get("text")
            d.click("取消","text")
            check(self.profile(B) is None,"Dialog cancellation saved a profile")
            self.edit("serial","DRAFT123456")
            self.rotate(1)
            d.find("device-save")
            d.tap(self.find_edit("serial"))
            check(d.find("device-input:serial").get("text")=="DRAFT123456","Rotation lost draft")
            d.click("取消","text");self.rotate(0)
            d.click("device-back");d.click("丢弃","text")
            check(self.profile(B) is None,"Discard saved a profile")
            return {"dialogCancel":True,"pageDiscard":True,"rotationRetainsDraft":True,"randomDialogValueGenerated":bool(pending)}
        self.case("D02-drafts-rotation",drafts)
        def invalid():
            old=self.profile();self.open_editor();d.tap(self.find_edit("imei"))
            node=d.find("device-input:imei");d.tap(node);d.shell("input","keyevent","KEYCODE_MOVE_END")
            d.shell("input","keyevent",*(["KEYCODE_DEL"]*len(node.get("text",""))));d.shell("input","text","123")
            d.back();d.click("更新草稿","text")
            check(d.find("device-input:imei").get("text")=="123","Invalid field dialog closed")
            check(self.profile()==old,"Invalid input saved")
            d.click("取消","text");d.click("device-back")
            return {"invalidIMEIRejected":True,"storedProfileUnchanged":True}
        self.case("D04-invalid-input",invalid)
        def preset():
            self.open_editor(B);d.click("device-enabled");d.click("device-preset")
            d.click("OPPO Find X9s · 国际版","text");d.click("使用预设","text");self.save()
            profile=self.profile(B)
            check(profile["values"]["model"]=="CPH2873" and profile["values"]["width"]=="1256","Wrong OPPO preset")
            check(profile["values"]["imei"]!=profile["values"]["imei2"],"Slot identifiers collide")
            return self.compare(profile,self.read(B,cold=True))
        self.case("D03-oppo-preset",preset)
        self.open_editor();d.screenshot(str(OUT/"machine-editor-0.4.0.png"));d.click("device-back")
    def runtime(self):
        d=self.d
        def edits():
            original=self.profile();self.open_editor()
            d.tap(self.find_edit("model"));d.click("device-dialog-preset");d.click("OPPO Find X9s · 国际版","text")
            check(d.find("device-input:model").get("text")=="CPH2873","Single-field preset not filled")
            d.click("更新草稿","text");self.save()
            updated=self.profile()
            check(updated["values"]["model"]=="CPH2873" and updated["values"]["imei"]==original["values"]["imei"],"Single preset replaced unrelated fields")
            self.open_editor();self.edit("model",original["values"]["model"]);self.edit("meid",on=False);self.save()
            before=self.profile();self.open_editor();d.click("device-random-all");d.click("更新","text");self.save()
            after=self.profile()
            check(after["values"]["imei"]!=before["values"]["imei"] and after["values"]["serial"]!=before["values"]["serial"],"Group random did not update identifiers")
            for key in ["meid","model","latitude","longitude"]:
                check(after["values"][key]==before["values"][key],"Group random changed unselected/nonrandom "+key)
            self.open_editor();self.edit("meid",on=True);self.save()
            return {"singleFieldPreset":True,"unrelatedFieldsRetained":True,"selectedRandomOnly":True}
        self.case("D04-single-preset-group-random",edits)
        def stable():
            p=self.profile();first=self.read(cold=True);second=self.read()
            for key in ["imei","imei2","serial","android_id","wifi_mac","bssid"]:
                check(first["reads"][key]==second["reads"][key],"Ordinary reads regenerate "+key)
            check(first["pid"]==second["pid"],"Stable read changed PID")
            return {"samePid":first["pid"],"stableFields":p["selected"],"observed":second}
        self.case("D05-stable-reads",stable)
        def live_fields():
            before=self.read();self.open_editor()
            changes={"android_id":secrets.token_hex(8),"oaid":str(uuid.uuid4()),
                "latitude":"22.5431","longitude":"114.0579"}
            for key,value in changes.items():self.edit(key,value)
            self.save();p=self.profile();after=self.revision_read(p)
            for key in ["android_id","latitude","longitude"]:self.live(before,after,p,key)
            check(after["reads"]["android_id_cursor"]["value"]==changes["android_id"],"Android ID cursor mismatch")
            # AOSP lacks vivo service; verify live OAID on the debug SDK fixture independently.
            a0=self.read(A,cold=True);self.open_editor(A)
            if d.find("device-enabled").get("checked")!="true":d.click("device-enabled")
            self.edit("oaid",changes["oaid"]);self.save()
            ap=self.profile(A);a1=self.revision_read(ap,A)
            check(a0["pid"]==a1["pid"],"Enabling live profile restarted debug target")
            fixtures=a1["reads"]["fixtures"].get("value")
            check(fixtures and fixtures["msa"]["oaid"]==changes["oaid"],"MSA concrete supplier not spoofed")
            check(fixtures["xiaomi"]["oaid"]==changes["oaid"],"Xiaomi adapter mismatch")
            check(fixtures["heytap"]["oaid"]==changes["oaid"],"HeyTap adapter mismatch")
            for route in ["msa","xiaomi","heytap"]:
                for key in ["vaid","aaid"]:check(fixtures[route][key]==ap["values"][key],"Independent ID mismatch")
            check(fixtures["msa"]["ordinary"]=="ordinary-supplier" and fixtures["heytap"]["ordinary"]=="fixture-heytap-OTHER","Ordinary SDK method changed")
            check(a1["reads"]["gaid"]["value"]==ap["values"]["gaid"],"GAID adapter mismatch")
            check(a1["reads"]["oaid"]["value"]==changes["oaid"],"Named vivo cursor fixture mismatch")
            return {"primary":after,"debugFixture":a1,"realOEMServiceValidated":False}
        self.case("D05-D10-live-fields-OEM-fixtures",live_fields)
        def isolation():
            pa=self.profile(A);pb=self.profile(B)
            a=self.read(A,cold=True);b=self.read(B,cold=True);c=self.read(cold=True)
            check(a["reads"]["imei"]["value"]==pa["values"]["imei"],"A profile mismatch")
            check(b["reads"]["imei"]["value"]==pb["values"]["imei"],"B profile mismatch")
            check(len({a["reads"]["imei"]["value"],b["reads"]["imei"]["value"],c["reads"]["imei"]["value"]})==3,"Apps share identifiers")
            other=self.read(process=True)
            check(other["pid"]!=c["pid"],"Secondary process not launched")
            check(other["reads"]["imei"]["value"]==c["reads"]["imei"]["value"],"Same package processes differ")
            d.home_settings();d.click("custom:"+B,scroll=True);d.click("remove-custom",scroll=True)
            d.click("android:id/button1","resource-id");d.find("add-app")
            off=self.read(B,cold=True)
            check(not off["module"]["deviceEnabled"] and self.profile(B) is None,"Deleting customization retained profile")
            check(set(off["module"]["enabled"])==set(METHODS),"Delete altered legacy defaults")
            return {"appA":a,"appB":b,"primary":c,"samePackageOtherProcess":other,"BdeletedDefault":off,"UIDsIndependent":True}
        self.case("D07-apps-processes-delete",isolation)
        def paths():
            p=self.profile();r=self.read(cold=True);v=p["values"];reads=r["reads"]
            native=reads["native"]["value"]
            for key,id in {"ro.product.model":"model","ro.product.brand":"brand","ro.product.manufacturer":"manufacturer",
                "ro.build.fingerprint":"fingerprint","ro.serialno":"serial","ro.hardware":"hardware"}.items():
                check(reads["java_properties"]["value"][key]==v[id],"Java property mismatch "+key)
                for route,value in native["properties"][key].items():
                    if value is not None:check(value==v[id],"Native property mismatch "+key+"/"+route)
            for name,mac in native["interfaces"].items():
                if name.startswith(("eth","wlan")):check(mac.lower()==v["wifi_mac"].lower(),"Native interface mismatch")
            for name,mac in reads["java_macs"]["value"].items():
                if name.startswith(("eth","wlan")):check(mac.lower()==v["wifi_mac"].lower(),"Java interface mismatch")
            f=self.read(A,cold=True)["reads"]["fixtures"]["value"]
            for key in ["latitude","longitude","accuracy"]:
                check(float(f["location"]["callback"][key])==float(self.profile(A)["values"][key]),"Location callback getter mismatch")
            check(f["location"]["serializedRawLatitude"]==float(self.profile(A)["values"]["latitude"])
                and f["location"]["serializedRawLongitude"]==float(self.profile(A)["values"]["longitude"]),"Parcel retained raw coordinates")
            check(f["cell"]["serializedRawCi"]==int(self.profile(A)["values"]["cid"]),"Cell Parcel retained raw ID")
            check("error" not in f["nmea"] and "3113.8240,N,12128.4220,E" in f["nmea"].get("message",""),"NMEA adapter did not replace coordinates: "+str(f["nmea"]))
            check(f["location"]["timeControl"]==123456 and f["location"]["providerControl"]=="fixture","Ordinary location metadata changed")
            check(f["parcelControl"]=="ordinary-binder-string" and f["parcelIntControl"]==42,"Ordinary Parcel changed")
            for stage,row in r["early"].items():
                check(isinstance(row,dict) and row["model"]==v["model"] and row["androidId"]==v["android_id"],"Early profile missing "+stage)
            return {"nativeAndJava":r,"syntheticObjects":f,"modemOrOEMCallback":False}
        self.case("D08-D12-multiple-paths",paths)
        def fieldoff():
            before=self.read(A,cold=True);self.open_editor(A);self.edit("oaid",on=False);self.save()
            p=self.profile(A);after=self.revision_read(p,A)
            check(before["pid"]==after["pid"],"Field-off restarted reader")
            check(after["reads"]["fixtures"]["value"]["msa"]["oaid"]=="fixture-msa-oaid","OAID field-off retained spoof")
            check(after["reads"]["fixtures"]["value"]["msa"]["vaid"]==p["values"]["vaid"],"OAID affected VAID")
            self.open_editor(A);d.click("device-enabled");self.save();off=self.revision_read(self.profile(A),A)
            check(not off["module"]["deviceEnabled"],"Master switch not disabled")
            check(off["reads"]["model"]["value"]==BuildModel,"Static model failed to restore")
            return {"fieldOff":after,"masterOff":off,"samePid":off["pid"]}
        BuildModel=self.report["cases"]["D01-upgrade-default"]["evidence"]["reads"]["model"]["value"]
        self.case("D06-fieldoff-masteroff",fieldoff)
        def environment():
            self.open_editor()
            for key in ["total_ram","storage","timezone","language","hide_sensors","drm_id"]:self.edit(key,on=True)
            self.save();p=self.profile();r=self.read(cold=True);self.compare(p,r)
            check(r["reads"]["ordinary"]["value"]["localeExplicit"]=="en-US","Explicit Locale changed")
            check(r["reads"]["ordinary"]["value"]["timezoneExplicit"]=="UTC","Explicit timezone changed")
            for key in ["total_ram","storage","timezone","language","hide_sensors","drm_id"]:
                self.open_editor();self.edit(key,on=False);self.save()
            return {"observed":r,"optionalFieldsDisabledAfter":True}
        self.case("D14-optional-environment",environment)
        def rotation():
            p=self.profile();self.rotate(1);r=self.read(cold=True)
            check(str(r["reads"]["width"]["value"])==p["values"]["height"],"Landscape width not swapped")
            check(str(r["reads"]["height"]["value"])==p["values"]["width"],"Landscape height not swapped")
            d.find("machine-summary");d.screenshot(str(OUT/"machine-landscape-0.4.0.png"))
            self.rotate(0);portrait=self.read()
            check(str(portrait["reads"]["width"]["value"])==p["values"]["width"],"Portrait width not restored")
            return {"landscape":r,"portrait":portrait,"systemWm":d.shell("wm","size")}
        self.case("D13-display-rotation",rotation)
        def sampling():
            first=self.read()
            path="/data/user/0/"+PRIMARY+"/files/machine-result.json"
            def periodic():
                value=json.loads(d.shell("cat",path))
                return value if value["timestamp"]>first["timestamp"] else None
            next=self.wait(periodic,"Foreground timer did not sample again",timeout=8)
            check(next["pid"]==first["pid"] and next["timestamp"]>first["timestamp"],"Foreground sample did not update")
            interval=next["timestamp"]-first["timestamp"]
            check(1600<=interval<=4500,"Unexpected autonomous sampling interval: "+str(interval))
            d.shell("input","keyevent","HOME")
            # Wait for already queued work before establishing the paused baseline.
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:d.shell("pidof",PRIMARY)
            paused=d.shell("cat",path)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:d.shell("pidof",PRIMARY)
            check(d.shell("cat",path)==paused,"Background polling continued")
            resumed=self.read();check(resumed["timestamp"]>next["timestamp"],"Resume did not refresh")
            d.screenshot(str(OUT/"machine-verifier-0.4.0.png"))
            return {"before":first["timestamp"],"after":next["timestamp"],"autonomousIntervalMs":interval,
                "activityRelaunchBetweenTimerSamples":False,"backgroundStops":True,"resume":resumed["timestamp"]}
        self.case("D15-two-second-foreground",sampling)
    def final_checks(self):
        """IMEI edits retain real UI; all-field opt-out uses a dedicated bulk fixture."""
        d=self.d
        original=self.profile()
        check(original and original["enabled"],"Final field check requires the active profile")
        def cached_binder():
            try:
                self.open_editor()
                d.click("device-enabled")
                self.save()
                baseline=self.read(cold=True)
                pid=str(baseline["pid"])
                check(not baseline["module"]["deviceEnabled"],"Cached test must call unspoofed APIs")
                check(baseline.get("phoneWorker",{}).get("pid") not in {None,baseline["pid"]},
                    "Phone APIs were not read in a separate process")
                self.wait(lambda: PRIMARY+":phone_reads" not in d.shell("ps","-A","-o","NAME"),
                    "Phone worker retained pending Binder calls",timeout=8)
                binder=d.shell("cat","/dev/binderfs/binder_logs/proc/"+pid)
                phone_pid=d.shell("pidof","com.android.phone")
                check(not re.search(r"outgoing transaction .* to "+phone_pid+r":",binder),
                    "Main Activity retained a synchronous phone Binder transaction")
                d.shell("input","keyevent","HOME")
                def frozen():
                    check(pid in d.shell("pidof",PRIMARY).split(),"Cached reader was terminated")
                    log=d.adb("logcat","-d","-b","system","-s","ActivityManager")
                    rows=[line for line in log.splitlines() if "freezing "+pid+" "+PRIMARY in line]
                    return rows[-1] if rows else None
                freeze=self.wait(frozen,"System did not attempt to freeze the cached process",timeout=110)
                # The previous failure exhausted freeze retries within five seconds.
                finish=time.monotonic()+8
                while time.monotonic()<finish:
                    check(pid in d.shell("pidof",PRIMARY).split(),"Reader died during Binder freezing")
                    time.sleep(.25)
                after=self.read()
                check(after["pid"]==baseline["pid"],"Cached reader did not resume in the same process")
                return {"samePid":after["pid"],"unspoofedPhoneSample":baseline,
                    "phoneWorkerReleased":True,"mainBinder":binder,"systemFreeze":freeze,"resumed":after}
            finally:
                self.open_editor()
                if d.find("device-enabled").get("checked")!="true":d.click("device-enabled")
                self.save()
                check(self.profile()["values"]==original["values"],"Cached check changed profile values")
        self.case("D15-cached-binder",cached_binder)
        def manual_imei():
            # Public Luhn example; never derived from a user's physical device.
            manual="490154203237518"
            try:
                before=self.read(cold=True)
                self.open_editor()
                self.edit("imei",manual,on=True)
                self.save()
                profile=self.profile()
                after=self.revision_read(profile)
                check(profile["values"]["imei"]==manual,"Valid manual IMEI was not saved")
                return self.live(before,after,profile,"imei")
            finally:
                self.open_editor()
                self.edit("imei",original["values"]["imei"],on=True)
                self.save()
                check(self.profile()["values"]==original["values"],"Manual IMEI did not restore")
        self.case("D04-valid-manual-imei",manual_imei)
        def all_off():
            try:
                d.batch_profile(PRIMARY,dict(original,enabled=False))
                baseline=self.read(cold=True)
                check(not baseline["module"]["deviceEnabled"],"Master-off baseline is still active")
                check(baseline.get("phoneWorker",{}).get("revision")==baseline["module"]["deviceRevision"],
                    "Master-off phone worker does not match the sampled revision")
                active=d.batch_profile(PRIMARY,original)
                activated=self.revision_read(active)
                self.compare(active,activated)
                check(activated["pid"]==baseline["pid"],"Profile activation restarted the reader")
                check(activated["module"]["deviceNative"],"Profile revision was published before native initialization")
                native=activated["reads"]["native"]["value"]["properties"]
                for property_name,field in [("ro.product.model","model"),("ro.product.brand","brand")]:
                    check(len(native[property_name])==3 and
                        all(value==active["values"][field] for value in native[property_name].values()),
                        "First active snapshot retained original native values: "+property_name)
                print("PASS first active snapshot: same PID, Java and three native property paths",flush=True)
                empty=d.batch_profile(PRIMARY,dict(original,selected=[]))
                check(empty["enabled"] and not empty["selected"],"Empty whitelist was not saved")
                observed=self.revision_read(empty)
                check(observed["pid"]==baseline["pid"],"All-fields-off restarted the reader")
                check(observed["module"]["deviceEnabled"] and not observed["module"]["deviceSelected"],
                    "Reader retained a selected field")
                fields=re.findall(r'f\("([^"]+)","[^"]+","([^"]+)"',
                    (ROOT/"shared/java/io/github/lwtdzh/deviceprofile/DeviceField.java").read_text())
                check(len(fields)==46,"All-fields check does not match the shared catalog")
                diagnostic={"baseline":baseline,"activated":activated,"observed":observed,
                    "profile":empty,"artifacts":self.report["artifacts"]}
                (OUT/"machine-all-fields-off-diagnostic-0.4.0.json").write_text(
                    json.dumps(diagnostic,ensure_ascii=False,indent=2)+"\n")
                for key,label in fields:
                    before=baseline["reads"][key]
                    after=observed["reads"][key]
                    if "error" in before:
                        check(after.get("error")==before["error"],"Field-off error changed: "+key)
                    else:
                        check("error" not in after and after.get("value")==before.get("value"),
                            "Field-off differs: "+key+" "+json.dumps({"before":before,"after":after},ensure_ascii=False))
                check(baseline["reads"]["java_properties"]["value"]==observed["reads"]["java_properties"]["value"],
                    "Empty whitelist retained Java property overrides")
                check(baseline["reads"]["native"]["value"]["properties"]==
                    observed["reads"]["native"]["value"]["properties"],
                    "Empty whitelist retained native property overrides")
                print("PASS all 46 original values/errors and Java/native properties restored",flush=True)
                return {"fields":46,"masterRemainsOn":True,"selectedFields":[],
                    "configuration":"dedicated-emulator atomic bulk fixture",
                    "baseline":baseline,"observed":observed,"originalValuesRetained":True,
                    "javaAndThreeNativePropertyPathsRestored":True,"samePid":observed["pid"],
                    "enabledProfileObservedBeforeClearing":activated}
            finally:
                d.batch_profile(PRIMARY,original)
                restored=self.profile()
                check(restored["enabled"]==original["enabled"] and restored["values"]==original["values"]
                    and set(restored["selected"])==set(original["selected"]),"Original profile did not restore")
        self.case("D06-all-fields-off",all_off)
    def restore(self):
        d=self.d;original=json.loads((STATE/"state.json").read_text())
        for pkg in PACKAGES:
            d.shell("am","force-stop",pkg)
            if pkg not in original["packages"]:
                if "package:"+pkg in d.shell("pm","list","packages").splitlines():d.adb("uninstall",pkg)
                continue
            saved=original["packages"][pkg];d.adb("install","--no-incremental","-r","-d",saved["apk"])
            temporary="/data/local/tmp/machine-restore.tar";d.adb("push",saved["data"],temporary)
            folder="/data/user/0/"+pkg
            uid=re.search(r"userId=(\d+)",d.shell("dumpsys","package",pkg)).group(1)
            d.shell("tar","-xf",temporary,"-C",folder);d.shell("chown","-R",uid+":"+uid,folder)
            d.shell("restorecon","-R",folder);d.shell("rm","-f",temporary)
        for module in original["modules"]:
            current={(r["APP_PACKAGE"],r["USER_ID"]) for r in d.cli("scope","ls",module["PACKAGE"])}
            expected={(r["APP_PACKAGE"],r["USER_ID"]) for r in original["scopes"][module["PACKAGE"]]}
            for pkg,user in current-expected:d.cli("scope","rm",module["PACKAGE"],pkg+"/"+str(user))
            for pkg,user in expected-current:d.cli("scope","add",module["PACKAGE"],pkg+"/"+str(user))
            d.cli("modules","enable" if module["STATUS"]=="enabled" else "disable",module["PACKAGE"])
            check(d.cli("scope","ls",module["PACKAGE"])==original["scopes"][module["PACKAGE"]],"Scope restore mismatch")
        for ns,values in original["settings"].items():
            for key,value in values.items():
                d.shell("settings","delete",ns,key) if value=="null" else d.shell("settings","put",ns,key,value)
                check(d.shell("settings","get",ns,key)==value,"Settings restore mismatch")
        if d.shell("getenforce")!=original["mode"]:d.shell("setenforce","1" if original["mode"]=="Enforcing" else "0")
        d.shell("rm","-f",d.ui_path)
        self.case("D18-restored",lambda:{"settings":True,"scopes":True,"originalPackages":True,"mode":original["mode"]})
    def events(self):
        """A real SystemUI save and both registered capture callbacks, with machine on."""
        d=self.d
        media="content://media/external/images/media"
        def ids():
            return set(map(int,re.findall(r"_id=(\d+)",d.shell("content","query","--uri",media,"--projection","_id"))))
        created=set()
        profile=self.profile()
        check(profile and profile["enabled"],"Machine profile required for real screenshot regression")
        def clipboard(command):
            path="/data/user/0/"+B+"/files/services-result.json"
            d.shell("rm","-f",path)
            d.shell("am","start","-W","--activity-clear-top","-n",
                B+"/io.github.lwtdzh.screenshotdetector.FixtureActivity","--es","command",command)
            def ready():
                raw=d.shell("sh","-c","test ! -f "+path+" || cat "+path)
                if not raw:return None
                value=json.loads(raw)
                return value if isinstance(value.get("clipboardHas"),bool) else None
            self.wait(ready,"Clipboard preservation fixture did not finish",timeout=10)
        def run():
            stages={}
            clipboard("clipboard-save")
            try:
                for protected,label in [(False,"off"),(True,"on"),(False,"off-restored")]:
                    d.batch_policy(PRIMARY,{"screenshot"} if protected else set())
                    initial=d.start_probe(PRIMARY,"shot")
                    check(initial["module"]["deviceEnabled"],"Machine profile was lost")
                    before=ids()
                    d.shell("input","-d","0","keyevent","SYSRQ")
                    added=self.wait(lambda:ids()-before,"SystemUI did not save a real screenshot",timeout=15)
                    created.update(added)
                    def observed():
                        value=d.read_shot(PRIMARY)
                        return value if value.get("screen_capture_callbacks",0)>0 and value.get("raw_screen_capture_callbacks",0)>0 else None
                    if protected:
                        deadline=time.monotonic()+4
                        while time.monotonic()<deadline:d.shell("pidof",PRIMARY)
                        value=d.read_shot(PRIMARY)
                        check(value["screen_capture_callbacks"]==0 and value["raw_screen_capture_callbacks"]==0,"Real capture callback leaked")
                    else:value=self.wait(observed,"Real capture callback missing",timeout=10)
                    stages[label]={"systemSaved":True,"callbacks":value["screen_capture_callbacks"],
                        "rawCallbacks":value["raw_screen_capture_callbacks"],"machineRevision":value["module"]["deviceRevision"]}
                    self.wait(lambda:"com.android.systemui.screenshot" not in d.shell("dumpsys","window","windows"),
                        "SystemUI screenshot overlay did not finish",timeout=15)
                return stages
            finally:
                d.shell("am","force-stop",PRIMARY)
                for ident in created:d.shell("content","delete","--uri",media+"/"+str(ident))
                clipboard("clipboard-restore")
                d.batch_policy(PRIMARY,set(METHODS))
        self.case("D16-actual-system-screenshot",run)
    def ownership(self):
        """Nested callbacks exercise independent, SELinux and developer property hooks."""
        d=self.d;profile=self.profile()
        def run():
            observed={}
            try:
                for enabled,label in [(set(),"independent"),({"selinux"},"selinux"),
                    ({"debug"},"developer"),(set(METHODS),"combined")]:
                    d.batch_policy(PRIMARY,enabled)
                    value=self.read(cold=True);self.compare(profile,value)
                    for key,field in [("ro.product.model","model"),("ro.product.brand","brand")]:
                        for route,result in value["reads"]["native"]["value"]["properties"][key].items():
                            check(result==profile["values"][field],"Native ownership baseline differs: "+key+"/"+route)
                    observed[label]=value["reads"]["native"]
                return observed
            finally:d.batch_policy(PRIMARY,set(METHODS))
        self.case("D08-native-callback-ownership",run)
    def regression(self):
        """Reuse existing native/method assertions; retain current machine profile throughout."""
        self.budget_seconds=1200
        import importlib.util
        spec=importlib.util.spec_from_file_location("machine_selinux",ROOT/"scripts/selinux-test.py")
        legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
        legacy.VERSION="0.4.0"
        legacy.STATE=STATE/"regression-original"
        runner=legacy.Run()
        runner.only=set(self.only)
        profile=self.profile()
        check(profile and profile["enabled"],"Machine must be on before the regression")
        runner.resume_revision=profile["revision"]
        if not (legacy.STATE/"state.json").exists():runner.capture()
        if runner.report["cases"].get("L01-prepare",{}).get("artifacts")==runner.report["artifacts"]:
            runner.validate_setup()
        else:
            runner.prepare()
        original_sample=runner.sample
        def sample(*args,**kwargs):
            result=original_sample(*args,**kwargs)
            pkg=kwargs.get("pkg",args[1] if len(args)>1 else PRIMARY)
            if pkg==PRIMARY and kwargs.get("injected",True):
                check(result["module"].get("deviceEnabled"),"Regression accidentally disabled machine spoofing")
                check(result["module"]["deviceRevision"]==profile["revision"],"Regression changed machine profile")
            return result
        runner.sample=sample
        d=self.d
        for mode in ["Permissive","Enforcing"]:
            name="D17-uninjected-"+mode.lower()
            if runner.pending(name):
                d.shell("setenforce","0" if mode=="Permissive" else "1")
                d.scope(MODULE,PRIMARY,False)
                runner.case(name,lambda mode=mode:sample(set(),injected=False,mode=mode))
            for enabled,label in [(set(),"all-off"),({"selinux"},"selinux-only"),(set(METHODS),"all-on")]:
                name="D17-"+mode.lower()+"-"+label
                if runner.pending(name):
                    d.shell("setenforce","0" if mode=="Permissive" else "1")
                    d.scope(MODULE,PRIMARY,True);d.batch_policy(PRIMARY,enabled)
                    runner.case(name,lambda enabled=enabled,mode=mode:sample(enabled,mode=mode))
        d.scope(MODULE,PRIMARY,True)
        d.shell("setenforce","0")
        runner.matrix()
        d.batch_policy(PRIMARY,set(METHODS))
        def ordinary():
            value=d.start_probe(PRIMARY)
            check(value["module"].get("deviceEnabled"),"Full state probe lost machine profile")
            for key in ["foreignReadDenied","otherPackageDenied","writeDenied","insertDenied","updateDenied","deleteDenied","queryDenied"]:
                check(value[key] is True,"Provider isolation failed "+key)
            check(value["internet"]==204,"Ordinary HTTPS failed")
            check(value["native"]["listLifetimeOk"] and value["native"]["getpidOk"],"Ordinary native network failed")
            return value
        runner.case("D07-D16-provider-HTTPS-native-controls",ordinary)
        runner.native()
        if self.only:
            return  # Keep original fixtures and snapshot for remaining scoped cases.
        if not self.only:
            self.case("D16-D17-legacy-regression",lambda:{"report":runner.path.name,"machineRevision":profile["revision"],
                "combinations":64,"realSELinuxModes":["Permissive","Enforcing"],"nativeScreenshotFDandClone":True})
        # Restore regression settings/services, keeping tested APKs and machine profiles.
        saved=json.loads((legacy.STATE/"state.json").read_text())
        d.shell("am","force-stop",B)
        d.shell("rm","-rf",legacy.FIXTURE)
        d.shell("setenforce","1" if saved["mode"]=="Enforcing" else "0")
        for key,value in saved["settings"].items():
            d.shell("settings","delete","global",key) if value=="null" else d.shell("settings","put","global",key,value)
        d.shell("settings","delete","system","font_scale") if saved["fontScale"]=="null" else d.shell("settings","put","system","font_scale",saved["fontScale"])
        self.case("D17-regression-fixtures-clean",lambda:{"vpnStopped":"tun0" not in d.shell("ip","link","show"),
            "fixtureAbsent":not d.shell("sh","-c","test ! -e "+legacy.FIXTURE+" || echo present")})

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("phase",choices=["capture","prepare","install","smoke","ui","runtime","regression","events","ownership","final_checks","restore"])
    parser.add_argument("--case",action="append",default=[])
    args=parser.parse_args();run=Run();run.only=set(args.case);getattr(run,args.phase)()
