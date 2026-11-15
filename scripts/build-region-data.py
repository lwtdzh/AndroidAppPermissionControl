#!/usr/bin/env python3
"""Reduce the pinned MIT hierarchy to offline names and representative WGS84 points."""
import argparse
import csv
import hashlib
import json
import math
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]

def wgs84(lng,lat):
    # Invert GCJ-02 by iterative forward residual. This is an approximation, not surveyed coordinates.
    if not (72.004<=lng<=137.8347 and .8293<=lat<=55.8271):return lng,lat
    def forward(x,y):
        a=x-105;b=y-35
        dy=-100+2*a+3*b+.2*b*b+.1*a*b+.2*math.sqrt(abs(a))
        dx=300+a+2*b+.1*a*a+.1*a*b+.1*math.sqrt(abs(a))
        common=(20*math.sin(6*a*math.pi)+20*math.sin(2*a*math.pi))*2/3
        dy+=common+(20*math.sin(b*math.pi)+40*math.sin(b/3*math.pi))*2/3
        dy+=(160*math.sin(b/12*math.pi)+320*math.sin(b*math.pi/30))*2/3
        dx+=common+(20*math.sin(a*math.pi)+40*math.sin(a/3*math.pi))*2/3
        dx+=(150*math.sin(a/12*math.pi)+300*math.sin(a/30*math.pi))*2/3
        rad=y/180*math.pi;magic=1-.006693421622965943*math.sin(rad)**2
        dy=dy*180/((6378245*(1-.006693421622965943))/(magic*math.sqrt(magic))*math.pi)
        dx=dx*180/(6378245/math.sqrt(magic)*math.cos(rad)*math.pi)
        return x+dx,y+dy
    x,y=lng,lat
    for _ in range(8):
        fx,fy=forward(x,y);x-=fx-lng;y-=fy-lat
    return x,y

def main():
    parser=argparse.ArgumentParser();parser.add_argument("directory",type=pathlib.Path)
    src=parser.parse_args().directory;csv.field_size_limit(100000000)
    names=list(csv.DictReader((src/"ok_data_level3.csv").open(encoding="utf-8-sig")))
    geo={r["id"]:r for r in csv.DictReader((src/"ok_geo.csv").open(encoding="utf-8-sig"))}
    lines=[];missing=[]
    for r in names:
        if r["id"].startswith("91"):continue
        point=geo.get(r["id"],{}).get("geo","EMPTY");lng=lat=""
        if point!="EMPTY":
            x,y=map(float,point.split())
            # Taiwan and HK/Macao are not GCJ-encrypted in this source.
            if r["id"][:2] not in {"71","81","82"}:x,y=wgs84(x,y)
            lng=f"{x:.6f}";lat=f"{y:.6f}"
            assert -180<=x<=180 and -90<=y<=90
        else:missing.append(r["id"])
        lines.append("\t".join([r["id"],r["pid"],r["ext_name"],lng,lat]))
    dest=ROOT/"app/src/main/assets/china-regions.tsv";dest.write_text("\n".join(lines)+"\n")
    ids={r.split("\t")[0] for r in lines}
    assert all(r.split("\t")[1]=="0" or r.split("\t")[1] in ids for r in lines)
    assert sum(r.split("\t")[1]=="0" for r in lines)==34
    manifest={"source":"https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov",
        "release":"2025.251231.260403","published":"2026-04-03","rows":len(lines),
        "missingPointIds":missing,"missingPoints":len(missing),
        "inputSHA256":{n:hashlib.sha256((src/n).read_bytes()).hexdigest()
            for n in ["ok_data_level3.csv","ok_geo.csv"]},
        "outputSHA256":hashlib.sha256(dest.read_bytes()).hexdigest(),
        "coordinates":"Mainland GCJ-02 representative points approximately converted to WGS84; HK/Macao/Taiwan unchanged.",
        "limitations":"Missing district coordinates remain unavailable. Dataset snapshot may omit later administrative changes. Cell IDs are synthetic."}
    (ROOT/"app/src/main/assets/china-regions-source.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:manifest[k] for k in ["rows","missingPoints","outputSHA256"]}))

if __name__=="__main__":main()
