#!/usr/bin/env python3
"""0.4.7 model/display UI checks only. Never run historical native samplers."""
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("incremental",ROOT/"scripts/incremental-environment-test.py")
inc=importlib.util.module_from_spec(spec);spec.loader.exec_module(inc)
run=inc.run;run.budget_seconds=360
d=inc.d;A=inc.A;MODULE=inc.machine.MODULE

def profile():return run.profile(A)
def editor():run.open_editor(A)
def gate():
    try:return d.find("device-model-enabled")
    except AssertionError:
        d.click("device-group:model",scroll=True)
        return d.find("device-model-enabled",scroll=True)
def save():
    before=profile()
    run.save()
    return run.wait(lambda:profile() if profile()!=before else None,"UI save not persisted",timeout=5)
def preset(name):
    d.click("device-preset",scroll=True);d.click(name,"text")
    d.click("使用预设","text")
def observe(p,baseline=False):
    model=d.shell("getprop","ro.product.model") if not p.get("modelEnabled") else p["values"]["model"]
    fingerprint=d.shell("getprop","ro.build.fingerprint") if not p.get("modelEnabled") else p["values"]["fingerprint"]
    d.shell("am","force-stop",A);d.shell("rm","-f",inc.output)
    d.shell("am","start","-W","-n",inc.activity,"--ez","modelOnly","true",
        "--es","model",model,"--es","fingerprint",fingerprint,
        "--es","androidId",p.get("values",{}).get("android_id",""),
        "--el","revision",str(p["revision"]))
    def ready():
        raw=d.shell("sh","-c","test ! -f "+inc.output+" || cat "+inc.output)
        try:return json.loads(raw) if raw else None
        except ValueError:return None
    observed=run.wait(ready,"Model-only check did not finish",timeout=20)
    assert "error" not in observed,observed
    assert observed["oldNativeChecksSkipped"] and observed["modelMatches"] and observed["fingerprintMatches"],observed
    if not baseline:assert observed["androidIdMatches"] and observed["simState"]==1,observed
    return observed

def main():
    # Fixture-only extensions do not invalidate completed UI cases.
    # Their original per-case artifact hashes stay in the report.
    original_case=run.case
    def case(name,action):
        previous=run.report["cases"].get(name,{})
        if previous.get("status")=="passed":
            print("KEEP "+name,flush=True)
            return previous["evidence"]
        return original_case(name,action)
    run.case=case
    for name in ["AppStateShield-0.4.7.apk","Verifier-A-0.4.7.apk"]:
        path=ROOT/"verification"/name
        d.adb("install","--no-incremental","-r",str(path))
        run.report["artifacts"][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    d.shell("cmd","locale","set-app-locales",MODULE,"--locales","zh-CN")
    d.batch_policy(A,set())
    if "G00-original-model-display" not in run.report["cases"]:
        p=d.batch_profile(A,{"schema":1,"enabled":False,"values":{},"selected":[],"preset":"custom"})
        run.case("G00-original-model-display",lambda:{"observation":observe(p,True)})
    original=run.report["cases"]["G00-original-model-display"]["evidence"]["observation"]["display"]
    def defaults():
        editor();assert d.find("device-enabled").get("checked")=="false"
        d.click("device-enabled")
        node=d.find("device-group:model",scroll=True)
        assert "已关闭" in node.get("text","")
        names={n.get("content-desc","") for n in d.nodes()}
        assert "device-model-enabled" not in names and "device-group:display" not in names
        d.tap(node);assert gate().get("checked")=="false"
        d.screenshot(str(ROOT/"verification/model-system-merged-0.4.7.png"))
        p=save()
        assert p["enabled"] and not p["modelEnabled"] and not p["locationEnabled"] and p["networkMode"]=="no_sim"
        observed=observe(p);assert observed["display"]==original,observed
        return {"defaultOnlyIdentifiersAndNoSIM":True,"modelInitiallyCollapsed":True,"displayMerged":True,
            "observation":observed}
    run.case("G01-default-merged-real-readings",defaults)
    def cancel():
        before=profile();editor();d.tap(gate())
        d.click("device-back");d.click("丢弃","text")
        assert profile()==before
        return {"discardKeepsSavedFlagValuesAndSelections":True}
    run.case("G02-model-toggle-cancel",cancel)
    def enabled():
        editor();node=gate()
        if node.get("checked")!="true":
            d.tap(node);p=save()
        else:
            p=profile();d.click("device-back")
        assert p["modelEnabled"]
        observed=observe(p)
        for key in ["width","height","density"]:
            if key in p["selected"] and key in p["values"]:
                assert observed["display"][key]==int(p["values"][key]),(key,observed)
        assert observed["module"]["modelEnabled"]
        return {"savedModelAndScreenActive":True,"observation":observed}
    run.case("G03-model-display-opt-in",enabled)
    def preset_on():
        editor();preset("vivo X200 Pro mini");p=save()
        assert p["modelEnabled"] and p["preset"]=="vivo-x200-pro-mini"
        return {"presetKeepsExplicitOn":True}
    run.case("G04-preset-preserves-on",preset_on)
    def off():
        before=profile();editor();d.tap(gate());p=save()
        assert not p["modelEnabled"] and p["values"]==before["values"] and p["selected"]==before["selected"]
        editor();preset("小米 14 · 国际版");p=save()
        assert not p["modelEnabled"] and p["preset"]=="xiaomi-14"
        observed=observe(p);assert observed["display"]==original,observed
        assert not observed["module"]["modelEnabled"]
        return {"toggleOffKeepsValuesAndSelections":True,"presetKeepsOff":True,
            "originalModelAndDisplayRestored":True,"observation":observed}
    run.case("G05-off-and-preset-restoration",off)

if __name__=="__main__":
    try:main()
    finally:inc.machine.REPORT.write_text(json.dumps(run.report,ensure_ascii=False,indent=2)+"\n")
