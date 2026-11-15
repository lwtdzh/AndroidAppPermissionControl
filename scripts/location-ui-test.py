#!/usr/bin/env python3
"""Affected 0.4.2 cases only. Real UI for drafts; atomic fixtures for gate combinations."""
import hashlib
import json
import pathlib
import time
import importlib.util
import re
from test_device import MODULE, PRIMARY, ADB
from test_evidence import case_inputs

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"verification"
spec=importlib.util.spec_from_file_location("requirement_cases",ROOT/"scripts/requirement-ui-test.py")
requirement=importlib.util.module_from_spec(spec);spec.loader.exec_module(requirement)
machine=requirement.machine
machine.STATE=pathlib.Path.home()/"Library/Application Support/ScreenshotShield/location-ui-0.4.2"
machine.REPORT=OUT/"location-ui-0.4.2-results.json"
machine.PACKAGES=(MODULE,PRIMARY)
VERSION="0.4.2"
CELLULAR={"imsi","iccid","phone","operator","mcc","mnc","lac","cid","tac","pci","signal"}
LOCATION={"latitude","longitude","accuracy"}
CASES=["L01-default-and-baseline","L02-region-UI-draft-save","L03-location-three-gates",
       "N01-present-SIM-coherence","N02-no-SIM-and-real-restoration","R01-category-refresh"]

class Audit(requirement.Audit):
    def search_editor(self,query):
        d=self.d;node=d.find("device-field-search",scroll=True);d.tap(node)
        text=node.get("text","")
        d.shell("input","keyevent","KEYCODE_MOVE_END")
        if text:d.shell("input","keyevent",*(["KEYCODE_DEL"]*len(text)))
        if query:d.shell("input","text",query)
        d.back()
    def switch_mode(self,mode):
        self.open_editor();self.search_editor("network")
        self.d.click("device-network-mode:"+mode,scroll=True);self.save()
        return self.profile()
    @staticmethod
    def value(sample,key):
        row=sample["reads"][key]
        assert "error" not in row,(key,row)
        return row.get("value")
    def assert_present(self,profile,sample):
        v=lambda k:self.value(sample,k)
        values=profile["values"]
        assert v("sim_state")==5 and v("sim_state_slot0")==5 and v("sim_state_slot1")==1
        assert v("sim_card_state")==11 and v("sim_application_state")==10 and v("has_sim") is True
        assert v("subscription_count")==1 and v("default_subscription")==1
        assert v("network_type")==v("voice_network_type")==13 and v("data_state")==2 and not v("roaming")
        assert v("sim_operator")==values["mcc"]+values["mnc"] and v("sim_operator_name")==values["operator"]
        assert v("sim_country")==v("network_country")=="cn"
        for key in CELLULAR:assert str(v(key))==values[key],(key,v(key),values[key])
        sub=v("subscriptions")
        assert len(sub)==1 and sub[0]["id"]==1 and sub[0]["slot"]==0
        for observed,key in [("iccid","iccid"),("mcc","mcc"),("mnc","mnc"),("carrier","operator"),("phone","phone"),
                             ("parcelIccid","iccid"),("parcelMcc","mcc"),("parcelMnc","mnc")]:
            assert sub[0][observed]==values[key],(observed,sub)
        service=v("service_state")
        assert service["state"]==0 and service["numeric"]==values["mcc"]+values["mnc"]
        assert service["operator"]==values["operator"] and len(service["registrations"])==2
        assert all(row["registered"] and row["technology"]==13 for row in service["registrations"])
        assert {row["domain"] for row in service["registrations"]}=={1,2}
        assert v("cells")==v("async_cells") and len(v("cells"))==1
        cell=v("cells")[0];assert cell["registered"]
        for observed,key in [("mcc","mcc"),("mnc","mnc"),("cid","cid"),("tac","tac"),("pci","pci"),
                             ("signal","signal"),("parcelCid","cid"),("parcelSignal","signal")]:
            assert str(cell[observed])==values[key],(observed,cell,values[key])

    def run_checks(self):
        d=self.d;self.budget_seconds=300
        if not (machine.STATE/"state.json").exists():self.capture()
        self.report["artifacts"]={f"{name}-{VERSION}.apk":hashlib.sha256((OUT/f"{name}-{VERSION}.apk").read_bytes()).hexdigest()
                                 for name in ["AppStateShield","AppStateVerifier"]}
        for name in self.report["artifacts"]:d.adb("install","--no-incremental","-r",str(OUT/name))
        original=json.loads((machine.STATE/"state.json").read_text())
        for row in d.cli("modules","ls"):d.scope(row["PACKAGE"],PRIMARY,False)
        d.cli("modules","enable",MODULE);d.scope(MODULE,PRIMARY,True)
        d.shell("settings","put","global","hidden_api_policy","1")
        for pkg in [MODULE,PRIMARY]:
            d.shell("cmd","locale","set-app-locales",pkg,"--locales","zh-CN")
        for permission in ["READ_PHONE_STATE","ACCESS_FINE_LOCATION","ACCESS_COARSE_LOCATION","BLUETOOTH_CONNECT"]:
            d.shell("pm","grant",PRIMARY,"android.permission."+permission)
        d.batch_profile(PRIMARY,{"schema":1,"enabled":False,"preset":"custom","values":{},"selected":[]})
        self.input_metadata=case_inputs(d,self.report["artifacts"])
        baseline=self.read(cold=True)
        self.report["baseline"]=baseline
        def default():
            assert baseline["module"]["injected"] and not baseline["module"]["deviceEnabled"]
            self.open_editor();assert d.find("device-enabled").get("checked")=="false"
            d.click("device-enabled");self.save()
            profile=self.profile()
            assert profile["networkMode"]=="no_sim" and not profile["locationEnabled"]
            assert len(profile["values"])==46
            for pkg,name in [(MODULE,"AppStateShield"),(PRIMARY,"AppStateVerifier")]:
                path=d.shell("pm","path",pkg).splitlines()[0].removeprefix("package:")
                assert d.shell("sha256sum",path).split()[0]==self.report["artifacts"][f"{name}-{VERSION}.apk"]
            return {"machineDefaultOff":True,"locationDefaultOff":True,"networkDefaultNoSIM":True,"profile":profile}
        result=self.case("L01-default-and-baseline",default)
        # Resume restores each prerequisite fixture explicitly, without re-running passed UI cases.
        profile=result["profile"];d.batch_profile(PRIMARY,profile)
        def region_ui():
            before=self.profile()
            self.open_editor();self.search_editor("location")
            assert d.find("device-location-enabled").get("checked")=="false"
            d.click("device-region-picker");d.find("device-region:0");d.find("device-region:1");d.find("device-region:2")
            assert "北京市" in d.find("device-region-preview").get("text")
            d.click("取消","text");d.click("device-back");assert self.profile()==before
            self.open_editor();self.search_editor("location");d.click("device-region-picker")
            d.click("device-region:2");d.click("西城区","text",scroll=True)
            assert "西城区" in d.find("device-region-preview").get("text")
            d.click("应用到草稿","text")
            assert d.find("device-location-enabled").get("checked")=="false"
            d.shell("settings","put","system","accelerometer_rotation","0")
            d.shell("settings","put","system","user_rotation","1")
            d.find("device-region-status",scroll=True)
            assert "西城区" in d.find("device-region-status").get("text")
            d.shell("settings","put","system","user_rotation","0")
            self.save();after=self.profile()
            assert not after["locationEnabled"] and after["regionId"]=="110102" and not after["regionOverrides"]
            changed={k for k in before["values"] if before["values"][k]!=after["values"][k]}
            assert changed<=LOCATION and {"latitude","longitude"}<=changed
            assert CELLULAR<set(after["values"])
            self.open_editor();self.search_editor("location");d.click("device-location-enabled")
            self.edit("latitude","39.915",True);self.save()
            manual=self.profile();assert manual["regionOverrides"]==["latitude"]
            self.open_editor();self.edit("accuracy",None,False);self.save()
            disabled=self.profile();assert "accuracy" not in disabled["selected"]
            return {"profile":manual,"cancelDoesNotSave":True,"threeLevelPicker":True,
                    "onlyThreeLocationFields":True,"rotationKeepsDraft":True,"manualOverride":True,"fieldSwitch":True}
        regional=self.case("L02-region-UI-draft-save",region_ui)["profile"]
        def gates():
            initial=self.read();pid=initial["pid"];observations=[]
            for machine_on,location_on,field_on in [(False,True,True),(True,False,True),(True,True,False),(True,True,True)]:
                fixture=dict(regional,enabled=machine_on,locationEnabled=location_on,networkMode="off",
                             selected=sorted(set(regional["selected"]) if field_on else set(regional["selected"])-{"latitude"}))
                saved=d.batch_profile(PRIMARY,fixture);sample=self.revision_read(saved)
                assert sample["pid"]==pid
                row=sample["reads"]["latitude"]
                if machine_on and location_on and field_on:assert self.value(sample,"latitude")==39.915
                else:assert row.get("value")==baseline["reads"]["latitude"].get("value") and row.get("error")==baseline["reads"]["latitude"].get("error")
                assert sample["module"]["locationEnabled"]==location_on
                observations.append({"gates":[machine_on,location_on,field_on],"observed":sample})
            saved=d.batch_profile(PRIMARY,dict(regional,locationEnabled=False,networkMode="off"))
            restored=self.revision_read(saved)
            assert restored["pid"]==pid
            for key in LOCATION:
                assert restored["reads"][key].get("value")==baseline["reads"][key].get("value")
                assert restored["reads"][key].get("error")==baseline["reads"][key].get("error")
            return {"samePid":pid,"gateObservations":observations,"restored":restored}
        self.case("L03-location-three-gates",gates)
        def sim():
            d.batch_profile(PRIMARY,dict(regional,enabled=True,networkMode="no_sim",locationEnabled=False))
            saved=self.switch_mode("simulate");sample=self.revision_read(saved)
            self.assert_present(saved,sample)
            d.screenshot(str(OUT/"location-present-SIM-0.4.2.png"))
            first_tick=self.sample(after=int(time.time()*1000))
            next_sample=self.sample(after=first_tick["timestamp"])
            assert next_sample["pid"]==sample["pid"]
            self.assert_present(saved,next_sample)
            interval=next_sample["timestamp"]-first_tick["timestamp"];assert 1600<=interval<=4500,interval
            return {"profile":saved,"observed":sample,"repeat":next_sample,"autonomousIntervalMs":interval,
                    "syncAsyncAndParcelAgree":True,"singleSIMSlot0":True}
        sim_evidence=self.case("N01-present-SIM-coherence",sim)
        def restore_modes():
            d.batch_profile(PRIMARY,sim_evidence["profile"]);start=self.read();pid=start["pid"]
            no=self.switch_mode("no_sim");sample=self.revision_read(no);v=lambda k:self.value(sample,k)
            self.report.setdefault("observations",{})["N02-noSIM"]=sample
            assert sample["pid"]==pid and v("sim_state")==v("sim_state_slot0")==v("sim_state_slot1")==1
            assert not v("has_sim") and v("subscription_count")==0 and v("subscriptions")==[]
            assert v("default_subscription")==-1 and v("cells")==v("async_cells")==[]
            assert v("network_type")==v("voice_network_type")==v("data_state")==0
            service=v("service_state")
            # Android 16 init() retains UNKNOWN CS/PS WWAN and PS WLAN placeholders.
            assert service["state"]==1 and all(not row["registered"] and row["technology"]==0
                                               for row in service["registrations"]),service
            for key in ["imsi","iccid","phone","operator","sim_operator","sim_operator_name","mcc","mnc","lac","cid","tac","pci","signal"]:
                assert v(key) in (None,""),(key,v(key))
            assert v("imei")==no["values"]["imei"] # modem identity survives SIM removal
            real=self.switch_mode("off");off=self.revision_read(real)
            assert off["pid"]==pid
            keys=CELLULAR|{"sim_state","sim_state_slot0","sim_state_slot1","sim_card_state","sim_application_state",
                           "has_sim","sim_operator","sim_operator_name","sim_country","network_country","network_type",
                           "voice_network_type","data_state","roaming","subscription_count","default_subscription",
                           "subscriptions","service_state","cells","async_cells","wifi_mac","bssid","bt_mac","ssid"}
            for key in keys:
                assert off["reads"][key].get("value")==baseline["reads"][key].get("value"),(key,off["reads"][key],baseline["reads"][key])
                assert off["reads"][key].get("error")==baseline["reads"][key].get("error"),(key,off["reads"][key],baseline["reads"][key])
            disabled=d.batch_profile(PRIMARY,dict(sim_evidence["profile"],enabled=False))
            gated=self.revision_read(disabled);assert gated["pid"]==pid
            assert gated["reads"]["sim_state"]==off["reads"]["sim_state"]
            return {"samePid":pid,"noSIM":sample,"offRestored":off,"machineOff":gated,"storedValuesRetained":no["values"]==real["values"]}
        self.case("N02-no-SIM-and-real-restoration",restore_modes)
        def refresh():
            profile=d.batch_profile(PRIMARY,dict(regional,enabled=True,networkMode="simulate",locationEnabled=False))
            changes=[]
            for group,query in [("network","network"),("model","brand"),("ids","imei")]:
                before=self.profile();self.open_editor();self.search_editor(query.replace(" ","%s"))
                d.click("device-group-refresh:"+group,scroll=True);d.click("刷新","text");self.save()
                after=self.profile();assert after["networkMode"]==before["networkMode"] and after["locationEnabled"]==before["locationEnabled"]
                catalog=(ROOT/"shared/java/io/github/lwtdzh/deviceprofile/DeviceField.java").read_text()
                group_keys=set(re.findall(r'f\("([^"]+)","'+group+r'"',catalog))
                assert {k:v for k,v in before["values"].items() if k not in group_keys}=={
                    k:v for k,v in after["values"].items() if k not in group_keys}
                assert group_keys<=set(after["selected"])
                if group=="network":
                    assert after["values"]["imsi"].startswith(after["values"]["mcc"]+after["values"]["mnc"])
                    self.assert_present(after,self.revision_read(after))
                if group=="model":
                    assert after["values"]["device"]==after["values"]["product"]
                    assert after["values"]["device"] in after["values"]["fingerprint"]
                if group=="ids":
                    assert after["values"]["imei"][:8]==after["values"]["imei2"][:8]
                    assert after["values"]["imei"]!=before["values"]["imei"]
                changes.append({"group":group,"before":before,"after":after})
            return {"categoryChanges":changes,"otherGroupsPreserved":True,"modesPreserved":True,"networkCoherenceAfterRefresh":True}
        self.case("R01-category-refresh",refresh)

if __name__=="__main__":
    import subprocess
    run=Audit()
    run.run_checks()
    run.restore()
