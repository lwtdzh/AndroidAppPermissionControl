#include "../native/property-area.h"
#include "../native/code-view.h"
#include <cassert>
#include <iostream>
#include <random>

void word(std::vector<uint8_t>&v,size_t at,uint32_t value){memcpy(v.data()+at,&value,4);}
std::vector<uint8_t> fixture(bool mutableNeighbour=false) {
    std::vector<uint8_t> v(32768);
    word(v,0,12000);word(v,8,0x504f5250);word(v,12,0xfc6ed0ab);
    word(v,128+16,112);
    size_t node=128+112;
    word(v,node,4);memcpy(v.data()+node+20,"test",5);word(v,node+4,8192);
    size_t info=128+8192;
    const char *name="ro.fixture.identity";
    memcpy(v.data()+info+96,name,strlen(name)+1);
    word(v,info,10u<<24);memcpy(v.data()+info+4,"real-value",11);
    if(mutableNeighbour) {
        word(v,node+12,140);
        size_t other=128+140;word(v,other,7);memcpy(v.data()+other+20,"mutable",8);
        word(v,other+4,8500);size_t p=128+8500;
        word(v,p,4u<<24);memcpy(v.data()+p+4,"live",5);memcpy(v.data()+p+96,"persist.fixture",16);
    }
    return v;
}
int main() {
    using shield_properties::Area;
    Area area;auto original=fixture();
    assert(area.load(original.data(),original.size()));
    for(size_t n:{size_t(1),size_t(91),size_t(92),size_t(128),size_t(256)}) {
        assert(area.load(original.data(),original.size()));
        assert(area.replace({{"ro.fixture.identity",std::string(n,'F')}}));
        Area decoded;assert(decoded.load(area.bytes().data(),area.bytes().size()));
        const auto &p=decoded.properties[0];
        assert(p.valueSize==n+1);
        assert(!memcmp(decoded.bytes().data()+p.value,std::string(n,'F').c_str(),n+1));
        assert(std::search(area.bytes().begin(),area.bytes().end(),
            original.begin()+8324,original.begin()+8334)==area.bytes().end());
    }
    assert(area.load(original.data(),original.size()));
    assert(area.replace({{"ro.fixture.identity","fake"}},true));
    auto pages=area.immutablePages(4096);
    assert(pages==std::vector<size_t>{8192});
    auto mixed=fixture(true);assert(area.load(mixed.data(),mixed.size()));
    assert(area.replace({{"ro.fixture.identity","fake"}},true));
    assert(area.immutablePages(4096).empty());
    assert(area.bytes()==mixed); // whole rejected property restored
    assert(area.load(original.data(),original.size()));
    assert(area.replace({{"ro.fixture.identity",std::string(128,'F')}},true));
    assert(area.bytes()==original); // insufficient original payload storage
    assert(area.load(original.data(),original.size()));
    assert(!area.replace({{"ro.fixture.identity",std::string(32768,'F')}}));
    assert(area.bytes()==original);
    auto malformed=original;word(malformed,128+112+16,112);
    assert(!area.load(malformed.data(),malformed.size()));
    malformed=original;word(malformed,128+112+4,0xfffffff0);
    assert(!area.load(malformed.data(),malformed.size()));
    malformed=original;word(malformed,128+8192,11u<<24);
    assert(!area.load(malformed.data(),malformed.size()));
    std::mt19937 random(47);
    for(int i=0;i<2000;i++) {
        malformed=original;size_t at=random()%12500;
        malformed[at]=static_cast<uint8_t>(random());
        if(area.load(malformed.data(),malformed.size()))
            area.replace({{"ro.fixture.identity","fuzz"}});
    }
    shield_code::Views code;
    uint8_t before[16],patched[16],buffer[32];
    memset(before,0x11,16);memset(patched,0x22,16);
    code.remember(4096,before,patched,16);
    memset(buffer,0x77,32);memcpy(buffer+8,patched,16);
    code.overlay(4088,buffer,32);
    assert(buffer[0]==0x77 && buffer[31]==0x77 && !memcmp(buffer+8,before,16));
    memcpy(buffer,patched,7);code.overlay(4100,buffer,7);assert(!memcmp(buffer,before+4,7));
    memset(buffer,0x33,16);code.overlay(4096,buffer,16);
    assert(buffer[0]==0x33); // later modification remains observable
    std::cout<<"New area codec, safe-page selection, erasure, 2000 mutations and code views passed\n";
}
