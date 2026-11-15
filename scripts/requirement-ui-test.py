#!/usr/bin/env python3
"""0.4.1 affected UI/sampling checks only; historical 64-combination evidence is untouched."""
import hashlib
import importlib.util
import json
import pathlib
import re
import time
from test_device import MODULE, PRIMARY
from test_evidence import case_inputs

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
spec=importlib.util.spec_from_file_location("machine_cases",ROOT/"scripts/machine-test.py")
machine=importlib.util.module_from_spec(spec);spec.loader.exec_module(machine)
machine.STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/requirement-ui-0.4.1"
machine.REPORT=OUT/"requirement-ui-0.4.1-results.json"
machine.PACKAGES=(MODULE,PRIMARY)

class Audit(machine.Run):
    def restore(self):
        original=json.loads((machine.STATE/"state.json").read_text())
        # Remove only captured test-package files before restoring the complete snapshot.
        for pkg in original["packages"]:
            self.d.shell("am","force-stop",pkg)
            self.d.shell("sh","-c","find /data/user/0/"+pkg+
                         " -mindepth 1 -maxdepth 1 -exec rm -rf {} +")
        super().restore()
        for pkg,saved in original["packages"].items():
            path=self.d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
            assert self.d.shell("sha256sum",path).split()[0]==hashlib.sha256(pathlib.Path(saved["apk"]).read_bytes()).hexdigest()
        current={row["PACKAGE"]:row["STATUS"] for row in self.d.cli("modules","ls")}
        assert current=={row["PACKAGE"]:row["STATUS"] for row in original["modules"]}
        self.report["restoration"]={"originalAPKBytes":True,"completeDataSnapshotRestored":True,
                                    "modulesAndScopes":True,"settings":True,"mode":self.d.shell("getenforce")}
        machine.REPORT.write_text(json.dumps(self.report,ensure_ascii=False,indent=2)+"\n")
    def sample(self,filename="machine-result.json",after=0):
        def ready():
            raw=self.d.shell("sh","-c","test ! -f /data/user/0/"+PRIMARY+"/files/"+filename+
                             " || cat /data/user/0/"+PRIMARY+"/files/"+filename)
            try:
                value=json.loads(raw)
                return value if value["timestamp"]>after else None
            except (ValueError,KeyError):return None
        return self.wait(ready,"No autonomous sample: "+filename,timeout=8)
    def home(self):
        self.d.shell("am","start","-W","--activity-clear-top","-n",PRIMARY+"/.MainActivity")
        self.d.find("machine-overview:imei")
        return self.sample("machine-home-result.json")
    def search_detail(self,value):
        d=self.d;node=d.find("machine-field-search");d.tap(node)
        text=node.get("text","");d.shell("input","keyevent","KEYCODE_MOVE_END")
        if text:d.shell("input","keyevent",*(["KEYCODE_DEL"]*len(text)))
        if value:d.shell("input","text",value)
        d.back()
    def run_checks(self):
        d=self.d
        if not (machine.STATE/"state.json").exists():
            if machine.STATE.exists() and not any(machine.STATE.iterdir()):machine.STATE.rmdir()
            self.capture()
        self.report["artifacts"]={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()
                                 for name in ["AppStateShield-0.4.1.apk","AppStateVerifier-0.4.1.apk"]}
        for pkg,name in [(MODULE,"AppStateShield-0.4.1.apk"),(PRIMARY,"AppStateVerifier-0.4.1.apk")]:
            d.adb("install","--no-incremental","-r",str(OUT/name))
        original=json.loads((machine.STATE/"state.json").read_text())
        for pkg in [MODULE,PRIMARY]:
            if pkg not in original["packages"]:d.shell("cmd","locale","set-app-locales",pkg,"--locales","zh-CN")
        for row in d.cli("modules","ls"):d.scope(row["PACKAGE"],PRIMARY,False)
        d.cli("modules","enable",MODULE);d.scope(MODULE,PRIMARY,True)
        d.shell("settings","put","global","hidden_api_policy","1")
        # Only our synthetic target; original complete preferences are captured above.
        off={"schema":1,"enabled":False,"preset":"custom","values":{},"selected":[]}
        d.batch_profile(PRIMARY,off)
        self.input_metadata=case_inputs(d,self.report["artifacts"])
        baseline=self.read(cold=True)
        def default():
            assert baseline["module"]["injected"] and not baseline["module"]["deviceEnabled"]
            for pkg,name in [(MODULE,"AppStateShield"),(PRIMARY,"AppStateVerifier")]:
                path=d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
                assert d.shell("sha256sum",path).split()[0]==self.report["artifacts"][name+"-0.4.1.apk"]
                assert "versionName=0.4.1" in d.shell("dumpsys","package",pkg)
            return {"defaultOff":True,"baseline":baseline,"installedBytesMatch":True}
        self.case("U01-install-default",default)
        def homepage():
            first=self.home()
            nodes=d.nodes();names={n.get("content-desc") for n in nodes}
            assert {"machine-overview:"+key for key in ["imei","imei2","android_id","oaid","serial","model"]}<=names
            next_sample=self.sample("machine-home-result.json",first["timestamp"])
            interval=next_sample["timestamp"]-first["timestamp"]
            assert 1600<=interval<=4500 and next_sample["pid"]==first["pid"]
            for node in nodes:
                if node.get("content-desc") in {"machine-overview:imei","machine-overview:imei2"}:
                    assert node.get("text") not in {"","—","正在读取…","Reading…"}
            d.screenshot(str(OUT/"requirement-home-0.4.1.png"))
            d.shell("input","keyevent","HOME")
            paused=d.shell("cat","/data/user/0/"+PRIMARY+"/files/machine-home-result.json")
            time.sleep(2.3)
            assert d.shell("cat","/data/user/0/"+PRIMARY+"/files/machine-home-result.json")==paused
            self.home()
            return {"visibleIdentifiers":6,"autonomousIntervalMs":interval,"samePid":first["pid"],
                    "backgroundStops":True,"noActivityRelaunchBetweenSamples":True}
        self.case("U02-home-timer-and-pause",homepage)
        def detail():
            d.click("machine-probe",scroll=True);d.find("machine-read:imei")
            first=self.sample()
            ids=re.findall(r'f\("([^"]+)","', (ROOT/"shared/java/io/github/lwtdzh/deviceprofile/DeviceField.java").read_text())
            assert len(ids)==46 and set(ids)<=set(first["reads"])
            self.search_detail("imei");names={n.get("content-desc") for n in d.nodes()}
            assert {"machine-read:imei","machine-read:imei2"}<=names
            assert "machine-read:model" not in names
            self.search_detail("native");d.find("machine-read:native_macs",scroll=True)
            native=d.find("machine-read:native_macs").get("text")
            assert "getifaddrs" in native
            self.search_detail("")
            d.screenshot(str(OUT/"requirement-identifiers-0.4.1.png"))
            newer=self.sample(after=first["timestamp"]);assert newer["pid"]==first["pid"]
            assert newer.get("phoneWorker",{}).get("revision")==newer["module"]["deviceRevision"]
            return {"readDirectory":46,"idsFirst":True,"searchFilters":True,"nativeMacReadable":True,
                    "phoneWorkerRevisionMatches":True}
        self.case("U03-detail-directory-search",detail)
        def editor():
            self.open_editor()
            assert d.find("device-enabled").get("checked")=="false"
            d.click("device-enabled");d.find("device-preset")
            self.save();profile=self.profile()
            assert profile["enabled"] and profile["values"]["imei"] and profile["values"]["imei2"]
            self.open_editor();d.tap(self.find_edit("imei"))
            assert d.find("device-dialog-preset") is not None and d.find("device-dialog-random") is not None
            old=d.find("device-input:imei").get("text")
            d.click("device-dialog-random")
            assert d.find("device-input:imei").get("text")!=old
            d.click("取消","text");d.click("device-back");assert self.profile()==profile
            self.open_editor();d.tap(self.find_edit("imei"));d.click("device-dialog-preset")
            d.click("OPPO Find X9s · 国际版","text")
            generated=d.find("device-input:imei").get("text");assert generated!=old and len(generated)==15
            d.click("更新草稿","text");self.save();saved=self.profile()
            assert saved["values"]["imei"]==generated
            assert {k:v for k,v in saved["values"].items() if k!="imei"}=={
                k:v for k,v in profile["values"].items() if k!="imei"}
            return {"defaultOffInEditor":True,"firstPresetGeneratedTwoIMEIs":True,
                    "singleRandomFieldPreset":True,"onlyIMEIChanged":True,"cancelDoesNotSave":True}
        self.case("U04-editor-preset-and-cancel",editor)
        def row_random():
            profile=self.profile();profile["selected"].remove("serial");d.batch_profile(PRIMARY,profile)
            self.open_editor();self.find_edit("serial")
            d.click("device-random:serial",scroll=True);self.save()
            after=self.profile()
            assert "serial" in after["selected"] and after["values"]["serial"]!=profile["values"]["serial"]
            return {"unselectedFieldAutoSelected":True,"newValueSaved":True}
        self.case("U05-row-random-selects",row_random)
        def integration():
            profile=self.profile()
            # Isolate a single ID so the test does not manipulate display/environment fields.
            profile["selected"]=["imei"];profile["enabled"]=True
            profile=d.batch_profile(PRIMARY,profile);before=self.read()
            assert before["module"]["deviceEnabled"] and before["reads"]["imei"]["value"]==profile["values"]["imei"]
            self.open_editor();self.edit("imei","490154203237518",True);self.save()
            saved=self.profile();after=self.revision_read(saved)
            assert after["pid"]==before["pid"] and after["reads"]["imei"]["value"]=="490154203237518"
            assert after["reads"]["ordinary"]["value"]["file"]=="ordinary-device-control"
            saved["enabled"]=False;off_profile=d.batch_profile(PRIMARY,saved)
            restored=self.revision_read(off_profile)
            assert not restored["module"]["deviceEnabled"] and restored["pid"]==before["pid"]
            assert restored["reads"]["imei"].get("value")==baseline["reads"]["imei"].get("value")
            assert restored["reads"]["imei"].get("error")==baseline["reads"]["imei"].get("error")
            self.search_detail("imei")
            nodes=d.nodes();row=next(n for n in nodes if n.get("content-desc")=="machine-read:imei")
            if restored["reads"]["imei"].get("error")=="SecurityException":
                assert "权限" in row.get("text") or "permission" in row.get("text")
            return {"enabled":before,"updated":after,"disabled":restored,"samePid":before["pid"],
                    "manualIMEIApplied":True,"originalValueOrErrorRestored":True}
        self.case("U06-enable-manual-update-disable",integration)
        def legacy():
            d.shell("am","start","-W","--activity-clear-top","-n",
                    PRIMARY+"/io.github.lwtdzh.devicestateprobe.ProbeActivity","--es","action","selinux")
            d.find("machine-overview:imei");d.find("machine-probe",scroll=True)
            first=self.sample("machine-home-result.json")
            next_sample=self.sample("machine-home-result.json",first["timestamp"])
            assert first["pid"]==next_sample["pid"]
            d.click("machine-probe",scroll=True);d.find("machine-read:imei")
            switched=self.sample(after=next_sample["timestamp"])
            assert switched["pid"]==next_sample["pid"] and switched.get("phoneWorker")
            return {"legacyHasOverviewAndEntry":True,"autonomousRefresh":True,"switchKeepsPid":switched["pid"],
                    "phoneWorkerRepliesAfterSwitch":True}
        self.case("U07-legacy-entry-switch",legacy)
        def active_visible():
            profile={"schema":1,"enabled":True,"preset":"custom","selected":["imei"],
                     "values":{"imei":"490154203237518"}}
            profile=d.batch_profile(PRIMARY,profile)
            detail=self.revision_read(profile)
            assert detail["reads"]["imei"]["value"]=="490154203237518"
            self.search_detail("imei")
            assert "490154203237518" in d.find("machine-read:imei").get("text")
            d.screenshot(str(OUT/"requirement-imei-active-0.4.1.png"))
            before=int(time.time()*1000);self.home()
            home=self.sample("machine-home-result.json",after=before)
            assert home["pid"]==detail["pid"] and "490154203237518" in d.find("machine-overview:imei").get("text")
            d.screenshot(str(OUT/"requirement-home-active-0.4.1.png"))
            return {"homeAndDetailShowObservedIMEI":True,"samePid":home["pid"],
                    "observedIMEIIsPublicTestExample":True}
        self.case("U08-visible-active-IMEI",active_visible)

if __name__=="__main__":
    run=Audit()
    try:run.run_checks()
    finally:
        if (machine.STATE/"state.json").exists():run.restore()
